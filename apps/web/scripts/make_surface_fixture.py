"""Fixture planar tracker (stand-in for the server's surface-track job, SCHEMA v2 §A).
Usage: server/.venv/bin/python apps/web/scripts/make_surface_fixture.py <project-id> <surface-id> <keyFrame> x0,y0 x1,y1 x2,y2 x3,y3
Corners normalized TL,TR,BR,BL. Features inside the quad (minus the subject matte) are tracked with LK flow
forwards and backwards from keyFrame; a RANSAC homography per frame moves the corners.
Writes apps/web/public/fixtures/<id>/surfaces/<sid>.json. Reads data/ only.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[3]
pid, sid, key = sys.argv[1], sys.argv[2], int(sys.argv[3])
quad = np.array([[float(v) for v in c.split(',')] for c in sys.argv[4:8]], np.float32)
proj = json.loads((ROOT / 'data/projects' / pid / 'project.json').read_text())
cap = cv2.VideoCapture(str(ROOT / 'data/projects' / pid / proj['media']['video']['path']))
frames = []
while True:
    ok, f = cap.read()
    if not ok: break
    frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
H, W = frames[0].shape
matte_dir = ROOT / 'data/projects' / pid / proj['analysis']['matte']
def subject(i):
    p = matte_dir / f'fg_{i+1:05d}.png'
    if not p.exists(): return np.zeros((H, W), np.uint8)
    a = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)[:, :, 3]
    return cv2.dilate((a > 20).astype(np.uint8), np.ones((15, 15), np.uint8))
px = quad * [W, H]
out = {key: (px.copy(), 1.0)}
def run(step):
    corners = px.copy(); i = key
    mask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(mask, corners.astype(np.int32), 1); mask &= (1 - subject(i))
    pts = cv2.goodFeaturesToTrack(frames[i], 400, .01, 6, mask=mask * 255)
    while 0 <= i + step < len(frames) and pts is not None and len(pts) >= 8:
        j = i + step
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(frames[i], frames[j], pts, None, winSize=(21, 21), maxLevel=3)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(frames[j], frames[i], nxt, None, winSize=(21, 21), maxLevel=3)
        good = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm(back - pts, axis=2)[:, 0] < 1.0)
        sub = subject(j); inside = np.array([sub[min(H-1, max(0, int(y))), min(W-1, max(0, int(x)))] == 0 for x, y in nxt[:, 0]])
        good &= inside
        if good.sum() < 8: break
        Hm, inl = cv2.findHomography(pts[good], nxt[good], cv2.RANSAC, 2.0)
        if Hm is None: break
        corners = cv2.perspectiveTransform(corners[None], Hm)[0]
        conf = float(inl.sum()) / max(1, good.sum())
        out[j] = (corners.copy(), conf)
        pts = nxt[good][inl[:, 0] == 1].reshape(-1, 1, 2)
        if len(pts) < 60:  # re-seed inside the moved quad
            mask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(mask, corners.astype(np.int32), 1); mask &= (1 - sub)
            extra = cv2.goodFeaturesToTrack(frames[j], 400, .01, 6, mask=mask * 255)
            if extra is not None: pts = np.concatenate([pts, extra.astype(np.float32)])
        i = j
run(1); run(-1)
data = {'fps': proj['fps'], 'frames': [{'f': f, 'corners': [[round(float(x) / W, 5), round(float(y) / H, 5)] for x, y in c], 'conf': round(conf, 3)} for f, (c, conf) in sorted(out.items())]}
dst = ROOT / 'apps/web/public/fixtures' / pid / 'surfaces' / f'{sid}.json'
dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(json.dumps(data))
print(dst, len(data['frames']), 'of', len(frames), 'frames tracked')
