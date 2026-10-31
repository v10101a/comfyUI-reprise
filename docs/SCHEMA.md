# Typeset — shared contracts

All agents build against this file. Coordinates are **normalized** (0..1 of frame width/height) unless stated. Times are **seconds** (float). Frame index `f` is `round(t * fps)`.

## 1. Project file — `data/projects/<id>/project.json`

```ts
type Project = {
  version: 1;
  id: string;                 // uuid
  name: string;
  fps: number;                // output fps, default = video fps or 24
  width: number; height: number;   // output size, default = video size (cap 1920 on long edge)
  duration: number;           // seconds
  media: {
    video?: MediaRef;         // background footage (may contain the audio)
    audio?: MediaRef;         // separate music/VO; if absent, use video's audio
    lyrics?: string;          // optional user-provided lyrics text (newline-separated lines)
  };
  analysis: {
    words?: string;           // relative path: "analysis/words.json"
    matte?: string;           // relative dir:  "analysis/matte/" (contains fg_%05d.png and fg.webm)
    tracks?: string;          // relative path: "analysis/tracks.json"
    depth?: string;           // relative dir (Day 3, optional)
  };
  style: TextStyle;           // project defaults
  words: Word[];              // the editable timeline (seeded from analysis.words)
  shots: GenShot[];           // generative in-world clips (Day 2)
};

type MediaRef = { path: string; duration: number; width?: number; height?: number; fps?: number; hasAudio?: boolean };

type TextStyle = {
  fontFamily: string;         // one of the bundled fonts
  fontWeight: number;
  fontSize: number;           // fraction of frame height, e.g. 0.08
  fill: string;               // CSS color
  stroke?: string; strokeWidth?: number;   // strokeWidth as fraction of fontSize
  letterSpacing?: number;     // em
  align: 'left' | 'center' | 'right';
};

type Placement = 'overlay' | 'behind' | 'anchor' | 'inworld';
type Preset = 'pop' | 'karaoke' | 'typewriter' | 'hud' | 'none';

type Word = {
  id: string;
  text: string;
  start: number; end: number;      // seconds; editable
  lineId: string;                  // words sharing a lineId are laid out together
  placement: Placement;            // 'behind' = drawn under the fg cutout
  preset: Preset;
  position?: { x: number; y: number };   // anchor point for overlay/behind; default from line layout
  anchor?: { trackId: string; dx: number; dy: number };   // for placement 'anchor': follow tracks.json track, offset in frame fractions
  style?: Partial<TextStyle>;
  shotId?: string;                 // for 'inworld': the GenShot that renders this word
};

type GenShot = {
  id: string;
  wordIds: string[];
  start: number; end: number;      // seconds on the project timeline
  prompt: string;
  plate?: string;                  // "gen/<shot>/plate.png" (image model output)
  video?: string;                  // "gen/<shot>/clip.mp4" (LTX output)
  status: 'pending' | 'running' | 'done' | 'failed';
  workflow: 'text_plate+ltx_i2v' | 'ltx_morph';
};
```

## 2. Analysis outputs

### `analysis/words.json`
```json
{
  "source": "faster-whisper",       // or "aligned" when snapped to provided lyrics
  "model": "small",
  "language": "en",
  "words": [ { "text": "neon", "start": 1.02, "end": 1.31, "confidence": 0.93, "lineId": "l0" } ],
  "lines": [ { "id": "l0", "text": "neon lights", "start": 1.02, "end": 1.80 } ]
}
```
Rules: words sorted by start; `end > start`; lines = Whisper segments, or user lyrics lines when aligned.

### `analysis/tracks.json`
```json
{
  "fps": 24,
  "frames": 480,
  "tracks": [
    { "id": "person0", "label": "person", "frames": [ { "f": 0, "bbox": [0.31, 0.12, 0.22, 0.80], "cx": 0.42, "cy": 0.30 } ] }
  ]
}
```
`bbox` = `[x, y, w, h]` normalized. `cx, cy` = anchor point (for a person: face/head area ≈ top 20 % of bbox; otherwise bbox center). Missing frames mean "not visible" — renderer holds the last known position for ≤ 6 frames then hides.

### `analysis/matte/`
- `fg_%05d.png` — RGBA cutout of the foreground (subject) per frame, same size as project, 1‑based index starting at `fg_00001.png`.
- `fg.webm` — VP9 with alpha (`-pix_fmt yuva420p`), same fps, for browser preview (Chrome/Chromium). Produced by the **server** from the PNGs.
- Optional `mask_%05d.png` grayscale.

## 3. Workflow sidecars — `workflows/<name>.inputs.json`

The server never hardcodes node ids. Each workflow ships a sidecar:
```json
{
  "workflow": "matte.api.json",
  "description": "Per-frame person cutout + bbox track",
  "inputs": {
    "video":  { "node": "1",  "field": "file",   "kind": "comfy_input_path" },
    "fps":    { "node": "7",  "field": "fps",    "kind": "float", "default": 24 }
  },
  "outputs": {
    "fg_png":  { "node": "12", "type": "image" },
    "tracks":  { "node": "15", "type": "text" }
  }
}
```
`kind` ∈ `comfy_input_path` (a path relative to the selected ComfyUI host's input directory (locally `~/ComfyUI/input/`)), `string`, `int`, `float`, `bool`. Local analysis uses filesystem staging; optional remote LTX generation uploads its plate to the remote input endpoint and downloads remote outputs via HTTP. The server sets `wf.set_input(node, field, value)` for each input, submits, polls, and fetches outputs by node id via `job.get_outputs(node)`.

Required workflows (W3):

| file | purpose | inputs | outputs |
|---|---|---|---|
| `words.api.json` | word timestamps (+ optional alignment to lyrics) | `audio` (comfy_input_path), `lyrics` (string, may be ""), `language` (string, "auto") | `words_json` (text) |
| `matte.api.json` | person cutout per frame + tracks | `video`, `fps` | `fg_png` (image sequence), `tracks_json` (text) |
| `text_plate.api.json` | deterministic neon/chrome lettering prototype on a frame (not generative image editing) | `frame` (comfy_input_path, PNG), `text` (string), `prompt` (string), `mask_png` (optional) | `plate` (image) |
| `ltx_i2v.api.json` | animate a plate | `image` (comfy_input_path), `prompt`, `length` (int, 8k+1), `width`, `height`, `seed` | `video` (mp4) |
| `ltx_morph.api.json` | first/last‑frame material morph | `first`, `last`, `prompt`, `length`, `seed` | `video` |

Custom node outputs of type text are returned by a node that saves a `.json`/`.txt` into the output dir (e.g. a `SaveText`‑style node in `typeset_nodes`), so the SDK can download them like any other output.

## 4. Server REST API (W2 implements; W1 consumes). Base `http://localhost:8787`

| Method & path | Body → Response |
|---|---|
| `POST /api/projects` | `{name}` → `Project` |
| `GET /api/projects` | → `Project[]` (summaries) |
| `GET /api/projects/{id}` | → `Project` |
| `PUT /api/projects/{id}` | `Project` → `Project` (full save) |
| `POST /api/projects/{id}/media` | multipart `file`, field `kind`=`video`\|`audio` → `MediaRef` (ffprobe‑filled; project updated) |
| `POST /api/projects/{id}/analyze/words` | `{language?}` → `Job` |
| `POST /api/projects/{id}/analyze/matte` | `{}` → `Job` |
| `POST /api/projects/{id}/generate/inworld` | `{wordIds, prompt, start, end}` → `Job` (creates GenShot) |
| `POST /api/projects/{id}/export` | `{layer: 'text'\|'composite', formats: ['mp4','mov','webm']}` → `Job` |
| `GET /api/jobs/{jobId}` | → `Job` |
| `GET /files/projects/{id}/...` | static files under `data/projects/{id}/` |

```ts
type Job = { id: string; kind: 'words'|'matte'|'inworld'|'export'; status: 'queued'|'running'|'done'|'failed'; progress?: number; message?: string; result?: any; projectId: string };
```
On `done`, analysis jobs have already written files and updated `project.json` (`analysis.*` paths, seeded `words`). The web app re‑fetches the project.

## 5. Renderer contract (W1 implements; W2's exporter calls it)

Route `#/render?project=<id>&layer=text|composite&server=http://localhost:8787`
- Page loads the project from the server, preloads fonts, media and assets, then sets `window.__typeset`:
```ts
window.__typeset = {
  ready: Promise<void>;                  // resolves when fonts + assets are loaded
  frames: number;                        // total frames = round(duration * fps)
  renderFrame(i: number): Promise<void>; // draws frame i synchronously-deterministic into the single <canvas id="stage">; resolves after paint
};
```
- `layer=text`: canvas is transparent; draws **only** the words (all placements except `inworld`; `behind` words are drawn as if nothing were in front — the fg cutout is composited later by ffmpeg).
- `layer=composite`: draws background (or active generated shot) → behind-subject words → foreground cutout → overlay/anchor words. This is also the final MP4 render source, preserving placement and generated-shot behavior.
- Optional `text-behind` / `text-front` layers isolate the corresponding words for downstream compositing. The combined `text` overlay is unoccluded and cannot alone reproduce mixed front/behind placements in another editor.
- Canvas CSS size = project width × height, `devicePixelRatio` forced to 1 in render mode. Body background transparent. No animations driven by wall‑clock time; everything is a pure function of `i`.
- The exporter screenshots the canvas element with `omit_background=True`.

Spring/motion presets must be deterministic functions of (word, t) so preview and export match.

## 6. Export outputs — `data/projects/<id>/export/<jobId>/`
Each export uses a stable project state (writes are locked during capture) and its own output directory. Transparent text frames feed `text_overlay.mov` (ProRes 4444) and `text_overlay.webm` (VP9 alpha). `final.mp4` uses deterministic composite frames (background + behind text + foreground + front text) and project audio when `layer=composite`; `layer=text` uses text on black. Return actual download URLs in the job result; clients must not guess directory names. ffmpeg defaults to `/opt/homebrew/bin/ffmpeg` and is configurable.

## 7. Fonts (bundled in `apps/web/public/fonts/`, OFL)
Inter (sans), Space Mono (HUD/mono), and one display face (e.g. Bebas Neue or Anton). `TextStyle.fontFamily` must be one of these.

---

## v2 additions (2026-10-31) — surface placement, auto-placement, reframe

Agreed contract for the build after the concept review (see `docs/CONCEPTS.md`). Existing fields keep working; everything below is additive and optional.

### A. `surface` placement — text on a wall that stays on the wall
- `Placement` gains `'surface'`. A surface word has `surfaceId: string`.
- `Project.surfaces?: Surface[]`:
```ts
type Surface = {
  id: string;
  label?: string;
  keyFrame: number;                 // frame where the user drew the quad
  corners: [number, number][];      // 4 normalized points at keyFrame, order TL, TR, BR, BL
  track?: string;                   // "analysis/surfaces/<id>.json" once tracked
  status?: 'drawn' | 'tracking' | 'tracked' | 'failed';
};
```
- `analysis/surfaces/<id>.json` (written by the server's surface-track job):
```json
{ "fps": 24, "frames": [ { "f": 0, "corners": [[x,y],[x,y],[x,y],[x,y]], "conf": 0.93 } ] }
```
  Missing frames = lost; renderer holds the last pose ≤ 6 frames, then hides.
- Renderer draws surface words in the quad's plane (perspective/homography warp of the text), in the **behind** layer (the subject occludes them). Without a track, it uses the static `corners`.
- Server: `POST /api/projects/{id}/surfaces/{sid}/track` → `Job(kind='surface')`. Planar tracking with OpenCV (features inside the quad at keyFrame, tracked forwards and backwards, homography + RANSAC per frame).

### B. Occupancy grid — where the subject is not
- `analysis/occupancy.json` (written by the matte job, or by `POST /api/projects/{id}/analyze/occupancy` for existing projects):
```json
{ "fps": 24, "cols": 32, "rows": 18, "step": 1,
  "frames": [ "<base64 of cols*rows uint8, 0..255 = fraction of the cell covered by the subject>" ] }
```
  Row-major, top row first. `step` = frames per entry (1 = every frame).
- `Project.analysis.occupancy?: string`.
- `Word.autoPlace?: boolean` (default true for `behind` and `overlay` words without an explicit `position`). When on, the renderer chooses the line's position: the region that stays readable (least covered) over the line's whole time span, preferring the lower and upper thirds, inside the safe area, and stable for the line's duration (no jumping mid-line). Must be deterministic: computed from the data, never from wall-clock time.

### C. Reframe — landscape → vertical with text re-layout
- `Project.frame?: { aspect: '16:9' | '9:16' | '1:1' | '4:5'; source?: { projectId: string } ; crop?: string }`:
  - A reframed project is a **new project** whose `media` points at the same files as the source project (copied or referenced), with `width/height` for the new aspect and `frame.crop = "analysis/crop.json"`.
- `analysis/crop.json`:
```json
{ "fps": 24, "aspect": "9:16", "frames": [ { "f": 0, "x": 0.31, "y": 0.0, "w": 0.32, "h": 1.0 } ] }
```
  Crop window in **source-normalized** coordinates, smoothed (follows `person0` with an easing/dead-zone virtual camera, never jitters).
- Renderer: in a reframed project, the bg video, matte, tracks, occupancy and surfaces are sampled in source space and mapped through the per-frame crop into output space. Word positions/sizes are in **output space**.
- Text re-layout on reframe: copy words; clear explicit `position`s and set `autoPlace: true`; scale `fontSize` so the longest line fits ~86 % of the new width; surface words keep their surface (it's mapped through the crop) and are hidden when the quad leaves the crop.
- Server: `POST /api/projects/{id}/reframe` `{aspect, name?, focus?}` → `Job(kind='reframe')` → result `{projectId}` of the new project.
- **Focus regions** (e.g. a generated word the crop must not cut): `focus: [{start, end, box: [x0, y0, x1, y1], mode?: 'auto' | 'pan', label?}]`, with seconds and source-normalized boxes. `GenShot.focus?: [x0, y0, x1, y1]` adds its shot's `[start, end)` automatically. Each range is its own camera segment, treated like a cut.
  - `auto` (the default) keeps following the person but clamps the window so the box plus a 2 % margin stays inside. If the box is bigger than the crop, it zooms out to the smallest window of the same aspect that contains it. That window can extend past the source (`x`/`y` < 0, `w`/`h` > 1), so the output is letterboxed and the renderer leaves the outside transparent.
  - `pan` keeps the normal window and scans across the box over the range (smoothstep).
  - `crop.json` echoes the resolved list as `focus: [{f0, f1, box, mode, margin, label, applied: 'follow' | 'zoom' | 'pan'}]`, so `w`/`h` can vary per frame inside a focus range.

### D. Remote generation in the app
- `GenShot.workflow` gains `'remote_edit+minimax'` (Qwen-Image-Edit or Klein on a frame → MiniMax H3 i2v on the 4090) alongside the local LTX path. Request body for `POST /generate/inworld` gains optional `{engine: 'local-ltx' | 'remote-minimax', editModel?: 'qwen' | 'klein' | 'none'}`. A generated shot replaces the background for `[start, end)` as before.

---

## v3 additions (2026-10-31) — art direction: looks, hierarchy, quiet, optics

Owner: R (renderer). Implements `research/kinetic-type-feature-brief.md` with the coordinator revisions. All fields are optional; a project without `look` renders exactly as in v2 (verified pixel-identical).

### Project fields
```ts
Project.look?: { id: LookId; overrides?: Partial<Omit<Look,'id'>> } | null;   // by reference; null/'default' = no look
Project.lineMeta?: Record<lineId, { hook?: boolean; heroWordId?: string; hidden?: boolean }>;
Word.hero?: boolean;     // manual hero for the line (one per line)
Word.hidden?: boolean;   // quiet: stays in the timeline, not drawn
type LookId = 'default' | 'red-glow' | 'lens-bound' | 'paper-cut' | 'ticker' | 'flat-card';
type Look = {
  id: LookId;
  font: { hero: string; body: string; heroWeight?: number; bodyWeight?: number; heroCase?: 'upper'|'lower'|'as-is'; bodyCase?: … };
  palette: { text: string; accent: string; shadow?: string; card?: string };
  texture?: 'none' | 'grain' | 'paper' | 'halftone';           // halftone: reserved
  optics: { glow?; grain?; chroma?; motionBlur?; lensWarp?; blur?; extrude? };   // 0..1
  grade?: { tint: string; amount: number } | null;
  layout: 'line' | 'hero' | 'constellation' | 'stack';
  quiet?: 'none' | 'hooks-only';
  heroFill?: 'text' | 'accent';     // colour of hero words / hook lines
  motion?: 'none' | 'marquee';      // ticker: lines scroll through a fixed band
};
```
Presets live in code (`apps/web/src/looks.ts`); a project stores only `{id, overrides}`, so tuning a preset restyles every project. Names describe rules, not artists.

### Semantics
- **Styling.** Under a look, the look owns typeface, weight, colour, case and letter-spacing for every placement (including surface text, which also takes the look's glow). Per-word `fontSize` and `align` still apply in `line` layout. HUD labels keep Space Mono but take the palette (only colours light enough for the dark HUD backdrop).
- **Hooks.** `lineMeta.hook` if set; else lines whose normalized text occurs 2+ times; if nothing qualifies, lines set in ≥80% of the project's largest type count as hooks, so `hooks-only` never blanks a project. **Hero word:** `Word.hero` → `lineMeta.heroWordId` → longest non-stopword (built-in English stopword list), ties → later start.
- **Quiet.** A word is drawn only if it is not `Word.hidden`, its line is not `lineMeta.hidden`, and (under `quiet:'hooks-only'`) its line is a hook or a surface line.
- **Layouts** (overlay and behind lines; anchor/HUD and surface lines keep their own placement):
  - `line`: two registers. Hooks keep authored size/placement in the hero face; verses become a small (≤5.5% of min(w,h)) subtitle in the accent colour, auto-placed low, in front.
  - `hero`: one hero word per line at 0.45 × min(width,height), shrunk until ≥60% of the word stays in frame (deliberate bleed allowed), `behind` when a matte exists. Satellites (the other words, multi-token words are split) at 0.048 × min(w,h), in front, placed by `autoPlace` in strict mode (any subject coverage counts) at least one hero-height from the hero centre, stable for the line. One line on screen at a time: a hero line yields when the next line starts.
  - `constellation`: every word small (0.05 × min) spread through negative space. `stack`: one word per row, left-aligned, auto-placed preferring a corner.
- **Optics** (deterministic; text layer = also in the alpha overlay exports): motion blur (6 sub-renders over a shutter of 0.5 frame × motionBlur, tracks and surface poses interpolated between frames, averaged additively) → chroma (R/B shifted ±chroma × 0.004 × width along the subject's velocity, x when static) → blur → lens warp (barrel `r' = r(1 + k r²)`, k = lensWarp × 0.35, text only) → glow (blurred copies, radius glow × 0.03 × height, screen in composite / lighter in text layers). **Composite only:** `grade` (a `color` tint plus a light multiply on the footage and the subject cutout, keeping luminance) and grain (seeded per frame, overlay blend). `texture:'paper'` = hard offset shadow in `palette.shadow` + seeded paper erosion. `optics.extrude` = 12 darkened copies stepped along the quad's down-right diagonal under surface text.
- **Cost (P0b).** Measured on the 1344×768 walk, sequential frames incl. PNG encode, headless Chromium: no look 112 ms, red-glow 172 ms, lens-bound with motion blur + chroma 255 ms, the same with them off 197 ms → P0b ≈ +58 ms/frame (≈ +7 s per 124-frame export). Capped at `MOTION_BLUR_SAMPLES = 6`; `StageRenderer.heavyOptics = false` skips P0b for scrubbing.
- **Render route:** `#/render?…&look=<id>` previews a look without saving it.

### v3.1 (2026-10-31) — reframe + subtitle register (R)
- **Surface text under a crop:** the renderer fits surface text into the part of the plane that stays in frame. It picks the (u,v) rectangle of the surface whose grid vertices are inside the output in ≥90 % of the line's frames, relaxed to 75/60/45 % when the camera pans past, choosing the rectangle that gives the largest type. The plane aspect comes from the key-frame quad in *source* pixels (`width/crop.w × height/crop.h`), so 9:16 text is no longer stretched. Without a crop nothing changes.
- **Reframe ensembles:** overlay/behind lines with explicit positions, the same font size (±10 %) and overlapping lifetimes, such as the hero ending EVERY/WORD/I/KNOW, are laid out as rows in reading order. They use the authored rows, or one line per row if that gives larger type. Positions are explicit (`autoPlace: false`). Rows narrower than 75 % of the frame or centred below 30 % of its height become `overlay`. Client `reframe.ts:layoutEnsembles` = server `analysis_v2.py:_ensemble_layout`.
- **Subtitle register** (`looks.ts:isSubtitleLine`): an overlay line whose words are all `karaoke`, or which has an explicit position, `autoPlace: false` and fontSize ≤ 0.045. Under any look it keeps its authored position, size and alignment, set in Space Mono (unless the word sets a family) in `palette.text`, with `palette.accent` on the active karaoke word. It is drawn crisp outside the optics chain and is never auto-placed, never hidden by quiet, and doesn't make hero lines yield. Reframe keeps its position and shrinks it so the whole line fits.
- **Neon surfaces** (`material: 'neon'`): filled tubes (halo + filled letters + white-hot face); edge heights pulled halfway to their mean (less perspective squash).
- **v3.2 (R):**
  - **Static surfaces to titles.** On reframe, a static/untracked (`noTrack`) surface that is <50 % inside the crop at a line's mid-frame becomes screen-space text: its lines turn into `behind` lines at the quad centre, which then join the ensemble layout.
  - **Ensemble rows.** Rows are top-aligned. A short stack (height ≤ 0.45) splits around the subject: the first half at the top, the rest from 55 % down. With the front rule this gives HOLD above the head (behind) and ON over the torso (front).
  - **Surface text under a crop** is shown only during the longest run of frames where its plane rectangle is fully in frame. It is never cut by the frame edge, and the subject's coverage is a soft penalty.
  - **Fixed text as obstacles.** Auto-placed lines avoid fixed-position overlay/behind text (`autoPlace(..., obstacles)`).
  - **Looks.** flat-card draws its card on surfaces. Neon surfaces take `palette.accent` under a look. The subtitle register uses the look's light HUD ink when `palette.text` is dark.
- **v3.3 (R):**
  - **Warp-aware title-safe margins** (`geometry.ts:warpSafeMargins` = `analysis_v2.py:_warp_safe_margins`): text stays ≥6 % from every edge after the look's barrel warp.
    - Reframe stacks assume the largest look warp, since the look can change later: 7.3 % x / 9.5 % y in 9:16.
    - The planner (≥6 %) and anchored HUD labels (≥3 %) use the current look's warp.
    - HUD labels clamp by alignment and the tag's width. They drop below fixed text that is on screen.
  - **Faces** (`_head_band`): the head band is person0's bbox top → head anchor `cy` + the same again, through the crop, over the stack's lifetime. Stacked rows never cover it.
    - The first k rows go above the head (keeping their placement); the rest go below the chin, in front.
    - k and the size maximize the type. A layout with ≥1 row above the head wins if its type is ≥60 % of the best.
    - Without a track, the earlier split rule applies.
  - Rows stay above y = 0.86 (the subtitle band).
