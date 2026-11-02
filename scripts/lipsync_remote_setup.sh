#!/bin/bash
# Remote-side setup for the LatentSync 1.6 lip-sync pass on the 4090 (run over ssh by scripts/lipsync_remote.sh).
# Idempotent. Reuses the ComfyUI python (torch + CUDA already installed) through a --system-site-packages venv,
# installs only LatentSync's extra deps, downloads the two weight files (~5.2 GB).
#   RDIR   install dir (default ~/lipsync)
#   PYBIN  python to base the venv on (default: the python running ComfyUI, else python3)
set -euo pipefail
RDIR=${RDIR:-$HOME/lipsync}
mkdir -p "$RDIR"; cd "$RDIR"

if [[ -z "${PYBIN:-}" ]]; then
  # the python that runs ComfyUI already has a CUDA torch
  PYBIN=$(ps -eo args | grep -E "python[0-9.]* .*main\.py" | grep -v grep | awk '{print $1}' | head -1 || true)
  [[ -n "$PYBIN" && -x "$PYBIN" ]] || PYBIN=$(command -v python3)
fi
echo "base python: $PYBIN ($($PYBIN -V 2>&1))"
$PYBIN -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda, torch.cuda.is_available())"

[[ -d LatentSync ]] || git clone -q --depth 1 https://github.com/bytedance/LatentSync.git
cd LatentSync
if [[ -f ../latentsync.patch ]] && ! git apply --check -R ../latentsync.patch >/dev/null 2>&1; then
  git apply ../latentsync.patch && echo "patch applied"
fi

if [[ ! -x .venv/bin/python ]]; then
  $PYBIN -m venv --system-site-packages .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
# LatentSync requirements minus torch/torchvision (from the base python), gradio and DeepCache (not needed).
.venv/bin/python -m pip install -q "diffusers==0.32.2" "transformers==4.48.0" "accelerate==0.26.1" "einops==0.7.0" \
  "omegaconf==2.3.0" "opencv-python-headless==4.9.0.80" "python_speech_features==0.6" "librosa==0.10.1" \
  "imageio==2.31.1" "imageio-ffmpeg==0.5.1" "face-alignment==1.4.1" "huggingface-hub==0.30.2" "numpy==1.26.4" \
  "kornia==0.8.0" "insightface==0.7.3" onnxruntime-gpu soundfile ffmpeg-python
.venv/bin/python -c "import decord" 2>/dev/null || .venv/bin/python -m pip install -q "decord==0.6.0" || true

mkdir -p checkpoints/whisper
if [[ ! -s checkpoints/latentsync_unet.pt ]]; then
  .venv/bin/python -m huggingface_hub.commands.huggingface_cli download ByteDance/LatentSync-1.6 latentsync_unet.pt whisper/tiny.pt config.json --local-dir checkpoints 2>/dev/null \
  || .venv/bin/huggingface-cli download ByteDance/LatentSync-1.6 latentsync_unet.pt whisper/tiny.pt config.json --local-dir checkpoints
fi
ls -la checkpoints checkpoints/whisper
command -v ffmpeg >/dev/null || echo "WARNING: no ffmpeg on PATH (LatentSync needs it)"
df -h "$RDIR" | tail -1
echo "setup done"
