#!/usr/bin/env bash
# Download every weight used by docs/model-eval.md into ~/ComfyUI/models/<kind>/.
# Resumable (curl -C -); writes to <name>.part and renames on success so ComfyUI never lists a partial file.
# Usage: scripts/eval/download_models.sh [ltx|image|all]   (default: all; two streams can run in parallel)
set -u
M=${COMFY_MODELS:-$HOME/ComfyUI/models}
dl() { # dl <url> <dest-path>
  local url=$1 dest=$2
  if [ -s "$dest" ]; then echo "have  $dest"; return 0; fi
  mkdir -p "$(dirname "$dest")"
  echo "fetch $dest"
  curl -fL -C - --retry 5 --retry-delay 3 -sS -o "$dest.part" "$url" && mv "$dest.part" "$dest" && echo "done  $dest ($(du -h "$dest" | cut -f1))"
}
ltx() {
  dl https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-spatial-upscaler-0.9.8.safetensors \
     "$M/latent_upscale_models/ltxv-spatial-upscaler-0.9.8.safetensors"
  dl https://huggingface.co/biali/LTXV-13B-0.9.8-distilled-GGUF/resolve/main/LTXV-13B-0.9.8-distilled-Q4_K_M.gguf \
     "$M/unet/LTXV-13B-0.9.8-distilled-Q4_K_M.gguf"
}
image() {
  dl https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors \
     "$M/text_encoders/qwen_3_4b.safetensors"
  dl https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors \
     "$M/vae/flux2-vae.safetensors"
  dl https://huggingface.co/Comfy-Org/flux2-klein/resolve/main/split_files/diffusion_models/flux-2-klein-4b.safetensors \
     "$M/diffusion_models/flux-2-klein-4b.safetensors"
  dl https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors \
     "$M/diffusion_models/z_image_turbo_bf16.safetensors"
}
case "${1:-all}" in
  ltx) ltx ;;
  image) image ;;
  all) ltx; image ;;
esac
