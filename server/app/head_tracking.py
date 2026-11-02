"""Head tracks per immutable media source. Trims/transforms are applied by the renderer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .store import write_json_atomic

MODEL = Path(__file__).resolve().parents[1] / "models/face_detection_yunet_2023mar.onnx"
FPS = 12


def head_sources(project) -> list[dict]:
    assets = {a['id']: a for a in getattr(project, 'assets', None) or []}
    sources = {}
    if project.media.video:
        sources[project.media.video.path] = dict(path=project.media.video.path, kind='video')
    for layer in getattr(project, 'layers', None) or []:
        if layer.get('kind') == 'media' and not layer.get('hidden'):
            asset = assets.get(layer.get('assetId'))
            if asset and asset.get('kind') in ('video', 'image'):
                sources[asset['path']] = dict(path=asset['path'], kind=asset['kind'])
    for shot in project.shots:
        if shot.status == 'done' and shot.video:
            sources[shot.video] = dict(path=shot.video, kind='video')
    return list(sources.values())


def choose_face(faces, previous):
    """Prefer the main (largest) face; continuity prevents jumping to a smaller bystander."""
    if faces is None or not len(faces):
        return None
    def score(face):
        x, y, w, h = face[:4]
        continuity = 1
        if previous is not None:
            px, py, pw, ph = previous[:4]
            distance = np.hypot(x+w/2-px-pw/2, y+h/2-py-ph/2) / max(pw, ph, 1)
            continuity += 2 * max(0, 1-distance)
        return float(w*h*face[-1]*continuity)
    return max(faces, key=score)


def track_source(path: Path, kind: str, progress=lambda _: None) -> dict:
    if not MODEL.is_file():
        raise ValueError('Head tracking model is missing: server/models/face_detection_yunet_2023mar.onnx')
    detector = cv2.FaceDetectorYN.create(str(MODEL), '', (320, 320), .7, .3, 1000)
    cap = None
    if kind == 'image':
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('Cannot read head tracking image')
        native_fps, total = FPS, 1
    else:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            raise ValueError('Cannot read head tracking video')
        native_fps = cap.get(cv2.CAP_PROP_FPS) or FPS
        total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    fps = min(FPS, native_fps)
    points, previous, missing = [], None, 0
    index, sample, width, height = 0, 0, 0, 0
    try:
        while True:
            if cap:
                ok, image = cap.read()
                if not ok:
                    break
            elif index:
                break
            if index + .5 >= sample * native_fps / fps:
                height, width = image.shape[:2]
                scale = 320/max(width, height)
                w, h = round(width*scale), round(height*scale)
                padded = np.zeros((320, 320, 3), np.uint8)
                padded[:h, :w] = cv2.resize(image, (w, h))
                _, faces = detector.detect(padded)
                face = choose_face(faces, previous)
                if face is not None:
                    x, y, fw, fh = map(float, face[:4])
                    points.append(dict(f=sample, bbox=[round(x/w, 5), round(y/h, 5), round(fw/w, 5), round(fh/h, 5)],
                                       cx=round((x+fw/2)/w, 5), cy=round((y+fh*.35)/h, 5)))
                    previous, missing = face, 0
                else:
                    missing += 1
                    if missing >= 3:
                        previous = None
                sample += 1
                if sample % 12 == 0:
                    progress(min(1, index/total))
            index += 1
        if not width:
            raise ValueError('Head tracking source has no readable frames')
    finally:
        if cap:
            cap.release()
    # Centered smoothing only within contiguous detections; never interpolate across a missing person or cut.
    smoothed = []
    for i, point in enumerate(points):
        near = [p for p in points[max(0, i-1):i+2] if abs(p['f']-point['f']) <= 1
                and np.hypot(p['cx']-point['cx'], p['cy']-point['cy']) < .12]
        smoothed.append({**point, 'cx': round(sum(p['cx'] for p in near)/len(near), 5),
                         'cy': round(sum(p['cy'] for p in near)/len(near), 5)})
    return dict(fps=fps, frames=max(1, sample), width=width, height=height,
                tracks=[dict(id='person0', label='head', frames=smoothed)])


def analyze_heads(store, pid, ctx, sources=None):
    from .pipeline import project_path
    project = store.load(pid)
    sources = sources if sources is not None else head_sources(project)
    if not sources:
        raise ValueError('Add footage to the timeline first')
    refs, detected = {}, 0
    for i, source in enumerate(sources):
        path = project_path(store, pid, source['path'])
        stat = path.stat()
        signature = [source['path'], stat.st_size, stat.st_mtime_ns, 'yunet-v1']
        digest = hashlib.sha256(json.dumps(signature).encode()).hexdigest()[:20]
        rel = f'analysis/heads_{digest}.json'
        dest = project_path(store, pid, rel)
        ctx.progress(i/len(sources), f'Tracking heads · clip {i+1}/{len(sources)}')
        if dest.is_file():
            doc = json.loads(dest.read_text())
        else:
            doc = track_source(path, source['kind'], lambda v: ctx.progress((i+v)/len(sources)))
            write_json_atomic(dest, doc)
        refs[source['path']] = rel
        detected += bool(doc['tracks'][0]['frames'])
        # Merge only analysis; never replace the edit or a matte from a concurrent job.
        def update(p):
            p.analysis.headTracks = {**(p.analysis.headTracks or {}), source['path']: rel}
        store.update(pid, update)
    return dict(headTracks=refs, sources=len(sources), detected=detected, engine='opencv-yunet')
