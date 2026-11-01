"""ffprobe / ffmpeg helpers and staging of media into ComfyUI's input directory."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path, PurePosixPath

from .config import settings
from .models import MediaRef

log = logging.getLogger("typeset.media")

MAX_LONG_EDGE = 1920


class FfmpegError(RuntimeError):
    pass


def run_cmd(cmd: list[str], *, timeout: float | None = None, what: str = "ffmpeg") -> subprocess.CompletedProcess:
    log.debug("%s: %s", what, " ".join(str(c) for c in cmd))
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        raise FfmpegError(f"{what} failed (exit {proc.returncode}): " + " | ".join(tail))
    return proc


def ffmpeg(args: list, *, timeout: float | None = None, what: str = "ffmpeg") -> None:
    run_cmd([settings.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *args], timeout=timeout, what=what)


# ---- probing ---------------------------------------------------------------------

def ffprobe_frames(path: Path) -> int:
    """Exact video frame count (counts packets; cheap, no decode)."""
    out = run_cmd([settings.ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
                       "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)], what="ffprobe(frames)").stdout
    return int(str(out).strip().split()[0])


def ffprobe(path: Path) -> dict:
    proc = run_cmd(
        [settings.ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        what="ffprobe",
    )
    return json.loads(proc.stdout or "{}")


def _parse_rate(raw: str | None) -> float | None:
    if not raw or raw in ("0/0", "0"):
        return None
    try:
        return float(Fraction(raw))
    except (ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path, rel_path: str) -> MediaRef:
    info = ffprobe(path)
    streams = info.get("streams", [])
    fmt = info.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = None
    for cand in (fmt.get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            if cand is not None:
                duration = float(cand)
                break
        except ValueError:
            continue
    ref = MediaRef(path=rel_path, duration=round(duration or 0.0, 3), hasAudio=audio is not None)
    if video is not None:
        w, h = int(video.get("width") or 0), int(video.get("height") or 0)
        rot = 0
        for sd in video.get("side_data_list", []) or []:
            if "rotation" in sd:
                try:
                    rot = int(round(float(sd["rotation"])))
                except (TypeError, ValueError):
                    pass
        if rot % 180 != 0:
            w, h = h, w
        ref.width, ref.height = w, h
        fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))
        if fps:
            ref.fps = round(fps, 3)
    return ref


def even(n: float) -> int:
    v = int(round(n))
    return v if v % 2 == 0 else v - 1


def fit_within(w: int, h: int, max_long: int = MAX_LONG_EDGE) -> tuple[int, int]:
    if w <= 0 or h <= 0:
        return 1920, 1080
    long_edge = max(w, h)
    scale = min(1.0, max_long / long_edge)
    return max(2, even(w * scale)), max(2, even(h * scale))


# ---- filenames -----------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, fallback: str = "file") -> str:
    base = os.path.basename(name or "").strip()
    base = _SAFE.sub("_", base).strip("._")
    return base or fallback


# ---- ComfyUI input staging -----------------------------------------------------

def comfy_rel(pid: str, *parts: str) -> str:
    return "/".join(["typeset", pid, *parts])


def stage_to_comfy_input(src: Path, pid: str, *rel_parts: str) -> str:
    """Hard-link (or copy) `src` into ~/ComfyUI/input/typeset/<pid>/<rel_parts>.

    Returns the path relative to ComfyUI's input dir, which is what `comfy_input_path`
    workflow inputs expect (e.g. LoadVideo.file = "typeset/<pid>/clip.mp4").
    """
    rel = comfy_rel(pid, *(rel_parts or (src.name,)))
    dest = settings.comfy_input_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            if os.path.samefile(src, dest) or (dest.stat().st_size == src.stat().st_size and dest.stat().st_mtime >= src.stat().st_mtime):
                return rel
        except OSError:
            pass
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return rel


def comfy_input_abs(rel: str) -> Path:
    return settings.comfy_input_dir / rel


# ---- ffmpeg building blocks ---------------------------------------------------

def extract_frame(video: Path, t: float, out_png: Path, width: int | None = None, height: int | None = None) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2" if width and height else "null"
    ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1", "-vf", vf, out_png], what="ffmpeg(extract_frame)")
    return out_png


def extract_audio_wav(src: Path, out_wav: Path, sample_rate: int = 16000, mono: bool = True) -> Path:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", src, "-vn", "-ar", str(sample_rate)]
    if mono:
        args += ["-ac", "1"]
    args += ["-c:a", "pcm_s16le", out_wav]
    ffmpeg(args, what="ffmpeg(extract_audio)")
    return out_wav


def encode_alpha_webm(pattern: Path, fps: float, out: Path, start_number: int = 1, crf: int = 30) -> Path:
    """PNG sequence (RGBA) → VP9 with alpha for Chromium preview."""
    ffmpeg(
        [
            "-framerate", f"{fps}", "-start_number", str(start_number), "-i", pattern,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
            "-b:v", "0", "-crf", str(crf), "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
            "-r", f"{fps}", out,
        ],
        what="ffmpeg(vp9-alpha)",
    )
    return out


def encode_prores4444(pattern: Path, fps: float, out: Path, start_number: int = 0) -> Path:
    ffmpeg(
        [
            "-framerate", f"{fps}", "-start_number", str(start_number), "-i", pattern,
            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0",
            "-r", f"{fps}", out,
        ],
        what="ffmpeg(prores4444)",
    )
    return out


# ---- studio preview proxies ---------------------------------------------------------
# Half-size, short-GOP copies for the studio's draft renders (scrubbing, dragging, look thumbnails). Seeking the
# originals decodes from the last keyframe (~100 ms per frame on the hero footage, ~150 ms for the VP9-alpha matte);
# these seek in ~17 ms (outputs/perf/seek-candidates-hero.json). Found by convention, never by a project field:
# media/proxy/<video stem>.mp4 and <matte dir>/fg_proxy.webm. Export, TypesetRender and capture read the originals.
PROXY_MAX_LONG = 672
PROXY_GOP = 12
# Studio "seek copies": the same short GOP at full size, for paused (settled) studio frames, so they stay full quality
# but seek in ~20 ms instead of up to ~0.9 s (long-GOP mattes). media/proxy/<stem>.full.mp4 and <matte>/fg_seek.webm.


def _scale(max_long: int) -> str:
    """Long edge to max_long (never upscaled; 0 = keep size), both dimensions even."""
    if not max_long:
        return "scale=w='trunc(iw/2)*2':h='trunc(ih/2)*2'"
    return (f"scale=w='trunc(min(1,{max_long}/max(iw,ih))*iw/2)*2'"
            f":h='trunc(min(1,{max_long}/max(iw,ih))*ih/2)*2'")


PROXY_SCALE = _scale(PROXY_MAX_LONG)


def proxy_rel(video_rel: str) -> str:
    """media/<name>.<ext> -> media/proxy/<name>.mp4 (apps/web/src/renderer.ts proxyPath mirrors this)."""
    p = PurePosixPath(video_rel)
    return str(p.parent / "proxy" / f"{p.stem}.mp4")


def seek_rel(video_rel: str) -> str:
    """media/<name>.<ext> -> media/proxy/<name>.full.mp4 (renderer.ts seekPath mirrors this). Upload names are unique,
    so a new video never reuses an old copy."""
    p = PurePosixPath(video_rel)
    return str(p.parent / "proxy" / f"{p.stem}.full.mp4")


def encode_preview_proxy(src: Path, out: Path, gop: int = PROXY_GOP, full: bool = False) -> Path:
    """Studio-only H.264 proxy of a project video; written atomically so a studio mid-load never sees a partial file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    ffmpeg(
        [
            "-i", src, "-vf", _scale(0) if full else PROXY_SCALE,
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "fastdecode", "-crf", "17" if full else "20", "-pix_fmt", "yuv420p",
            "-x264-params", f"keyint={gop}:min-keyint={gop}:scenecut=0:bframes=0",
            "-an", "-movflags", "+faststart", tmp,
        ],
        what="ffmpeg(preview proxy)",
    )
    tmp.replace(out)
    return out


def clear_matte_proxies(matte_dir: Path) -> None:
    """Drop studio copies of a matte that is about to be rewritten, so they can never disagree with fg.webm."""
    for name in ("fg_proxy.webm", "fg_seek.webm", "fg_proxy.tmp.webm", "fg_seek.tmp.webm"):
        (matte_dir / name).unlink(missing_ok=True)


def encode_matte_proxy(matte_dir: Path, fps: float, gop: int = PROXY_GOP, full: bool = False) -> Path | None:
    """<matte>/fg_proxy.webm (VP9 alpha, half size, short GOP) from the fg_%05d.png sequence, or from fg.webm when the
    PNGs are gone. None when there is nothing to encode from."""
    pngs = sorted(matte_dir.glob("fg_[0-9]*.png"))
    webm = matte_dir / "fg.webm"
    if pngs:
        first = int(pngs[0].stem.split("_", 1)[1])
        src = ["-framerate", f"{fps}", "-start_number", str(first), "-i", matte_dir / "fg_%05d.png"]
    elif webm.exists():
        src = ["-c:v", "libvpx-vp9", "-i", webm]  # the libvpx decoder keeps alpha; the native one drops it
    else:
        return None
    name = "fg_seek" if full else "fg_proxy"
    out = matte_dir / f"{name}.webm"
    tmp = matte_dir / f"{name}.tmp.webm"
    ffmpeg(
        [
            *src, "-vf", _scale(0) if full else PROXY_SCALE,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30" if full else "32",
            "-g", str(gop), "-row-mt", "1", "-deadline", "realtime", "-cpu-used", "8", "-r", f"{fps}", "-an", tmp,
        ],
        what="ffmpeg(matte proxy)",
    )
    tmp.replace(out)
    return out


def make_test_video(out: Path, duration: float = 3.0, fps: float = 24, size: str = "640x360", with_audio: bool = True) -> Path:
    """Synthetic bg clip (testsrc2 + sine tone) — used by tests and smoke checks."""
    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={duration}"]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast"]
    if with_audio:
        args += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    args += ["-movflags", "+faststart", out]
    ffmpeg(args, what="ffmpeg(testsrc)")
    return out
