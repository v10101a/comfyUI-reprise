# Typeset

**Words that live in the scene.** Typeset is a typography studio and ComfyUI node pack for lyrics, titles and motion graphics. Put words behind a person, track them onto a wall, anchor a label to a head, or let the music and movement shape the type. Every letter stays editable.

ComfyUI prepares the scene: word timings, subject mattes, wall tracks, beats and motion fields. You direct the result in a timeline. Changing a word, a look or an animation uses that saved analysis, without generating the shot again.

The front page includes **[Fall For Me · Angel](apps/web/public/showcase/ffm-angel.mp4)** and **[So I Die](apps/web/public/showcase/so-i-die.mp4)**, alongside the Neon Rain, DANCING and Looks demos. Each piece opens its editable Studio project when that project is available locally.

## Try the current examples

| Example | What to look for |
|---|---|
| [Fall For Me · Angel · 27 s](apps/web/public/showcase/ffm-angel.mp4) | Dreamy lettering and pixel effects. Compare the [original](apps/web/public/showcase/ffm-angel-source.mp4). |
| [So I Die · 23 s](apps/web/public/showcase/so-i-die.mp4) | A scene-based lyric edit with HUD typography and Film grading; linked to the shot Studio project. |
| [Neon Rain · 22 s](apps/web/public/showcase/hero-16x9.mp4) | Flat card lyrics, wall tracking, behind-subject type, a head-anchored HUD and a timed count-in. |
| [DANCING · 8 s](apps/web/public/showcase/louder-fields.mp4) | Large Glow lettering behind the dancer, shaped by motion and vocal energy. Compare the [clean source](apps/web/public/showcase/louder-source.mp4). |
| [Fall For Me · 24 s](apps/web/public/showcase/ffm.mp4) | A tighter lyric edit over stylized footage, with editable word timing and a trimmed song. Compare the [original](apps/web/public/showcase/ffm-source.mp4). |
| [Looks comparison · 4 s](apps/web/public/showcase/README.md#looks-section-srclookssectiontsx) | Eight looks on the same wall shot, each in four footage grades. Open the local demo page to switch looks and grades on one audio clock. |

**Looks style the text; grades style the footage.** These are actual renders of the same shot and lyric sequence:

| Flat card | Paper cut | Neon |
|---|---|---|
| [![Flat card](apps/web/public/showcase/looks/flat-card.jpg)](apps/web/public/showcase/looks/flat-card.mp4) | [![Paper cut](apps/web/public/showcase/looks/paper-cut.jpg)](apps/web/public/showcase/looks/paper-cut.mp4) | [![Neon](apps/web/public/showcase/looks/neon.jpg)](apps/web/public/showcase/looks/neon.mp4) |
| Photocopy | Graffiti | Marquee |
| [![Photocopy](apps/web/public/showcase/looks/xerox.jpg)](apps/web/public/showcase/looks/xerox.mp4) | [![Graffiti](apps/web/public/showcase/looks/graffiti.jpg)](apps/web/public/showcase/looks/graffiti.mp4) | [![Marquee](apps/web/public/showcase/looks/ticker.jpg)](apps/web/public/showcase/looks/ticker.mp4) |

Paper cut uses opaque fibres and a cut-paper shadow. Photocopy uses printed strips and photocopied texture. Neon has thin tubes and scene lighting; Marquee uses scrolling dot-matrix lettering. The demo also includes HUD and Scatter, with ungraded, Mono, Noir and Film comparisons. [Media and render notes](apps/web/public/showcase/README.md).

Studio also includes **Glyph**: a grid of letters from your lyric line, lit by the footage and confined to the subject, the surrounding scene, the frame or a tracked wall. Its cell size and backing are editable independently of the words.

## Direct it in Studio

- **Organize scenes and takes.** Keep references, generation recipes and alternate takes together on the scene board. Preview a full source, then add it to the edit or replace a selected clip.
- **Edit the timeline.** Add text on a track, double-click a word to edit, drag and trim clips, copy/paste, split at the playhead, hide tracks and undo/redo. Filmstrips, the waveform, beat markers and zoom help place words precisely.
- **Place text in the shot.** Draw and adjust a wall quad, track it through the scene, put a title behind the subject, or use a head-anchored HUD. Adjust each line's size, position and left/centre/right alignment.
- **Keep the words visible while styling.** Look thumbnails preview your text; the inspector follows the selected line or group and exposes the controls relevant to its look.
- **Work with the song.** Trim, move or slip the audio clip, optionally moving linked lyrics with it. Forced alignment gives a starting point; word timing remains editable.
- **Animate from signals.** Motion fields drive drift and local distortion. Bass and vocal fields drive the type's pulse. These controls reuse precomputed analysis.
- **Direct a generated lettering shot.** In-world opens a brief saved with the line: exact words, lettering and setting, camera, movement, timing, detail, optional face reference and seed. Appearance goes to the image edit; movement goes to the video model. Generated spelling and identity still need visual review.
- **Finish independently.** Change the footage grade, reframe to 9:16, and export an MP4 with audio or text-only ProRes 4444 / VP9-alpha overlays.

Timeline shortcuts: **⌘/Ctrl+C** copy, **⌘/Ctrl+V** paste, **⌘/Ctrl+B** split, **⌘/Ctrl+Z** undo; **+ / −** zoom and `\` fit. Double-click empty track space to add text.

## Prepare → animate → finish

```text
Footage + song + lyrics
  │
  ├─ Prepare in ComfyUI
  │    alignment · subject matte · wall tracks · beats · motion/audio fields
  │    saved as reusable project data
  │
  ├─ Animate in Studio
  │    editable words · timeline · placement · looks · signal-driven motion
  │    lightweight media during playback and dragging
  │
  └─ Finish
       footage grade · reframe · full-quality browser render → ffmpeg
       MP4 with audio / ProRes 4444 / VP9 alpha
```

The React studio, server export and ComfyUI's `TypesetRender` share the browser renderer. Text geometry and timing come from the same project data. Interactive playback uses smaller proxies and cheaper effects; a settled preview restores quality, and export uses the original media. Preview compression can therefore differ from the final output.

Recent performance work renders Look cards at a maximum 480-pixel edge, reuses their placement plans, and caches the graded footage and subject frame while you edit text. Thumbnail generation pauses during dragging; obsolete frame requests are coalesced, and short-GOP preview/seek copies reduce decoding work. Sequential decoding accelerates eligible exports, with a seek fallback. Measurement and cache-accuracy checks live in [`scripts/perf/`](scripts/perf/).

The standalone demo page also has synchronized **Typeset / Original** switches. Saving a mapped showcase project queues a refreshed demo render. The [piece registry](apps/web/src/showcase-pieces.json) controls which projects and encodes it uses.

## ComfyUI nodes and workflows

Use the studio inside ComfyUI at `/typeset/`, or start with the [**words in your shot** App Mode workflow](custom_nodes_dev/typeset_nodes/example_workflows/typeset%20-%20words%20in%20your%20shot.json): clip + lyrics → look, grade, voice and flow controls → lyric video. Switch to the graph to rewire the steps.

| Nodes | Purpose |
|---|---|
| `TypesetAlignLyrics`, `WhisperWords` | Align a lyric sheet to the vocal, or transcribe word timestamps. |
| `MaskToTracks`, `TypesetOccupancyGrid` | Turn subject masks into anchors and readability maps. |
| `TypesetPlanarTrack`, `TypesetReframeCrop` | Track a wall plane and build a subject-following crop. |
| `TypesetBeatGrid`, `TypesetAudioField`, `TypesetVoiceField`, `TypesetFlowField` | Extract beats, bass energy, vocal features and motion. |
| `TypesetLook`, `TypesetGrade` | Set text styling and footage grading independently. |
| `TypesetRender` | Render through the studio engine in Chromium; an explicitly reported Python draft is available as a fallback. |

Analysis outputs are plain JSON, so they can also feed another renderer. See the [node-pack reference](custom_nodes_dev/typeset_nodes/README.md), [project types](apps/web/src/types.ts) and [API workflows](workflows/).

## Run locally

Requirements: Python 3.12, Node/npm, ffmpeg/ffprobe and ComfyUI (the commands below assume `~/ComfyUI`).

```bash
python3.12 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements.txt
server/.venv/bin/python -m playwright install chromium
(cd apps/web && npm install && npm run build)

# Link the nodes; also install ComfyUI-RMBG and VideoHelperSuite.
ln -s "$PWD/custom_nodes_dev/typeset_nodes" ~/ComfyUI/custom_nodes/typeset_nodes
~/ComfyUI/.venv/bin/python -m pip install -r custom_nodes_dev/typeset_nodes/requirements.txt
```

**Inside ComfyUI:** restart ComfyUI, then open `http://127.0.0.1:8188/typeset/`. The built studio is served by the node pack. Rebuild `apps/web` after changing the renderer. Graph-based Chromium rendering needs Playwright in the ComfyUI environment or the repo's `server/.venv`.

**Standalone development:**

```bash
scripts/comfy.sh start  # ComfyUI + comfy-api-proxy
scripts/dev.sh          # API on :8787; prints the web URL
```

Open the printed web URL for the demos, or `/#/studio` for the editor. The offline sample needs no model download; analysis and project exports need the backend. Use one host at a time for a shared project store.

The [node-pack reference](custom_nodes_dev/typeset_nodes/README.md) lists analysis dependencies. [Server configuration](server/app/config.py) defines environment variables and defaults; [`scripts/comfy-remote.sh`](scripts/comfy-remote.sh) manages the optional remote ComfyUI proxy. Additional setup and research notes in the root `docs/` and `research/` folders are local-only and are not included in a fresh checkout.

## Current limits

- Wall tracking assumes a plane; cloth and curved surfaces need another approach.
- Behind-subject text needs a usable matte. HUD placement follows the matte's tracked region, so multi-person shots need review.
- Singing alignment can need manual timing corrections, especially with dense mixes or long instrumental intros.
- The Python draft renderer supports fewer effects than Chromium. Graph App Mode currently uses the clip's audio; Studio's audio-clip edits are a separate path.
- Text-only alpha exports are unoccluded; another editor also needs the matte to recreate behind-subject placement.
- The optional generated in-world shot path depends on configured edit/video models and is separate from editable text compositing.

## Development checks

```bash
(cd apps/web && npm run build)
(cd apps/web && npm test)
(cd server && .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v)
~/ComfyUI/.venv/bin/python -m unittest discover -s custom_nodes_dev/typeset_nodes/tests -v
```

The Node test command requires a version that supports `--experimental-strip-types` and runs every frontend unit test. Browser checks in `apps/web/scripts/` and `scripts/qa/` use the local services and, where noted, demo projects. Check the front page with `server/.venv/bin/python apps/web/scripts/check_showcase.py`; set `TYPESET_WEB_URL` if the web server is not on port 5174.

## Repository

| Path | Contents |
|---|---|
| `apps/web/` | Studio, demo page, shared renderer, looks and fonts |
| `apps/web/scripts/` | Frontend unit tests and browser checks |
| `apps/web/ux-proposals/` | Standalone interaction studies, outside the production app |
| `server/` | Project API, analysis jobs, proxies and export capture |
| `server/models/` | Small bundled face detector, checksum and licence |
| `custom_nodes_dev/typeset_nodes/` | ComfyUI nodes and the mounted studio host |
| `workflows/` | API graphs, input sidecars and editor workflows |
| `scripts/` | Service launchers, workflow tools, remote generation and lip-sync entry points |
| `scripts/content/` | Demo production, song imports and scene generation |
| `scripts/qa/`, `scripts/perf/`, `scripts/eval/` | Browser regressions, performance probes and model evaluation |

The root `data/`, `outputs/`, `docs/` and `research/` directories are local-only. Ignoring or untracking them does not delete local work; back them up separately. Dependency folders, caches, browser captures, logs, environment secrets and downloaded model weights are also ignored. The small licensed YuNet detector is explicitly included so head tracking works without a runtime download.

Keep reusable source, workflow definitions, tests, lockfiles and licensed runtime assets in Git. Put generated takes, full-size exports and temporary experiments in `outputs/`; project state belongs in `data/`. Only the curated encodes in [`apps/web/public/showcase/`](apps/web/public/showcase/README.md) are shipped as demo media. Existing script and prototype paths remain stable for local workflows.

Code is [MIT](LICENSE). Fonts and model weights have separate licences; see the [bundled font files](apps/web/public/fonts/) and [detector provenance](server/models/README.md).
