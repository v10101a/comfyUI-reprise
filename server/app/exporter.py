"""Deterministic Chromium canvas frames → ffmpeg deliverables."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .config import settings
from .jobs import JobContext
from .media import ffmpeg, encode_alpha_webm, encode_prores4444
from .models import ExportBody
from .pipeline import project_path
from .store import ProjectStore


def await_renderer(page, frame: int | None = None):
    """Playwright evaluate does not inherit page's operation timeout for promises."""
    return page.evaluate("""async ({frame, timeout}) => {
        let timer;
        try {
            await Promise.race([
                Promise.resolve().then(() => frame === null
                    ? window.__typeset.ready : window.__typeset.renderFrame(frame)),
                new Promise((_, reject) => {
                    timer = setTimeout(() => reject(new Error(
                        frame === null ? 'Renderer readiness timed out' : `Frame ${frame} timed out`
                    )), timeout);
                })
            ]);
        } finally { clearTimeout(timer); }
    }""", {"frame": frame, "timeout": settings.render_timeout * 1000})


def capture_frames(project, layer: str, dest: Path, ctx: JobContext, base: float, span: float):
    from playwright.sync_api import sync_playwright

    dest.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(project.duration * project.fps + .5))
    url = settings.render_url_template.format(web=settings.web_url, project=quote(project.id),
                                              layer=layer, server=quote(settings.server_url, safe=""))
    ctx.progress(base, f"Loading {layer} renderer")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        try:
            page = browser.new_page(viewport={"width": project.width, "height": project.height}, device_scale_factor=1)
            page.set_default_timeout(settings.render_timeout * 1000)
            # Keep a mocked connection open without forwarding HMR messages. Closing it
            # makes Vite poll/reload, repeatedly replacing __typeset during capture.
            page.route_web_socket("**", lambda socket: None)
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_function("window.__typeset !== undefined")
                await_renderer(page)
            except Exception as exc:
                raise RuntimeError(f"Renderer did not become ready at {url}: {errors or str(exc)}") from exc
            canvas = page.locator("#stage")
            for frame in range(frames):
                await_renderer(page, frame)
                canvas.screenshot(path=str(dest / f"frame_{frame:05d}.png"), omit_background=True,
                                  animations="disabled", scale="css")
                if frame % 8 == 0 or frame == frames - 1:
                    ctx.progress(base + span * (frame + 1) / frames, f"Rendering {layer}: {frame + 1}/{frames}")
            if errors:
                raise RuntimeError("Renderer errors: " + "; ".join(errors[:3]))
        finally:
            browser.close()
    return dest / "frame_%05d.png"


def export_project(store: ProjectStore, pid: str, body: ExportBody, ctx: JobContext):
    # PUT and analysis-result updates use the same lock. The renderer may GET this stable
    # on-disk project while edits queue; it never reads a half-updated project mid-export.
    with store.lock(pid):
        project = store.load(pid)
        if project.duration <= 0:
            raise ValueError("Project needs a duration before export")
        dest = store.project_dir(pid) / "export" / ctx.id
        dest.mkdir(parents=True, exist_ok=True)
        result = {}
        formats = set(body.formats)
        if "mp4" in formats:
            # MP4 follows the requested layer; text is flattened on black (H.264 has no alpha).
            pattern = capture_frames(project, body.layer, dest / "mp4_frames", ctx, .02, .40)
            args = ["-framerate", str(project.fps), "-start_number", "0", "-i", pattern]
            audio = project.media.audio or (project.media.video if project.media.video and project.media.video.hasAudio else None)
            if audio:
                args += ["-i", project_path(store, pid, audio.path), "-map", "0:v:0", "-map", "1:a:0?", "-af", "apad", "-c:a", "aac", "-b:a", "192k"]
            if body.layer == "text":
                args += ["-vf", "format=gbrap,premultiply=inplace=1,format=rgb24"]
            args += ["-t", str(project.duration), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dest / "final.mp4"]
            ctx.progress(.45, "Encoding finished MP4")
            ffmpeg(args, what="ffmpeg(composite export)")
            result["mp4"] = f"export/{ctx.id}/final.mp4"
        if formats & {"mov", "webm"}:
            # Transparent delivery is always the text layer, regardless of the UI preview selection.
            pattern = capture_frames(project, "text", dest / "text_frames", ctx, .48, .40)
            if "mov" in formats:
                ctx.progress(.9, "Encoding ProRes 4444 overlay")
                encode_prores4444(pattern, project.fps, dest / "text_overlay.mov", start_number=0)
                result["mov"] = f"export/{ctx.id}/text_overlay.mov"
            if "webm" in formats:
                ctx.progress(.95, "Encoding VP9 alpha overlay")
                encode_alpha_webm(pattern, project.fps, dest / "text_overlay.webm", start_number=0)
                result["webm"] = f"export/{ctx.id}/text_overlay.webm"
        ctx.progress(1, "Export ready")
        return {"files": result, "urls": {k: f"/files/projects/{pid}/{v}" for k, v in result.items()}}
