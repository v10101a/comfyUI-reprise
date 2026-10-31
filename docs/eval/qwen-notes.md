# Qwen-Image-Edit-2511 comparison

This is the optional local Qwen comparison for Typeset. The model is image-edit conditioned: every case starts from the same deterministic brick-wall input. Comparing it with Z-Image/Klein text-to-image outputs is qualitative, not a controlled equal-input model ranking.

## Configuration

- Workflow: `workflows/eval/qwen2511_int8_edit.api.json`
- Diffusion model: [Comfy-Org INT8 ConvRot 2511 weights](https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/blob/main/split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors), 20,499,083,824 bytes. Header inspection confirms INT8 diffusion tensors plus BF16/F32 tensors and scale metadata.
- Encoder: [Qwen 2.5 VL 7B FP8-scaled](https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/blob/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors), explicitly loaded on CPU because MPS does not support storing that FP8 dtype.
- Decoder: [Qwen Image VAE](https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/blob/main/split_files/vae/qwen_image_vae.safetensors).
- Four-step accelerator: [LightX2V 2511 Lightning LoRA](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/blob/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors).
- 768×448, seed 104, 4 steps, CFG 1.0, Euler/simple, shift 3.1, denoise 1.0.
- No changes to ComfyUI's global precision settings or model-management code.

The installed ComfyUI `supports_int8_compute()` returns false on MPS. Therefore this is an INT8 *storage* experiment with the runtime's fallback path; it must not be marketed as proven native INT8 acceleration on this Mac. A small isolated matrix test is insufficient evidence that this full model runs correctly.

## Reproduce

```bash
bash scripts/eval/download_qwen.sh
python3 scripts/eval/run_qwen_suite.py --case edit_wall
# Only after the first image succeeds:
python3 scripts/eval/run_qwen_suite.py
```

The suite runs one preserved-wall edit, then the six prompts in `scripts/eval/prompts_text.json`. It records results in `docs/eval/current-results.jsonl` under `qwen_edit_wall`, `qwen_neon`, `qwen_louder`, `qwen_stay`, `qwen_holdon`, `qwen_forever`, and `qwen_echo`. A failed case stops the suite so unsupported inference does not silently become six meaningless failures. Outputs, if produced, live in `docs/eval/current/<tag>/`.

## Results

**Local preserved-wall edit succeeded**, at 768×448, four Lightning steps and seed 104. Prompt ID: `e48a3f4a-d5b8-4d5e-896c-f5aea5672aa9`.

| Measurement | Observed |
|---|---:|
| Server execution, including loading/encoding | 267.52 seconds |
| Wall time | 268.56 seconds |
| Queue wait | 0.02 seconds |
| Sampling loop alone (launch log) | about 191 seconds |
| Output | 768×448 PNG |

The exact **NEON** lettering is readable in the produced image. Neon tubes, glow and dark electrical leads are plausible for the stylized wall fixture. The edit does **not** preserve the source wall precisely: brick scale/layout and apparent framing change noticeably. Do not claim a faithful frame edit from this single example. This synthetic flat wall also does not test people, occlusion, arbitrary camera perspectives or sustained text accuracy.

- [Generated image](current/qwen_edit_wall/qwen2511_edit_00001_.png)
- [Input/output contact sheet](contact-sheets/qwen_edit.jpg)
- [Measurement record](current-results.jsonl)
- [Submission/output log](current/qwen_edit_wall/runner.log)

All four downloads are complete (30.99 GB decimal, about 28.86 GiB total), and each safetensors file length matches its header/data offsets. The earlier attempt was interrupted when a local process session ended; no completed output was recovered from that attempt. It is not recorded as an inference incompatibility or out-of-memory failure.

**The six physical-word Qwen cases have not been run.** After the user supplied a remote RTX 4090 endpoint for heavy rendering, this local run was limited to the first feasibility case. The six-case comparison is deferred to the remote setup; the local successful wall result must not be presented as a completed three-model bake-off. No remote Qwen timing or quality claim is established here.

The evidence supports local feasibility, with roughly 4.5 minutes for this cold wall-edit case. It does not support Qwen as the default interactive image editor on this Mac. The installed runtime reports emulated INT8 operations, so the result also does not establish native INT8 acceleration. Prefer the already tested lighter models for the default local path until a controlled remote comparison is available.

Per-case `runner.log` files preserve submission IDs and streamed progress so interrupted jobs can be recovered. The helper stops after a failed case rather than creating six redundant failures; it only targets its own prompt ID if timeout cleanup is needed.
