# Typeset Comfy integration

The five production workflows live in `workflows/`, with matching `*.inputs.json` sidecars. The server binds named inputs through `ComfyRunner`, stages files directly into ComfyUI's input directory, submits via the local Comfy SDK proxy, then copies/downloads outputs. No paid partner nodes are used.

| Workflow | Inputs | Output | Implementation |
|---|---|---|---|
| `words` | audio, lyrics (optional), language (auto default), model_size (small default) | words_json | Core LoadAudio → CPU/int8 faster-whisper → SaveTextFile |
| `matte` | video, fps | fg_png, tracks_json | Core LoadVideo/GetVideoComponents → BiRefNet lite → RGBA PNGs and largest-component anchors |
| `text_plate` | frame, text, prompt, optional mask_png | plate | Deterministic font plate prototype: neon/chrome styling; not a generative scene edit |
| `ltx_i2v` | image, prompt, length, width, height, seed, fps | video | Local LTX-Video 2B 0.9.8 distilled, 8 sampling steps |
| `ltx_morph` | first, last, prompt, length, width, height, seed, fps | video | First/last image guides → LTX → crop guide latents → video |

`matte` requires the server to normalize the source video to project dimensions and fps before submission. Its fps input labels track frame times; it does not resample footage. All frame cutouts are returned in order; the server renames them `fg_%05d.png` and encodes preview VP9 alpha. The original VHS loader was replaced because its lazy audio cache raises errors on silent clips in this installed version.

LTX defaults are 512×320, 49 frames, 24 fps, seed 42. Dimensions must be multiples of 32 and length must be `8k+1`. The shared fps primitive controls both conditioning and output playback. LTX generation is stochastic and can deform text; a completed job is not proof of correct spelling.

## Setup used here

ComfyUI is installed at `~/ComfyUI`, with this repository's `custom_nodes_dev/typeset_nodes` symlinked into `custom_nodes`. Restart ComfyUI after changing node Python. The implementation turn restarted the idle process and verified registration via `/object_info/TextToMask`.

Required packs: Typeset, VideoHelperSuite (video encoding), ComfyUI-RMBG (BiRefNet). GGUF is only needed for separate evaluation workflows. Some optional RMBG SAM modules report missing dependencies; the selected BiRefNet class is independent and operational.

Installed missing dependency: `timm==1.0.30` in `~/ComfyUI/.venv`. BiRefNet lite's 177,634,392-byte weights and required code/config files were downloaded to `~/ComfyUI/models/RMBG/BiRefNet/`. The installed RMBG pack fetches its converted model from [1038lab/BiRefNet](https://huggingface.co/1038lab/BiRefNet), not BRIA RMBG-2.0. Record that exact provenance when packaging; the [original BiRefNet project](https://github.com/ZhengPeng7/BiRefNet) is separate from the node wrapper and converted artifact.

Whisper small was already cached. LTX checkpoint and T5 encoder were already present. First-time installations need those weights and custom-pack dependencies; cloning this repo alone does not install ComfyUI.

## Validation

CPU behavior checks:

```bash
~/ComfyUI/.venv/bin/python -m unittest discover -s custom_nodes_dev/typeset_nodes/tests -v
```

Four checks cover empty recognition, lyric correction/interpolation order, missing-mask frame boundaries and largest-component selection, and actual font raster output.

Real SDK integration fixtures use synthesized speech, an existing LTX-generated person clip, and deterministic text plates. Outputs and run records are under ignored `outputs/integration/`. Commands from the repository root:

```bash
server/.venv/bin/python workflows/tests/run_integration.py words
server/.venv/bin/python workflows/tests/run_integration.py matte
server/.venv/bin/python workflows/tests/run_integration.py text_plate
server/.venv/bin/python workflows/tests/run_integration.py ltx_i2v
server/.venv/bin/python workflows/tests/run_integration.py ltx_morph
```

These commands expect this machine's fixtures: `typeset/test/words-test.wav`, `typeset/test/person_short.mp4`, and `eval/{wall,neon,chrome}_768x448.png` under ComfyUI input. Generate the WAV with macOS `say` using “Words belong in the world. Neon light, chrome dreams.” then convert to mono 16kHz WAV. The short person clip is the first 0.5 seconds of `typeset/test/person_speech.mp4`, resized to 512×320 at 24 fps. Eval plates are made by `scripts/eval/make_plates.py`.

Words validation recovered all nine expected tokens in order, with two lyric lines and positive durations. A 12-frame segmentation run produced RGBA PNGs with alpha spanning 0–255 and twelve tracked frames. The plate output was visually inspected: exact NEON text in pink on the brick-wall input. LTX output dimensions/frame counts are checked with ffprobe. Run records include queue time because all workers share one ComfyUI queue; those totals are not model benchmarks.

## Completed SDK runs (2026-10-30)

| Workflow | Job ID | Verified result |
|---|---|---|
| words | `e06f3bc9-0dab-4e1b-b546-75da9ce94e94` | Nine expected tokens; ordered positive word durations |
| matte (final native loader) | `6bfe6128-e8c5-40b3-bb20-dfae54686b46` | Twelve 512×320 RGBA PNGs; alpha 0–255; 12 track frames at 24fps |
| text_plate | `906a078c-6a73-4778-9790-be72ce8717b8` | PNG with exact readable NEON; visually inspected |
| ltx_i2v | `65daf2bd-1fb7-4f19-9136-fbc826c625f9` | MP4 512×320×25 frames; middle frame remains readable |
| ltx_morph | `7f3a4c2d-6111-4904-b951-ac4b46ba26b2` | MP4 512×320×25 frames; middle frame shows silver NEON |

All five graphs were also checked against the running node registry for class availability, required inputs, link references, sidecar bindings, and real output nodes. These small examples establish integration, not general quality across footage. The final matte run took about 8.6 seconds after it began running; its 215-second SDK total includes waiting behind the 13B model evaluation.

## Known limits

- `WhisperWords` lyric matching uses `difflib` and interpolation, not acoustic forced alignment. With lyrics, the words job now prefers `TypesetAlignLyrics` (below) and only falls back to it.
- Tracks describe the largest foreground component per frame, not identity tracking or face landmarks. Multiple people can switch the anchor.
- BiRefNet processes frames independently. Hair edges and mask flicker need footage-specific review; long clips consume memory and run time.
- The default plate node guarantees deterministic glyph placement, not physical integration with the scene. Its prompt currently selects simple neon/chrome and color styling. Other wording is passed downstream to LTX by the server.
- LTX morph is an experimental model effect. Exact letter preservation is not guaranteed.

## 2026-10-31: lyric alignment on the demo song

`WhisperWords` now ignores song-structure tag lines (`[verse]`, `[chorus]`, `(x2)` — ACE-Step lyrics contain them) both for alignment and for the initial prompt, and places missed words next to the recognized word on the same side of a long pause (a missed line start hugs the next recognized word). The node receives a tensor from core `LoadAudio`, so faster-whisper's own PyAV file decoding (the `metadata_errors` incompatibility noted in CONCEPTS.md) is never used by the workflow. On `outputs/concept-tests/song/neon_rain_00001.flac` with the `song.json` lyrics, raw Whisper small (en) hears "say the soul" / "Outer than the radio" / "Every time repeat your name"; aligned output is "Hold on, say it slow" / "Louder than the radio" / "Every sign repeats your name" with Whisper timings. Whisper also glues a line's first word to the end of the previous line across an instrumental pause ("Every" 2.18–5.24 s; the repeated "Every word I know" started at 21.4 s instead of ~24.2 s); line-initial words longer than 1 s are now trimmed to their last second (→ 4.24 s and 24.02 s). This is a heuristic, not acoustic forced alignment. `typeset_nodes` changes need a local ComfyUI restart to load.

## 2026-10-31: analysis nodes and workflows
`typeset_nodes` now has TypesetOccupancyGrid, TypesetPlanarTrack, TypesetReframeCrop, TypesetBeatGrid and TypesetLoadImageSequence; see the pack README for node docs and screenshots. Server workflows: `occupancy`, `surface_track`, `reframe` and `beats` (`.api.json` + `.inputs.json`). The showcase is `workflows/showcase/typeset_analysis.json`. It was loaded in the real ComfyUI frontend (0.43 / frontend 1.57) with Playwright: 18 nodes and 24 links, and `graphToPrompt()` gives exactly `typeset_analysis.api.json`. Regenerate everything with `scripts/build_typeset_workflows.py` while ComfyUI is running.

## 2026-10-31: TypesetAlignLyrics (forced alignment of known lyrics)

New node `TypesetAlignLyrics` (`custom_nodes_dev/typeset_nodes/lyric_align.py`) and workflow `align.api.json` + `align.inputs.json` (generated by `scripts/build_typeset_workflows.py`). The pipeline: HDemucs vocal stem (chunked) → MMS_FA CTC forced alignment of the lyric letters (star token between lines) → start snapped to a vocal onset within ±50 ms → sustained-note ends → `lowConfidence` flags. The separator and aligner are swappable registries. The node pack README has the details.

**Server.** When `media.lyrics` is set, `analyze_words` extracts 44.1 kHz stereo, runs `align` (passing `project.timing.vocalStart` when present), and copies the preview to `analysis/words_align.png`. On any failure it falls back to the Whisper `words` workflow. Job result: `engine: "align" | "whisper"` plus `note` (and `lowConfidence`, `preview` for align). `TYPESET_WORDS_ALIGNER=0` disables it. Needs an API restart, and a ComfyUI restart to register the node.

**Renderer.** `Project.timing.leadMs` draws text that many ms ahead of the voice; `lineMeta.pinTiming` exempts lines placed on cuts. Absent means 0.

**Validation** (`scripts/align_validate.py hero|ffm`, run in-process with the ComfyUI venv). Outputs are in `outputs/align/`: `<song>_words.json` (proposed, not applied), `<song>_report.json`, `<song>_compare.png`, `<song>_clicks.wav` and `<song>_clicks_old.wav`.
- Hero (neon_rain, lyrics from the project): line-start error vs pYIN voiced entries on the stem was old 580–960 ms (mean 695), raw CTC 43–72 (59), final 10–72 (43). Every karaoke line used to start 0.5–1.0 s early, during silence or the previous word's tail.
- Fall For Me (master 126.857 s + 45.733 s): the first FALL FOR ME lands within -31/-51/+69 ms of the ear-confirmed hook. "Stop thinking" moves 17.22 → 18.27 with no `vocal_start`: the global pass drops it into intro bleed at 14.68, and the duration-cap re-anchoring moves it back. A hand-set `vocal_start` of 17.9 gives the identical result. "For a minute" moves 18.34 → 20.79. Later lines move +0.03…+0.65 s.
- Nearest-onset distances (dense broadband flux, so a random time is ~90 ms from an onset) are a weak metric. They are in the reports, but the anchors above are the real check.
- Known limits: the MMS posteriors on a separated singing stem are low (0.01–0.5), and sustained vowels give little evidence. A long intro with vocal-like bleed can attract a line in the global pass; re-anchoring catches it when the misplacement leaves a > 2.5 s voiced hold before the next line. `vocal_start` remains as an override. RoFormer separation is not wired in (W's option 4): HDemucs is the only separator registered. MMS_FA weights are CC-BY-NC (W). Dense mixes leave bleed in the stem.

## 2026-10-31: Typeset runs inside ComfyUI (`/typeset`)

The node pack now hosts the whole studio. With `custom_nodes_dev/typeset_nodes` symlinked into `ComfyUI/custom_nodes` and `apps/web` built (`pnpm build`), start ComfyUI and open `http://127.0.0.1:8188/typeset/`. No FastAPI server, no comfy-api-proxy and no Playwright are needed.

- **API.** `studio_host.py` mounts the project API on ComfyUI's aiohttp server under `/typeset/api/…`. The logic is shared with the FastAPI adapter through `server/app/service.py`, imported as `typeset_server` because ComfyUI owns a top-level `app` package.
- **Queue.** The runner's `direct` transport (`TYPESET_COMFY_MODE=direct`, the default inside ComfyUI) posts the API graph to `/prompt`, polls `/history` and copies outputs from the output dir. The `sdk` transport (comfy-sdk → proxy) is unchanged for the standalone server.
- **Export.** When `/api/health` reports `capture: "browser"`, the studio renders each frame through the same `#/render` route Playwright used and uploads PNGs (`POST …/export/frames`, `PUT …/frames/{session}/{layer}/{i}`). ffmpeg encodes them as before. On a 1344×768 × 124-frame project the canvas readback is pixel-identical to the Playwright screenshot (PSNR ∞), and both layers took about 30 s.
- **Graph glue.** `web/typeset.js` adds a `typeset` sidebar tab (open the studio, recent projects, and videos or songs saved by graphs this session) and an **open in typeset** node-menu item. Both call `POST /typeset/api/import`, which turns a ComfyUI output file into a new project.
- **Verified on a second instance (:8198):** a project imported from `output/eval/ltx13b_t2v_00001.mp4`, then a 49-frame matte run through `/typeset` on the direct transport, then a browser-capture export (mp4 + ProRes 4444 + VP9 alpha).
- **Caveat:** projects and jobs share `data/` with the :8787 server. A starting host marks unfinished jobs in `data/jobs` as failed, so don't run both while a job is in flight.

## 2026-10-31: fields, the in-graph render node, and App Mode

- **`TypesetFlowField`** (`flow_field.py`, `workflows/flow.*`, job `/analyze/flow`): DIS optical flow on a 64-cell grid, CPU only, no weights. The studio splits it into two effects:
  - **camera drift:** the type drifts with the frame's median motion and settles back;
  - **glass ripples:** quick local motion (residual above 6 px/frame on a 1000 px frame) spreads out as expanding rings that refract the type.

  Bodies walking do not drag letters around. Walls, anchors and HUD lines are excluded, because they are already tracked. Implemented in `apps/web/src/flow.ts` and `render_node.py`.
- **`TypesetVoiceField`** (`voice_field.py`, `workflows/voice.*`, job `/analyze/voice`): HDemucs vocal stem (or a connected stem), then per-frame loudness, pYIN pitch, vibrato and onsets. Each word's weight and width swell with loudness, its baseline follows the melody relative to the line's median pitch, and vibrato makes it wobble. Sung words relax back. Implemented in `apps/web/src/voice.ts`.
- **Studio:** a `fields` group (flow, voice: 0..1) in the look params writes `look.overrides.fields`. With 0 or absent, frames are pixel-identical to before (checked on 5 frames across 2 projects).
- **`TypesetRender`** (`render_node.py`): words + look + matte + fields burned into an IMAGE batch. One line at a time, behind the subject. It is draft fidelity; the studio does walls, HUD and exact export. Measured at 3.7 s for 192 frames at 672×384.
- **App Mode** (`workflows/app_words_in_your_shot.api.json`, UI graph `workflows/showcase/typeset_app_words_in_your_shot.json`, also shipped as the node-pack template `example_workflows/typeset - words in your shot.json`):
  - The graph runs LoadVideo → BiRefNet matte + TypesetAlignLyrics → VoiceField (re-using the aligner's stem) + FlowField → TypesetLook + TypesetGrade → TypesetRender → CreateVideo → SaveVideo.
  - It is one graph with two views. `extra.linearMode` plus `linearData` expose file, lyrics, preset, grade, voice and flow.
  - On the 8 s dancer chorus at 1344×768, the whole graph took 81 s on an M5 Max (:8198).
