"""v2 §D: in-world shot via frame → (local Qwen-Image-Edit / Klein edit) → MiniMax H3 i2v on the remote 4090.

Uses the verified graphs in workflows/eval/ (qwen2511_int8_edit, klein4b_edit, minimax_remote_i2v) over
ComfyUI's raw HTTP API, the same way scripts/qwen_wall_word.py and scripts/remote_minimax.py do.
Config: TYPESET_MINIMAX_URL (default the 4090), TYPESET_MINIMAX_LONG_EDGE (default 736 → 736×416, fast;
a request's `longEdge` overrides it, up to 1344), TYPESET_EDIT_COMFY_URL (default local ComfyUI :8188).
With a reference image the video comes from MiniMaxH3ReferenceToVideo (+ MiniMaxH3AddGuide for the
first frame), the graph scripts/content/minimax_ref.py used for the hero's same-face shots. No extra models.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

from .config import settings
from .media import extract_frame, stage_to_comfy_input

MINIMAX_URL = os.environ.get("TYPESET_MINIMAX_URL", "http://100.104.17.103:8188").rstrip("/")
EDIT_URL = os.environ.get("TYPESET_EDIT_COMFY_URL", settings.comfyui_url).rstrip("/")
LONG_EDGE = int(os.environ.get("TYPESET_MINIMAX_LONG_EDGE", "736"))
MAX_LONG_EDGE = 1344      # MiniMax H3's native 16:9 size; the hero shots were made at 1344×768
EDIT_MAX_LONG_EDGE = 1024  # the local Qwen/Klein edit runs at most this big (as for the hero's LOUDER)
EVAL = settings.workflows_dir / "eval"

Report = Callable[[str], None]


def gen_size(width: int, height: int, long_edge: int = LONG_EDGE) -> tuple[int, int]:
    """Model size with the project's aspect, both sides multiples of 32."""
    s = long_edge / max(width, height)
    r = lambda v: max(256, int(round(v * s / 32)) * 32)
    return r(width), r(height)


def minimax_length(seconds: float, fps: float = 24) -> int:
    """Frames covering the shot at 24 fps, multiple of 4 (56 and 124 are the verified lengths)."""
    return max(28, min(244, int(math.ceil(seconds * fps / 4)) * 4))


def edit_prompt(text: str, how: str) -> str:
    how = how.strip() or "painted in large letters on the wall behind the person, matching the scene's light"
    return (f"Add the exact text \"{text}\" {how}. Spell it exactly \"{text}\". "
            "Keep the person, camera framing, lighting and everything else unchanged.")


def motion_prompt(text: str, how: str, motion: str | None) -> str:
    move = (motion or "").strip() or "The camera keeps moving gently as in the original footage; the person keeps moving naturally"
    where = f" ({how.strip()})" if how.strip() else ""
    words = (f" The words \"{text}\" from <Picture 1>{where} stay fixed on their surface, spelled exactly \"{text}\", fully legible."
             if text else "")
    return f"<Picture 1> continues as one continuous shot. {move}.{words} No cuts, no additional text."


# ---- raw ComfyUI HTTP ------------------------------------------------------------------

def _submit(base: str, graph: dict) -> str:
    pid = str(uuid.uuid4())
    r = httpx.post(f"{base}/prompt", json={"prompt": graph, "prompt_id": pid, "client_id": pid}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{base} rejected the graph ({r.status_code}): {r.text[:800]}")
    return pid


def _queue_position(base: str, pid: str) -> str:
    try:
        q = httpx.get(f"{base}/queue", timeout=10).json()
    except Exception:
        return "waiting"
    if any(item[1] == pid for item in q.get("queue_running", [])):
        return "running"
    pending = [item[1] for item in sorted(q.get("queue_pending", []), key=lambda it: it[0])]
    if pid in pending:
        ahead = pending.index(pid) + len(q.get("queue_running", []))
        return f"queued behind {ahead} job{'s' if ahead != 1 else ''}"
    return "finishing"


def _wait(base: str, pid: str, label: str, report: Report, timeout: float) -> dict:
    t0 = time.monotonic()
    last = 0.0
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > timeout:
            raise TimeoutError(f"{label}: no result after {timeout:.0f}s (the job may still run on {base})")
        h = httpx.get(f"{base}/history/{pid}", timeout=30).json()
        if pid in h:
            entry = h[pid]
            status = entry.get("status", {})
            if status.get("status_str") != "success":
                msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                detail = msgs[-1][1].get("exception_message", "") if msgs else json.dumps(status)[:600]
                raise RuntimeError(f"{label} failed: {detail}")
            return entry
        if elapsed - last >= 4.5:
            report(f"{label}: {_queue_position(base, pid)} ({elapsed:.0f}s)")
            last = elapsed
        time.sleep(3)


def _download(base: str, entry: dict, keys: tuple[str, ...], dest: Path) -> list[Path]:
    saved = []
    for node_out in entry.get("outputs", {}).values():
        for key in keys:
            for f in node_out.get(key, []) or []:
                if f.get("type") != "output":
                    continue
                params = {"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": "output"}
                r = httpx.get(f"{base}/view", params=params, timeout=600)
                r.raise_for_status()
                out = dest / f["filename"]
                out.write_bytes(r.content)
                saved.append(out)
    return saved


def upload_image(base: str, local: Path, subfolder: str) -> str:
    with local.open("rb") as fh:
        r = httpx.post(f"{base}/upload/image", files={"image": (local.name, fh, "image/png")},
                       data={"subfolder": subfolder, "overwrite": "true"}, timeout=120)
    r.raise_for_status()
    info = r.json()
    sub = info.get("subfolder") or subfolder
    return f"{sub}/{info['name']}" if sub else info["name"]


# ---- graphs (node lookups by class, like scripts/remote_minimax.py) -----------------------

def _node(g: dict, cls: str) -> str:
    return next(k for k, v in g.items() if v["class_type"] == cls)


def qwen_graph(image: str, prompt: str, w: int, h: int, seed: int, prefix: str) -> dict:
    g = json.loads((EVAL / "qwen2511_int8_edit.api.json").read_text())
    g[_node(g, "LoadImage")]["inputs"]["image"] = image
    g[_node(g, "ImageScale")]["inputs"].update({"width": w, "height": h})
    enc = [k for k, v in g.items() if v["class_type"] == "TextEncodeQwenImageEditPlus"]
    pos = next(k for k in enc if g[k]["inputs"].get("prompt"))
    g[pos]["inputs"]["prompt"] = prompt
    g[_node(g, "KSampler")]["inputs"]["seed"] = seed
    g[_node(g, "SaveImage")]["inputs"]["filename_prefix"] = prefix
    return g


def klein_graph(image: str, prompt: str, w: int, h: int, seed: int, prefix: str) -> dict:
    g = json.loads((EVAL / "klein4b_edit.api.json").read_text())
    g[_node(g, "LoadImage")]["inputs"]["image"] = image
    g[_node(g, "CLIPTextEncode")]["inputs"]["text"] = prompt
    g[_node(g, "EmptyFlux2LatentImage")]["inputs"].update({"width": w, "height": h})
    g[_node(g, "Flux2Scheduler")]["inputs"].update({"width": w, "height": h})
    g[_node(g, "RandomNoise")]["inputs"]["noise_seed"] = seed
    g[_node(g, "SaveImage")]["inputs"]["filename_prefix"] = prefix
    return g


def minimax_ref_graph(reference: str, prompt: str, w: int, h: int, length: int, seed: int, prefix: str,
                      first_frame: str | None = None, ref_size: str = "match") -> dict:
    """MiniMaxH3ReferenceToVideo on the i2v base graph (same loaders), optionally with the first frame
    anchored at frame 0 by MiniMaxH3AddGuide (which outputs only conditioning; the latent stays the
    reference node's) — scripts/content/minimax_ref.py:build, by class lookup."""
    g = json.loads((EVAL / "minimax_remote_i2v.api.json").read_text())
    i2v = _node(g, "MiniMaxH3ImageToVideo")
    clip, vae = g[i2v]["inputs"]["clip"], g[i2v]["inputs"]["vae"]
    audio_vae = g[_node(g, "VAEDecodeAudio")]["inputs"]["vae"]
    load = _node(g, "LoadImage")
    g[load]["inputs"]["image"] = reference
    g[i2v] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
        "clip": clip, "vae": vae, "audio_vae": audio_vae, "prompt": prompt, "width": w, "height": h,
        "length": length, "ref_image_size": ref_size, "ref_images.ref_image_1": [load, 0]}}
    guider, sampler = _node(g, "BasicGuider"), _node(g, "SamplerCustomAdvanced")
    if first_frame:
        g["typeset_first"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        g["typeset_guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": [i2v, 0], "latent": [i2v, 1], "frame_idx": 0, "vae": vae, "image": ["typeset_first", 0]}}
        g[guider]["inputs"]["conditioning"] = ["typeset_guide", 0]  # AddGuide outputs conditioning only
        g[sampler]["inputs"]["latent_image"] = [i2v, 1]
    g[_node(g, "RandomNoise")]["inputs"]["noise_seed"] = seed
    g[_node(g, "VHS_VideoCombine")]["inputs"]["filename_prefix"] = prefix
    return g


def ref_prompt(text: str, how: str, motion: str | None) -> str:
    """Prompt for reference-to-video. A motionPrompt that already mentions <Picture 1> is used verbatim
    (full control, like the hero's shot list)."""
    if motion and "<Picture 1>" in motion:
        return motion
    move = (motion or "").strip() or "The camera keeps moving gently as in the original footage; the person keeps moving naturally"
    where = f" {how.strip()}" if how.strip() else ""
    words = (f" The words \"{text}\"{where} stay fixed on their surface, spelled exactly \"{text}\", fully legible."
             if text else " No readable text.")
    return (f"The person from <Picture 1>, same face, same hair, same clothes. One continuous shot. {move}.{words} "
            "No cuts, no additional text.")


def edit_focus(frame: Path, plate: Path) -> tuple[float, float, float, float] | None:
    """Source-normalized [x0, y0, x1, y1] of what the edit model added (the generated word), used by reframe
    to keep it in the crop. Edits also relight the scene and nudge the person, so this keeps only the
    strongest changes (top 3 % of the LAB difference), merges them into blobs and returns the blob with the
    most change."""
    import cv2
    import numpy as np
    a, b = cv2.imread(str(frame)), cv2.imread(str(plate))
    if a is None or b is None:
        return None
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    blur = lambda im: cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32), (0, 0), 2)
    d = np.linalg.norm(blur(a) - blur(b), axis=2)
    H, W = d.shape
    m = (d > max(30.0, float(np.percentile(d, 97)))).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    k = max(3, int(round(0.03 * max(H, W))))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))  # letters → one blob
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    weight = np.bincount(lab.ravel(), weights=d.ravel(), minlength=n)
    weight[0] = 0
    best = int(np.argmax(weight))
    if stats[best, cv2.CC_STAT_AREA] < 0.002 * H * W:
        return None
    L, T, Wd, Ht = cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT
    by0, by1 = stats[best, T], stats[best, T] + stats[best, Ht]

    def same_line(i):  # a word split by something in front of it (her head) is still one text line
        y0, y1 = stats[i, T], stats[i, T] + stats[i, Ht]
        return min(y1, by1) - max(y0, by0) >= 0.5 * min(y1 - y0, by1 - by0)

    keep = [i for i in range(1, n) if i == best or (weight[i] >= 0.2 * weight[best] and same_line(i))]
    x0 = min(stats[i, L] for i in keep); y0 = min(stats[i, T] for i in keep)
    x1 = max(stats[i, L] + stats[i, Wd] for i in keep); y1 = max(stats[i, T] + stats[i, Ht] for i in keep)
    r = lambda v: round(min(1.0, max(0.0, float(v))), 4)
    return r(x0 / W), r(y0 / H), r(x1 / W), r(y1 / H)


def minimax_graph(first_frame: str, prompt: str, w: int, h: int, length: int, seed: int, prefix: str) -> dict:
    g = json.loads((EVAL / "minimax_remote_i2v.api.json").read_text())
    g[_node(g, "MiniMaxH3ImageToVideo")]["inputs"].update({"prompt": prompt, "width": w, "height": h, "length": length})
    g[_node(g, "LoadImage")]["inputs"]["image"] = first_frame
    g[_node(g, "RandomNoise")]["inputs"]["noise_seed"] = seed
    g[_node(g, "VHS_VideoCombine")]["inputs"]["filename_prefix"] = prefix
    return g


# ---- the pipeline ----------------------------------------------------------------------

def run_remote_shot(*, video: Path, start: float, end: float, fps: float, width: int, height: int, text: str,
                    prompt: str, motion: str | None, edit_model: str, project_id: str, shot_id: str, dest: Path,
                    report: Callable[[float, str], None], seed: int | None = None, long_edge: int | None = None,
                    reference: Path | None = None, guide_first_frame: bool = True) -> dict:
    """Returns {"plate": Path, "clip": Path, "timings": {...}, "focus": box | None}; writes everything into dest."""
    t_all = time.monotonic()
    seed = seed if seed is not None else uuid.uuid4().int % (2**31)
    long_edge = min(MAX_LONG_EDGE, long_edge or LONG_EDGE)
    w, h = gen_size(width, height, long_edge)
    ew, eh = gen_size(width, height, min(long_edge, EDIT_MAX_LONG_EDGE))
    length = minimax_length(end - start, 24)
    timings: dict[str, float] = {}
    dest.mkdir(parents=True, exist_ok=True)
    meta = {"engine": "remote-minimax", "editModel": edit_model, "size": [w, h], "editSize": [ew, eh], "length": length,
            "seed": seed, "minimaxUrl": MINIMAX_URL, "editUrl": EDIT_URL,
            "reference": str(reference) if reference else None, "guideFirstFrame": guide_first_frame}

    stage = lambda frac, msg: report(frac, f"{msg} · {time.monotonic() - t_all:.0f}s total")
    stage(.03, "Extracting starting frame")
    frame = extract_frame(video, start, dest / "frame.png", ew, eh)
    plate = frame
    if edit_model != "none" and text:
        t0 = time.monotonic()
        staged = stage_to_comfy_input(frame, project_id, shot_id, "frame.png")
        p = edit_prompt(text, prompt)
        meta["editPrompt"] = p
        g = (qwen_graph if edit_model == "qwen" else klein_graph)(staged, p, ew, eh, seed, f"typeset/{project_id}/{shot_id}/edit")
        (dest / f"edit_{edit_model}.workflow.json").write_text(json.dumps(g, indent=2))
        pid = _submit(EDIT_URL, g)
        label = f"Writing \"{text}\" into the frame ({'Qwen-Image-Edit' if edit_model == 'qwen' else 'FLUX.2 Klein'}, local)"
        entry = _wait(EDIT_URL, pid, label, lambda m: stage(.1, m), timeout=1500)
        imgs = _download(EDIT_URL, entry, ("images",), dest)
        if not imgs:
            raise RuntimeError("Edit model produced no image")
        shutil.copy2(imgs[0], dest / "plate.png")
        plate = dest / "plate.png"
        timings["edit"] = round(time.monotonic() - t0, 1)
        meta["focus"] = edit_focus(frame, plate)
    else:
        shutil.copy2(frame, dest / "plate.png")
        plate = dest / "plate.png"

    t0 = time.monotonic()
    if reference is not None:
        stage(.5, "Uploading reference" + (" and first frame" if guide_first_frame else "") + " to the remote GPU")
        remote_ref = upload_image(MINIMAX_URL, reference, f"typeset/{project_id}")
        remote_first = upload_image(MINIMAX_URL, plate, f"typeset/{project_id}") if guide_first_frame else None
        mp = ref_prompt(text, prompt, motion)
        g = minimax_ref_graph(remote_ref, mp, w, h, length, seed, f"typeset/{shot_id[:8]}", remote_first)
    else:
        stage(.5, "Uploading first frame to the remote GPU")
        remote_image = upload_image(MINIMAX_URL, plate, f"typeset/{project_id}")
        mp = motion_prompt(text, prompt, motion)
        g = minimax_graph(remote_image, mp, w, h, length, seed, f"typeset/{shot_id[:8]}")
    meta["motionPrompt"] = mp
    (dest / "minimax.workflow.json").write_text(json.dumps(g, indent=2))
    pid = _submit(MINIMAX_URL, g)
    meta["remotePromptId"] = pid
    entry = _wait(MINIMAX_URL, pid, f"Animating with MiniMax H3{' (reference)' if reference is not None else ''} on the 4090 ({w}×{h}, {length} frames)",
                  lambda m: stage(.55, m), timeout=1800)
    stage(.95, "Downloading clip")
    vids = [p for p in _download(MINIMAX_URL, entry, ("gifs", "videos", "images"), dest) if p.suffix == ".mp4"]
    if not vids:
        raise RuntimeError("MiniMax produced no mp4")
    clip = dest / "clip.mp4"
    shutil.copy2(sorted(vids, key=lambda p: ("audio" not in p.name, p.name))[0], clip)
    timings["video"] = round(time.monotonic() - t0, 1)
    timings["total"] = round(time.monotonic() - t_all, 1)
    meta["timings"] = timings
    (dest / "generation.json").write_text(json.dumps(meta, indent=2))
    return {"plate": plate, "clip": clip, "timings": timings, "size": [w, h], "length": length, "focus": meta.get("focus")}
