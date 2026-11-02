"""Re-sync the mouth of a generated take to its vocal with a dedicated lip-sync model (LatentSync 1.6, or Wav2Lip
as a fallback), then lay the original song window back over it.

MiniMax H3 "guide" mode only produces generic soft singing: a shift-control test scored the same with the audio
moved by a second, so its takes never followed the vocal. This pass keeps the H3 picture (likeness, film look,
camera) and replaces only the mouth region, driven by the vocal stem window the take was generated for
(<take>/clip.wav); <take>/mux.wav (song window) is muxed back on the result.

  server/.venv/bin/python scripts/lipsync_pass.py outputs/songs/so-i-die/clips/lipsync/sid_r3_esc_film2 \\
      [--engine latentsync|wav2lip] [--steps 20] [--guidance 1.5] [--seed 1247] [--audio other.wav]

Writes <take>/<engine>/<take>_<engine>.mp4 (synced picture + clip.wav) and <take>/<engine>/<take>_<engine>_mux.mp4
(synced picture + song window), plus run.json. Tools live in ~/dev/lipsync (venv, LatentSync, Wav2Lip).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path.home() / "dev/lipsync"
PY = TOOLS / ".venv/bin/python"
LS = TOOLS / "LatentSync"
W2L = TOOLS / "Wav2Lip"


def run(cmd, cwd=None, env=None):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def latentsync(video: Path, audio: Path, out: Path, a) -> None:
    env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1", "PYTHONUNBUFFERED": "1"}
    tmp = out.parent / "tmp"
    cmd = [PY, "-m", "scripts.inference", "--unet_config_path", f"configs/unet/{a.config}.yaml",
           "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", a.steps,
           "--guidance_scale", a.guidance, "--seed", a.seed, "--video_path", video.resolve(),
           "--audio_path", audio.resolve(), "--video_out_path", out.resolve(), "--temp_dir", tmp.resolve(), "--fps", a.fps]
    if a.deepcache:
        cmd.append("--enable_deepcache")
    if a.fp16:
        cmd.append("--fp16")
    run(cmd, cwd=LS, env=env)
    shutil.rmtree(tmp, ignore_errors=True)


def wav2lip(video: Path, audio: Path, out: Path, a) -> None:
    env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1", "PYTHONUNBUFFERED": "1"}
    cmd = [PY, "inference.py", "--checkpoint_path", "checkpoints/wav2lip_gan.pth", "--face", video.resolve(),
           "--audio", audio.resolve(), "--outfile", out.resolve(), "--pads", 0, a.pad_bottom, 0, 0,
           "--face_det_batch_size", 8, "--wav2lip_batch_size", 64]
    if a.nosmooth:
        cmd.append("--nosmooth")
    run(cmd, cwd=W2L, env=env)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("take", type=Path, help="take folder holding <name>_mux.mp4, clip.wav, mux.wav")
    p.add_argument("--engine", choices=["latentsync", "wav2lip"], default="latentsync")
    p.add_argument("--audio", type=Path, help="driving audio (default <take>/clip.wav, the vocal stem window)")
    p.add_argument("--video", type=Path, help="source picture (default <take>/<name>_mux.mp4)")
    p.add_argument("--tag", help="output folder name (default the engine name)")
    # latentsync
    p.add_argument("--config", default="stage2_512", help="stage2_512 (1.6, 512 px) or stage2 (256 px)")
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--guidance", type=float, default=1.5)
    p.add_argument("--seed", type=int, default=1247)
    p.add_argument("--deepcache", action="store_true")
    p.add_argument("--fp16", action="store_true")
    p.add_argument("--fps", type=int, default=24, help="working frame rate (the takes are 24 fps)")
    # wav2lip
    p.add_argument("--pad-bottom", type=int, default=10)
    p.add_argument("--nosmooth", action="store_true")
    a = p.parse_args()

    take = a.take.resolve()
    name = take.name
    video = a.video or take / f"{name}_mux.mp4"
    audio = a.audio or take / "clip.wav"
    song = take / "mux.wav"
    for f in (video, audio):
        if not f.is_file():
            sys.exit(f"missing {f}")
    tag = a.tag or a.engine
    out_dir = take / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    synced = out_dir / f"{name}_{tag}.mp4"

    # 16 kHz mono copy of the driving audio: both models resample internally, but a mono wav avoids
    # channel surprises and keeps the window exactly the clip's length.
    drive = out_dir / "drive.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-ac", "1", "-ar", "16000", drive])

    t0 = time.time()
    (latentsync if a.engine == "latentsync" else wav2lip)(video, drive, synced, a)
    dt = time.time() - t0

    mux = out_dir / f"{name}_{tag}_mux.mp4"
    if song.is_file():
        run(["ffmpeg", "-v", "error", "-y", "-i", synced, "-i", song, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "256k", "-shortest", mux])
    meta = {"engine": a.engine, "source_video": str(video), "drive_audio": str(audio), "song_audio": str(song),
            "seconds": round(dt, 1), "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()},
            "synced": str(synced), "mux": str(mux) if song.is_file() else None}
    (out_dir / "run.json").write_text(json.dumps(meta, indent=2))
    print(f"[{name}/{tag}] {dt:.0f} s -> {mux if song.is_file() else synced}")


if __name__ == "__main__":
    main()
