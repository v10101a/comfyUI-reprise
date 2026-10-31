#!/usr/bin/env python
"""Generate the zero-backend sample for Typeset's mock mode.

Writes into apps/web/public/sample/:
  project.json, words.json, tracks.json      (SCHEMA.md §1 / §2)
  sample.wav                                  (12 s synthetic beat, 22.05 kHz mono)
  sample.mp4                                  (1280x720 @ 24 fps gradient + walking "person", with the audio muxed)
  matte/fg.webm                               (VP9 + alpha cutout of the same "person")

Run with the server venv python (needs numpy; ffmpeg at /opt/homebrew/bin/ffmpeg):
  /Users/lh1783/dev/comfy/server/.venv/bin/python apps/web/scripts/make_sample.py [--no-media]
"""
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "sample"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

W, H, FPS, DUR = 1280, 720, 24, 12.0
FRAMES = int(round(DUR * FPS))
SR = 22050

# ----------------------------------------------------------------------------- lyric
# (lineId, preset, placement, extra, [(text, start, end), ...])
LINES = [
    ("l0", "pop", "overlay", {"style": {"fontFamily": "Inter", "fontWeight": 800}},
     [("Static", 0.50, 0.82), ("in", 0.86, 0.98), ("the", 1.00, 1.14), ("hallway", 1.18, 1.70), ("light", 1.76, 2.30)]),
    ("l1", "karaoke", "behind", {"position": {"x": 0.5, "y": 0.5}, "style": {"fontFamily": "Inter", "fontWeight": 700, "fontSize": 0.11}},
     [("Count", 2.60, 2.90), ("the", 2.92, 3.04), ("frames", 3.08, 3.50), ("I", 3.54, 3.64), ("left", 3.68, 4.00), ("behind", 4.04, 4.50)]),
    ("l2", "hud", "anchor", {"anchor": {"trackId": "person0", "dx": 0.14, "dy": -0.10}},
     [("SIGNAL", 4.80, 5.40), ("FOUND", 5.50, 6.30)]),
    ("l3", "typewriter", "overlay", {"position": {"x": 0.08, "y": 0.18}, "style": {"fontFamily": "Space Mono", "fontWeight": 400, "fontSize": 0.055, "align": "left"}},
     [("You", 6.60, 6.85), ("were", 6.90, 7.15), ("never", 7.20, 7.60), ("out", 7.65, 7.90), ("of", 7.95, 8.10), ("frame", 8.15, 8.60)]),
    ("l4", "pop", "anchor", {"anchor": {"trackId": "person0", "dx": 0.0, "dy": -0.20}, "style": {"fontFamily": "Bebas Neue", "fontWeight": 400, "fontSize": 0.09}},
     [("Hold", 8.80, 9.20), ("still", 9.25, 9.80)]),
    ("l4", "none", "inworld", {"shotId": "s0"},
     [("glass", 9.85, 10.30)]),
    ("l5", "pop", "behind", {"position": {"x": 0.5, "y": 0.52}, "style": {"fontFamily": "Anton", "fontWeight": 400, "fontSize": 0.22, "fill": "#f5e9d0"}},
     [("Typeset", 10.50, 10.95), ("the", 11.00, 11.20), ("night", 11.25, 11.90)]),
]


def build_words():
    words, lines, project_words = [], {}, []
    k = 0
    for line_id, preset, placement, extra, ws in LINES:
        for text, s, e in ws:
            wid = f"w{k:02d}"
            k += 1
            words.append({"text": text, "start": s, "end": e, "confidence": 0.9, "lineId": line_id})
            pw = {"id": wid, "text": text, "start": s, "end": e, "lineId": line_id, "placement": placement, "preset": preset}
            for key in ("position", "anchor", "style", "shotId"):
                if key in extra:
                    pw[key] = extra[key]
            project_words.append(pw)
            ln = lines.setdefault(line_id, {"id": line_id, "text": "", "start": s, "end": e})
            ln["text"] = (ln["text"] + " " + text).strip()
            ln["start"] = min(ln["start"], s)
            ln["end"] = max(ln["end"], e)
    words.sort(key=lambda w: w["start"])
    project_words.sort(key=lambda w: w["start"])
    return words, list(lines.values()), project_words


# ----------------------------------------------------------------------------- "person" path
def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def person_at(t: float):
    """Normalized head center + body bbox for the walking capsule."""
    cx = 0.30 + 0.40 * smoothstep(t / DUR) + 0.03 * math.sin(2 * math.pi * t / 3.0)
    head_y = 0.36 + 0.015 * math.sin(2 * math.pi * t / 2.3)
    body_h = 0.52
    body_w = 0.16 + 0.01 * math.sin(2 * math.pi * t / 1.7)
    top = head_y - 0.07
    bbox = [cx - body_w / 2, top, body_w, body_h]
    return cx, head_y, bbox


def build_tracks():
    frames = []
    for f in range(FRAMES):
        # Detector dropouts: a short gap (hold) and a long gap (hide).
        if 60 <= f <= 63 or 150 <= f <= 168:
            continue
        t = f / FPS
        cx, cy, bbox = person_at(t)
        # tiny deterministic detector noise so the EMA smoothing has something to do
        n = (math.sin(f * 12.9898) * 43758.5453) % 1.0 - 0.5
        frames.append({"f": f, "bbox": [round(v, 4) for v in bbox], "cx": round(cx + n * 0.006, 4), "cy": round(cy - n * 0.004, 4)})
    return {"fps": FPS, "frames": FRAMES, "tracks": [{"id": "person0", "label": "person", "frames": frames}]}


# ----------------------------------------------------------------------------- audio
def build_audio(path: Path):
    n = int(DUR * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float64)
    # kick every 0.5 s
    for b in np.arange(0, DUR, 0.5):
        i0 = int(b * SR)
        seg = t[: int(0.25 * SR)]
        env = np.exp(-seg * 18)
        kick = np.sin(2 * np.pi * (48 + 90 * np.exp(-seg * 30)) * seg) * env
        out[i0 : i0 + len(kick)] += 0.8 * kick[: n - i0]
    # hats every 0.25 s
    rng = np.random.default_rng(7)
    for b in np.arange(0.25, DUR, 0.5):
        i0 = int(b * SR)
        seg = t[: int(0.06 * SR)]
        hat = rng.standard_normal(len(seg)) * np.exp(-seg * 70)
        out[i0 : i0 + len(hat)] += 0.12 * hat[: n - i0]
    # pad chords, change every 2 s
    chords = [[55, 62, 65], [53, 60, 65], [50, 57, 62], [48, 55, 60], [53, 60, 65], [55, 62, 67]]
    for ci, chord in enumerate(chords):
        i0, i1 = int(ci * 2 * SR), int(min(DUR, (ci + 1) * 2) * SR)
        seg = t[i0:i1] - t[i0]
        env = np.minimum(1, seg * 6) * np.minimum(1, (seg[-1] - seg) * 4 + 0.05)
        pad = np.zeros_like(seg)
        for m in chord:
            f0 = 440 * 2 ** ((m - 69) / 12)
            pad += np.sin(2 * np.pi * f0 * seg) + 0.5 * np.sin(2 * np.pi * f0 * 1.005 * seg)
        out[i0:i1] += 0.08 * pad * env
    out = np.tanh(out * 1.2)
    pcm = (out * 32000).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ----------------------------------------------------------------------------- video
def render_media(wav: Path, mp4: Path, webm: Path):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = xx / W, yy / H
    base_a = np.array([14, 18, 34], np.float32)   # deep blue
    base_b = np.array([92, 38, 48], np.float32)   # wine
    base_c = np.array([210, 150, 80], np.float32)  # amber glow

    bg_cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
              "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
              "-i", str(wav),
              "-c:v", "libx264", "-preset", "fast", "-crf", "27", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(mp4)]
    fg_cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
              "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
              "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "34",
              "-deadline", "good", "-cpu-used", "5", "-row-mt", "1", str(webm)]
    bg = subprocess.Popen(bg_cmd, stdin=subprocess.PIPE)
    fg = subprocess.Popen(fg_cmd, stdin=subprocess.PIPE)
    try:
        for f in range(FRAMES):
            t = f / FPS
            # slow drifting gradient
            g = 0.5 + 0.5 * np.sin(2.2 * nx + 1.3 * ny + t * 0.35)
            glow = np.exp(-(((nx - 0.7 - 0.1 * math.sin(t * 0.4)) ** 2) * 4 + ((ny - 0.25) ** 2) * 6))
            img = base_a[None, None, :] * (1 - g[..., None]) + base_b[None, None, :] * g[..., None]
            img += base_c[None, None, :] * glow[..., None] * 0.55
            # floor
            floor = np.clip((ny - 0.78) * 12, 0, 1)[..., None]
            img = img * (1 - floor * 0.35)
            # person (capsule body + head)
            cx, hy, bbox = person_at(t)
            bx, by, bw, bh = bbox
            body_cx, body_top, body_bot = cx, hy + 0.06, by + bh
            rx = bw / 2
            dxn = (nx - body_cx) / rx
            dyn = np.where(ny < body_top, (ny - body_top) / 0.03, 0) * (ny < body_top)
            dyb = np.clip((ny - body_bot) / 0.03, 0, None)
            body = ((dxn ** 2 + dyn ** 2 + dyb ** 2) <= 1.0) & (ny >= body_top - 0.03) & (ny <= body_bot + 0.03)
            head = ((nx - cx) / 0.045) ** 2 + ((ny - hy) / 0.075) ** 2 <= 1.0
            mask = (body | head).astype(np.float32)
            # soften edge by 1px blur-ish (cheap: average with shifted copies)
            soft = (mask + np.roll(mask, 1, 0) + np.roll(mask, -1, 0) + np.roll(mask, 1, 1) + np.roll(mask, -1, 1)) / 5
            shade = 0.75 + 0.25 * np.clip((nx - (cx - rx)) / (2 * rx), 0, 1)
            pcol = np.array([38, 40, 46], np.float32)[None, None, :] * shade[..., None] + np.array([60, 20, 15], np.float32) * (1 - shade[..., None]) * 0.4
            comp = img * (1 - soft[..., None]) + pcol * soft[..., None]
            bg.stdin.write(np.clip(comp, 0, 255).astype(np.uint8).tobytes())
            rgba = np.concatenate([np.clip(pcol, 0, 255), (soft * 255)[..., None]], axis=2).astype(np.uint8)
            fg.stdin.write(rgba.tobytes())
    finally:
        bg.stdin.close()
        fg.stdin.close()
        bg.wait()
        fg.wait()
    if bg.returncode or fg.returncode:
        raise SystemExit(f"ffmpeg failed: bg={bg.returncode} fg={fg.returncode}")


def main():
    no_media = "--no-media" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "matte").mkdir(exist_ok=True)
    words, lines, project_words = build_words()
    with open(OUT / "words.json", "w") as f:
        json.dump({"source": "aligned", "model": "sample", "language": "en", "words": words, "lines": lines}, f, indent=1)
    with open(OUT / "tracks.json", "w") as f:
        json.dump(build_tracks(), f, separators=(",", ":"))
    lyrics = "\n".join(l["text"] for l in lines)
    project = {
        "version": 1,
        "id": "sample",
        "name": "Sample — Static in the hallway light",
        "fps": FPS, "width": W, "height": H, "duration": DUR,
        "media": {
            "video": {"path": "media/sample.mp4", "duration": DUR, "width": W, "height": H, "fps": FPS, "hasAudio": True},
            "audio": {"path": "media/sample.wav", "duration": DUR, "hasAudio": True},
            "lyrics": lyrics,
        },
        "analysis": {"words": "analysis/words.json", "matte": "analysis/matte/", "tracks": "analysis/tracks.json"},
        "style": {"fontFamily": "Inter", "fontWeight": 700, "fontSize": 0.08, "fill": "#ffffff",
                  "stroke": "#000000", "strokeWidth": 0.0, "letterSpacing": 0, "align": "center"},
        "words": project_words,
        "shots": [{"id": "s0", "wordIds": ["w21"], "start": 9.85, "end": 10.30,
                   "prompt": "the word GLASS as frosted glass letters leaning against the hallway wall, cinematic",
                   "status": "pending", "workflow": "text_plate+ltx_i2v"}],
    }
    # make sure the inworld shot points at the right word id
    glass = next(w for w in project_words if w["text"] == "glass")
    project["shots"][0]["wordIds"] = [glass["id"]]
    glass["shotId"] = "s0"
    with open(OUT / "project.json", "w") as f:
        json.dump(project, f, indent=1)
    print(f"wrote project.json ({len(project_words)} words, {len(lines)} lines), words.json, tracks.json")
    if no_media:
        return
    build_audio(OUT / "sample.wav")
    print("wrote sample.wav")
    render_media(OUT / "sample.wav", OUT / "sample.mp4", OUT / "matte" / "fg.webm")
    for p in ("sample.mp4", "matte/fg.webm"):
        print(f"wrote {p} ({os.path.getsize(OUT / p) // 1024} KB)")


if __name__ == "__main__":
    main()
