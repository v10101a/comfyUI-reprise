# Typeset local API and exporter

Run from the repository root:

```bash
server/.venv/bin/uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8787
```

The existing environment contains the dependencies in `server/requirements.txt`. For another machine, create a Python 3.12 environment, install that file, and run `python -m playwright install chromium`. Install ffmpeg/ffprobe separately and override their paths if Homebrew is not under `/opt/homebrew`.

The API implements the routes in `SCHEMA.md`. Interactive endpoint documentation is at `http://127.0.0.1:8787/docs`. The editor normally runs at `http://localhost:5173`; on this machine an unrelated app owns that port, so the active Typeset editor uses `http://127.0.0.1:5174`. Set `TYPESET_WEB_URL` and add the selected origin to `TYPESET_CORS_ORIGINS` when starting the API. if `apps/web/dist` exists at API startup, the server also serves that built app at `/`.

## What happens during a job

- Words with lyrics: extract 44.1 kHz stereo, run `align.inputs.json` (TypesetAlignLyrics forced alignment; `timing.vocalStart` bounds the intro), copy its preview to `analysis/words_align.png`; result `engine: "align"`. On failure (or `TYPESET_WORDS_ALIGNER=0`, or no lyrics) fall back to Whisper below, `engine: "whisper"`.
- Words (Whisper): extract 16 kHz mono WAV, stage it under local ComfyUI input, run `words.inputs.json` through the Comfy SDK/proxy, read the saved JSON, seed editable words clipped to project duration. The raw analysis retains the full transcription if separate audio is longer than the footage.
- Matte: normalize footage to project dimensions/fps, run the matte sidecar, copy RGBA frames into a job-specific analysis directory, encode VP9 alpha for Chrome, and save normalized tracks.
- In-world: extract a 512×320 starting frame, run the text-plate workflow, run LTX I2V, then attach the result to selected words. The text-plate workflow currently determines whether lettering is deterministic or generative; the API does not assume its implementation. Clips are limited to ten seconds. Failure marks the shot failed and preserves its intermediate artifacts.
- Export: drive the renderer at `#/render`, wait for fonts/media, capture deterministic canvas frames, then encode files with ffmpeg. MP4 follows the requested `layer`: `composite` preserves behind/front placement and generated shots; `text` is text on black because H.264 has no alpha. MOV and WebM always contain the transparent text layer.

A single Comfy worker lane serializes model jobs; a separate export worker captures frames. Jobs persist under `data/jobs/` and report progress and useful failures via `GET /api/jobs/{id}`. Restarted in-progress jobs become failed rather than remaining stuck. There is no cancellation or resume endpoint yet.

Exports are written under `data/projects/<id>/export/<job-id>/`, with `final.mp4`, `text_overlay.mov`, and `text_overlay.webm`. Result JSON includes `files` (relative project paths) and `urls` (download paths). PNG frames remain beside deliverables for inspection. Alpha overlays contain all non-inworld words; compositing an overlay elsewhere requires the foreground matte for behind-subject occlusion.

The exporter keeps a mocked WebSocket open without forwarding messages, preventing Vite hot reload from replacing the renderer mid-capture. Closing that socket would trigger Vite reconnect/reload behavior. Renderer readiness and each frame promise also have explicit bounded timeouts; Playwright evaluate does not inherit the normal operation timeout for unresolved JavaScript promises. It holds a project write lock while capturing. GET remains available; edits and analysis-result updates wait until capture/encoding finishes. This prevents live edits changing frames mid-export. Avoid starting long exports while editing that project.

## Configuration

| Variable | Default |
|---|---|
| `TYPESET_DATA_DIR` | repository `data/` |
| `TYPESET_WORKFLOWS_DIR` | repository `workflows/` |
| `TYPESET_COMFY_DIR` | `~/ComfyUI` |
| `COMFY_BASE_URL` | `http://127.0.0.1:8189` |
| `COMFY_API_KEY` | `local` |
| `TYPESET_COMFYUI_URL` | `http://127.0.0.1:8188` |
| `TYPESET_COMFY_TIMEOUT` | `1800` seconds |
| `TYPESET_WEB_URL` | `http://localhost:5173` |
| `TYPESET_SERVER_URL` | `http://localhost:8787` |
| `TYPESET_WEB_DIST` | repository `apps/web/dist/` |
| `TYPESET_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `TYPESET_RENDER_TIMEOUT` | `120` seconds per browser operation |
| `FFMPEG`, `FFPROBE` | `/opt/homebrew/bin/ffmpeg`, `/opt/homebrew/bin/ffprobe` |

Set both WEB_URL and SERVER_URL to `http://localhost:8787` to export from a built app served by FastAPI. Keep services bound to loopback: this is a local single-user tool without authentication.

Uploaded filenames receive unique prefixes, project identifiers are restricted, and project media paths cannot escape their project directory. Uploads are limited to 4 GiB. Model/runtime errors become failed jobs rather than silent success. Words and image paths are preserved for investigation; there is no automatic disk cleanup.

## Checks

```bash
PYTHONPATH=server server/.venv/bin/python -m unittest discover -s server/tests -v
# With API :8787 and its configured web URL running:
server/.venv/bin/python server/tests/smoke_export.py
server/.venv/bin/python server/tests/check_renderer_timeout.py
```

The offline suite checks API preconditions, editable-word persistence and invalid timing, real ffprobe upload metadata, static download, and path-traversal rejection. The integration check creates a one-second synthetic video, uploads it, adds a caption, exports through the actual browser, and checks codecs and dimensions for all three formats. It also verifies behind/front occlusion with a synthetic foreground, and decodes actual alpha pixels from both MOV and WebM (using libvpx-vp9 for the latter).

Real Comfy integrations are available as `server/tests/smoke_analysis.py` (uses existing synthesized speech/person fixtures in ComfyUI input) and `server/tests/smoke_generate.py <project-id>` (runs one short lettering-to-LTX shot). These tests use local model computation and create retained project artifacts.

Verified in the 2026-10-30 handoff: API upload/probe, words and matte through the local Comfy SDK, a plate-to-LTX in-world shot, deterministic browser export, H.264/ProRes4444/VP9 codecs, actual decoded alpha in both overlay formats, behind/front occlusion, and black-backed text-only MP4. Four offline regressions pass, including longer audio clipped to the video timeline.

## Full demo verification

The persisted twelve-second synthetic demo (`54414535-19a7-4ae2-9c76-03e16a5a96e9`) exported all three formats in 78.41 seconds after the renderer guard correction. The job record is [`eval/demo-export.json`](eval/demo-export.json); outputs are under that project's `export/96157e57-f3a2-4977-b9a6-6e5f89af7705/`. Each output has 288 frames at 1280×720 and twelve seconds duration. The MP4 includes audio, and both overlay codecs were decoded to verify alpha spans 0–255 at an active caption frame.

## Remote ComfyUI

Remote GPU generation is optional and **off by default**. When `TYPESET_REMOTE_COMFY_URL` is set, only the production LTX video step uses that host. Transcription, matte extraction, deterministic lettering plates, browser rendering, and exports stay on the Mac. Local analysis continues through the existing proxy on 8189.

The remote runner sends the small plate image through the GPU host's `/upload/image` endpoint, submits the graph through the **Comfy SDK** and a separate local proxy, then downloads outputs through that proxy. It never treats the remote host's files as local files. The SDK clients retain separate URLs; construction restores the process environment afterward. Remote preflight checks the proxy upstream, required node classes, and exact model filenames before generation.

Start a separate proxy in its own terminal **only if port 8190 is not already serving the correct upstream**:

```bash
curl -f http://127.0.0.1:8190/api/v2/health
# Expected upstream: http://100.104.17.103:8188

~/ComfyUI/.venv/bin/comfy-api-proxy run \
  --comfyui http://100.104.17.103:8188 \
  --host 127.0.0.1 --port 8190 --state-dir data/remote-proxy
```

Use `run` here. This proxy version's `start`/`stop` service manager has shared singleton state; using it for the second proxy could interfere with the existing local proxy. Do not pass the Mac's `--comfyui-base-dir` to the remote proxy.

After the GPU host finishes the [installation checklist](gpu-host-install.md), verify LTX readiness without submitting a GPU job:

```bash
TYPESET_REMOTE_COMFY_URL=http://100.104.17.103:8188 \
PYTHONPATH=server server/.venv/bin/python -c \
  'from app.comfy import generation_runner; generation_runner().preflight("ltx_i2v"); print("Remote LTX ready")'
```

Only after that passes, stop the existing **Typeset API** process and launch it with remote generation enabled (keep the web editor on 5174):

```bash
COMFY_BASE_URL=http://127.0.0.1:8189 \
TYPESET_REMOTE_COMFY_URL=http://100.104.17.103:8188 \
TYPESET_REMOTE_COMFY_BASE_URL=http://127.0.0.1:8190 \
TYPESET_WEB_URL=http://127.0.0.1:5174 \
TYPESET_SERVER_URL=http://127.0.0.1:8787 \
TYPESET_CORS_ORIGINS=http://127.0.0.1:5174,http://localhost:5174 \
server/.venv/bin/python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8787
```

`GET /api/health` reports `generationTarget` and remote health when configured. `TYPESET_REMOTE_COMFY_API_KEY` defaults to `local`; set it if the separate proxy uses `--token`. To return to all-local execution, restart the API with `TYPESET_REMOTE_COMFY_URL` unset. Do not change `COMFY_BASE_URL` away from 8189 for this split configuration.

### Remote transport verification

```bash
# Requires the separate proxy and the authorized remote host; does not change API settings.
server/.venv/bin/python server/tests/smoke_remote.py
# Offline path isolation, model preflight, upload naming, and SDK URL isolation tests:
PYTHONPATH=server server/.venv/bin/python -m unittest discover -s server/tests -p 'test_*.py' -v
```

The no-model upload → SDK → remote graph → download test passed in **2.185 seconds**, with image dimensions and pixel values checked. Evidence: `outputs/remote-sdk-smoke/report.json`, job `827e47a5-fd66-4d3d-9c54-c1d0a41608b4`. At that check, remote LTX readiness correctly failed for `ltxv-2b-0.9.8-distilled.safetensors`, `t5xxl_fp16.safetensors`, and `VHS_VideoCombine`. The GPU host's installation is a separate step; a working transport alone does not establish LTX readiness. No running application setting was switched to remote during these checks.

## v2 server features (2026-10-31): occupancy, surface tracking, reframe, remote generation

Implements the server side of `SCHEMA.md` "v2 additions" A–D. Pure CV lives in `server/app/vision.py` (unit-tested in `server/tests/test_vision.py`), the jobs in `server/app/analysis_v2.py`, remote generation in `server/app/remote_gen.py`. New dependency: `opencv-python-headless` (pure wheel; in `server/requirements.txt`). Surface, reframe and occupancy jobs run on a separate **cpu** lane, remote MiniMax shots on a **remote** lane, so neither waits behind a local model job.

### Endpoints

| Method & path | Body → result |
|---|---|
| `POST /api/projects/{id}/analyze/occupancy` | none → `Job(kind='occupancy')`; result `{path, frames, cols, rows}` |
| `POST /api/projects/{id}/surfaces/{sid}/track` | none → `Job(kind='surface')`; result `{path, tracked, frames, first, last, meanConf}` |
| `POST /api/projects/{id}/reframe` | `{aspect: '16:9'|'9:16'|'1:1'|'4:5', name?}` → `Job(kind='reframe')`; result `{projectId, width, height, crop, frames}` |
| `POST /api/projects/{id}/generate/inworld` | existing body plus `engine: 'local-ltx'|'remote-minimax'` (default local), `editModel: 'qwen'|'klein'|'none'` (default qwen), `text?` (default: the selected words), `motionPrompt?` |

Surfaces are created/edited by the client inside `project.surfaces` with the normal `PUT`; the track endpoint 404s for a surface that is not saved yet. While tracking, the job sets `surface.status` to `tracking` and then `tracked` + `surface.track`, or `failed`. **Re-fetch the project after a job finishes before the next PUT**, otherwise a stale editor copy overwrites `status/track`.

### Files per project
- `analysis/occupancy.json` — schema §B. Grid is 32×18 for landscape, 18×32 for portrait (32 cells on the long edge, ~square cells); value = area-averaged matte alpha per cell (0 = empty, 255 = fully covered). Written automatically at the end of every matte job (`project.analysis.occupancy` set) and by the endpoint. ~3 s for 124 frames at 1344×768.
- `analysis/surfaces/<sid>.json` — schema §A, normalized corners TL,TR,BR,BL, `conf` 0..1. Frames below 0.35 confidence or without a sane (convex, same winding, area ratio 0.1–10) quad are omitted.
- Reframe creates a **new project** (name `"<source> · 9:16"`) with hard links of the source media, matte dir, tracks, occupancy, surfaces and shot media under the same relative paths (source space), plus `analysis/crop.json` and `frame = {aspect, source: {projectId}, crop: "analysis/crop.json"}`. Output size: the largest crop of that aspect, scaled so the long edge is 1280–1920 (1344×768 → 9:16 = 720×1280).

### Surface tracker (vision.track_plane)
Features (`goodFeaturesToTrack`) are taken inside the key-frame quad **grown by 100 % around its center** (same wall, much more texture than the quad alone) with the subject (matte alpha > 60, dilated 15 px) masked out. Pyramidal LK tracks them frame to frame, forwards then backwards from `keyFrame`, with a forward-backward check (< 1.5 px). Each live feature remembers its key-frame position, so the homography is always estimated **key frame → current frame** with RANSAC (3 px), not chained, which avoids drift. Points that move onto the subject are dropped; when fewer than 120 remain, new features are detected in the current quad region and mapped back to key-frame coordinates. conf = inlier ratio × min(1, inliers/40). Corners are smoothed with a ±2-frame triangular window that never bridges a lost gap.

Verified on the walk clip (`beeba9e1…`, 124 frames 1344×768, ~2.5 s per surface): surface `s-shutter` (roller shutter right of the pole at f70) tracked f42–123 (82 frames, mean conf 0.88); `s-poster` (poster wall at the left edge at f70) f66–118 (53 frames, 0.94; it leaves the frame before f66). Looked at: `outputs/verify/surface/walk_shutter_sheet.jpg`, `walk_shutter_zoom_e1.jpg` (the quad's left edge stays on the pole/shutter seam from f50 to f104 while the camera travels and she walks through it), `walk_poster_zoom.jpg` (right edge stays on the poster edge f66–f114). With the original 35 % feature region the shutter quad visibly shrank/rotated after f86 (repetitive slats, features clustered); `walk_shutter_zoom.jpg` keeps that failure for reference.

### Reframe virtual camera (vision.follow_axis)
Per frame target: x = 0.65·head cx + 0.35·bbox center of `person0` (or the first track); y puts the head at the upper third (only matters when the crop is shorter than the source). If a tracked surface is on screen and person+surface fit in 92 % of the crop width, the target is the middle of their union, otherwise the person wins. Then: hold missing targets, 0.35 s look-ahead, ±0.5 s box pre-smoothing, a 6 % dead zone with hysteresis (stays still while the subject wobbles; once it leaves the zone it follows until caught up), and a critically damped spring (ω = 3 rad/s); position clamped inside the frame (velocity zeroed at the edge). Verified: `outputs/verify/reframe/walk_9x16.jpg` (crop drifts right with her, max 0.0035 of frame width per frame) and `talk_9x16.jpg` (face centred, small motion).

Word re-layout on reframe: overlay/behind words get `position: null`, `autoPlace: true`; a line wider than 86 % of the new width (estimated 0.58 em per character) gets a proportionally smaller `style.fontSize` on its words; anchor/surface/inworld words keep their settings. Surfaces are copied in source space.

### Remote generation (engine `remote-minimax`)
`frame at start` (ffmpeg, at model size: the project aspect with 736 px on the long edge, multiples of 32 → 736×416) → optional local edit through ComfyUI's raw HTTP API on :8188 using the verified `workflows/eval/qwen2511_int8_edit.api.json` or `klein4b_edit.api.json` (prompt: *Add the exact text "TEXT" {prompt}. Spell it exactly "TEXT". Keep the person, camera framing, lighting and everything else unchanged.*) → upload to the 4090 (`/upload/image`) → `minimax_remote_i2v.api.json` with length = shot × 24 fps rounded up to a multiple of 4 (28–244) → download the `-audio.mp4` → `gen/<shot>/clip.mp4` + `plate.png`, words switched to `inworld`. Job messages carry the stage, the remote queue position ("queued behind 1 job") and elapsed seconds. Everything for the shot lands in `gen/<shot>/`: `frame.png`, `plate.png`, both workflow JSONs, `generation.json` (prompts, seed, size, timings, remote prompt id). Env: `TYPESET_MINIMAX_URL` (default `http://100.104.17.103:8188`), `TYPESET_MINIMAX_LONG_EDGE` (736; 1344 gives the verified full size at ~3 min), `TYPESET_EDIT_COMFY_URL` (default local :8188). The GPU host must not download anything; this path only uses weights already there.

Verified end to end through the API (job `7ef49548…`, test project `dc73a6fe-7ba0-4e95-ad9d-f81dfc99e855` "S test — remote MiniMax shot", walk footage, words HOLD ON, 2.9–5.1 s, editModel qwen): Qwen edit 225 s locally (spelled HOLD ON, but again repainted the poster wall, see CONCEPTS.md) + upload/MiniMax/download 34.5 s on an idle 4090 = 260 s total; clip 736×416, 56 frames, 2.33 s, with audio. Evidence: `outputs/verify/remote/frame_vs_plate.jpg`, `outputs/verify/remote/clip_sheet.jpg`. Klein is the faster edit option but misspells; `editModel: 'none'` animates the raw frame.

### Words / lyric alignment check
The words job through the API on the demo song (test project `e333dc8f-d0dd-4898-ad7d-166aeeb32e47`, `song.json` lyrics incl. `[verse]` tags, language en) ran in 4.2 s with `source: "aligned"` and returns exactly the written lines: "Hold on, say it slow" (Whisper: "say the soul") and "Louder than the radio" (Whisper: "Outer than the radio" / "Loud as under radio"). The PyAV `metadata_errors` problem does not affect the workflow (LoadAudio passes a tensor). Details and the node changes: `comfy-integration.md` (2026-10-31 section).

### 2026-10-31 (later): the analyses now run as ComfyUI workflows

Occupancy, surface tracking and reframe (and the new beat grid) are **ComfyUI nodes in `typeset_nodes`**. The server runs them as API workflows through the Comfy SDK and the :8189 proxy:

| Job | Workflow + sidecar | Nodes |
|---|---|---|
| occupancy (and the end of every matte job) | `workflows/occupancy.api.json` | TypesetLoadImageSequence(matte dir, staged into ComfyUI `input/typeset/<pid>/`) → TypesetOccupancyGrid → SaveTextFile |
| surface | `workflows/surface_track.api.json` | LoadVideo(normalized mp4) → GetVideoComponents → TypesetPlanarTrack (+ matte via TypesetLoadImageSequence) → SaveTextFile |
| reframe | `workflows/reframe.api.json` | TypesetReframeCrop(tracks/surfaces JSON as strings) → SaveTextFile |
| beats (new: `POST /api/projects/{id}/analyze/beats` → `analysis/beats.json` + `beats.png`, `analysis.beats`) | `workflows/beats.api.json` | LoadAudio → TypesetBeatGrid → SaveTextFile + SaveImage |

`scripts/build_typeset_workflows.py` generates all four, plus the drag-in showcase `workflows/showcase/typeset_analysis.json` (UI format, widget order taken from the live `/object_info`) and its API twin.

**Fallback.** The CV code lives once, in `custom_nodes_dev/typeset_nodes/core_vision.py`; `server/app/vision.py` loads that file by path. When ComfyUI or the proxy is unreachable, or the workflow fails, occupancy/surface/reframe run the same code in-process. The job message names the path that ran, e.g. "via ComfyUI workflow surface_track.api.json (job 386605ca, 7.2s)" or "ComfyUI unreachable; in-process OpenCV fallback (2.1s)", and `result.engine` is `comfy` or `fallback`. Beats need ComfyUI, because librosa is only in the ComfyUI venv. `TYPESET_ANALYSIS_ENGINE=local` forces the in-process path; the offline tests use it.

**Same input on both paths.** Tracking reads `analysis/frames_<video>_<w>x<h>_<fps>.mp4` (the footage normalized with the matte job's filter, x264 crf 12, cached). The Comfy path decodes it with LoadVideo; the fallback decodes it with ffmpeg → RGB → `cv2.COLOR_RGB2GRAY`.

**Tracker upgrade (both paths).** Every pose is refined with masked ECC against the key frame (`cv2.findTransformECCWithMask`, half resolution). The features are then re-anchored to the refined pose, so LK slippage on repetitive slats cannot accumulate. Below 45 % visible region (occluded or off screen) a 4-DOF similarity update of the previous pose replaces the full homography. Alignment score (correlation of the key region with the current frame warped back, frames ≥ 15 from the key): shutter 0.37 (LK only) → 0.67; poster 0.40 → 0.51. Cost: shutter 2.6 s → ~7 s per 124 frames.

**Parity (walk clip), Comfy vs in-process, displacement of the visible part of the quad:**
- shutter: median 0.18 px, p95 17.6 px, 77 vs 77 frames
- poster: median 0.29 px, max 3.5 px, 58 vs 58 frames
- occupancy: byte-identical
- crop: identical (max |Δx| = 0)

The shutter tail comes from frames 43–53 and 83–90, where the quad is mostly off screen or behind her head. Images: `outputs/verify/surface/comfy_shutter_zoom.jpg`, `comfy_poster_zoom.jpg`, `walk_shutter_ecc_sheet.jpg`, `outputs/verify/reframe/comfy_walk_9x16.jpg`; showcase outputs under `outputs/verify/showcase/`.

Timings via ComfyUI (124 frames, 1344×768): occupancy 3.1 s, surface 3–7 s, reframe 0.5 s, beats 2.1 s (32 s song). The full showcase graph takes 34 s, BiRefNet included.

### Reframe focus regions (LOUDER)
`POST /reframe` takes `focus: [{start, end, box, mode}]`, and generated shots add theirs from `GenShot.focus`. The format is in SCHEMA.md §C. The regions reach the ComfyUI node as `TypesetReframeCrop.focus_json` (workflow input `focus_json`) and the fallback as `compute_crop(..., focus=)`; on the hero, both produce identical `crop.json` (max diff 0).

The hero's LOUDER sign (13.93–16.32 s, box `[0.19, 0.05, 0.81, 0.31]`) is about 0.62 of the frame wide. A full-height 9:16 window of 1344×768 is only 0.32 wide, so no full-height crop can hold the sign:
- `auto` zooms out to w 0.66 / h 2.06 for that shot. The whole sign and the woman are visible, with transparent bars above and below.
- `pan` keeps full height and scans LOU → DER.

The other shots keep their crops. S5's camera now starts fresh at the cut instead of carrying over the LOUDER shot's motion.

Projects: `66d3b86a-8379-44e3-90f6-110d996d9201` (auto) and `89d6d8a5-4927-43a9-b556-9dfe52338a17` (pan). Images: `outputs/verify/reframe/louder_focus_9x16.jpg` (before/auto/pan, f326–f396), `louder_overview_f356.jpg` (windows on the source) and `louder_web_renderer.jpg` (real web renderer).

### generate/inworld: 1344 px and identity reference (remote-minimax)
New request fields:
- `longEdge` (256–1344). 1344 gives 1344×768 for 16:9; the default is still `TYPESET_MINIMAX_LONG_EDGE` = 736. The local Qwen/Klein edit runs at most 1024 (1024×576), as for the hero's LOUDER plate; MiniMax upscales the plate.
- `referenceImage` (project-relative path) or `referenceTime` (seconds into the project video). With either, the video comes from `MiniMaxH3ReferenceToVideo`, and the prompt calls the reference `<Picture 1>`. The graph is identical to `scripts/content/minimax_ref.py:build` (a test checks this). A `motionPrompt` that contains `<Picture 1>` is used verbatim, like the hero shot list.
- `guideFirstFrame` (default true) anchors the edited plate at frame 0 with `MiniMaxH3AddGuide`, for continuity with the footage. With false you get pure reference-to-video, like the same-face plates.
- Upload a reference with `POST /api/projects/{id}/media` and `kind=reference` (an image of 50 MiB or less). It returns `{path, width, height}` and does not touch `media.video` or `media.audio`.

These nodes and weights are already on the 4090, so nothing new is downloaded. Each shot adds an mp4 of a few MB to the remote output folder.

`GenShot.focus` is filled automatically from the plate-vs-frame difference: the strongest changes, with blobs on the same text line merged. A later `/reframe` keeps that box in the crop. On C's LOUDER edit (`outputs/hero/gen/s1_f490.png` → `qwen_louder_00001_.png`) it finds `[0.199, 0.055, 0.811, 0.380]`.

The local-ltx engine ignores these fields.

Verified on the 4090 (Oct 31): the reference graph ran with the first-frame guide at 1344×768, 56 frames, in 58 s. Inputs were C's `ref_character.png` and a Qwen "LOUDER" plate made by the app. "LOUDER" is spelled correctly and stays legible, and the woman matches the reference. Sheet: `outputs/verify/inworld/ref1344_louder_sheet.jpg`.

Fix: `MiniMaxH3AddGuide` outputs only CONDITIONING. The sampler must keep the reference node's latent, so wiring `[guide, 1]` is rejected. The same fix is in the `first_frame` branch of `scripts/content/minimax_ref.py`, which had never been run.

Caution: the app's remote path still runs the Qwen edit on the **local** ComfyUI, which needs about 27 GB. At 02:01 it crashed the shared ComfyUI while other jobs were running. Run inworld only when local ComfyUI is otherwise idle, or use `editModel: "none"` with a ready plate.

### Matte on long clips: bounded memory (Oct 31)
At 02:15 a single matte job (1115 frames at 1080×1280) crashed ComfyUI, because the whole clip went into BiRefNet as one batch. Per frame, ComfyUI holds the float32 frame, an RGBA output, the mask, a mask image and the list copies before `torch.cat`. Measured on M's clip, the peak grows by roughly 50 MB per frame, and the last prompt's outputs stay cached (≈40–60 MB per frame).

**Now:**
- Clips longer than `matte_chunk_frames(w, h)` = 64 MP / (w×h), clamped to 8–240, are split by `split_lossless` into x264 qp-0 chunks in one ffmpeg pass. That is 46 frames per chunk at 1080×1280 and 62 at 1344×768; `TYPESET_MATTE_CHUNK_PIXELS` changes the budget.
- The decoded frames are bit-identical to the original: 538/538 frames were checked with PyAV.
- `matte.api.json` runs once per chunk with `frame_offset`, `raw_tracks=true`, and `unload_model` only on the last chunk.
- Mattes are written as each chunk finishes, and the chunk's run directory and staged input are deleted.
- Tracks are merged with `core_vision.merge_track_chunks`, which smooths across chunk boundaries exactly as one pass would (tested). Occupancy is computed from the PNGs as before.
- Clips that fit in one chunk use the old single-pass path unchanged.
- If ComfyUI still has the old `MaskToTracks` (no `frame_offset`), the job fails with "restart ComfyUI" instead of writing wrong tracks.

**Measured** (ComfyUI physical footprint via `footprint`, sampled every 0.5 s; M's 1080×1280, 30 fps clip):

| Run | Frames | Peak footprint | Δ over idle | Time |
|---|---|---|---|---|
| old, one batch | 60 | 11.3 GB | +8.9 GB | 21.5 s |
| old, one batch | 100 | 13.3 GB | +8.8 GB (6.9 GB held afterwards) | 31.4 s |
| old, one batch | 1115 | extrapolated ≈ 65 GB, so it crashes on 36 GB | | |
| **chunked**, 25 × 46 | **1115** | **8.8 GB**, flat from chunk 2 to 25 | **+1.9 GB** | **435 s** (0.39 s/frame; split 2.2 s) |

The chunked mattes for frames 1–100, which cross chunk boundaries at 46 and 92, are byte-identical to the single-batch run (100/100, max diff 0).
