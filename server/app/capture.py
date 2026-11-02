"""Headless Chromium capture of the #/render route: one PNG per frame.

The single capture loop behind both the FastAPI exporter (exporter.capture_frames) and the in-graph
TypesetRender node (which runs this file as a subprocess: `python -I capture.py --url ... --out ...`).
Stdlib + Playwright only, so any Python with `playwright` installed can run it.

Pipeline (v2). The old loop screenshotted the canvas element through Playwright after every frame: ~270 ms per
1080×1280 frame of compositor capture + transfer, on top of ~100 ms of software rendering, so a 26 s clip took
5–6 minutes. Now the page keeps rendering while a small pool of Web Workers encodes the finished frames: after
each frame the main thread snapshots the canvas (createImageBitmap, a GPU-side copy), hands the bitmap to an
idle worker, and renders the next frame; the worker encodes the PNG (OffscreenCanvas.convertToBlob) and POSTs it
to a loopback HTTP server in this process, which writes frame_%05d.png. The browser is new-headless Chrome
(channel "chromium"), whose canvas filters run on the GPU, ~2× the headless shell's software raster.
Frames are the canvas's own pixels (the same bytes the studio's browser-side export uploads), no longer a
compositor screenshot.

Env: TYPESET_CAPTURE_BROWSER=shell → the bundled headless shell (software raster); TYPESET_CAPTURE_WORKERS (3).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKERS = max(1, int(os.environ.get("TYPESET_CAPTURE_WORKERS", "3")))


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


# Runs detached in the page; capture() polls window.__typesetCapture. One frame per worker in flight (back-pressure),
# so memory stays at a few bitmaps and a slow encoder throttles the renderer instead of queueing.
CAPTURE_LOOP = """({frames, timeout, url, workers}) => {
    const state = window.__typesetCapture = {done: 0, error: null, finished: false};
    const canvas = document.getElementById('stage');
    const src = `self.onmessage = async e => { const {i, bmp, url} = e.data;
        try {
            const oc = new OffscreenCanvas(bmp.width, bmp.height); oc.getContext('2d').drawImage(bmp, 0, 0); bmp.close();
            const blob = await oc.convertToBlob({type: 'image/png'});
            const r = await fetch(url, {method: 'POST', headers: {'X-Frame': String(i)}, body: blob});
            if (!r.ok) throw new Error('upload failed (' + r.status + ')');
            self.postMessage({i});
        } catch (err) { self.postMessage({i, error: String((err && err.message) || err)}); } };`;
    const script = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
    const idle = [], waiters = []; let inflight = 0;
    const pool = Array.from({length: workers}, () => { const w = new Worker(script);
        w.onmessage = e => { inflight--; if (e.data.error) { if (!state.error) state.error = `Frame ${e.data.i}: ${e.data.error}`; } else state.done++;
            const next = waiters.shift(); if (next) next(w); else idle.push(w); };
        w.onerror = e => { if (!state.error) state.error = 'Encoder worker: ' + (e.message || 'failed'); };
        return w; });
    idle.push(...pool);
    const take = () => idle.length ? Promise.resolve(idle.shift()) : new Promise(res => waiters.push(res));
    const race = (p, what) => { let t; return Promise.race([p, new Promise((_, rej) => {
        t = setTimeout(() => rej(new Error(what + ' timed out')), timeout); })]).finally(() => clearTimeout(t)); };
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    (async () => {
        for (let i = 0; i < frames && !state.error; i++) {
            await race(window.__typeset.renderFrame(i), `Frame ${i}`);
            const bmp = await createImageBitmap(canvas);
            const w = await take(); inflight++; w.postMessage({i, bmp, url}, [bmp]);
        }
        while (inflight > 0 && !state.error) await sleep(10);
    })().catch(err => { state.error = String((err && err.message) || err); })
      .finally(() => { state.finished = true; pool.forEach(w => w.terminate()); });
}"""


class _FrameSink(ThreadingHTTPServer):
    """Loopback receiver for the workers' PNG uploads."""
    daemon_threads = True

    def __init__(self, dest: Path):
        super().__init__(("127.0.0.1", 0), _FrameHandler)
        self.dest = dest
        self.failures: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/frame"


class _FrameHandler(BaseHTTPRequestHandler):
    server: _FrameSink

    def log_message(self, *args):  # quiet
        pass

    def _headers(self, status: int):
        self.send_response(status)
        # The page is on the web app's origin: answer CORS, and let Chrome cache the preflight for the whole run.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Frame, Content-Type")
        self.send_header("Access-Control-Max-Age", "7200")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_POST(self):
        try:
            index = int(self.headers["X-Frame"])
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not data.startswith(b"\x89PNG"):
                raise ValueError("body is not a PNG")
            final = self.server.dest / f"frame_{index:05d}.png"
            part = final.with_suffix(".png.part")
            part.write_bytes(data)
            os.replace(part, final)
            self._headers(200)
        except Exception as exc:
            self.server.failures.append(str(exc))
            self._headers(500)


def _gpu_args() -> list[str]:
    args = ["--enable-gpu-rasterization", "--enable-accelerated-2d-canvas", "--ignore-gpu-blocklist"]
    if sys.platform == "darwin":
        args.append("--use-angle=metal")
    return args


def launch(pw):
    """New-headless Chrome (channel "chromium": GPU canvas) unless TYPESET_CAPTURE_BROWSER=shell or that channel is
    not installed (`playwright install chromium`), then the bundled headless shell as before."""
    base = ["--autoplay-policy=no-user-gesture-required"]
    if os.environ.get("TYPESET_CAPTURE_BROWSER", "chromium") != "shell":
        try:
            return pw.chromium.launch(headless=True, channel="chromium", args=base + _gpu_args())
        except Exception as exc:
            print(f"capture: chromium channel unavailable ({str(exc)[:120]}); using the headless shell", file=sys.stderr)
    return pw.chromium.launch(headless=True, args=base)


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
    sink = _FrameSink(dest)
    threading.Thread(target=sink.serve_forever, name="typeset-capture-sink", daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = launch(pw)
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
                page.evaluate(CAPTURE_LOOP, {"frames": frames, "timeout": timeout * 1000, "url": sink.url, "workers": WORKERS})
                done = 0
                while True:
                    state = page.evaluate("() => window.__typesetCapture")
                    if state["error"]:
                        detail = "; ".join(sink.failures[:2] + errors[:2])
                        raise RuntimeError(f"Capture failed: {state['error']}" + (f" ({detail})" if detail else ""))
                    if progress and state["done"] != done:
                        done = state["done"]
                        progress(done, frames)
                    if state["finished"]:
                        break
                    time.sleep(.15)
                if errors:
                    raise RuntimeError("Renderer errors: " + "; ".join(errors[:3]))
                missing = [i for i in range(frames) if not (dest / f"frame_{i:05d}.png").is_file()]
                if missing:
                    raise RuntimeError(f"{len(missing)} of {frames} frames were not captured (first missing: {missing[0]})")
            finally:
                browser.close()
    finally:
        sink.shutdown()
        sink.server_close()
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
