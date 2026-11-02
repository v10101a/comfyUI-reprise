"""Wan 2.2 S2V (speech-to-video) on the remote 4090: a still of the person + a vocal window -> a clip that sings it.

Native lip sync from the audio, the still's exact face at frame 0 (ComfyUI core WanSoundImageToVideo, fp8 14B,
4-step lightx2v LoRA; graph workflows/s2v.api.json). S2V works at 16 fps; the result is retimed to 24 fps
(motion-interpolated) and the song window (--mux-audio) laid over it.

  server/.venv/bin/python scripts/remote_s2v.py --name sid_l3 --image still.png \\
      --audio outputs/songs/so-i-die/so-i-die_section_vocals.flac --start 11.1 --dur 3.75 \\
      --mux-audio outputs/songs/so-i-die/so-i-die_section.wav \\
      --prompt "Close-up, the person sings quietly to camera ..." [--width 1344 --height 768 --seed 7 --steps 4]

Waits for the shared remote queue to be empty and unloads the other models (POST /free) first. Writes
outputs/songs/<song>/singing/<name>/: ref.png, clip.wav (what the model heard), the raw 16 fps mp4, <name>_24.mp4 (24 fps, vocal),
<name>_mux.mp4 (24 fps + song window), run.json.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
from PIL import Image

from remote_minimax import run, upload_image
from remote_h3_audio import cut_audio, prep_image, upload_audio, wait_for_idle
from song_paths import singing_output_root

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "workflows/s2v.api.json"
S2V_FPS = 16
OUT_FPS = 24


def snap_length(frames: int) -> int:
    """S2V latent grid: 4k+1 frames, rounded UP so the clip is never shorter than asked."""
    return max(5, frames + (-(frames - 1)) % 4)


MP_MODEL = Path.home() / "dev/lipsync/face_landmarker.task"


def _face_box_mediapipe(rgb) -> list[int] | None:
    """Face bounding box [x, y, w, h] from MediaPipe FaceLandmarker (robust on phone photos); None if unavailable."""
    try:
        import mediapipe as mp
    except Exception:
        return None
    if not MP_MODEL.is_file():
        return None
    opts = mp.tasks.vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(MP_MODEL)),
                                                 running_mode=mp.tasks.vision.RunningMode.IMAGE, num_faces=1)
    with mp.tasks.vision.FaceLandmarker.create_from_options(opts) as lm:
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not res.face_landmarks:
        return None
    hgt, wid = rgb.shape[:2]
    xs = [p.x * wid for p in res.face_landmarks[0]]
    ys = [p.y * hgt for p in res.face_landmarks[0]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def prep_image_face(src: Path, dest: Path, w: int, h: int, face_y: float = 0.42) -> dict:
    """Cover-fit like prep_image, but slide the crop so the (largest) face sits at `face_y` of the frame height
    and is horizontally centred; portrait phone photos become usable landscape start frames."""
    import cv2
    import numpy as np
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    info: dict = {"face": None, "detector": None}
    cx, cy = im.width / 2, im.height / 2
    box = _face_box_mediapipe(np.array(im))
    if box:
        info["detector"] = "mediapipe"
    else:  # fallback: OpenCV haar cascade; a start frame is a portrait, so ignore small detections
        arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        det = cas.detectMultiScale(arr, 1.05, 4, minSize=(h // 6, h // 6))
        if len(det):
            box = [int(v) for v in max(det, key=lambda d: d[2] * d[3])]
            info["detector"] = "haar"
    if box:
        x, y, fw, fh = box
        cx, cy = x + fw / 2, y + fh / 2
        info["face"] = [int(x), int(y), int(fw), int(fh)]
    left = int(min(max(0, cx - w / 2), im.width - w))
    top = int(min(max(0, cy - h * face_y), im.height - h))
    im.crop((left, top, left + w, top + h)).save(dest)
    info.update({"crop": [left, top, w, h], "scaled": [im.width, im.height]})
    return info


def build(prompt: str, w: int, h: int, length: int, seed: int, steps: int, ref: str, audio: str, prefix: str,
          lora: str | None, shift: float, cfg: float) -> dict:
    g = json.loads(GRAPH.read_text())
    g["5"]["inputs"]["text"] = prompt
    g["9"]["inputs"]["audio"] = audio
    g["11"]["inputs"]["image"] = ref
    g["12"]["inputs"].update({"width": w, "height": h, "length": length})
    g["13"]["inputs"].update({"seed": seed, "steps": steps, "cfg": cfg})
    g["3"]["inputs"]["shift"] = shift
    g["15"]["inputs"]["filename_prefix"] = prefix
    if lora is None:  # no speed LoRA: plain model, more steps, cfg > 1
        g["3"]["inputs"]["model"] = ["1", 0]
        del g["2"]
    else:
        g["2"]["inputs"]["lora_name"] = lora
    return g


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://100.104.17.103:8188")
    p.add_argument("--name", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--image", type=Path, required=True, help="reference still (cover-fit + centre-crop to the frame)")
    p.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="explicit source crop (overrides the face crop)")
    p.add_argument("--no-face-crop", action="store_true", help="plain centre crop instead of centring the crop on the face")
    p.add_argument("--face-y", type=float, default=0.42, help="where the face centre sits in the frame height (0..1)")
    p.add_argument("--audio", type=Path, required=True, help="vocal stem (or mix) the model listens to")
    p.add_argument("--start", type=float, default=0.0, help="seconds into --audio")
    p.add_argument("--dur", type=float, default=4.0, help="seconds (snapped to the 16 fps 4k+1 grid)")
    p.add_argument("--mux-audio", type=Path, help="audio laid over the result (same window); default --audio")
    p.add_argument("--mux-start", type=float, help="seconds into --mux-audio for the window (default --start); lets --audio be a prepared drive track starting at 0")
    p.add_argument("--width", type=int, default=1152, help="generation size (1152x656 fits the 4090 fully for ~5 s; 1344x768 spills to CPU and is 5x slower)")
    p.add_argument("--height", type=int, default=656)
    p.add_argument("--out-size", default="1344x768", help="final frame size (upscaled with lanczos); '' = keep the generation size")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--cfg", type=float, default=1.0)
    p.add_argument("--shift", type=float, default=8.0)
    p.add_argument("--lora", default="wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", help="speed LoRA; 'none' = base model (use --steps 20 --cfg 5)")
    p.add_argument("--no-free", action="store_true", help="don't unload the remote's other models first")
    p.add_argument("--retime", choices=["mci", "dup"], default="mci", help="16->24 fps: motion interpolation or frame duplication")
    p.add_argument("--pre", type=float, default=0.25, help="pre-roll s: generate from start-pre and trim it (S2V's first frames flash)")
    p.add_argument("--stretch", type=float, default=1.0, help="<1 = slow the vocal down for generation (pitch kept), then speed the picture back up; e.g. 0.8 for fast lines")
    p.add_argument("--motion", type=Path, help="optional preceding video motion for S2V ref_motion conditioning")
    p.add_argument("--motion-seconds", type=float, default=1.5, help="source seconds of preceding motion (maximum 3.5)")
    p.add_argument("--out", type=Path, help="output directory (default: the song's singing/ folder)")
    p.add_argument("--timeout", type=float, default=1800)
    a = p.parse_args()

    pre = max(0.0, min(a.pre, a.start))  # generated pre-roll, trimmed from the result
    st = max(0.5, min(1.0, a.stretch))  # generation runs at st x real speed (0.8 = 25 % slower), picture sped back up after
    length = snap_length(round((a.dur + pre) / st * S2V_FPS))
    gen_dur = length / S2V_FPS  # generated (slow) length incl. pre-roll
    dur = gen_dur * st  # real-time length incl. pre-roll
    out = (a.out or singing_output_root(a.name, a.audio)) / a.name
    out.mkdir(parents=True, exist_ok=True)
    if a.crop or a.no_face_crop:
        prep_image(a.image, out / "ref.png", a.width, a.height, a.crop)
        crop_info = {"crop": a.crop}
    else:
        crop_info = prep_image_face(a.image, out / "ref.png", a.width, a.height, a.face_y)
        print(f"[{a.name}] face crop {crop_info}", flush=True)
    cut_audio(a.audio, a.start - pre, dur, out / "real.wav")  # real-time window incl. pre-roll
    if st < 1.0:  # what the model hears: the same words, slower, same pitch
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out / "real.wav"), "-af", f"atempo={st:.4f}", "-ar", "48000", "-ac", "2", str(out / "gen.wav")], check=True)
    else:
        (out / "gen.wav").write_bytes((out / "real.wav").read_bytes())
    cut_audio(a.audio, a.start, dur - pre, out / "clip.wav")
    mux_start = a.start if a.mux_start is None else a.mux_start
    cut_audio(a.mux_audio or a.audio, mux_start, dur - pre, out / "mux.wav")

    wait_for_idle(a.base)
    if not a.no_free:
        try:
            httpx.post(f"{a.base}/free", json={"unload_models": True, "free_memory": True}, timeout=60)
        except httpx.HTTPError as e:
            print(f"/free failed ({e!r}); continuing", flush=True)
    ref_bytes = (out / "ref.png").read_bytes()
    ref_local = out / f"ref_{hashlib.sha256(ref_bytes).hexdigest()[:16]}.png"
    ref_local.write_bytes(ref_bytes)
    ref = upload_image(a.base, ref_local, "typeset/s2v")
    aud = upload_audio(a.base, out / "gen.wav", f"typeset_s2v_{a.name}.wav")
    lora = None if a.lora.lower() == "none" else a.lora
    g = build(a.prompt, a.width, a.height, length, a.seed, a.steps, ref, aud, f"s2v/{a.name}", lora, a.shift, a.cfg)
    motion_remote = None
    if a.motion:
        motion = out / "motion.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", str(max(.25, min(3.5, a.motion_seconds))),
                        "-i", str(a.motion), "-vf", f"setpts=PTS/{st},fps=16,scale={a.width}:{a.height}",
                        "-frames:v", "73", "-an", "-c:v", "libx264", "-crf", "17", str(motion)], check=True)
        filename = "motion_" + hashlib.sha256(motion.read_bytes()).hexdigest()[:16] + ".mp4"
        with motion.open("rb") as fh:
            uploaded = httpx.post(f"{a.base}/upload/image", files={"image": (filename, fh, "video/mp4")},
                                  data={"subfolder": "typeset/s2v", "overwrite": "true"}, timeout=120)
        uploaded.raise_for_status()
        info = uploaded.json()
        motion_remote = f"{info.get('subfolder') or 'typeset/s2v'}/{info['name']}"
        g["19"] = {"class_type": "VHS_LoadVideo", "inputs": {"video": motion_remote, "force_rate": 16,
                   "custom_width": a.width, "custom_height": a.height, "frame_load_cap": 73,
                   "skip_first_frames": 0, "select_every_nth": 1, "format": "None"}}
        g["12"]["inputs"]["ref_motion"] = ["19", 0]
    t0 = time.time()
    res = run(a.base, g, out, a.timeout)
    gen_s = time.time() - t0
    raw = next(f for f in res["files"] if f.endswith(".mp4"))
    # 16 -> 24 fps (duration unchanged, so the audio stays aligned), then the song window on top.
    vf = f"minterpolate=fps={OUT_FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" if a.retime == "mci" else f"fps={OUT_FPS}"
    if st < 1.0:  # speed the slow generation back up to real time (16 fps -> 16/st fps worth of motion, then 24 fps)
        vf = f"setpts={st:.4f}*PTS," + vf
    if a.out_size and a.out_size.lower() != f"{a.width}x{a.height}":
        ow, oh = (int(v) for v in a.out_size.lower().split("x"))
        vf += f",scale={ow}:{oh}:flags=lanczos"
    v24 = out / f"{a.name}_24.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-i", str(out / "clip.wav"), "-map", "0:v", "-map", "1:a",
                    "-vf", f"{vf},trim=start={pre:.4f},setpts=PTS-STARTPTS",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(v24)], check=True)
    mux = out / f"{a.name}_mux.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v24), "-i", str(out / "mux.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", str(mux)], check=True)
    meta = {**res, "engine": "wan2.2-s2v-14B-fp8", "audio": str(a.audio), "start": a.start, "duration": dur, "length": length, "stretch": st, "gen_duration": gen_dur,
            "s2v_fps": S2V_FPS, "out_fps": OUT_FPS, "retime": a.retime, "size": [a.width, a.height], "seed": a.seed, "steps": a.steps,
            "cfg": a.cfg, "shift": a.shift, "lora": lora, "prompt": a.prompt, "source_image": str(a.image), "source_crop": crop_info, "pre": pre,
            "remote_inputs": [ref, aud], "gen_seconds": round(gen_s, 1), "raw": raw, "v24": str(v24), "mux": str(mux)}
    if a.motion:
        meta.update(motion_reference=str(a.motion), motion_seconds=a.motion_seconds)
        meta["remote_inputs"].append(motion_remote)
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    print(f"[{a.name}] gen {gen_s:.0f} s -> {mux}")


if __name__ == "__main__":
    main()
