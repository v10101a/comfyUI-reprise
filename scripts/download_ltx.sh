#!/usr/bin/env bash
# Downloads LTX weights into ~/ComfyUI/models. Resumable, single-instance (lock), size-verified against the server.
#   ./download_ltx.sh            -> Tier 1: LTX-Video 2B 0.9.8 distilled + T5-XXL fp16 (~16 GB). Runs locally on the M5 Max.
#   ./download_ltx.sh tier2      -> Tier 2 (STRETCH, unverified on MPS): LTX-2.3 22B distilled GGUF Q4_K_S + Gemma-3-12B fp8 (~33 GB).
set -euo pipefail
M="${COMFY_MODELS:-$HOME/ComfyUI/models}"
LOCK="$M/.download_ltx.lock"
if ! mkdir "$LOCK" 2>/dev/null; then echo "another download_ltx.sh is running (lock: $LOCK). Exiting."; exit 1; fi
trap 'rmdir "$LOCK"' EXIT

get() { # get <url> <dest>
  local url=$1 dest=$2 want have
  mkdir -p "$(dirname "$dest")"
  want=$(curl -sIL "$url" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
  if [ -f "$dest" ]; then
    have=$(stat -f%z "$dest")
    if [ "$have" = "$want" ]; then echo "ok    $(basename "$dest") (complete)"; return; fi
    echo "size mismatch on $(basename "$dest") ($have vs $want) -> re-downloading"; rm -f "$dest"
  fi
  if [ -f "$dest.part" ] && [ "$(stat -f%z "$dest.part")" -gt "${want:-0}" ]; then
    echo "stale .part larger than server file -> discarding"; rm -f "$dest.part"
  fi
  echo "fetch $(basename "$dest") ($((want / 1000000)) MB)"
  curl -L -C - --retry 5 --retry-all-errors --progress-bar -o "$dest.part" "$url"
  have=$(stat -f%z "$dest.part")
  if [ "$have" != "$want" ]; then echo "FAILED size check for $(basename "$dest"): $have vs $want"; return 1; fi
  mv "$dest.part" "$dest"; echo "done  $(basename "$dest")"
}

HF=https://huggingface.co
if [ "${1:-}" = "tier2" ]; then
  echo "Tier 2: ~33 GB. Needs ComfyUI-GGUF (git clone https://github.com/city96/ComfyUI-GGUF into custom_nodes; uv pip install gguf)."
  get $HF/QuantStack/LTX-2.3-GGUF/resolve/main/LTX-2.3-distilled-1.1/LTX-2.3-22B-distilled-1.1-Q4_K_S.gguf "$M/unet/LTX-2.3-22B-distilled-1.1-Q4_K_S.gguf"
  get $HF/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors "$M/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors"
  get $HF/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-distilled_video_vae.safetensors "$M/vae/ltx-2.3-22b-distilled_video_vae.safetensors"
  get $HF/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-distilled_audio_vae.safetensors "$M/vae/ltx-2.3-22b-distilled_audio_vae.safetensors"
  get $HF/unsloth/LTX-2.3-GGUF/resolve/main/text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors "$M/text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors"
else
  echo "Tier 1: ~16 GB total"
  get $HF/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors "$M/checkpoints/ltxv-2b-0.9.8-distilled.safetensors"
  get $HF/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp16.safetensors "$M/text_encoders/t5xxl_fp16.safetensors"
fi
echo "all done:"; ls -lh "$M"/checkpoints/*.safetensors "$M"/text_encoders/*.safetensors "$M"/unet/* "$M"/vae/*.safetensors 2>/dev/null
