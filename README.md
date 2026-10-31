# Typeset

A local lyric and kinetic typography editor built on ComfyUI. Correct word timings, animate text, place it behind a subject or follow a mask-derived anchor, and export a finished video plus transparent text overlays. Optional LTX shots animate a lettering plate.

**Early working prototype.** This repository previously explored a beat-synced editor named Recut. Typeset is the current project. Code is [MIT](LICENSE); bundled fonts retain their OFL licenses, and model weights have their own terms.

## Open the showcase and editor

On this development machine, the **showcase is http://127.0.0.1:5174** and the **editor is http://127.0.0.1:5174/#/studio**. The API is **http://127.0.0.1:8787**. Another application owns port 5173. ComfyUI's separate node editor is **http://127.0.0.1:8188**.

The showcase is the hackathon entry point: three playable outputs, starting-image/source-footage comparisons, a transparent text preview, six image studies, downloads, and links into the live editor. **Presentation mode** expands the player; use **← / →** to switch scenes and **Esc** to leave. The page includes a 90-second walkthrough near the bottom. All preview media is bundled locally and labeled as recorded output; viewing it does not submit a generation job.

The showcase and sample editor also run without the API or GPU. To serve the production build for a presentation:

```bash
cd apps/web
npm run build
npm run preview -- --host 127.0.0.1 --port 5180
```

Open the URL printed by Vite. Saved clips and sample editing work in this mode; project uploads, analysis, generation, and export require the API. With the API available, “Open this clip in studio” opens the corresponding saved project; otherwise the showcase links to the offline sample. The current live setup remains on 5174.

To start a new session from this checkout:

```bash
scripts/comfy.sh start
scripts/dev.sh
```

`dev.sh` starts the API on 8787 and finds a free web port from 5173 through 5180; it prints the selected URL. Ctrl-C stops its children. It does not stop existing services or launch duplicate API instances. The helper assumes the dependencies below are installed, as they are on this machine.

1. Click **Open studio** and explore the **offline sample**: play/scrub, select a word, change its motion, placement, timing, and style. Sample edits save in your browser.
2. In **Media**, create a project and upload footage or audio. Add optional lyrics/script, then **Transcribe audio**.
3. For behind-subject or anchored text, use **Isolate subject**. These features need a foreground matte/track.
4. Correct the words and timing. Position and anchor controls apply to the selected line; style/preset controls edit the selected word.
5. **Export** a finished MP4, ProRes 4444 text overlay, and VP9-alpha text overlay. Download links appear when the job completes. Use Chrome/Chromium for alpha preview.

An exportable **Typeset — typography demo** project is also installed in this workspace (Media → Projects). To create another from the bundled sample, run `server/.venv/bin/python scripts/import_sample.py` while the API is running.

Generation is local, with no Comfy Cloud credits for the supplied workflows. Paid API/partner nodes are separate and are not part of this pipeline.

## What works and what is experimental

| Component | Current behavior |
|---|---|
| Editor | Timeline, waveform, playback/frame stepping, editable words/timings/styles, pop/karaoke/typewriter/HUD presets, offline sample, project save/upload and job feedback |
| Rendering | Deterministic closed-form motion; background → behind text → subject → front text; frame-addressed browser renderer used by export |
| Analysis | faster-whisper timestamps, optional heuristic lyric matching, BiRefNet foreground cutouts, largest-mask-component anchors |
| Export | Chromium frame capture → ffmpeg H.264 MP4, ProRes 4444 MOV, VP9-alpha WebM; per-job output directories |
| LTX | Plate-to-video generation; a separate first/last-frame morph workflow is available in ComfyUI |
| Lettering plate | **Deterministic neon/chrome font compositor**, not yet a generative scene-editing model in the production path |
| Model experiments | LTX 2B resolutions/upscaler, 13B GGUF, lettering I2V/morph, image-model rendering/editing comparisons; see evaluation notes |

Mask anchors are not face recognition, identity tracking, or perspective/surface tracking. Lyric matching is not acoustic forced alignment. Review singing and multi-person footage carefully. Generated letters can drift; exact captions use rendered fonts. A transparent text-only export is unoccluded: reproducing behind-subject placement in another editor also requires the foreground layer.

## Dependencies and setup

The current installation uses Python 3.12, Node/npm (pnpm lockfile included), ffmpeg/ffprobe, and Chromium from Playwright. ComfyUI and models live **outside this repository**, at `~/ComfyUI`; cloning this repository does not install them.

For app dependencies on a new checkout:

```bash
python3.12 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
server/.venv/bin/python -m playwright install chromium
cd apps/web
npm install
npm run build
```

Install ComfyUI separately, its `comfy-sdk`/`comfy-api-proxy`, required model files, and the custom node dependencies. Follow [Comfy integration setup](docs/comfy-integration.md) rather than installing every experiment model. ffmpeg defaults to `/opt/homebrew/bin/ffmpeg`; configure `FFMPEG` and `FFPROBE` on other systems. See [server settings](docs/server.md).

For separate terminals (use the same web port in each):

```bash
# API
TYPESET_WEB_URL=http://127.0.0.1:5174 \
TYPESET_CORS_ORIGINS=http://127.0.0.1:5174,http://localhost:5174 \
server/.venv/bin/python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8787

# Web, from apps/web
npm run dev -- --host 127.0.0.1 --port 5174
```

## Remote GPU setup

The Tailscale server at `100.104.17.103:8188` has an RTX 4090 with 24 GB VRAM, but only about 3.6 GB free disk space. Its Krea2 pipeline is verified. Keep LTX video generation on the Mac, where the complete model and encoder are already installed. A standalone no-download helper connects Krea image generation on the GPU host to LTX animation on the Mac:

```bash
server/.venv/bin/python scripts/render_available.py
# Or reuse one of the existing plates:
server/.venv/bin/python scripts/render_available.py \
  --plate docs/eval/current/krea2_remote_neon/krea2_00001_.png
```

Results and exact submitted graphs go to `outputs/available-models/<run>/`. This helper is separate from the editor's current deterministic lettering-plate default. Qwen also runs on the Mac; the six-case remote Qwen comparison is deferred.

MiniMax H3 also passed a short remote test: 736×416, 56 frames, 39.33 seconds of execution, with a stereo AAC track. The target word remained readable in sampled frames. To generate both the image and video on the GPU host, use `server/.venv/bin/python scripts/render_available.py --video-model minimax`. The Mac only submits jobs and downloads outputs in this mode. [Remote connection details](docs/remote-comfy.md) and [model evaluation](docs/model-eval.md) cover the setup and limitations.

The complete remote Krea → MiniMax command also passed at **1344×768 / 124 frames (5.17 seconds)**: roughly 18 seconds for the image and 191 seconds for video, including transfer. Run `server/.venv/bin/python scripts/render_available.py --video-model minimax --full-size` for that size. The result is available in **Media → Projects → Typeset — GPU neon demo**, or at `docs/eval/current/minimax_remote_neon_1344x768_124/typeset_minimax_00002-audio.mp4`. Sampled lettering remained readable; these two clips do not establish general text accuracy.

Verified with the previously generated remote Krea NEON plate: local LTX completed in 34.98 seconds and produced a 49-frame, 512×320 H.264 video. The word remained readable in the first, middle, and final sampled frames. Local result: `outputs/available-models/9512602474fd/video/ltx_i2v_00003.mp4`; sampled frames: `outputs/available-models/9512602474fd/frames.jpg`. These are a short smoke test, not a quality benchmark.

Remote SDK transport is ready when space permits completing remote LTX: [enable and rollback commands](docs/server.md#remote-comfyui). The [GPU install manifest](docs/gpu-host-install.md) is now marked deferred, not a prerequisite for using the project.

## Learn ComfyUI or run a graph directly

The [35–40 minute tutorial](docs/comfy-ltx-crash-course.md) covers nodes, local LTX video, image-to-video and the SDK. The browser is optional for API jobs:

```bash
export COMFY_BASE_URL=http://127.0.0.1:8189
~/ComfyUI/.venv/bin/python scripts/run_local_workflow.py \
  docs/workflows/smoke_test_api.json 3
~/ComfyUI/.venv/bin/python scripts/run_local_workflow.py \
  docs/workflows/ltx_t2v_api.json 12 --seed-node 10 --seed -1
```

The second graph uses LTX-Video 2B 0.9.8 distilled for 49 frames at 512×320. The original outputs remain in ComfyUI; downloaded copies go to `outputs/`. Keep `COMFY_BASE_URL` pointed to loopback for local execution.

## Repository map

| Path | Contents |
|---|---|
| `apps/web/` | React/Vite editor, Canvas renderer, sample and fonts |
| `server/` | FastAPI service, project storage, jobs and exporter |
| `custom_nodes_dev/typeset_nodes/` | Typeset ComfyUI node pack |
| `workflows/` | Production API graphs and input/output sidecars |
| `workflows/eval/`, `scripts/eval/` | Reproducible model experiments and download helpers |
| `docs/model-eval.md`, `docs/eval/` | Measurements, contact sheets and sample outputs |
| `docs/ARCHITECTURE.md`, `docs/SCHEMA.md` | Implementation structure and shared contracts |
| `research/verified-assessment.md` | Prior art and realistic product differentiation |
| `data/`, `outputs/` | Local projects/results, excluded from git |

The product hypothesis is easier correction, placement, and useful exports. Kinetic captions and text behind subjects already exist; Typeset does not claim to invent those effects. See the verified assessment for sources and competition context.
