# ComfyUI + LTX: a 35–40 minute local tutorial

You already have ComfyUI installed. **You do not need credits, an account, or a second installation for the exercises below.** Use the browser UI to learn the graph; the same graph can run from Python without the UI. Local generation uses your computer's memory, electricity, and time. Paid partner/API nodes are a separate execution path.

Verified on this machine on 2026-10-30: `~/ComfyUI`, Python environment `~/ComfyUI/.venv`, ComfyUI 0.43.0, PyTorch 2.15.0, MPS device, 36 GiB unified RAM. Both `http://127.0.0.1:8188/system_stats` and the proxy's `http://127.0.0.1:8189/api/v2/health` responded successfully. This is a snapshot; use the status checks below next time.

The project is now **Typeset**, an early working lyric/kinetic-typography editor. Its React editor and FastAPI service run separately from ComfyUI; see the root README for launch commands. The exercises below work independently of the app.

## 0–5 minutes: understand the pieces and open the UI

From this repository:

```bash
cd ~/dev/comfy
bash scripts/comfy.sh status
# If down:
bash scripts/comfy.sh start
```

Open **http://127.0.0.1:8188** in your browser. This browser page talks to a server running on your Mac. It is not Comfy Cloud. The proxy on port 8189 is for the SDK, not the node editor.

If the helper fails, start ComfyUI directly in a terminal and leave that terminal open:

```bash
cd ~/ComfyUI
PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python main.py --listen 127.0.0.1 --port 8188
```

Only do that if port 8188 is not already serving ComfyUI. For SDK exercises, start the local proxy separately if needed:

```bash
~/ComfyUI/.venv/bin/comfy-api-proxy start --comfyui http://127.0.0.1:8188 --port 8189 --comfyui-base-dir ~/ComfyUI
curl -f http://127.0.0.1:8189/api/v2/health
```

Three concepts explain most of ComfyUI:

- **Node:** one operation, such as load weights, encode text, sample frames, or save a video. Wires carry typed data between operations.
- **Workflow:** the recipe linking those operations. A model is one ingredient in a workflow, not the workflow itself.
- **Queue:** the jobs you ask the server to execute. Unchanged intermediate results can be cached. A near-instant repeat may be a cache hit, not a fast generation.

Files live under `~/ComfyUI/models/` (weights), `~/ComfyUI/input/` (uploaded inputs), and `~/ComfyUI/output/` (results).

## 5–10 minutes: one image, no model required

1. Drag `docs/workflows/smoke_test_api.json` from Finder onto the canvas. The current frontend can import this API graph; it may arrange nodes automatically.
2. Find **LoadImage → ImageScale → SaveImage**. `example.png` is already in this installation's input folder. You can also use LoadImage's upload control for your own picture.
3. Click **Run** / **Queue Prompt**. Find the saved image in `~/ComfyUI/output/smoke/`.
4. Change ImageScale width and height from 256 to 384 and run again. Notice that only the affected branch needs work.
5. Search Settings for **Dev mode**, enable it if required, and use the workflow menu's **Export (API)** option.

Normal UI JSON stores the canvas layout, links, and widgets. API JSON stores node IDs, `class_type`, and `inputs`. The API format is what scripts submit. If importing an API graph is unavailable in a different frontend version, use the SDK command in the final exercise; the graph itself needs no conversion for that route.

**Checkpoint:** you can change a parameter, execute a workflow, and find its output.

## 10–22 minutes: generate a short LTX video

**LTX is Lightricks' video-model family.** This tutorial uses **LTX-Video 2B 0.9.8 distilled**, an older, smaller video model. “2B” is its approximate parameter count. “Distilled” means it was trained for a shorter sampling process. LTX-2 is a newer family with joint audio/video generation; it is not another name for the installed 2B checkpoint. The official [LTX-Video model card](https://huggingface.co/Lightricks/LTX-Video) lists the 2B distilled variant, and the [LTX-2 repository](https://github.com/Lightricks/LTX-2) describes the newer family.

Already present here:

| File | Location | Size on disk |
|---|---|---|
| `ltxv-2b-0.9.8-distilled.safetensors` | `~/ComfyUI/models/checkpoints/` | about 5.9 GiB |
| `t5xxl_fp16.safetensors` | `~/ComfyUI/models/text_encoders/` | about 9.1 GiB |

No download is needed for this exercise. Weight size alone does not measure peak memory: activations, decoded frames, and macOS also consume unified memory. Newer large LTX workflows need separate compatibility and memory testing; do not swap their checkpoint into this graph.

1. Import `docs/workflows/ltx_t2v_api.json`.
2. Confirm the two filenames above are selected in **CheckpointLoaderSimple** and **CLIPLoader**.
3. Keep **512×320**, **49 frames**, **24 fps**, **8 steps**, **CFG 1.0**. That yields about two seconds of video.
4. Replace the positive prompt with a simple visible action, for example: “A red paper boat floats across a shallow puddle. Small ripples spread around it. The camera slowly moves closer in soft afternoon light.”
5. Queue once and watch the output node. The MP4 is written under `~/ComfyUI/output/ltx/`; filenames increment, so do not assume `_00001` is your result.
6. Change the sampler's `noise_seed` and queue once more. Compare motion and composition.

Read this graph as:

| Operation | Node(s) |
|---|---|
| Load video model and VAE | `CheckpointLoaderSimple` |
| Turn the description into conditioning | `CLIPLoader` → `CLIPTextEncode` |
| Choose dimensions and duration | `EmptyLTXVLatentVideo` |
| Set generation frame rate | `LTXVConditioning` |
| Set the denoising schedule | `ModelSamplingLTXV`, `LTXVScheduler` |
| Generate the video latent | `KSamplerSelect`, `SamplerCustom` |
| Decode and write frames | `VAEDecode`, `VHS_VideoCombine` |

For this graph, use dimensions divisible by 32 and frame counts `8k+1` (25, 49, 97). Keep the conditioning fps and output fps equal. At CFG 1, changing the negative prompt will not provide the usual classifier-free-guidance effect; spend your time on the positive prompt, input image, and seed.

The existing graph is a lightweight single-stage learning example. It is not the official multi-scale quality pipeline: the upstream [2B distilled configuration](https://raw.githubusercontent.com/Lightricks/LTX-Video/main/configs/ltxv-2b-0.9.8-distilled.yaml) uses an upscaler and separate sampling passes. Judge this exercise as a local feasibility demo, not the model's quality ceiling.

**Timing evidence:** a fresh SDK → proxy → ComfyUI run during this handoff completed in **31.9 seconds**, saving `outputs/verification/t2v_00006.mp4`; the model-free SDK smoke test completed in 1.0 second. Prior results in [eval/results.jsonl](eval/results.jsonl) record 18.49 seconds cold and 4.59 seconds warm for 512×320×49, and 51.87 seconds for 768×448×97. These are previous recorded runs, not a new benchmark or a universal speed promise. Memory pressure and loading can substantially change timings; larger runs in the log took roughly a minute. Do not benchmark by resubmitting an identical cached graph.

**Checkpoint:** you have generated a local MP4 and can explain prompt, seed, dimensions, and frame count.

## 22–30 minutes: animate your own image

1. Import `workflows/eval/ltx_i2v.api.json`.
2. In **LoadImage**, upload a photograph or an image with one large word. The synthetic `eval/neon_768x448.png` reference is now installed on this machine; use it or upload your own image.
3. In **LTXVImgToVideo**, reduce width/height to **512×320**, retain 49 frames, batch 1, and strength 1.0.
4. Keep the installed checkpoint and encoder, 8 steps, and CFG 1. Replace the positive prompt to describe your image and a small motion: a gentle push-in, drifting smoke, or changing light.
5. Queue. Look under `~/ComfyUI/output/eval/` for the I2V result.
6. If your still contains text, pause the output at the beginning, middle, and end. Inspect spelling, glyph shape, and placement. Does it remain readable?

The new branch is **LoadImage → LTXVPreprocess → LTXVImgToVideo**. It supplies image conditioning instead of starting with a completely empty video latent. The preprocessor simulates compression characteristics; the image-to-video node prepares the first-frame conditioning and latent.

This is the important Typeset experiment: a model may animate a convincing scene while warping the letters. For exact captions, keep text as a deterministic rendered layer and use masks/tracks to place it in the scene. Treat generative typography as a short optional shot whose legibility must be checked.

If generation takes longer than the timebox, finish the next section with the model-free smoke graph. The learning target is the workflow; extra renders can wait.

## 30–37 minutes: run without the node editor

The SDK route is **Python → local proxy :8189 → ComfyUI :8188**. Close the browser tab if you like; keep the server running.

```bash
cd ~/dev/comfy
export COMFY_BASE_URL=http://127.0.0.1:8189
~/ComfyUI/.venv/bin/python scripts/run_local_workflow.py docs/workflows/smoke_test_api.json 3 --out outputs/tutorial

~/ComfyUI/.venv/bin/python scripts/run_local_workflow.py docs/workflows/ltx_t2v_api.json 12 \
  --prompt-node 3 --prompt "A red paper boat floats across a puddle, ripples spreading, slow camera push in, afternoon light" \
  --seed-node 10 --seed 104 --out outputs/tutorial
```

Here `3` and `12` are output node IDs, not counts. For the video graph, node `3` is the positive prompt and node `10` owns the noise seed. The downloaded result goes to `outputs/tutorial/`; the original remains under ComfyUI's output directory.

Open `scripts/run_local_workflow.py`. Follow these steps in the code: load JSON → override inputs → submit → poll status → download outputs. It includes a grace period for a previously observed local-proxy `expired` race. The explicit loopback base URL is what keeps this exercise on your machine; hosted services are separate targets with their own costs and requirements.

For native ComfyUI API exploration, visit `http://127.0.0.1:8188/object_info` (node schemas) and `http://127.0.0.1:8188/history` (completed jobs). Submission uses `POST /prompt` with `{"prompt": <API graph>}`. This is a different API from the proxy's API v2.

**Checkpoint:** you can generate from code and understand how a future Typeset UI could hide the graph.

## 37–40 minutes: open weights and your next step

**Yes, you can run open-weight models: that is what you just did.** The checkpoint is on your disk and inference happens locally. Open weights does not mean all model licenses are Apache/MIT, or that training data and training code are all available.

For this exact 0.9.8 checkpoint, the model card links the **LTXV Open Weights License 0.X**. It includes usage and redistribution conditions and a separate commercial-license requirement for entities meeting its revenue threshold. The code repository's Apache license should not be substituted for the weights license. See the [checkpoint license](https://huggingface.co/Lightricks/LTX-Video/blob/main/LTX-Video-Open-Weights-License-0.X.txt). Other LTX generations have their own terms.

For an open-weights competition category, using this local model is technically compatible with that direction, but the entire submitted workflow and the current competition rules determine eligibility. Avoid adding hosted closed-model/API nodes to a workflow you intend to present as entirely open weights. A rented GPU running downloadable weights remains open-weight inference, but costs rental money.

For Typeset, the next useful milestone is one short clip with readable words, a foreground mask, and an exported overlay. The custom node source lives in `custom_nodes_dev/typeset_nodes/`; it is symlinked into ComfyUI. Registration can lag behind source edits until a restart. `TextToMask` and the other Typeset nodes were registered after the build restart. The tutorial remains independent of these custom nodes; see `docs/comfy-integration.md` for their tests and `docs/server.md` for the working export path.

## If something fails

- **Can't connect:** check `bash scripts/comfy.sh status`, then `/tmp/comfyui.log`. A sandboxed agent's failed localhost request does not prove the service is down; the browser or an approved host request can distinguish that.
- **Missing image:** use the LoadImage upload control. `example.png` and the synthetic eval neon plate are installed on this development machine.
- **Missing model:** check the exact filename and directory listed above, then refresh the model choices. Do not replace it with an unrelated LTX-2 checkpoint.
- **Missing node:** check the launch log for import errors. `VHS_VideoCombine` was verified available; new Typeset nodes may require restarting the owning ComfyUI process after the queue is idle.
- **Memory pressure:** close heavy applications; reduce frames to 25 and keep 512×320, batch 1. Unified memory is shared with the whole Mac.
- **Unsupported MPS operation:** the direct launch command enables PyTorch's CPU fallback where supported. This can be much slower and does not fix every failure.
- **Black/noisy results:** inspect logs and verify the matching checkpoint, sampling settings, and decoder. Do not assume a completed job means a visually valid result.
