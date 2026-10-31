"""v2 jobs (docs/SCHEMA.md "v2 additions"): occupancy grid, surface tracking, reframe."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np

from . import vision
from .config import settings
from .jobs import JobContext
from .models import Project
from .store import ProjectStore, write_json_atomic


def _ppath(store: ProjectStore, pid: str, rel: str) -> Path:
    from .pipeline import project_path
    return project_path(store, pid, rel)


# ---- shared frame access ---------------------------------------------------------------

def matte_files(store: ProjectStore, project: Project) -> list[Path]:
    if not project.analysis.matte:
        return []
    return sorted(_ppath(store, project.id, project.analysis.matte).glob("fg_*.png"))


def load_alpha(path: Path) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA").getchannel("A"), dtype=np.uint8)


def decode_gray(store: ProjectStore, project: Project) -> list[np.ndarray]:
    """Footage as grayscale frames, decoded exactly like the ComfyUI path sees it: the normalized mp4
    (project width/height/fps, same filter as the matte job) → RGB → cv2 RGB2GRAY."""
    import cv2
    if project.media.video is None:
        raise ValueError("Project has no video")
    w, h = project.width, project.height
    src = normalized_video(store, project)
    proc = subprocess.run([settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(src), "-an",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.decode(errors='replace')[-400:]}")
    buf = np.frombuffer(proc.stdout, np.uint8)
    n = buf.size // (w * h * 3)
    return [cv2.cvtColor(buf[i * w * h * 3:(i + 1) * w * h * 3].reshape(h, w, 3), cv2.COLOR_RGB2GRAY) for i in range(n)]


# ---- Comfy path with in-process fallback --------------------------------------------------
# Each analysis runs as a ComfyUI workflow (typeset_nodes, via the SDK + proxy) when ComfyUI is up; the same
# core_vision code runs in-process only when ComfyUI is unreachable or the workflow fails. The job message
# and result say which path ran.

def comfy_up() -> bool:
    if os.environ.get("TYPESET_ANALYSIS_ENGINE", "comfy") == "local":
        return False
    from .comfy import runner
    h = runner.health()
    return bool((h.get("proxy") or h.get("transport") == "direct") and h.get("comfyui"))


def run_analysis(name: str, label: str, ctx: JobContext | None, comfy_fn, local_fn, base: float = .1, span: float = .8):
    """Returns (result, engine, note). comfy_fn/local_fn take no args and return the analysis document."""
    note = ""
    if comfy_up():
        try:
            t0 = time.monotonic()
            doc, job_id = comfy_fn()
            return doc, "comfy", f"via ComfyUI workflow {name}.api.json (job {job_id[:8]}, {time.monotonic() - t0:.1f}s)"
        except Exception as exc:  # noqa: BLE001 — keep the editor working; report honestly
            note = f"ComfyUI workflow {name} failed ({type(exc).__name__}: {str(exc)[:160]}); "
            if ctx:
                ctx.progress(base, f"{label}: {note}falling back to in-process OpenCV")
    else:
        note = "ComfyUI unreachable; "
    t0 = time.monotonic()
    doc = local_fn()
    return doc, "fallback", f"{note}in-process OpenCV fallback ({time.monotonic() - t0:.1f}s)"


def _comfy_progress(ctx: JobContext | None, label: str, base: float):
    if ctx is None:
        return None
    return lambda status, elapsed: ctx.progress(base, f"{label} in ComfyUI: {status} ({elapsed:.0f}s)")


def stage_dir(src: Path, pid: str, name: str, pattern: str = "fg_*.png") -> str:
    """Hard-link a folder's files into ComfyUI input/typeset/<pid>/<name>/; returns the input-relative dir."""
    from .media import stage_to_comfy_input
    files = sorted(src.glob(pattern))
    for f in files:
        stage_to_comfy_input(f, pid, name, f.name)
    return f"typeset/{pid}/{name}"


def normalized_video(store: ProjectStore, project: Project) -> Path:
    """Footage at project width/height/fps (same filter as the matte job), cached per size/fps."""
    from .media import ffmpeg
    src = _ppath(store, project.id, project.media.video.path)
    w, h = project.width, project.height
    out = store.project_dir(project.id) / "analysis" / f"frames_{src.stem[:12]}_{w}x{h}_{project.fps:g}.mp4"
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        tmp = out.with_suffix(".tmp.mp4")
        ffmpeg(["-i", src, "-an", "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={project.fps}",
                "-t", str(project.duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
                "-pix_fmt", "yuv420p", tmp])
        os.replace(tmp, out)
    return out


def _run_json(name: str, inputs: dict, out_dir: Path, key: str, ctx, label: str, base: float):
    from .comfy import runner, read_json_output
    result = runner.run(name, inputs, out_dir, progress=_comfy_progress(ctx, label, base))
    return read_json_output(result.outputs[key]), result.job_id


# ---- B. occupancy ----------------------------------------------------------------------

def write_occupancy(store: ProjectStore, project: Project, ctx: JobContext | None = None,
                    base: float = 0.0, span: float = 1.0) -> str:
    """Compute analysis/occupancy.json from the matte PNGs; returns the relative path (engine info in
    write_occupancy.last)."""
    files = matte_files(store, project)
    if not files:
        raise ValueError("Run foreground extraction (matte) first")
    matte_dir = _ppath(store, project.id, project.analysis.matte)
    run_dir = store.project_dir(project.id) / "analysis" / f"occupancy_run_{uuid.uuid4().hex[:8]}"

    def comfy():
        rel_dir = stage_dir(matte_dir, project.id, matte_dir.name)
        return _run_json("occupancy", {"matte_dir": rel_dir, "fps": project.fps}, run_dir, "occupancy_json",
                         ctx, "Occupancy", base)

    def local():
        first = load_alpha(files[0])
        h, w = first.shape
        return vision.occupancy_doc((load_alpha(f) for f in files), w, h, project.fps)

    doc, engine, note = run_analysis("occupancy", "Occupancy", ctx, comfy, local, base, span)
    doc["fps"] = project.fps
    rel = "analysis/occupancy.json"
    write_json_atomic(_ppath(store, project.id, rel), doc)
    write_occupancy.last = (engine, note)
    return rel


write_occupancy.last = ("", "")


def analyze_occupancy(store: ProjectStore, pid: str, ctx: JobContext):
    project = store.load(pid)
    t0 = time.monotonic()
    ctx.progress(.05, "Occupancy: staging matte frames")
    rel = write_occupancy(store, project, ctx, .1)
    engine, note = write_occupancy.last
    def update(p):
        p.analysis.occupancy = rel
    store.update(pid, update)
    data = json.loads(_ppath(store, pid, rel).read_text())
    ctx.progress(1, f"Occupancy ready: {len(data['frames'])} frames, {data['cols']}×{data['rows']} — {note}")
    return {"path": rel, "frames": len(data["frames"]), "cols": data["cols"], "rows": data["rows"],
            "engine": engine, "seconds": round(time.monotonic() - t0, 2)}


# ---- A. surface tracking ---------------------------------------------------------------

def track_surface(store: ProjectStore, pid: str, sid: str, ctx: JobContext):
    project = store.load(pid)
    surface = next((s for s in project.surfaces or [] if s.id == sid), None)
    if surface is None:
        raise ValueError("Surface not found")
    def set_status(status, track=None):
        def upd(p):
            for s in p.surfaces or []:
                if s.id == sid:
                    s.status = status
                    if track:
                        s.track = track
        store.update(pid, upd)
    set_status("tracking")
    try:
        t0 = time.monotonic()
        n_expected = max(1, round(project.duration * project.fps))
        key = min(max(0, surface.keyFrame), n_expected - 1)
        mattes = matte_files(store, project)
        w, h = project.width, project.height
        corners = [[float(x), float(y)] for x, y in surface.corners]
        run_dir = store.project_dir(pid) / "analysis" / f"surface_run_{sid}_{ctx.id[:8]}"

        def comfy():
            ctx.progress(.03, "Surface: preparing footage for ComfyUI")
            video = normalized_video(store, project)
            from .media import stage_to_comfy_input
            rel_video = stage_to_comfy_input(video, pid, video.name)
            matte_rel = stage_dir(_ppath(store, pid, project.analysis.matte), pid, Path(project.analysis.matte).name) if mattes else ""
            return _run_json("surface_track", {"video": rel_video, "matte_dir": matte_rel, "corners": json.dumps(corners),
                                               "key_frame": key, "fps": project.fps}, run_dir, "surface_json",
                             ctx, "Planar track", .1)

        def local():
            ctx.progress(.05, "Surface: decoding footage")
            frames = decode_gray(store, project)
            alpha_cache: dict[int, np.ndarray] = {}
            def subject(i):
                if i >= len(mattes):
                    return None
                if i not in alpha_cache:
                    alpha_cache[i] = load_alpha(mattes[i])
                return alpha_cache[i]
            k = min(key, len(frames) - 1)
            track = vision.track_plane(lambda i: frames[i], len(frames), k, np.array(corners) * [w, h], subject)
            return vision.surface_track_doc(track, w, h, project.fps)

        doc, engine, note = run_analysis("surface_track", "Planar track", ctx, comfy, local)
        rel = f"analysis/surfaces/{sid}.json"
        write_json_atomic(_ppath(store, pid, rel), doc)
        set_status("tracked", rel)
        fr = [x["f"] for x in doc["frames"]]
        span = (min(fr), max(fr)) if fr else (key, key)
        msg = (f"Tracked {len(fr)}/{n_expected} frames (f{span[0]}–{span[1]}) in {time.monotonic() - t0:.1f}s — {note}"
               + ("" if mattes else " (no matte: subject not masked)"))
        ctx.progress(1, msg)
        return {"path": rel, "tracked": len(fr), "frames": n_expected, "first": span[0], "last": span[1], "engine": engine,
                "meanConf": round(float(np.mean([x["conf"] for x in doc["frames"]])), 3) if fr else 0}
    except Exception:
        set_status("failed")
        raise


# ---- C. reframe ------------------------------------------------------------------------

def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    for f in src.rglob("*"):
        if f.is_file():
            _link_or_copy(f, dst / f.relative_to(src))


CHAR_W = 0.58  # average advance of a bold sans glyph / font size


def _is_subtitle_line(project: Project, line_id: str, base_fs: float) -> bool:
    """Subtitle/karaoke register (mirror of apps/web/src/looks.ts:isSubtitleLine): keeps its position on reframe."""
    ws = [w for w in project.words if w.lineId == line_id]
    if not ws or any(w.placement != "overlay" for w in ws):
        return False
    if all(w.preset == "karaoke" for w in ws):
        return True
    return all(w.position and getattr(w, "autoPlace", None) is False and (w.style or {}).get("fontSize", base_fs) <= .045 for w in ws)


LOOK_WARP_MAX = .5 * .35  # largest look lens warp (lens-bound); reframed layouts assume it


def _warp_safe_margins(w: float, h: float, k: float = LOOK_WARP_MAX, base: float = .06) -> tuple[float, float]:
    """Mirror of apps/web/src/geometry.ts:warpSafeMargins: pre-warp margins that stay ≥ base after the barrel."""
    R = (w * w + h * h) ** .5 / 2

    def solve(D):
        o = .5 - base
        for _ in range(30):
            r = o * D / R
            o = (.5 - base) / (1 + k * r * r)
        return .5 - o
    return solve(w), solve(h)


def _head_band(tracks: dict | None, crop: dict | None, fps: float):
    """(t0, t1) → output-y band (top, bottom) of person0's head through the crop, or None (mirror of reframe.ts)."""
    tr = (tracks or {}).get("tracks") or []
    person = next((t for t in tr if t.get("id") == "person0"), tr[0] if tr else None)
    if not person:
        return lambda t0, t1: None
    tf = (tracks or {}).get("fps") or fps
    frames = (crop or {}).get("frames") or []

    def crop_at(f):
        found = frames[0] if frames else None
        for fr in frames:
            if fr["f"] <= f:
                found = fr
            else:
                break
        return found

    def band(t0, t1):
        top, bot = 1.0, 0.0
        for fr in person.get("frames", []):
            t = fr["f"] / tf
            if t < t0 or t > t1:
                continue
            by, bh = fr["bbox"][1], fr["bbox"][3]
            hb = min(fr["cy"] + max(fr["cy"] - by, .06), by + .35 * bh)
            c = crop_at(round(t * fps))
            oy = (lambda y: (y - c["y"]) / c["h"]) if c else (lambda y: y)
            top, bot = min(top, oy(by)), max(bot, oy(hb))
        return (max(0.0, top), min(1.0, bot)) if bot > top else None
    return band


def _ensemble_layout(project: Project, new_w: int, new_h: int, base_fs: float, head=None) -> dict:
    """Multi-line endings keep reading order on reframe (mirror of apps/web/src/reframe.ts:layoutEnsembles).
    Ensemble = overlay/behind lines with explicit positions, same font size (±10 %) and overlapping lifetimes.
    Rows = authored rows (same y) in start order, or one line per row if that gives larger type.
    Rows narrower than 75 % of the frame or centred below 30 % of its height move to the front (behind → overlay).
    Returns {lineId: {"position": {x, y}, "fontSize": fs, "front": bool}}."""
    by: dict[str, dict] = {}
    for w in project.words:
        if w.placement not in ("overlay", "behind") or not w.position or getattr(w, "autoPlace", None):
            continue
        fs = (w.style or {}).get("fontSize", base_fs)
        units = (len(w.text) + 1) * CHAR_W
        l = by.get(w.lineId)
        if l is None:
            by[w.lineId] = dict(id=w.lineId, start=w.start, end=w.end, x=w.position.x, y=w.position.y, fs=fs, u=units)
        else:
            l.update(start=min(l["start"], w.start), end=max(l["end"], w.end), u=l["u"] + units)
    ls = sorted(by.values(), key=lambda l: (l["start"], l["y"], l["x"]))
    for l in ls:
        l["u"] -= CHAR_W  # no trailing space
    parent = list(range(len(ls)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(ls):
        for j in range(i + 1, len(ls)):
            b = ls[j]
            if (min(a["end"], b["end"]) - max(a["start"], b["start"]) > .05
                    and abs(a["fs"] - b["fs"]) <= .1 * max(a["fs"], b["fs"])
                    and ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** .5 > .02):
                parent[find(j)] = find(i)
    groups: dict[int, list] = {}
    for i, l in enumerate(ls):
        groups.setdefault(find(i), []).append(l)
    out: dict = {}
    GAP, LEAD = .28, 1.02
    for g in groups.values():
        if len(g) < 2:
            continue
        fs0 = g[0]["fs"]
        rows: list[list] = []
        for l in sorted(g, key=lambda l: l["y"]):
            r = next((r for r in rows if abs(r[0]["y"] - l["y"]) < fs0 * .5), None)
            (r.append(l) if r is not None else rows.append([l]))
        for r in rows:
            r.sort(key=lambda l: l["start"])
        rows.sort(key=lambda r: r[0]["start"])
        single = [[l] for l in g]

        def width(r):
            return sum(l["u"] for l in r) + GAP * (len(r) - 1)

        mx, my = _warp_safe_margins(new_w, new_h)
        BOT, GLY = .86, .5  # rows stay above the subtitle band

        def size_for(rs):
            return min(fs0, (1 - 2 * mx) * new_w / max(.01, max(width(r) for r in rs)) / new_h, (BOT - my) / (len(rs) * LEAD))
        a, b = size_for(rows), size_for(single)
        rs, size = (rows, a) if a >= b * .9 else (single, b)
        n = len(rs)
        # Never over the face: first k rows above the head band (keep placement), the rest below the chin in front.
        band = head(min(l["start"] for l in g), max(l["end"] for l in g)) if head else None
        pick = None
        if band:
            hT, hB = band[0] - .01, band[1] + .015
            opts = []
            for k in range(n + 1):
                s_ = size
                if k > 0:
                    s_ = min(s_, (hT - my) / (k * LEAD))
                if n - k > 0:
                    s_ = min(s_, (BOT - hB) / ((n - k) * LEAD))
                if s_ > 0:
                    opts.append((k, s_))
            if opts:
                best_all = max(o[1] for o in opts)
                above = [o for o in opts if o[0] > 0 and o[1] >= .6 * best_all]  # prefer a row above the head
                pick = max(above, key=lambda o: o[1]) if above else max(opts, key=lambda o: o[1])
            if pick and pick[1] < .5 * size:
                pick = None
        if pick:
            k, size = pick
            sp = size * LEAD

            def row_y(ri):
                return my + size * GLY + ri * sp if ri < k else hB + size * GLY + (ri - k) * sp

            def front_at(ri, wr):
                return ri >= k
        else:
            sp = size * LEAD
            top = my + size * GLY
            # Short stacks split around the subject: first half at the top, the rest from 55 % down (torso).
            split = (n + 1) // 2 if n >= 2 and n * sp <= .45 else n

            def row_y(ri):
                return top + ri * sp if ri < split else max(top + ri * sp, .55 + size / 2) + (ri - split) * sp

            def front_at(ri, wr):  # narrow / body-level rows can vanish behind the subject
                return wr * size * new_h / new_w < .75 or row_y(ri) > .3
        for ri, r in enumerate(rs):
            x = .5 - width(r) * size * new_h / new_w / 2
            front = front_at(ri, width(r))
            for l in r:
                w = l["u"] * size * new_h / new_w
                out[l["id"]] = {"position": {"x": round(x + w / 2, 4), "y": round(row_y(ri), 4)}, "fontSize": round(size, 4), "front": front}
                x += w + GAP * size * new_h / new_w
    return out


def surfaces_to_titles(project: Project, crop: dict | None) -> Project:
    """Mirror of apps/web/src/reframe.ts:surfacesToTitles. A static (untracked) surface mostly outside the crop
    at the line's mid-frame is a screen-space title: its lines become behind lines at the quad centre with an
    explicit position, so the ensemble layout stacks them in reading order."""
    frames = (crop or {}).get("frames") or []
    if not frames or not project.surfaces:
        return project

    def crop_at(f):
        found = frames[0]
        for fr in frames:
            if fr["f"] <= f:
                found = fr
            else:
                break
        return found
    conv: dict[str, tuple[float, float]] = {}
    for srf in project.surfaces:
        if srf.track and not getattr(srf, "noTrack", None):
            continue
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = srf.corners

        def at(u, v):
            return ((1 - v) * ((1 - u) * x0 + u * x1) + v * ((1 - u) * x3 + u * x2),
                    (1 - v) * ((1 - u) * y0 + u * y1) + v * ((1 - u) * y3 + u * y2))
        spans: dict[str, list[float]] = {}
        for w in project.words:
            if w.placement == "surface" and w.surfaceId == srf.id:
                sp = spans.setdefault(w.lineId, [w.start, w.end])
                sp[0], sp[1] = min(sp[0], w.start), max(sp[1], w.end)
        for lid, (a, b) in spans.items():
            c = crop_at(round((a + b) / 2 * project.fps))
            inside = 0
            for j in range(11):
                for i in range(11):
                    x, y = at(i / 10, j / 10)
                    ox, oy = (x - c["x"]) / c["w"], (y - c["y"]) / c["h"]
                    inside += 0 <= ox <= 1 and 0 <= oy <= 1
            if inside / 121 < .5:
                conv[lid] = at(.5, .5)
    if not conv:
        return project
    data = project.model_dump(mode="json")
    for d in data["words"]:
        if d["lineId"] in conv and d["placement"] == "surface":
            x, y = conv[d["lineId"]]
            d.update(placement="behind", surfaceId=None, position={"x": x, "y": y}, autoPlace=False)
    return Project.model_validate(data)


def relayout_words(project: Project, new_w: int, new_h: int, crop: dict | None = None, tracks: dict | None = None) -> tuple[list, dict]:
    """Copy words for a reframed project (v2 §C): overlay/behind words lose their explicit position and
    get autoPlace; a line that would be wider than ~86 % of the new width gets a smaller fontSize
    (per line, written into each word's style). Anchor/surface/inworld words keep their size.
    Returns (words, style)."""
    project = surfaces_to_titles(project, crop)
    style = project.style.model_dump(mode="json")
    base_fs = style.get("fontSize") or 0.08
    lines: dict[str, list] = {}
    for w in project.words:
        if w.placement in ("overlay", "behind"):
            lines.setdefault(w.lineId, []).append(w)
    line_scale: dict[str, float] = {}
    for lid, ws in lines.items():
        width = sum((len(w.text) + 1) * CHAR_W * (w.style or {}).get("fontSize", base_fs) * new_h for w in ws)
        width -= CHAR_W * (ws[-1].style or {}).get("fontSize", base_fs) * new_h  # no trailing space
        line_scale[lid] = min(1.0, 0.86 * new_w / width) if width > 0 else 1.0
        if ws[0].position and _is_subtitle_line(project, lid, base_fs):
            # Fixed subtitle: the whole line fits between its x and the right margin (mono, 0.6 em/char).
            mono = len(" ".join(w.text for w in ws)) * .6 * (ws[0].style or {}).get("fontSize", base_fs) * new_h
            x = min(max(ws[0].position.x, .05), .95)
            line_scale[lid] = min(1.0, (.95 - x) * new_w / max(1.0, width, mono))
    ensemble = _ensemble_layout(project, new_w, new_h, base_fs, _head_band(tracks, crop, project.fps))
    subtitles = {w.lineId for w in project.words if _is_subtitle_line(project, w.lineId, base_fs)}
    words = []
    for w in project.words:
        d = w.model_dump(mode="json")
        if w.lineId in ensemble:
            fx = ensemble[w.lineId]
            d.update(position=fx["position"], autoPlace=False)
            if fx["front"] and d["placement"] == "behind":
                d["placement"] = "overlay"
            d["style"] = {**(d.get("style") or {}), "fontSize": fx["fontSize"]}
        elif w.placement in ("overlay", "behind"):
            if w.lineId in subtitles and w.position:
                d["position"] = {"x": min(max(w.position.x, .05), .95), "y": w.position.y}
            else:
                d["position"] = None
                d["autoPlace"] = True
            k = line_scale.get(w.lineId, 1.0)
            if k < 1.0:
                fs = (w.style or {}).get("fontSize", base_fs)
                d["style"] = {**(d.get("style") or {}), "fontSize": round(fs * k, 4)}
        words.append(d)
    return words, style


def reframe_focus(project: Project, focus=()) -> list[dict]:
    """Focus regions for the crop: explicit ones from the request, plus every generated shot that knows
    where its word is (GenShot.focus)."""
    out = [f.model_dump(mode="json", exclude_none=True) if hasattr(f, "model_dump") else dict(f) for f in focus or ()]
    for shot in project.shots:
        if shot.focus and shot.end > shot.start:
            out.append({"start": shot.start, "end": shot.end, "box": list(shot.focus), "mode": "auto",
                        "label": f"shot {shot.id}"})
    return out


def reframe_project(store: ProjectStore, pid: str, aspect: str, name: str | None, ctx: JobContext, focus=()):
    src = store.load(pid)
    if src.media.video is None:
        raise ValueError("Upload a video first")
    t0 = time.monotonic()
    n = max(1, round(src.duration * src.fps))
    tracks = json.loads(_ppath(store, pid, src.analysis.tracks).read_text()) if src.analysis.tracks else None
    if tracks is None:
        ctx.progress(.05, "No person track: the crop will stay centered (run matte first to follow the subject)")
    surfaces = {}
    for s in src.surfaces or []:
        if s.track:
            try:
                surfaces[s.id] = json.loads(_ppath(store, pid, s.track).read_text())
            except FileNotFoundError:
                pass
    focus = reframe_focus(src, focus)
    ctx.progress(.1, "Planning virtual camera" + (f" ({len(focus)} focus region{'s' * (len(focus) != 1)})" if focus else ""))
    run_dir = store.project_dir(pid) / "analysis" / f"reframe_run_{ctx.id[:8]}"
    crop, engine, note = run_analysis(
        "reframe", "Reframe", ctx,
        lambda: _run_json("reframe", {"tracks_json": json.dumps(tracks or {"tracks": []}),
                                      "surfaces_json": json.dumps(list(surfaces.values())) if surfaces else "",
                                      "aspect": aspect, "fps": src.fps, "width": src.width, "height": src.height,
                                      "frames": n, "focus_json": json.dumps(focus) if focus else ""},
                          run_dir, "crop_json", ctx, "Reframe", .1),
        lambda: vision.compute_crop(src.width, src.height, src.fps, tracks, surfaces, aspect, n, focus=focus))
    new_w, new_h = vision.output_size(src.width, src.height, aspect)
    words, style = relayout_words(src, new_w, new_h, crop, tracks)
    dst = store.create(name or f"{src.name} · {aspect}")
    sdir, ddir = store.project_dir(pid), store.project_dir(dst.id)
    ctx.progress(.3, "Linking media and analysis into the new project")
    for ref in (src.media.video, src.media.audio):
        if ref:
            _link_or_copy(_ppath(store, pid, ref.path), ddir / ref.path)
    for rel in (src.analysis.words, src.analysis.tracks, src.analysis.occupancy, src.analysis.depth):
        if rel and (sdir / rel).exists():
            (_copy_tree if (sdir / rel).is_dir() else _link_or_copy)(sdir / rel, ddir / rel)
    if src.analysis.matte and (sdir / src.analysis.matte).is_dir():
        _copy_tree(sdir / src.analysis.matte, ddir / src.analysis.matte)
    if (sdir / "analysis" / "surfaces").is_dir():
        _copy_tree(sdir / "analysis" / "surfaces", ddir / "analysis" / "surfaces")
    for shot in src.shots:
        for rel in (shot.plate, shot.video):
            if rel and (sdir / rel).exists():
                _link_or_copy(sdir / rel, ddir / rel)
    write_json_atomic(ddir / "analysis" / "crop.json", crop)
    data = src.model_dump(mode="json")
    data.update(id=dst.id, name=dst.name, width=new_w, height=new_h, words=words, style=style,
                frame={"aspect": aspect, "source": {"projectId": pid}, "crop": "analysis/crop.json"})
    store.save(Project.model_validate(data))
    msg = f"Reframed to {aspect} ({new_w}×{new_h}) in {time.monotonic() - t0:.1f}s — {note}"
    ctx.progress(1, msg)
    return {"engine": engine, "projectId": dst.id, "width": new_w, "height": new_h, "crop": "analysis/crop.json", "frames": n}


# ---- beats (TypesetBeatGrid) ------------------------------------------------------------

def analyze_beats(store: ProjectStore, pid: str, ctx: JobContext):
    """analysis/beats.json {duration, bpm, beatsPerBar, beats, downbeats, sections} + beats.png. ComfyUI only
    (librosa lives in the ComfyUI venv); fails with a clear message when ComfyUI is down."""
    from .media import extract_audio_wav, stage_to_comfy_input
    project = store.load(pid)
    source = project.media.audio or project.media.video
    if source is None:
        raise ValueError("Upload audio or video first")
    if not comfy_up():
        raise RuntimeError("Beat analysis runs as a ComfyUI workflow (librosa); ComfyUI is unreachable")
    t0 = time.monotonic()
    pdir = store.project_dir(pid)
    ctx.progress(.05, "Beats: extracting audio")
    wav = extract_audio_wav(_ppath(store, pid, source.path), pdir / "analysis" / f"beats_{ctx.id[:8]}.wav", 22050)
    rel_audio = stage_to_comfy_input(wav, pid, wav.name)
    from .comfy import runner, read_json_output
    result = runner.run("beats", {"audio": rel_audio}, pdir / "analysis" / f"beats_run_{ctx.id[:8]}",
                        progress=_comfy_progress(ctx, "Beat grid", .2))
    doc = read_json_output(result.outputs["beats_json"])
    write_json_atomic(pdir / "analysis" / "beats.json", doc)
    if result.first("preview"):
        shutil.copy2(result.first("preview"), pdir / "analysis" / "beats.png")
    def update(p):
        p.analysis.beats = "analysis/beats.json"
    store.update(pid, update)
    ctx.progress(1, f"Beat grid: {doc['bpm']:.1f} BPM, {len(doc['beats'])} beats, {len(doc['sections'])} sections — "
                    f"via ComfyUI workflow beats.api.json (job {result.job_id[:8]}, {time.monotonic() - t0:.1f}s)")
    return {"path": "analysis/beats.json", "preview": "analysis/beats.png", "bpm": doc["bpm"], "beats": len(doc["beats"]),
            "downbeats": len(doc["downbeats"]), "sections": len(doc["sections"]), "engine": "comfy"}


# ---- F. motion field ----------------------------------------------------------------------

def analyze_flow(store: ProjectStore, pid: str, ctx: JobContext):
    """analysis/flow.json: per-frame coarse optical flow (TypesetFlowField) that pushes and smears the type."""
    from .media import stage_to_comfy_input
    project = store.load(pid)
    if project.media.video is None:
        raise ValueError("Upload video first")
    t0 = time.monotonic()
    pdir = store.project_dir(pid)
    ctx.progress(.05, "Motion: preparing footage")
    video = normalized_video(store, project)
    run_dir = pdir / "analysis" / f"flow_run_{ctx.id[:8]}"

    def comfy():
        rel = stage_to_comfy_input(video, pid, video.name)
        return _run_json("flow", {"video": rel, "fps": project.fps}, run_dir, "flow_json", ctx, "Motion field", .15)

    def local():
        grays = decode_gray(store, project)
        cols, rows = vision.flow_dims(project.width, project.height)
        return vision.flow_doc(vision.flow_grids(grays, cols, rows), project.fps)

    doc, engine, note = run_analysis("flow", "Motion field", ctx, comfy, local, .15)
    doc["fps"] = project.fps
    rel = "analysis/flow.json"
    write_json_atomic(_ppath(store, pid, rel), doc)
    def update(p):
        p.analysis.flow = rel
    store.update(pid, update)
    ctx.progress(1, f"Motion field ready: {len(doc['frames'])} frames, {doc['cols']}×{doc['rows']} — {note}")
    return {"path": rel, "frames": len(doc["frames"]), "cols": doc["cols"], "rows": doc["rows"], "engine": engine,
            "seconds": round(time.monotonic() - t0, 2)}


# ---- V. voice field -----------------------------------------------------------------------

def analyze_voice(store: ProjectStore, pid: str, ctx: JobContext):
    """analysis/voice.json + voice.png: per-frame vocal loudness, pitch, vibrato, onsets (TypesetVoiceField).
    ComfyUI only (HDemucs + librosa live in the ComfyUI venv)."""
    from .media import extract_audio_wav, stage_to_comfy_input
    project = store.load(pid)
    source = project.media.audio or project.media.video
    if source is None:
        raise ValueError("Upload audio or video first")
    if not comfy_up():
        raise RuntimeError("Voice analysis runs as a ComfyUI workflow (HDemucs + pYIN); ComfyUI is unreachable")
    t0 = time.monotonic()
    pdir = store.project_dir(pid)
    ctx.progress(.05, "Voice: extracting audio")
    wav = extract_audio_wav(_ppath(store, pid, source.path), pdir / "analysis" / f"voice_{ctx.id[:8]}.wav", 44100)
    rel_audio = stage_to_comfy_input(wav, pid, wav.name)
    from .comfy import runner, read_json_output
    result = runner.run("voice", {"audio": rel_audio, "fps": project.fps, "duration": project.duration},
                        pdir / "analysis" / f"voice_run_{ctx.id[:8]}", progress=_comfy_progress(ctx, "Voice field", .2))
    doc = read_json_output(result.outputs["voice_json"])
    write_json_atomic(pdir / "analysis" / "voice.json", doc)
    if result.first("preview"):
        shutil.copy2(result.first("preview"), pdir / "analysis" / "voice.png")
    def update(p):
        p.analysis.voice = "analysis/voice.json"
    store.update(pid, update)
    voiced = sum(1 for x in doc["pitch"] if x is not None)
    ctx.progress(1, f"Voice field: {doc['frames']} frames, {voiced} voiced — via ComfyUI workflow voice.api.json "
                    f"(job {result.job_id[:8]}, {time.monotonic() - t0:.1f}s)")
    return {"path": "analysis/voice.json", "preview": "analysis/voice.png", "frames": doc["frames"], "voiced": voiced, "engine": "comfy"}
