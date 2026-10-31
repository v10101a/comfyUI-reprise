#!/usr/bin/env bash
# Optional 2511 INT8 comparison weights (~29 GB). No hosted inference.
set -euo pipefail
model_root="${COMFY_MODELS:-$HOME/ComfyUI/models}"
fetch() {
  local url="$1" dest="$model_root/$2"
  [ -s "$dest" ] && return 0
  mkdir -p "$(dirname "$dest")"
  curl -fL -C - --retry 3 --retry-delay 2 --connect-timeout 20 -sS "$url" -o "$dest.part"
  mv "$dest.part" "$dest"
  echo "Downloaded $2"
}
fetch https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors
fetch https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
fetch https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors vae/qwen_image_vae.safetensors
fetch https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
