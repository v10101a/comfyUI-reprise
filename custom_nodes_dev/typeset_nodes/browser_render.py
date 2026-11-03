"""TypesetRender's studio path: the graph's inputs become a Reprise project, rendered by the studio's own renderer.

The project is written into the studio's store (the one /typeset serves, see studio_host.py), then headless
Chromium renders its `#/render` route frame by frame through server/app/capture.py, the same capture loop the
studio exporter uses. Same project + same renderer build = the same pixels as a studio export, for every look.

Project id `comfy-<footage hash>`: re-running the graph with the same footage updates that project in place (the
encoded footage and matte are reused when unchanged), and it can be opened in the studio at
/typeset/#/studio?project=<id>.

`unavailable()` says why this path can't run (no /typeset host, no studio build, no Playwright), so the node can
fall back to its Python draft renderer.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import numpy as np

log = logging.getLogger("typeset.render")

REPO = Path(__file__).resolve().parents[2]
CAPTURE = REPO / "server" / "app" / "capture.py"


def _service():
    return sys.modules.get("typeset_server.service")


def render_python() -> str | None:
    """A Python that can import Playwright: TYPESET_RENDER_PYTHON, this one, or the repo's server venv."""
    env = os.environ.get("TYPESET_RENDER_PYTHON")
    if env:
        return env if Path(env).is_file() else None
    if importlib.util.find_spec("playwright") is not None:
        return sys.executable
    venv = REPO / "server" / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else None


def unavailable() -> str | None:
    svc = _service()
    if svc is None:
        return "the /typeset studio host is not mounted (server/ missing or failed to load)"
    from typeset_server.config import settings
    if not (settings.web_dist / "index.html").is_file():
        return f"the studio is not built ({settings.web_dist}; run pnpm build in apps/web)"
    if not CAPTURE.is_file():
        return f"{CAPTURE} is missing"
    if render_python() is None:
        return "no Python with Playwright (pip install playwright, or set TYPESET_RENDER_PYTHON)"
    return None


# ---- project from graph inputs -------------------------------------------------------------------------------

def _digest(*parts) -> str:
    h = hashlib.blake2b(digest_size=12)
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()


def _u8(x) -> np.ndarray:
    return (np.clip(x, 0, 1) * 255 + .5).astype(np.uint8)


def _encode_footage(frames: np.ndarray, fps: float, out: Path):
    """uint8 [N,H,W,3] -> near-lossless BT.709 H.264 the browser can decode (yuv420p, tagged)."""
    from typeset_server.config import settings
    n, h, w, _ = frames.shape
    tmp = out.with_suffix(".tmp.mp4")
    cmd = [settings.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-framerate", f"{fps}", "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "10", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in frames:
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg (footage) failed: {err[-400:]}")
    os.replace(tmp, out)


def _write_matte(frames: np.ndarray, mask: np.ndarray, fps: float, out: Path):
    """The studio's matte layout (analysis/matte_*/fg_%05d.png RGBA + fg.webm VP9 alpha), from IMAGE + MASK."""
    from PIL import Image
    from typeset_server.media import encode_alpha_webm
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for i, (rgb, a) in enumerate(zip(frames, mask), 1):
        Image.fromarray(np.dstack([rgb, a])).save(tmp / f"fg_{i:05d}.png", compress_level=1)
    encode_alpha_webm(tmp / "fg_%05d.png", fps, tmp / "fg.webm")
    shutil.rmtree(out, ignore_errors=True)
    os.replace(tmp, out)


def build_project(images, words_json: str, fps: float, look, grade, mask=None, voice_json: str = "",
                  flow_json: str = "", fields: dict | None = None, name: str | None = None):
    """Create or update the project for these inputs. Returns the saved Project."""
    svc = _service()
    store = svc.store
    from typeset_server.models import Project
    from typeset_server.pipeline import timeline_words
    from typeset_server.media import probe_media
    from typeset_server.store import write_json_atomic
    from . import core_vision as cv
    from .tracks import MaskToTracks

    B, H, W = images.shape[:3]
    frames = _u8(images[..., :3].detach().cpu().numpy())
    fhash = _digest(frames.shape, fps, frames[:, ::4, ::4].tobytes(), frames[::max(1, B // 8)].tobytes())
    pid = f"comfy-{fhash[:20]}"
    pdir = store.project_dir(pid)
    for sub in ("media", "analysis", "gen", "export"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    duration = B / fps
    video_rel = f"media/footage_{fhash[:12]}.mp4"
    if not (pdir / video_rel).is_file():
        _encode_footage(frames, fps, pdir / video_rel)
    video = probe_media(pdir / video_rel, video_rel)

    matte_rel = tracks_rel = occ_rel = None
    if mask is not None:
        m = mask.detach().cpu().numpy().astype(np.float32)
        if m.ndim == 2:
            m = m[None]
        if m.shape[1:] != (H, W):
            import cv2
            m = np.stack([cv2.resize(x, (W, H)) for x in m])
        m = m[:B]
        if len(m) < B:
            m = np.concatenate([m, np.zeros((B - len(m), H, W), np.float32)])
        alpha = _u8(m)
        mhash = _digest(fhash, alpha[:, ::2, ::2].tobytes())[:12]
        matte_rel = f"analysis/matte_{mhash}/"
        matte_dir = pdir / matte_rel
        if not (matte_dir / "fg.webm").is_file():
            _write_matte(frames, alpha, fps, matte_dir)
        for old in (pdir / "analysis").glob("matte_*"):
            if old.name != f"matte_{mhash}":
                shutil.rmtree(old, ignore_errors=True)
        # What the studio's matte job adds alongside the matte: subject tracks and the occupancy grid (auto-placement).
        import torch
        tracks_rel, occ_rel = f"analysis/tracks_{mhash}.json", f"analysis/occupancy_{mhash}.json"
        if not (pdir / tracks_rel).is_file():
            doc = json.loads(MaskToTracks().run(fps, "person", mask=torch.from_numpy(m))[0])
            write_json_atomic(pdir / tracks_rel, doc)
        if not (pdir / occ_rel).is_file():
            doc = cv.occupancy_doc(iter(alpha), W, H, fps)
            doc["fps"] = fps
            write_json_atomic(pdir / occ_rel, doc)

    data = json.loads(words_json) if isinstance(words_json, str) else words_json
    data = {"words": data} if isinstance(data, list) else data
    words = timeline_words(data, duration)
    for i, w in enumerate(words):  # stable ids: re-runs keep the same project (seeded effects hash word ids)
        w.id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{pid}/{i}/{w.text}/{w.start:.4f}"))
    write_json_atomic(pdir / "analysis" / "words.json", data)

    def field(rel, text):
        if not text:
            return None
        write_json_atomic(pdir / rel, json.loads(text))
        return rel

    if look is not None and fields:
        look = {**look, "overrides": {**(look.get("overrides") or {}),
                                      "fields": {**((look.get("overrides") or {}).get("fields") or {}), **fields}}}
    with store.lock(pid):
        prev = store.load(pid).model_dump(mode="json") if store.exists(pid) else {}
        doc = {**prev, "version": 1, "id": pid, "name": name or prev.get("name") or f"comfy render {fhash[:6]}",
               "fps": fps, "width": W, "height": H, "duration": duration,
               "media": {"video": video.model_dump(mode="json"), "audio": None, "lyrics": None},
               "analysis": {"words": "analysis/words.json", "matte": matte_rel, "tracks": tracks_rel,
                            "occupancy": occ_rel, "flow": field("analysis/flow.json", flow_json),
                            "voice": field("analysis/voice.json", voice_json)},
               "words": [w.model_dump(mode="json") for w in words], "shots": [],
               "look": look, "grade": grade}
        project = store.save(Project.model_validate(doc))
    return project


# ---- render -------------------------------------------------------------------------------------------------

def _capture_cmd(project, layer: str, out: Path):
    from typeset_server.config import settings
    url = settings.render_url_template.format(web=settings.web_url, project=quote(project.id), layer=layer,
                                              server=quote(settings.server_url, safe=""))
    frames = max(1, int(project.duration * project.fps + .5))
    return [render_python(), "-I", str(CAPTURE), "--url", url, "--width", str(project.width), "--height",
            str(project.height), "--frames", str(frames), "--out", str(out), "--timeout", str(settings.render_timeout)]


def render(project, layers=("composite",), tick=None) -> tuple[dict[str, list[Path]], Path]:
    """Capture the given layers in parallel headless Chromium processes -> ({layer: [png paths]}, work dir).
    The caller removes the work dir once it has read the frames."""
    svc = _service()
    work = svc.store.project_dir(project.id) / "export" / "_comfy" / uuid.uuid4().hex[:12]
    procs, errs = {}, {}
    lock = threading.Lock()

    def pump(layer, proc):
        for line in proc.stdout:
            if line.startswith("frame ") and tick:
                with lock:
                    tick()

    threads = []
    try:
        for layer in layers:
            p = subprocess.Popen(_capture_cmd(project, layer, work / layer), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
            procs[layer] = p
            t = threading.Thread(target=pump, args=(layer, p), daemon=True)
            t.start()
            threads.append(t)
        for layer, p in procs.items():
            err = p.stderr.read()
            if p.wait() != 0:
                errs[layer] = err.strip().splitlines()[-1:] or [f"exit {p.returncode}"]
        for t in threads:
            t.join(5)
        if errs:
            raise RuntimeError("studio renderer failed: " + "; ".join(f"{k}: {v[0]}" for k, v in errs.items()))
        frames = max(1, int(project.duration * project.fps + .5))
        return {layer: [work / layer / f"frame_{i:05d}.png" for i in range(frames)] for layer in layers}, work
    except BaseException:
        for p in procs.values():
            if p.poll() is None:
                p.kill()
        shutil.rmtree(work, ignore_errors=True)
        raise


def load_rgb(paths, premultiply_alpha: bool = False) -> np.ndarray:
    """PNG frames -> float32 [N,H,W,3]. premultiply_alpha: RGBA text over black (the draft's text_layer)."""
    from PIL import Image
    out = []
    for p in paths:
        with Image.open(p) as im:
            a = np.asarray(im.convert("RGBA"), np.float32) / 255
        out.append(a[..., :3] * a[..., 3:4] if premultiply_alpha else a[..., :3])
    return np.stack(out)


def studio_url(project) -> str:
    from typeset_server.config import settings
    return f"{settings.web_url}/#/studio?project={quote(project.id)}"
