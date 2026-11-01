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
    audioClip?: {in: number; out: number; offset: number};  // song clip, seconds (see below); absent = whole song from 0
  };
  // media.audioClip (non-destructive; the song file is never rewritten):
  //   in/out  = trim points in song time (0 ≤ in < out ≤ song duration)
  //   offset  = project time at which `in` plays; may be < 0 (the head before 0 is cut)
  //   Song time s plays at project time s + (offset − in); silence outside [in, out).
  //   words[] stay in project time (the studio offers to shift them when the song slides);
  //   analysis beats.json / voice.json stay in song time and are mapped through offset − in.
  //   Exports (final.mp4, demo clips) apply it as ffmpeg atrim + adelay; the words job maps its
  //   song-time result into project time and drops words outside the clip. Uploading a new song clears it.
  analysis: {
    words?: string;           // relative path: "analysis/words.json"
    matte?: string;           // relative dir:  "analysis/matte/" (contains fg_%05d.png and fg.webm)
    tracks?: string;          // relative path: "analysis/tracks.json"
    depth?: string;           // relative dir (Day 3, optional)
    flow?: string;            // "analysis/flow.json" (TypesetFlowField)
    voice?: string;           // "analysis/voice.json" (TypesetVoiceField): vocal loud/pitch/vibrato/onset per frame
    audio?: string;           // "analysis/audio_<job>.json" (TypesetAudioField): {kind:'bass', fps, frames, band:[lo,hi] Hz,
                              //   level[0..1] per frame = peak over song seconds [t0 + f/fps, t0 + (f+1)/fps), t0, leadFrames}.
                              //   Centred STFT windows, low-band dB, percentile-normalised, instant attack / 250 ms release,
                              //   lead 0.5 frame: hits land on the kick's frame, never after. New path per run (the studio reloads).
  };
  // Both field docs cover only the audioClip section (t0 = clip in; absent = 0) and stay in song time.
  // look.fields.voice (studio "Audio", 0..1) sizes the type; look.fields.source 'bass' (default) | 'vocal' picks
  // analysis.audio or analysis.voice, falling back to whichever exists. A voice.json with kind 'bass' is read as audio.
  style: TextStyle;           // project defaults
  words: Word[];              // the editable timeline (seeded from analysis.words)
  shots: GenShot[];           // generative in-world clips (Day 2)
};

type MediaRef = { path: string; duration: number; width?: number; height?: number; fps?: number; hasAudio?: boolean };

Studio preview proxies live beside the originals by convention (no project fields): `media/proxy/<video stem>.mp4` and `<matte dir>/fg_proxy.webm`, long edge 672, 12‑frame GOP, so a seek costs ~17 ms instead of ~100 ms. The server makes them on video upload and at the end of the matte job; `scripts/make_proxies.py` backfills. Only the studio's draft renders read them (`StageRenderer.draftMedia` + `render(…, {proxy: true})`); export, `#/render`, TypesetRender and capture always read the originals.

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
  "source": "faster-whisper",       // or "aligned" (Whisper snapped to lyrics) or "forced-align" (TypesetAlignLyrics)
  "model": "small",
  "language": "en",
  "words": [ { "text": "neon", "start": 1.02, "end": 1.31, "confidence": 0.93, "lineId": "l0" } ],
  "lines": [ { "id": "l0", "text": "neon lights", "start": 1.02, "end": 1.80 } ]
}
```
Rules: words sorted by start; `end > start`; lines = Whisper segments, or user lyrics lines when aligned.
`forced-align` words may also carry `ctcStart` (raw CTC start), `onsetShift` (seconds moved to a vocal onset, or null), `lowConfidence` and `pinned` (no acoustic evidence: the word sat on the `vocal_start` edge). The doc has a `stats` object. Consumers ignore unknown fields.

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
- `fg_proxy.webm` — half‑size, short‑GOP VP9‑alpha copy for studio scrubbing (see preview proxies above). Optional.
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
| `align.api.json` | known lyrics → word timings by forced alignment (HDemucs vocals → MMS_FA CTC → vocal onsets); the words job prefers it when `media.lyrics` is set | `audio` (comfy_input_path, 44.1 kHz stereo WAV), `lyrics`, `vocal_start`/`vocal_end` (float s, 0 = whole file), `onset_window_ms` (50), `device` ("cpu") | `words_json` (text), `preview` (image, optional) |
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
Project.lineMeta?: Record<lineId, { hook?: boolean; heroWordId?: string; hidden?: boolean; pinTiming?: boolean }>;
Project.timing?: { leadMs?: number; vocalStart?: number };
// leadMs: the renderer draws every word leadMs earlier (onset-exact text reads late; ~40 is a good value). Absent = 0,
//   so existing projects render unchanged. Word times are never rewritten. Lines with lineMeta.pinTiming keep exact
//   times (e.g. lines deliberately placed on shot cuts). Media seeks are unaffected.
// vocalStart: seconds; the words job passes it to align.api.json so an instrumental intro can't attract the first line.
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

## v4 (2026-10-31) — grade split from look, look params, Neon (L)
- **`Project.grade?: { id: GradeId; amount?: number (0..1, default 1); overrides?: Partial<Grade> } | null`** — the footage treatment, independent of `Project.look` (which is now text only: type, colour, layout, motion, text optics). `null` = ungraded.
  `GradeId = 'none'|'mono'|'xerox'|'teal'|'film'|'wash'|'night'`; `Grade = { tint?: {color, amount}; mono?: {contrast, crush?, keep?: {hue, width, minSat}}; flash?: {amount, decay, beat?}; grain?: number; halation?: number }`.
  Composite only (footage + subject cutout; grain covers the whole frame). `amount` scales tint/grain/halation/flash and cross-fades mono.
- **Migration (load-time, `looks.ts:migrateProject`, applied by `api.getProject` and the render route):** a project without a `grade` key gets the grade its look used to imply (pre-v4 look `grade`/`mono`/`flash`/`optics.grain`, incl. old overrides) — a named grade when it matches exactly (red-glow → teal, xerox → xerox), else `film` with explicit overrides (lens-bound). The renderer falls back to the same mapping (`gradeOf`) when `grade` is absent, so unmigrated JSON renders the same. Files on disk change only when the studio next saves. Verified pixel-identical on 27 frames (hero, Fall For Me, dark copy, a lens-bound and the red-glow project) against the pre-v4 renderer.
- **Presets** live in `apps/web/src/look-presets.json` (`looks` + `grades`; copied to `custom_nodes_dev/typeset_nodes/look_presets.json`, a node test keeps them equal). `hidden: true` keeps a look rendering for old projects but out of the picker (red-glow).
- **New Look fields:** `card?: boolean` (palette.card behind every unit; with marquee a full-width band; replaces the flat-card id check), `scale?: number` (look-sized text), `intensity?: number` (pop/HUD motion amount), `flicker?: number` (pop-in flicker), `finish?: 'neon'|null` (every unit and wall drawn as tubes). `outlineWidth` without `palette.outline` uses `palette.shadow`.
- **Look params** (`looks.ts:LOOK_PARAMS`, same keys as the TypesetLook node): ink, accent, card, cards, font, body, case, layout, scale, motion, glow, flicker, outline, halo, soft, tubes, scroll, hooks. Each writes `project.look.overrides` (palette/font/optics/verse merge one level deep).
- **Render route:** `&grade=<id>[:amount]` and `&overrides=<json>` alongside `&look=`.

### v4.1 (L) — scene looks: Graffiti, physical Neon
- Picker: flat-card, paper-cut, graffiti, neon, hud, xerox, ticker, lens-bound, night-code, scatter. `dreamy` and `grey-noise` are now `hidden` (still render identically for Fall For Me and the angel project), like red-glow.
- **`Look.wall: 'spray'`** (Graffiti): surface text becomes spray paint (`material` 'spray'): drawn in plane space with seeded drips (`Look.drips`, grow after each word's onset) and a stencil bridge, warped into screen space, then overspray (two blurs under the paint), uneven coverage (erosion) and **wall modulation**: multiplied by 0.4 + 0.6 × the graded footage's brightened luminance, so the paint takes the wall's light falloff, grain and cracks. Screen units (no surface) get the same finish on the background. Every non-subtitle unit sits `behind` (subject occludes via the matte; never promoted to front).
- **`Look.finish: 'neon'` + `Look.light`** (Neon): units sit behind the subject on a mount (acrylic back-plate, standoffs, cable, blacked-out return tubes). Light pass (before the behind text): tubes alone → wide blurred spill + squashed wet-floor reflection below the sign, multiplied by the footage's luminance, added (`lighter`). Relight (after the matte): a rim on the matte edges facing the light centroid (matte − matte shifted toward the light, blurred, kept inside) added, plus a soft-light colour cast; strength = light × sign power × distance falloff. Light stats come from a 64-px readback of the tube layer: deterministic, same in preview and export.
- Both read `env` = this frame's graded footage (composite renders only; text-layer exports skip modulation and light).
- **Neon tubes** under the Neon look are hollow bent-glass outlines (bloom, tube, hot core; Inter caps), matching the old generated LOUDER sign; the light pass also adds an ambient cast of the sign colour multiplied by the footage luminance. Walls without the look keep the filled-tube neon material (unchanged).
- **Graffiti wear** (uneven coverage) is computed in the text's own space (unit / surface-plane coordinates, seeded per line) so it moves with the words; only the wall-luminance modulation is screen space.
- **`layout: 'hud'`** (HUD look): every non-subtitle line becomes a head-locked HUD label (`anchor` to person0, preset `hud`), lines alive at once stack in slots; slot 0 carries the leader and readout.
- **Ticker (`motion: 'marquee'`)** is now an LED dot-matrix crawl: all shown non-subtitle words in time order enter at their onset (de-duplicated, never more than 0.9 s late, else dropped) and crawl right→left at 7 em/s; mounted on the union of the surfaces in use (middle band, behind the subject) or a screen band at 74 % height. Housing = palette.card, LEDs = palette.text, unlit dots, bloom.
- **`LineMeta.fill / karaoke / dim`** (per-line colours, win over the look; unset = unchanged): fill = text colour (look, no-look, subtitle, HUD, neon surface), karaoke = active karaoke word, dim = upcoming karaoke words drawn at full opacity in that colour.
- **Render route `&subs=0`** hides the subtitle/karaoke register for that render only (Looks showcase clips).

### v4.2 (looks round 4) — entrances, monoline neon, LED font
- **`Look.enter`** replaces the `pop` preset under the look (subtitles keep their presets; absent = authored presets, so dreamy / grey-noise / red-glow are unchanged): `wipe` (flat-card) = each word wipes in L→R over 0.26 s and the card grows with it; the card wipes out in the last 0.24 s. `paste` (paper-cut) = 3 % scale + lifted shadow settling over 0.22 s, no bounce. `spray` (graffiti) = soft-edged L→R reveal, stays. `flicker` (neon) = seeded dropouts for 0.45 s × `flicker`, then powers off at the end. `type` (hud, night-code) = 28 chars/s with a block cursor, no jitter, nothing shown before onset. `fade` (scatter) = 0.3 s in/out. `cut` (xerox, ticker) = hard cut. Exits only on lines ≥ 1 s.
- **`Look.wallScale`** (paper-cut 1.4, graffiti 1.45): surface text grows about the plane centre past the drawn quad (width capped near the wall's width).
- **Carded looks on painted walls** draw `flat` (no erosion): clean cards.
- **Neon tubes** are monoline: Inter weight 100 (hero and body) stroked fat with round joins, so each stroke is one continuous tube; passes: tight bloom, saturated glass, brighter gas, near-white core. No back-plate, cable or return tubes; small supports only. Light pass / relight unchanged.
- **HUD layout**: default anchor offset dx .24, dy −.15 (label farther from the head; leader kept).
- **Ticker**: built-in 5×7 dot-matrix glyphs (trimmed widths, 1 dark column between glyphs) on a 9-row display, round lit dots with a hot centre, tighter bloom, crawls one column at a time at 8 em/s (em = 7 rows). The stream is per line: each line is one string (words 0.9 em apart) that enters no earlier than its first word's onset; a line already shown with the same text within 3 s (e.g. wall title + HUD label) is skipped. Lines sung back to back (< 1.5 s apart) form a phrase spaced evenly at 1.2 em, started up to 0.9 s late so no line shows early; a pause starts a new phrase on its own onset. Nothing is dropped. Mounted on the surfaces whose words are on screen (from 3 s before onset to 0.5 s after end), else a screen band.
- **lens-bound** is `hidden` (code kept; existing projects render unchanged).

### v4.3 (2026-10-31) — glyph fill: the lyric drawn with the footage's light
- **`Look.fill`** `{region:'subject'|'world'|'frame'; cell?; backing?; gain?; hooks?}` (absent/null = off; any look may set it; the `glyph` preset ships with it on). A **filled line** is drawn as a fixed letter grid instead of type: the line's text (look case) tiled in reading order over cells of `cell` × min(w,h) width (default .014) and 1.9× that height, each cell's brightness from the graded footage under it (`gain`, default 1.4; the darkest cell in the region still shows its letter), over a card of `palette.card` at `backing` opacity (default .85).
  - `subject`: inside the matte, in front of the cutout (no matte → whole frame). `world`: everything but the subject, behind the cutout (text-only renders of everything keep a hole for the subject). `frame`: everything, in front. A filled line placed on a wall fills that wall instead: the grid lives in the wall's plane (perspective-correct cells sampled through the surface homography), drawn behind the subject.
  - Which lines fill (`looks.ts lineIsFilled`): shown screen or wall lines; never subtitles, head-anchored labels or in-world shots; with `hooks` (default true) only hook lines fill and the others keep the look's register. Filled lines are not built as units (`lookUnits` skips them), so nothing else of theirs is drawn.
  - Deterministic and stateless: a cell keeps its letter for the whole line (rows are offset by 4 cells so repetitions stagger; the body moving over the grid reveals a stable page), sung words light up over 3 frames (unsung words at 22 %), the word being sung takes `palette.accent`, the fill fades in over 0.15 s at the line's start and out over 0.25 s after its end. Brightness is continuous (16 atlas levels per colour), never a quantised glyph ramp, so nothing flickers at level edges. Glyphs come from a per-look atlas (hero face/weight, 16 levels × ink/accent).
  - Renderer: `drawFill` runs at the top of `renderWords` in the pinned pass only (the motion field never warps it; the crisp subtitle pass skips it), inside the optics chain (glow/blur apply; text-only exports carry it). The fill reads `env` (the graded footage of the frame), so text-only renders with a fill seek the footage and matte too (`load` loads them when a fill is on).
  - Params (studio Adjust / `TypesetLook`): `fill` (off/subject/world/frame), `cell`, `backing`; `card` edits the backing colour without switching cards on; under a fill the `hooks` toggle means "only hook lines fill". Overrides merge `fill` one level deep (`lookOf`, `setLookOverrides`, `resolve_look`, `merge_overrides`); `fill: null` switches it off.
  - Preset `glyph`: Space Mono 700 caps / IBM Plex Mono verses, ink #e8f1ff, accent #7cf7c4, card #06080a, layout `line`, `enter: fade`, glow .1, fill subject/.014/.85/1.4/hooks.
