"""Headless Chromium capture of the #/render route: one PNG per frame.

The single capture loop behind both the FastAPI exporter (exporter.capture_frames) and the in-graph
TypesetRender node (which runs this file as a subprocess: `python -I capture.py --url ... --out ...`).
Stdlib + Playwright only, so any Python with `playwright` installed can run it.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def await_renderer(page, frame: int | None, timeout: float):
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
    }""", {"frame": frame, "timeout": timeout * 1000})


def _lower_priority_of_children(niceness: int = 10) -> None:
    """Best effort, POSIX only: renice every descendant of this process (the Playwright driver and its Chromium) so
    exports and showcase refreshes yield the CPU to the interactive studio. This process itself is left alone; when
    capture runs inside the API, other descendants (concurrent captures, ffmpeg) are background work too."""
    if not hasattr(os, "setpriority"):
        return
    try:
        import subprocess
        todo, seen = [os.getpid()], set()
        while todo:
            out = subprocess.run(["pgrep", "-P", str(todo.pop())], capture_output=True, text=True, timeout=5).stdout
            for pid in (int(x) for x in out.split()):
                if pid not in seen:
                    seen.add(pid)
                    todo.append(pid)
        for pid in seen:
            try:
                if os.getpriority(os.PRIO_PROCESS, pid) < niceness:
                    os.setpriority(os.PRIO_PROCESS, pid, niceness)
            except OSError:
                pass
    except Exception:
        pass


def capture(url: str, width: int, height: int, frames: int, dest: Path, timeout: float = 120.0,
            progress=None) -> Path:
    """Render frames 0..frames-1 of `url` into dest/frame_%05d.png. progress(done, total) is optional."""
    from playwright.sync_api import sync_playwright

    dest.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        _lower_priority_of_children()
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.set_default_timeout(timeout * 1000)
            # Keep a mocked connection open without forwarding HMR messages. Closing it
            # makes Vite poll/reload, repeatedly replacing __typeset during capture.
            page.route_web_socket("**", lambda socket: None)
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_function("window.__typeset !== undefined")
                await_renderer(page, None, timeout)
            except Exception as exc:
                raise RuntimeError(f"Renderer did not become ready at {url}: {errors or str(exc)}") from exc
            canvas = page.locator("#stage")
            for frame in range(frames):
                await_renderer(page, frame, timeout)
                canvas.screenshot(path=str(dest / f"frame_{frame:05d}.png"), omit_background=True,
                                  animations="disabled", scale="css")
                if progress:
                    progress(frame + 1, frames)
            if errors:
                raise RuntimeError("Renderer errors: " + "; ".join(errors[:3]))
        finally:
            browser.close()
    return dest / "frame_%05d.png"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=120.0)
    a = ap.parse_args(argv)
    # One line per frame on stdout, so a parent process can drive a progress bar.
    capture(a.url, a.width, a.height, a.frames, a.out, a.timeout,
            lambda i, n: print(f"frame {i}/{n}", flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
