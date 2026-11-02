"""Deterministic Chromium canvas frames → ffmpeg deliverables."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .capture import capture
from .config import settings
from .jobs import JobContext
from .media import ffmpeg, encode_alpha_webm, encode_prores4444
from .models import ExportBody
from .pipeline import project_path
from .audioclip import clip_filters
from .store import ProjectStore


def capture_frames(project, layer: str, dest: Path, ctx: JobContext, base: float, span: float, source_url: str | None = None,
                   scale: float = 1.0):
    frames = max(1, int(project.duration * project.fps + .5))
    url = settings.render_url_template.format(web=settings.web_url, project=quote(project.id),
                                              layer=layer, server=quote(settings.server_url, safe=""))
    if source_url:
        url += "&src=" + quote(source_url, safe="")
    if scale != 1:
        url += f"&scale={scale:g}"
    ctx.progress(base, f"Loading {layer} renderer")

    def tick(done, total):
        if done % 8 == 1 or done == total:
            ctx.progress(base + span * done / total, f"Rendering {layer}: {done}/{total}")
    return capture(url, round(project.width * scale), round(project.height * scale), frames, dest, settings.render_timeout, tick)


def frames_dir(store: ProjectStore, pid: str, session: str) -> Path:
    return store.project_dir(pid) / "export" / "_frames" / session


def uploaded_frames(store: ProjectStore, project, session: str, layer: str) -> Path:
    """Frames the studio rendered and uploaded (same renderer, no Playwright); all must be present."""
    src = frames_dir(store, project.id, session) / layer
    frames = max(1, int(project.duration * project.fps + .5))
    missing = [i for i in range(frames) if not (src / f"frame_{i:05d}.png").is_file()]
    if missing:
        raise RuntimeError(f"{len(missing)} of {frames} {layer} frames were not uploaded (first missing: {missing[0]})")
    return src / "frame_%05d.png"


def export_project(store: ProjectStore, pid: str, body: ExportBody, ctx: JobContext):
    # Freeze the input once, then release the save lock before Chromium/ffmpeg runs.
    # The renderer reads this snapshot so edits can save during a long export.
    with store.lock(pid):
        project = store.load(pid)
    if project.duration <= 0:
        raise ValueError("Project needs a duration before export")
    dest = store.project_dir(pid) / "export" / ctx.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "project.json").write_text(project.model_dump_json(indent=2), encoding="utf-8")
    source_url = f"{settings.server_url}/files/projects/{quote(pid)}/export/{quote(ctx.id)}/project.json"
    result = {}
    formats = set(body.formats)
    if "mp4" in formats:
        # MP4 follows the requested layer; text is flattened on black (H.264 has no alpha).
        pattern = (uploaded_frames(store, project, body.frames, body.layer) if body.frames
                   else capture_frames(project, body.layer, dest / "mp4_frames", ctx, .02, .40, source_url, body.scale))
        args = ["-framerate", str(project.fps), "-start_number", "0", "-i", pattern]
        audio = project.media.audio or (project.media.video if project.media.video and project.media.video.hasAudio else None)
        if audio:
            args += ["-i", project_path(store, pid, audio.path), "-map", "0:v:0", "-map", "1:a:0?", "-af", ",".join(clip_filters(project) + ["apad"]), "-c:a", "aac", "-b:a", "192k"]
        if body.layer == "text":
            args += ["-vf", "format=gbrap,premultiply=inplace=1,format=rgb24"]
        args += ["-t", str(project.duration), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dest / "final.mp4"]
        ctx.progress(.45, "Encoding finished MP4")
        ffmpeg(args, what="ffmpeg(composite export)")
        result["mp4"] = f"export/{ctx.id}/final.mp4"
    if formats & {"mov", "webm"}:
        # Transparent delivery is always the text layer, regardless of the UI preview selection.
        pattern = (uploaded_frames(store, project, body.frames, "text") if body.frames
                   else capture_frames(project, "text", dest / "text_frames", ctx, .48, .40, source_url, body.scale))
        if "mov" in formats:
            ctx.progress(.9, "Encoding ProRes 4444 overlay")
            encode_prores4444(pattern, project.fps, dest / "text_overlay.mov", start_number=0)
            result["mov"] = f"export/{ctx.id}/text_overlay.mov"
        if "webm" in formats:
            ctx.progress(.95, "Encoding VP9 alpha overlay")
            encode_alpha_webm(pattern, project.fps, dest / "text_overlay.webm", start_number=0)
            result["webm"] = f"export/{ctx.id}/text_overlay.webm"
    if body.frames:
        import shutil
        shutil.rmtree(frames_dir(store, pid, body.frames), ignore_errors=True)
    ctx.progress(1, "Export ready")
    return {"files": result, "urls": {k: f"/files/projects/{pid}/{v}" for k, v in result.items()}}
