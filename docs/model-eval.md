# Typeset model evaluation

Local measurements on the 36 GiB Apple Silicon development machine, 2026-10-30. These are small feasibility/quality experiments, not a benchmark of each model's best achievable quality. Images and video use one seed per case; broader seed/content testing is needed before generalizing.

## Current recommendation

Use LTX-Video 2B 0.9.8 distilled for short optional shots. Keep exact captions in the deterministic font renderer. The tested 768×448 NEON plate remained readable in five sampled frames; first/last-frame guidance also retained letters, but the neon-to-chrome transition finished very early. The 13B GGUF test ran successfully, at a substantially greater cost and without a clear improvement for this particular prompt. A larger model is not automatically a better default.

The production plate is still a deterministic compositor. The image-model comparison below is separate; no untested image workflow is silently substituted into the app. On the available 4090, Krea → MiniMax is now a tested optional command-line path that needs no additional weights. The full-size five-second test took about 3½ minutes across both stages; it is useful for optional generated shots, not instant caption preview.

## Video measurements

Current run records: [current-results.jsonl](eval/current-results.jsonl). Previous resolution sweep: [results.jsonl](eval/results.jsonl).

| Current experiment | Size / frames | Server execution | Wall including queue | Observation |
|---|---|---:|---:|---|
| 2B image-to-video, NEON plate | 768×448 / 49 | 48.09 s | 49.41 s | NEON legible in all five sampled frames; restrained motion |
| 2B first/last-frame morph | 768×448 / 49 | 42.74 s | 46.42 s | Legible endpoints; chrome reached by frame12, so transition timing is not controlled |
| 2B spatial upscale + second pass | 512×288 → 1024×576 / 49 | 44.16 s | 45.62 s | More defined scene detail, different geometry; generated sign is not meaningful typography |
| 13B Q4_K_M GGUF | 768×448 / 49 | 155.99 s | 204.75 s | Runnable locally; sampled scene is comparatively static, no clear win for this prompt |

The earlier 2B sweep recorded 14.40 s at 768×448×49, 50.53 s at 768×448×97, 50.64 s at 1024×576×49, and 62.69 s at 1024×576×97. Those are archival server timings with different cache/load state. Do not compare them as a controlled speedup against current runs. A separate fresh SDK tutorial run took 31.9 s at 512×320×49.

Contact sheets:

- [I2V lettering](eval/contact-sheets/i2v_letters.jpg)
- [First/last morph](eval/contact-sheets/morph_letters.jpg)
- [Spatial upscale](eval/contact-sheets/spatial_upscale.jpg) — first row refined output, second row base stage
- [13B GGUF](eval/contact-sheets/ltx13b_gguf.jpg)

A contact sheet samples motion; it cannot prove every intervening frame is correct. Full MP4s are under `docs/eval/current/<experiment>/`.

## Image rendering and editing

The experiment matrix uses the six physical-word prompts in `scripts/eval/prompts_text.json`: NEON, LOUDER, stay, HOLD ON, forever, ECHO. Klein and Z-Image generate from text at 1024×576. Klein's frame-edit case adds NEON to the fixed synthetic wall. Qwen uses its edit model and is evaluated separately because its image-conditioned task is not identical to text-to-image generation.

Both models produced readable target words in all six text-to-image samples inspected. That is six selected fixed-seed cases, not a general spelling accuracy estimate. Klein gives a convincing neon fixture and embroidery; Z-Image gives similarly readable words and a plausible carved stone treatment. Both condensation examples look more like raised/glassy lettering than text cleared with a fingertip, so spelling alone overstates prompt adherence.

| Prompt | Klein 4B execution | Z-Image Turbo execution |
|---|---:|---:|
| NEON | 70.57 s | 106.53 s |
| LOUDER | 59.41 s | 38.11 s |
| stay | 88.04 s | 30.13 s |
| HOLD ON | 69.53 s | 27.60 s |
| forever | 50.79 s | 28.20 s |
| ECHO | 23.23 s | 30.82 s |

These include loading/conditioning and different cache states. The first Z-Image case is cold; later cases are roughly 28–38 seconds. They were not simultaneous throughput tests.

**The frame-edit test exposes the more relevant failure:** Klein preserves the synthetic brick-wall composition and adds a convincing pink neon fixture, but renders **NEO**, dropping the final N from NEON (49.79 s execution). Therefore good text-to-image examples do not justify replacing the exact-font production plate with this edit graph. Keep the deterministic path and require a preview/retry step before adopting generative edits.

Qwen's local preserved-wall edit did complete: **267.52 s execution / 268.56 s wall** at 768×448 with four Lightning steps. It spells NEON correctly, but changes brick scale/layout and framing. This is a useful quality tradeoff, not a clear winner: Klein kept more of the wall but misspelled; Qwen spelled correctly but changed the wall. The six additional Qwen cases remain unrun and are deferred to the user's 4090 setup.

- [Klein six-prompt sheet](eval/contact-sheets/klein4b_t2i.jpg)
- [Z-Image six-prompt sheet](eval/contact-sheets/zimage_t2i.jpg)
- [Preserved-wall edit comparison](eval/contact-sheets/frame-edit.jpg)
- [Qwen configuration and separate execution results](eval/qwen-notes.md)


## Reproduce

The installed-model suite is sequential to avoid competing GPU allocations. ComfyUI still shares its queue with app jobs, so wall time can include waiting.

```bash
# Create input plates (writes to your local ComfyUI input directory)
~/ComfyUI/.venv/bin/python scripts/eval/make_plates.py
# Installed LTX/Klein/Z-Image cases; assumes all referenced weights exist
~/ComfyUI/.venv/bin/python -u scripts/eval/run_suite.py --group all --resume
# Rebuild labeled, unretouched contact sheets
~/ComfyUI/.venv/bin/python scripts/eval/contact_sheets.py
```

Qwen requires a separate optional ~29 GB download via `scripts/eval/download_qwen.sh`; source URLs are explicit in that script. Its initial graph is `workflows/eval/qwen2511_int8_edit.api.json`. The [official INT8 template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_edit_2511_int8.json) supplies the model/LoRA choices. Local testing uses the text encoder on CPU; successful download does not establish inference compatibility.

## Measurement caveats

- Server execution time includes model loading and graph caching behavior; queue wait is separately logged. It is not pure denoising time.
- The original RSS probe selected the first connection on 8188, sometimes a client rather than the server. Disregard RSS values in the archival sweep and the current morph/upscale/13B rows. The runner now restricts PID discovery to the listening process. RSS still does not measure total unified GPU memory.
- The older frame extractor used ffmpeg's removed `-vsync` flag and silently listed absent PNGs. It now uses `-fps_mode vfr` and checks subprocess success; missing contact-sheet frames were regenerated from the actual MP4s.
- The synthetic lettering plates are font-rendered test fixtures, not evidence of an image model's spelling ability. Only the generated-image matrix evaluates model-rendered letters.

An interrupted session left no completed Qwen result and stopped the remaining image cases. Completed case records/artifacts were retained; `--resume` skips them and runs only unfinished cases. Transport failures during service recovery are not model-quality failures.

## Tailscale GPU check

The user-provided server at `http://100.104.17.103:8188` reports an RTX 4090 with 24 GB VRAM, Linux and ComfyUI 0.34.0. Krea2 and MiniMax dependencies are installed. VideoHelperSuite loaded after the restart. The LTX checkpoint is now present but its T5 encoder is missing; Qwen's main diffusion weights are missing. With only about 3.6 GB free disk, further model downloads are deferred. A remote upload → no-model graph → download smoke test passed ([record](eval/remote-smoke.json)).

Using its existing Krea2 Turbo FP8 weights, an adapted [official template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_krea2_turbo_t2i.json) generated a 1024×576 NEON image in **14.17 s server execution / 14.81 s wall**. This uses 8 steps, CFG 1, seed 104, without the optional prompt rewriter or style LoRA. It does not use the paid Krea API node. [Image](eval/current/krea2_remote_neon/krea2_00001_.png), [run record](eval/remote-results.jsonl), graph `workflows/eval/krea2_remote_t2i.api.json`.

This establishes usable remote GPU rendering, not an apples-to-apples acceleration factor over the Mac: the model is different. The remaining Qwen matrix is paused until storage permits completing its dependencies. The current local app remains usable; no SSH access is needed to submit workflows to this host.

### MiniMax H3 with existing weights

Adapted the [official image-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_i2v.json) to the installed FP16 video VAE and VideoHelperSuite output node. The diffusion model is INT8 ConvRot, the Qwen3-VL 32B encoder is NVFP4 AWQ, and sampling uses the installed 8-step Turbo LoRA, `res_multistep`, simple scheduler, and BasicGuider. No paid API node or additional model download is used.

The first NEON image-to-video test passed at **736×416 / 56 frames / 24 fps**, taking **39.33 s execution / 39.84 s wall**. The downloaded H.264 MP4 is 2.33 seconds long with a 32 kHz stereo AAC track. NEON is readable in the first, middle, and final sampled frames; the scene remains close to the input with subtle motion. Audio presence was verified by probing the file, not by judging its sound. This short duration is below the node's documented trained range of roughly 124–362 frames, so treat it as a compatibility test.

- [Short video](eval/current/minimax_remote_neon_736x416_56/typeset_minimax_00001-audio.mp4)
- [Sampled frames](eval/current/minimax_remote_neon_736x416_56/frames.jpg)
- Graph: `workflows/eval/minimax_remote_i2v.api.json`; measurements: [remote-results.jsonl](eval/remote-results.jsonl)

Run `server/.venv/bin/python scripts/render_available.py --video-model minimax` for Krea → MiniMax entirely on the GPU host. The default remains Krea remotely → LTX locally. Both modes retain exact submitted graphs, job IDs, history, and downloaded media under `outputs/available-models/<run>/`.

The complete helper was then tested with `--video-model minimax --full-size`: a fresh Krea image followed by **1344×768 / 124 frames / 24 fps** MiniMax video. Krea took **17.47 s execution / 18.2 s including download**; MiniMax took **190.24 s execution / 190.8 s including download**. The result has 5.17 seconds of H.264 video and a stereo AAC track. NEON remains readable in the first, middle, and final sampled frames, with a visible slow push in. No audio-quality judgment or frame-by-frame spelling guarantee is implied. The input prompt/image differs from the earlier short probe, so these are separate feasibility cases rather than a controlled quality comparison.

- [Full-size video](eval/current/minimax_remote_neon_1344x768_124/typeset_minimax_00002-audio.mp4)
- [Full-size sampled frames](eval/current/minimax_remote_neon_1344x768_124/frames.jpg)
- [Exact submitted graph](eval/current/minimax_remote_neon_1344x768_124/workflow.json), [server history](eval/current/minimax_remote_neon_1344x768_124/history.json)
- Imported local project: **Typeset — GPU neon demo**, available in Media → Projects. [Project record](eval/gpu-demo-project.json).
