"""Save → demo page: re-render a project's showcase clip (apps/web/public/showcase/<file>) after studio saves.

The project→file map is apps/web/src/showcase-pieces.json (Showcase.tsx reads the same file). Only pieces with an
`encode` block are refreshed; their "Original" alts are never written. Coalesced per project: a request while a
refresh runs marks it dirty and the same job renders once more when it finishes. The project is snapshotted at the
start of each pass (no lock held while rendering, so studio saves never wait on it) and the clip is swapped in with
an atomic rename, so the page never sees a half file.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from urllib.parse import quote

from .capture import capture
from .config import REPO_ROOT, settings
from .jobs import JobContext, JobManager
from .media import ffmpeg
from .models import Job
from .pipeline import project_path
from .store import ProjectStore

PIECES_FILE = REPO_ROOT / "apps" / "web" / "src" / "showcase-pieces.json"
TARGET_DIRS = [REPO_ROOT / "apps" / "web" / "public" / "showcase", settings.web_dist / "showcase"]

_lock = threading.Lock()
_active: dict[str, dict] = {}  # pid -> {"job": Job, "again": bool}


def pieces() -> list[dict]:
    try:
        return json.loads(PIECES_FILE.read_text())["pieces"]
    except (OSError, ValueError, KeyError):
        return []


def piece_for(pid: str) -> dict | None:
    return next((p for p in pieces() if p.get("project") == pid and "encode" in p), None)


def versions() -> dict[str, int]:
    """Piece id → mtime of its clip (cache-busting for the demo page)."""
    out = {}
    for p in pieces():
        f = TARGET_DIRS[0] / p["file"]
        if f.is_file():
            out[p["id"]] = int(f.stat().st_mtime)
    return out


def encode_args(project, piece: dict, pattern: Path, audio: Path | None, out: Path) -> list:
    enc = piece.get("encode") or {}
    dur = project.duration
    args = ["-framerate", str(project.fps), "-start_number", "0", "-i", pattern]
    vf = []
    if enc.get("scale"):
        vf.append(f"scale={int(enc['scale'])}:-2:flags=lanczos")
    if enc.get("fadeOut"):
        d = float(enc["fadeOut"])
        vf.append(f"fade=t=out:st={max(0, dur - d):.4f}:d={d}")
    if audio:
        from .audioclip import clip_filters
        af = clip_filters(project) + ["apad"]
        if enc.get("audioFadeOut"):
            d = float(enc["audioFadeOut"])
            af.append(f"afade=t=out:st={max(0, dur - d):.4f}:d={d}")
        args += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0?", "-af", ",".join(af), "-c:a", "aac", "-b:a", "128k"]
    if vf:
        args += ["-vf", ",".join(vf)]
    # README settings: CRF 24, capped at 2.5 Mb/s, AAC 128k, faststart.
    args += ["-t", f"{dur:.4f}", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-maxrate", "2.5M", "-bufsize", "5M",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    return args


def install(src: Path, name: str) -> list[str]:
    """Copy next to the target, then rename over it (atomic on one filesystem)."""
    done = []
    for d in TARGET_DIRS:
        if not d.is_dir():
            continue
        tmp = d / f".{name}.{os.getpid()}.tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, d / name)
        done.append(str(d / name))
    return done


def render_once(store: ProjectStore, pid: str, piece: dict, ctx: JobContext, base: float, span: float) -> dict:
    with store.lock(pid):
        project = store.load(pid)
        snap = store.project_file(pid).read_bytes()
    if project.duration <= 0:
        raise ValueError("Project needs a duration")
    dest = store.project_dir(pid) / "export" / ctx.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "project.json").write_bytes(snap)
    src = f"{settings.server_url}/files/projects/{quote(pid)}/export/{ctx.id}/project.json"
    url = settings.render_url_template.format(web=settings.web_url, project=quote(pid), layer="composite",
                                              server=quote(settings.server_url, safe="")) + "&src=" + quote(src, safe="")
    frames = max(1, int(project.duration * project.fps + .5))

    def tick(done, total):
        if done % 8 == 1 or done == total:
            ctx.progress(base + span * .9 * done / total, f"showcase {done}/{total}")
    try:
        pattern = capture(url, project.width, project.height, frames, dest / "frames", settings.render_timeout, tick)
        audio = project.media.audio or (project.media.video if project.media.video and project.media.video.hasAudio else None)
        out = dest / "showcase.mp4"
        ffmpeg(encode_args(project, piece, pattern, project_path(store, pid, audio.path) if audio else None, out), what="ffmpeg(showcase)")
    finally:
        shutil.rmtree(dest / "frames", ignore_errors=True)
    return {"file": piece["file"], "installed": install(out, piece["file"]), "clip": f"export/{ctx.id}/showcase.mp4"}


def refresh_job(store: ProjectStore, jobs: JobManager, pid: str) -> Job | None:
    piece = piece_for(pid)
    if not piece:
        return None
    with _lock:
        cur = _active.get(pid)
        if cur:
            cur["again"] = True
            return cur["job"]
        job = jobs.create("showcase", pid)
        _active[pid] = {"job": job, "again": False}

    def run(ctx: JobContext):
        result, n = None, 0
        try:
            while True:
                result = render_once(store, pid, piece_for(pid) or piece, ctx, 0, 1)
                n += 1
                with _lock:
                    if not _active[pid]["again"]:
                        _active.pop(pid, None)
                        break
                    _active[pid]["again"] = False
                ctx.progress(0, "showcase: newer save")
        except BaseException:
            with _lock:
                _active.pop(pid, None)
            raise
        ctx.progress(1, "showcase ready")
        return {**result, "passes": n}
    return jobs.submit(job, run, lane="showcase")
