"""Audio-driven MiniMax H3 on the remote 4090: lip sync / music-driven performance from an existing track.

Two modes (both on the fl2va int8 weights + 8-step turbo LoRA that the remote has):
  guide  MiniMaxH3ImageToVideo(first_frame) + MiniMaxH3AddGuide(audio @ frame 0). The audio half of the joint
         latent is anchored to your track; the model generates the picture to match it.   (workflows/h3_lipsync.api.json)
  ref    MiniMaxH3ReferenceToVideo with the face as <Picture 1> and the track as <Audio 1> ("use <Audio 1> exactly as
         it is"), optionally plus the first frame as an image guide. Template pattern from video_minimax_h3_r2v.

  server/.venv/bin/python scripts/remote_h3_audio.py --name hook_vox --image face.png \\
      --audio outputs/align/ffm_vocals_roformer.flac --start 29.0 --mux-audio outputs/ffm/work/ffm_ext_audio.wav \\
      --prompt "Close-up ... sings ..." [--mode guide|ref] [--width 640 --height 896 --length 124 --seed 7]

Waits until the shared remote queue is empty before submitting (one job at a time). Writes outputs/h3_audio/<name>/:
face.png, clip.wav (what the model heard), the raw remote mp4, <name>_mux.mp4 (picture + original audio), workflow/history.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import httpx
from PIL import Image

from remote_minimax import run, upload_image

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "workflows/h3_lipsync.api.json"
FPS = 24


def snap_length(n: int) -> int:
    return n + (5 - n % 17) % 17  # model grid 17k+5


def prep_image(src: Path, dest: Path, w: int, h: int, crop: list[int] | None) -> None:
    im = Image.open(src).convert("RGB")
    if crop:
        x, y, cw, ch = crop
        im = im.crop((x, y, x + cw, y + ch))
    s = max(w / im.width, h / im.height)  # cover, then centre-crop to the exact size
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    im.crop((l, t, l + w, t + h)).save(dest)


def cut_audio(src: Path, start: float, dur: float, dest: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-t", f"{dur}", "-i", str(src),
                    "-ar", "48000", "-ac", "2", str(dest)], check=True)


def upload_audio(base: str, local: Path, name: str) -> str:
    # LoadAudio lists only the top level of input/, so the clip goes to the root under a unique name.
    with local.open("rb") as fh:
        r = httpx.post(f"{base}/upload/image", files={"image": (name, fh, "audio/wav")},
                       data={"overwrite": "true", "type": "input"}, timeout=120)
    r.raise_for_status()
    return r.json()["name"]


def wait_for_idle(base: str, poll: float = 3, max_wait: float = 7200) -> None:
    t0 = time.time()
    while True:
        try:
            q = httpx.get(f"{base}/queue", timeout=30).json()
        except httpx.HTTPError as e:  # tailnet hiccup: keep waiting
            print(f"queue poll failed ({e!r}); retrying", flush=True)
            time.sleep(poll)
            continue
        n = len(q["queue_running"]) + len(q["queue_pending"])
        if n == 0:
            return
        if time.time() - t0 > max_wait:
            raise SystemExit("remote queue never emptied")
        if int(time.time() - t0) % 60 < poll:
            print(f"remote busy ({n} job(s)); waiting", flush=True)
        time.sleep(poll)


def build(mode: str, prompt: str, w: int, h: int, length: int, seed: int, face: str, audio: str, prefix: str,
          ref_first_frame: bool, steps: int, turbo: bool = True, scheduler: str = "simple") -> dict:
    g = json.loads(GRAPH.read_text())
    g["5"]["inputs"]["image"] = face
    g["16"]["inputs"]["audio"] = audio
    g["7"]["inputs"]["noise_seed"] = seed
    g["10"]["inputs"]["steps"] = steps
    g["10"]["inputs"]["scheduler"] = scheduler
    if not turbo:  # base model, no 8-step LoRA (use ~20 steps)
        g["8"]["inputs"]["model"] = ["1", 0]
        g["10"]["inputs"]["model"] = ["1", 0]
        del g["2"]
    g["15"]["inputs"]["filename_prefix"] = prefix
    if mode == "guide":
        g["6"]["inputs"].update({"prompt": prompt, "width": w, "height": h, "length": length})
    else:
        g["6"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["3", 0], "vae": ["4", 0], "audio_vae": ["13", 0], "prompt": prompt, "width": w, "height": h,
            "length": length, "ref_image_size": "match",
            "ref_images.ref_image_1": ["5", 0], "ref_audios.ref_audio_1": ["16", 0]}}
        if ref_first_frame:
            g["17"]["inputs"] = {"positive": ["6", 0], "latent": ["6", 1], "frame_idx": 0, "vae": ["4", 0], "image": ["5", 0]}
        else:
            del g["17"]
            g["8"]["inputs"]["conditioning"] = ["6", 0]
    return g


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://100.104.17.103:8188")
    p.add_argument("--name", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", type=Path, required=True, help="local face / first-frame image")
    p.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="crop the image before fitting")
    p.add_argument("--audio", type=Path, required=True, help="track the model is conditioned on (vocal stem or mix)")
    p.add_argument("--start", type=float, default=0.0, help="seconds into --audio")
    p.add_argument("--mux-audio", type=Path, help="audio laid over the result (same window); default --audio")
    p.add_argument("--mode", choices=["guide", "ref"], default="guide")
    p.add_argument("--ref-first-frame", action="store_true", help="ref mode: also pin the image at frame 0")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=896)
    p.add_argument("--length", type=int, default=124)
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--no-turbo", action="store_true", help="drop the 8-step turbo LoRA (set --steps 20)")
    p.add_argument("--scheduler", default="simple", help="simple (turbo default) or beta")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, default=ROOT / "outputs/h3_audio")
    p.add_argument("--timeout", type=float, default=1800)
    a = p.parse_args()

    length = snap_length(a.length)
    dur = length / FPS
    out = a.out / a.name
    out.mkdir(parents=True, exist_ok=True)
    prep_image(a.image, out / "face.png", a.width, a.height, a.crop)
    cut_audio(a.audio, a.start, dur, out / "clip.wav")
    cut_audio(a.mux_audio or a.audio, a.start, dur, out / "mux.wav")

    wait_for_idle(a.base)
    face = upload_image(a.base, out / "face.png", "typeset/h3_audio")
    aud = upload_audio(a.base, out / "clip.wav", f"typeset_h3a_{a.name}.wav")
    g = build(a.mode, a.prompt, a.width, a.height, length, a.seed, face, aud, f"h3_audio/{a.name}",
              a.ref_first_frame, a.steps, not a.no_turbo, a.scheduler)
    res = run(a.base, g, out, a.timeout)
    raw = next(f for f in res["files"] if f.endswith(".mp4"))
    mux = out / f"{a.name}_mux.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-i", str(out / "mux.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", str(mux)], check=True)
    meta = {**res, "mode": a.mode, "audio": str(a.audio), "start": a.start, "duration": dur, "length": length,
            "size": [a.width, a.height], "seed": a.seed, "steps": a.steps, "turbo": not a.no_turbo, "scheduler": a.scheduler, "prompt": a.prompt,
            "remote_inputs": [face, aud], "mux": str(mux)}
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    print(f"[{a.name}] -> {mux}")


if __name__ == "__main__":
    main()
