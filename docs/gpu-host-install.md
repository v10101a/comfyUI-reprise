# GPU host setup

> **Updated storage-constrained plan:** only about 3.6 GB remains on the GPU host. Pause the model downloads below. Krea2 images and a short MiniMax H3 video have both rendered successfully on its existing weights. VideoHelperSuite is loaded after the restart. `scripts/render_available.py --video-model minimax` runs both stages remotely; omitting the option uses the Mac’s complete LTX installation for video. Qwen is already usable on the Mac, though slow. The manifest below is retained for a future disk expansion; it is not required to keep building.

## Deferred installation request

Prepare the existing ComfyUI at http://100.104.17.103:8188 (seraph-01, RTX 4090 / 24 GB) for Typeset's remote LTX generation and Qwen image-edit evaluation. Inspect the actual ComfyUI root and its Python environment first. Preserve the working Krea/Minimax setup and existing model files.

1. Install VideoHelperSuite from https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite into this ComfyUI's custom_nodes, and install its requirements in the Python environment that runs ComfyUI. Ensure ffmpeg is available.
2. Download the following weights into the listed paths relative to the actual ComfyUI models directory. Reuse verified complete existing files; use resumable temporary downloads and validate before renaming. Check disk space first (roughly 47 GB additional if none are present).

| Destination under models/ | Exact download URL |
|---|---|
| checkpoints/ltxv-2b-0.9.8-distilled.safetensors | https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors |
| text_encoders/t5xxl_fp16.safetensors | https://huggingface.co/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp16.safetensors |
| diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors | https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors |
| text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors | https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors |
| vae/qwen_image_vae.safetensors | https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors |
| loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors | https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors |

The Qwen VAE already appears in the remote registry, so verify and reuse it. LTX 2B here is the older LTX-Video 0.9.8 checkpoint, not LTX-2/22B. This checkpoint contains its own VAE.

3. Restart the existing ComfyUI service once its queue is idle. Verify `/system_stats` and `/object_info` expose all filenames and these node classes: `CheckpointLoaderSimple`, `CLIPLoader`, `LTXVImgToVideo`, `LTXVPreprocess`, `LTXVConditioning`, `LTXVScheduler`, `ModelSamplingLTXV`, `SamplerCustom`, `PrimitiveFloat`, `VHS_VideoCombine`, `LTXVAddGuide`, `LTXVCropGuides`, `UNETLoader`, `VAELoader`, `TextEncodeQwenImageEditPlus`, `LoraLoaderModelOnly`, and `ModelSamplingAuraFlow`.
4. Check that this ComfyUI version can read the Qwen INT8 ConvRot format. Record any compatibility issue rather than silently substituting a different model. Our side will submit the actual LTX/Qwen smoke workflows after the files are visible.
5. Reply with the ComfyUI root, Python executable/environment, installed filenames/sizes, restart command/service name, and any errors. Keep ComfyUI reachable at the existing Tailscale address and port 8188.

The Mac keeps Typeset custom nodes, transcription, foreground analysis, UI and export. The Mac also runs a separate SDK proxy on 8190 pointing to this GPU server. No Typeset node copy, remote SDK proxy, GGUF pack, or newer LTX family is needed for this first split setup.
