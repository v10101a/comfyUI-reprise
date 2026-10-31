# Typeset — Codex takeover handoff

Written 2026-10-30 for the user to resume with Claude. Workspace: `/Users/lh1783/dev/comfy`.

## Read this first: latest user direction

The user wants a web UI to preview the work, with an eventual hackathon presentation in mind. After seeing the current example, they said: **“I find this current example video quite lame.”** They asked for this handoff. The next priority is a compelling creative example and product story. The existing neon sign and synthetic mannequin are technical test fixtures, not an approved creative direction or a finished hackathon demo.

I concentrated on making the pipeline work, measuring actual outputs, and exposing them in a usable UI. That establishes feasibility; it does not establish that the result is interesting. The showcase is newly built and technically tested, but the user has not approved its design or its example content.

## My understanding and assumptions

- I interpreted the project as a local, editable motion-typography tool: correct word timing, animate text, put it behind a subject or follow a mask-derived anchor, and export useful video/layers. ComfyUI handles transcription, segmentation and optional generated shots.
- I treated physical/generative lettering as a second experimental path alongside exact font-rendered captions. This was my conservative implementation choice, not a final creative brief from the user. Revisit whether it matches the experience they actually want to demonstrate.
- The working name **Typeset**, MIT code license, OFL fonts, web/server split and basic four-worker architecture came from the preceding Claude plan. I continued that architecture and repaired the incorrect root README, which still described Recut.
- Local/downloadable weights and avoiding cloud credits mattered. The user explicitly offered a stronger remote GPU over Tailscale. That did not require all models to move onto that machine.
- For presentation reliability, the new showcase plays real saved outputs. It does not secretly start generation or pretend a recorded result was generated instantly. The live editor is separate and functional.

## What was completed or finished during the takeover

### Editor and rendering

`apps/web/` contains the React/Vite/TypeScript editor: transcript, waveform, word timeline, playback/frame stepping, word/style/timing controls, pop/karaoke/typewriter/HUD presets, and overlay/behind/anchor/inworld placements. Closed-form spring motion is deterministic under random seeking.

The compositing order is background → behind text → foreground cutout → front text. The `#/render` route exposes `window.__typeset.ready`, `frames`, and `renderFrame` for export. The bundled 12-second sample uses synthetic visuals/audio. A persisted exportable typography demo also exists.

Fixed a real Media-panel crash when the API returns `audio: null` or `video: null`. Updated frontend media types to admit null and added a browser regression case.

### Server, workflows and export

`server/` provides FastAPI project CRUD, uploads, jobs, analysis, generation and export. The Comfy SDK runner uses workflow sidecars, handles transient proxy expiry with polling/grace, stages inputs and collects outputs. Project paths and timings are validated; project writes are locked during an export capture.

Production workflows/node work includes `words`, `matte`, `text_plate`, `ltx_i2v`, and a separate `ltx_morph` graph. Whisper timings run with optional heuristic lyric matching. BiRefNet supplies cutouts and mask-derived tracks. The current production text plate is a **deterministic neon/chrome font compositor**, not an image-model scene editor.

Chromium → frame PNGs → ffmpeg export works for finished H.264 MP4, ProRes 4444 and VP9-alpha text overlays. Fixed transparent HTML/body backgrounds, a mocked Vite websocket reload loop, and unbounded renderer waits. A complete 12-second/288-frame demo export passed, including actual alpha checks. Combined transparent text is unoccluded; reproducing behind-subject placement in another editor also needs the foreground layer.

### Model experiments: actual results, not inferred from filenames

- Local LTX-Video **2B 0.9.8 distilled**, not LTX-2: tested resolutions, I2V lettering, first/last-frame morph and spatial upscaling. A 768×448/49-frame I2V run took ~48 seconds. Morphing reached its end material too early.
- Local LTX 13B GGUF ran (~156 seconds execution for the measured case), without a clear quality improvement for that particular scene.
- Six physical-word prompts each for FLUX.2 Klein 4B and Z-Image Turbo produced readable words in the inspected samples. This is not a general accuracy benchmark. Klein's wall edit dropped the last N from NEON; Qwen's edit spelled NEON but changed wall geometry.
- Local Qwen-Image-Edit 2511 completed one wall-edit case in ~268 seconds. The other six planned Qwen cases remain unrun; remote storage prevented moving that evaluation to the GPU host.
- Evaluation records, prompts, exact graphs, output images/videos and contact sheets are retained. See `docs/model-eval.md`, `docs/eval/current/`, `docs/eval/contact-sheets/`, and `docs/eval/*results.jsonl`.

### Remote GPU and the disk-space pivot

Remote ComfyUI: **http://100.104.17.103:8188**, host seraph-01, RTX 4090/24 GB, Linux, reported ComfyUI 0.34.0. The user has another Claude session on that machine. We use its HTTP API; no SSH credentials are needed for rendering.

The user reported **~3.6 GB disk free**. The remote LTX checkpoint exists but its T5 encoder is missing. Qwen's encoder/VAE/Lightning LoRA are installed but its main diffusion model is missing. Additional downloads were explicitly deferred. Do not blindly resume the old install manifest.

The existing **Krea2 and MiniMax H3 installations both actually run**. VideoHelperSuite loaded after the user restarted remote ComfyUI. Native local-weight nodes are used, not paid partner API nodes.

1. Verified remote Krea2 image generation (~14 seconds in the initial run).
2. Built `scripts/render_available.py`: Krea remotely → LTX on the Mac, with direct image transfer and downloaded outputs. That combination passed with existing weights.
3. Added `--video-model minimax`: both image and video stages run remotely. The Mac submits jobs and receives results.
4. MiniMax short test: **736×416, 56 frames, 2.33 seconds**, ~39 seconds execution, stereo AAC audio present.
5. Complete Krea → MiniMax full test: **1344×768, 124 frames, 5.17 seconds**. Krea ~18 seconds including download, MiniMax ~191 seconds including download, roughly 3½ minutes total. NEON readable in sampled first/middle/last frames. Audio presence verified; sound quality not evaluated.

Commands from the repo root:

```bash
# Quick remote Krea → MiniMax preview
server/.venv/bin/python scripts/render_available.py --video-model minimax

# The verified full-size run
server/.venv/bin/python scripts/render_available.py --video-model minimax --full-size

# Reuse an image; skip Krea
server/.venv/bin/python scripts/render_available.py --video-model minimax --plate /path/to/image.png

# Default: remote Krea → local LTX
server/.venv/bin/python scripts/render_available.py
```

`--image-prompt`, `--motion-prompt` and `--seed` are available. The defaults describe NEON, so change both prompts for another concept. Runs save media, exact graphs, job IDs and history under `outputs/available-models/<run>/`. A timeout does not cancel the remote job; check the queue before resubmitting.

**Integration boundary:** the editor's Generate button still uses the deterministic plate → LTX path. Krea/MiniMax generation is currently a CLI helper, not a generation form in the web app. Optional remote LTX SDK transport is implemented, but the remote T5 dependency is missing, so it is not the active route. Analysis/export remain local.

### New showcase UI, built immediately before this handoff

- `apps/web/src/Showcase.tsx` and `showcase.css`: a cream/charcoal/lime front page with playable neon, typography and morph clips; starting-image/source-footage views; transparent overlay preview; image-study lightboxes; downloads; and a 90-second presentation guide.
- Presentation mode expands the player. Left/right switch scenes; Escape exits, including when the seek slider has focus.
- `apps/web/public/showcase/` bundles ~10.7 MiB of actual existing outputs and posters. This avoids relying on a GPU or API connection to play the examples. A manifest README records provenance.
- Root URL now opens the showcase. `#/studio` opens the editor. `#/studio?project=<id>` opens a specific persisted project. `#/render` remains the export route.
- The showcase resolves matching saved projects when the API is available; otherwise editor links use the offline sample. Returning via the editor's brand saves dirty edits first.
- Tested desktop and 390px mobile layout, playback, seek, comparison views, alpha video loading, presentation keys, image lightbox, editor deep links, and API-unavailable fallback.

## Where to open things

- **Showcase:** http://127.0.0.1:5174
- **Editor:** http://127.0.0.1:5174/#/studio
- **API:** http://127.0.0.1:8787
- **Local ComfyUI:** http://127.0.0.1:8188; local SDK proxy: 8189
- Remote optional SDK proxy uses 8190, separately from the local proxy. See `docs/server.md` before changing settings.

Port 5173 belongs to another app. `scripts/dev.sh` selects a free web port when starting a fresh session and exits if API port 8787 is already occupied; check existing services before launching duplicates. Models and local ComfyUI live at `~/ComfyUI`, outside this repo.

Saved projects:

- **Typeset — typography demo:** `54414535-19a7-4ae2-9c76-03e16a5a96e9`
- **Typeset — GPU neon demo:** `b76ba642-6dd5-4353-aae3-d265ccbcd12f`

Useful outputs:

- Full remote clip: `docs/eval/current/minimax_remote_neon_1344x768_124/typeset_minimax_00002-audio.mp4`
- Full run record: `outputs/available-models/1f8b72d6ac89/result.json`
- Typography MP4/alpha exports: `data/projects/54414535-19a7-4ae2-9c76-03e16a5a96e9/export/96157e57-f3a2-4977-b9a6-6e5f89af7705/`
- Latest UI screenshots: `outputs/showcase-check/`; editor screenshot: `docs/eval/gpu-demo-editor.png`

## Validation and cautions for the next agent

Latest frontend checks: `npm run build`, `apps/web/scripts/check_browser.py`, and `apps/web/scripts/check_showcase.py`. The editor tests cover deterministic seeking, real transparent pixels, composite output, track gaps, and null media. Earlier takeover checks also covered server offline tests, custom-node behavior, actual workflow SDK runs, and the full export. Do not describe those as all rerun in this last UI pass.

`git status` currently shows the project files/directories as **untracked**. There is no clean commit-by-commit handoff or PR. Preserve the workspace; do not use `git clean` to tidy it.

Some older research prose, especially the “checkout actually supports” section in `research/verified-assessment.md`, describes the earlier scaffold state. Its ecosystem findings are useful; that implementation snapshot is stale. Any competition dates/rules need rechecking before relying on them. Current code, this handoff, and recent test records are better evidence of implementation status.

Known limitations: heuristic lyric alignment, largest-mask anchors rather than identity/face/planar tracking, small model-evaluation samples, generative spelling drift, and incomplete UI integration of remote generation. No model downloads were performed for the newest remote path or showcase. Do not assume any historical worker agents are still running.

## Recommended next move — a proposal, not a settled user brief

Ask for or develop a specific visual concept that the user finds exciting before spending time on more benchmark clips. Make one strong 8–15 second example with purposeful typography, real subject movement, visible interaction between words and scene, and a clear before/after. Use the existing editable/render/export infrastructure; make the hackathon story about what the user can create or control. If the user primarily wants generative physical text, promote that path deliberately and add actual UI job controls rather than representing the existing caption compositor as that product.

Replace the weak showcase assets once the creative example is approved. The current static neon push-in and synthetic mannequin should not be mistaken for the creative ceiling, or for content the user asked to keep.
