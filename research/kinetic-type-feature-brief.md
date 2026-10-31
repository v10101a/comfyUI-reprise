# Feature brief: art direction for Typeset (look packs, hierarchy, optics)

Hand-off for an agent editing the Typeset renderer. Background and references: `research/kinetic-type-references.md`.

## Why
The user rejected the current examples as "too normal". Typeset's motion presets are fine. What's missing is **art direction and composition**, which the reference videos all share:
- One rule for the whole piece: 1 font, 2–3 colors, a texture.
- Extreme scale (a hero word at 30–60% of frame height, often bleeding off the frame).
- Hierarchy within a line.
- Text that inherits the camera's optics (bloom, blur, lens warp).
- Stretches with no text.

Text-behind-subject alone is a stock CapCut template now, so it is not a differentiator.

## Constraints
- The renderer must stay **deterministic**: output is a pure function of (project, analysis, t). Preview and export must match. Never use `Math.random()` or wall-clock time. Use `hash01(seed)` from `apps/web/src/renderer.ts`.
- All changes are additive and optional, and existing projects render unchanged. Record new contract fields in `docs/SCHEMA.md` under a "v3 additions" heading.
- Fonts are OFL/Apache only, bundled in `apps/web/public/fonts/` with their license files, and loaded in `loadFonts()`.
- Deadline: demo on 2026-11-02. Do P0 first. Each item must be shippable alone.

## P0 (do these first)

### 1. `Project.look`: one-click art direction
```ts
type Look = {
  id: 'default' | 'red-glow' | 'lens-bound' | 'paper-cut' | 'ticker' | 'brat';
  font: { hero: string; body: string };         // bundled families
  palette: { text: string; accent: string; shadow?: string; card?: string }; // card = full-frame card bg
  texture?: 'none' | 'grain' | 'paper' | 'halftone';
  optics: { glow?: number; grain?: number; chroma?: number; motionBlur?: number; lensWarp?: number }; // 0..1
  grade?: { tint: string; amount: number };     // tint the footage toward the look
  layout: 'line' | 'hero' | 'constellation' | 'stack';
  quiet?: 'none' | 'hooks-only';                // see item 5
};
// Project.look?: Look  (absent = current behaviour)
```
- Look values override `Project.style` defaults, and per-word `style` still wins.
- Starting values, derived from the references:
  - `red-glow`: heavy condensed sans, #ff1a1a, glow 0.8, grade tint #0f6f7a at 0.35, layout `hero`.
  - `lens-bound`: white heavy grotesk with lowercase green (#7dff4a) verses, motionBlur 0.7, chroma 0.4, lensWarp 0.5.
  - `paper-cut`: rough condensed display, cream #efe6d2 / black / red #c8243a, texture paper, layout `hero`.
  - `ticker`: amber LED-style mono, glow 0.6, scrolling surface text.
  - `brat`: lowercase narrow sans, blur 0.3, single flat card colour.
- Editor: a look picker that restyles the whole project. This is the demo moment, so make switching fast and visible.
- **Accept when:** the same project renders visibly different under each look in preview and in export, and no per-word edits are needed.

### 2. Hero layout (`layout: 'hero'`)
- For each line, pick one hero word:
  - `Word.hero === true` if set manually,
  - otherwise the longest non-stopword,
  - with ties broken by the later `start`.
- Hero size is 0.30–0.60 of frame height. Clamp so at least about 60% of the glyph stays in frame, which allows a deliberate bleed.
- Satellites are 0.03–0.05 of frame height, placed in the least-occupied cells (reuse `autoPlace` / `OccupancySource` in `placement.ts`), at least 1 hero-height away from the hero's centre, and stable for the line's duration.
- The hero defaults to placement `behind` when a matte exists.
- `constellation` is the same without a hero (all small, spread through negative space). `stack` is one word per row, left-aligned, in a corner.
- **Accept when:** on the dancer project, each line shows one huge word partly occluded by the dancer, and its satellites never overlap the dancer for more than 10% of the line's frames.

### 3. Optics pass (renderer, text layers only)
Apply in this order:
1. Motion blur along the anchor/surface velocity: N = 6 sub-samples at `t ± shutter/2`, averaged, with shutter = 0.5 frame × `motionBlur`.
2. Chromatic offset: R and B channels shifted ±(chroma × 0.004 × width) along the velocity direction, or along x if static.
3. Glow: blurred copy, screen-blended, radius = glow × 0.03 × height.
4. Grain: deterministic noise seeded by frame index, applied after compositing.

The footage grade (`look.grade`) is a single tint layer over the background video before text.
- **Accept when:** export matches preview frame for frame (spot-check 3 frames, pixel diff < 2%).

### 4. Fonts
Add a variable-width display face (Anybody or Big Shoulders Display), a marker hand (Permanent Marker), an editorial serif (Instrument Serif), and one textured display face (Rubik Wet Paint or Rubik Glitch). Verify each license, ship the license files, and extend `loadFonts()`.

### 5. Quiet
- `Word.hidden?: boolean`, plus `look.quiet = 'hooks-only'`.
- Mark hook lines with `Line.hook` or a repeated-lyric heuristic (lines that appear 2+ times are hooks).
- Hidden words still stay in the timeline UI, greyed out.

## P1
- **Text on a path.** `Word.path?: { kind: 'arc' | 'circle-head' | 'contour'; bend: number }`.
  - Arc: bend over a circle.
  - Circle-head: orbit the `person0` head track.
  - Contour: run along the matte outline, sampled from the matte at line start.
- **Lens-matched text.** Barrel warp of the text layer only: `r' = r(1 + k r²)`, with k = `lensWarp × 0.35`, centred on the frame.
- **Fake extrusion on surfaces.** Draw N = 12 copies offset along the surface's estimated normal (approximate as the quad's down-right diagonal), darkened progressively, then draw the face on top. Hooks use this under `lens-bound`.
- **Card mode.** `GenShot`-like full-frame cards: flat `palette.card` background with the line set huge, cut on beats. Beat times come from a `analysis/beats.json` (librosa) job.
- **Write-on preset.** `Preset` gains `'write'`: a left→right reveal with a jittered edge (`hash01`). Pairs with the marker font.

## P2
- **Type world.** Replace the background with a flat-colour typographic set and keep the subject cutout with a contact shadow. The camera pans across giant letters.
- **Text as light.** Surface text also projects onto the subject: masked by the matte, displaced by subject luminance, with an additive spill blurred onto the wall.
- **Generated material end card.** The hook word as chrome, liquid or smoke via the existing `inworld` / remote MiniMax path. Use it for one beat only.

## Demo examples to produce after P0
1. **Night walk** under `lens-bound` (Concept A, "Neon Rain"), with an extruded hook on the wall if P1 lands.
2. **Dancer** under `red-glow`, using hero layout behind the subject.
3. The same clip shown in 3 looks side by side, as the "one click" proof.

---

## Coordinator revisions (2026-10-31, approved by the user) — these override the sections above where they conflict

1. **No artist-branded looks.** Rename `brat` → `flat-card` (lowercase narrow sans, slight blur, one flat card colour). No look names, colours-as-signatures or copy that reference a real artist or release. Competition rule: "free of unlicensed IP".
2. **No `Line` type exists** (lines = words grouped by `lineId`). Use `Project.lineMeta?: Record<lineId, { hook?: boolean; heroWordId?: string; hidden?: boolean }>` plus `Word.hidden?: boolean`. Hook fallback: lines whose normalized text repeats 2+ times; hero fallback: longest non-stopword (ship a small English stopword list), ties → later start.
3. **Layer rule for optics.** Glow, motion blur and chroma apply to the text layer, so they appear in the alpha overlay exports too. **Grain and `grade` apply only in the composite layer** (never write grain into the transparent overlay; the grade is a footage treatment).
4. **Orientation-aware sizing.** Hero size is a fraction of `min(width, height)`; clamp horizontal bleed so ≥60% of the word stays in frame in both 16:9 and 9:16. Acceptance must include a reframed (9:16) project.
5. **Store looks by reference:** `Project.look?: { id: LookId; overrides?: Partial<Look> }`. Presets live in code (`apps/web/src/looks.ts`), so tuning a preset updates every project and the picker is a one-field switch.
6. **Split P0.** P0a (ship first): look schema + presets + `setLook` API for the UI, fonts, hero/constellation/stack layouts, quiet, glow, grade, grain. P0b: motion blur + chromatic offset (6 sub-renders per frame; measure export cost and cap it).
7. **Looks style everything:** surface (wall) text takes the look's hero font/palette/glow; the HUD keeps its mono face in every look but takes the palette.
8. **Ownership:** R owns the renderer and look system (`renderer.ts`, `placement.ts`, `geometry.ts`, new `looks.ts`, fonts, SCHEMA "v3 additions"). The studio UI (`App.tsx` and its components/styles) is being redesigned in parallel by **U**; R exposes a small API U consumes: `LOOKS` (id, name, swatch colours, font names, one-line description), `lookOf(project)`, and project mutators for `look`, `lineMeta`, `Word.hero`, `Word.hidden`. Don't restyle the editor chrome yourself.
9. **Demo examples** (after P0a): night walk → `lens-bound`, dancer → `red-glow` with hero behind the subject, and one clip rendered in 3 looks side by side. The content agent (C) restyles the hero piece with these; R provides the looks, not the final edit.

---

## Addendum: tracking-driven text (`Project.fx`), 2026-10-31

This adds to the brief above. It doesn't change P0a/P0b.

Background: the "Tracking-driven text" section of `research/kinetic-type-references.md`. Seven prototype stills of these effects, rendered on our own footage, are in the research board. The prototype script lives in the session scratchpad; `blob_lyrics`, `contour_text`, `text_rain`, `body_fill`, `glyphize` and `echo_trail` are about 30 lines each of OpenCV + PIL.

**Shape.** Effects are time-ranged layers that *consume the words* in their range instead of the normal line layout:
```ts
type FxKind = 'blob-lyrics' | 'motion-blobs' | 'contour' | 'rain' | 'fill' | 'glyph' | 'echo';
type Fx = { id: string; kind: FxKind; start: number; end: number; lineIds?: string[];
            params?: Record<string, number | string | boolean> };   // per-kind, all optional
// Project.fx?: Fx[]   words covered by an active fx are drawn by the fx, not the line layout
```
The words come from the existing timeline. The current word is the one whose `start <= t < end`. Effects that show several words (blob labels, rain letters, fill text) use the line's words in order.

**Analysis (server, OpenCV, one job `POST /api/projects/{id}/analyze/fx`).** It writes small JSON files so the renderer stays deterministic and cheap:
- `analysis/contours.json`: the per-frame simplified outline of the largest matte component. Take `cv2.findContours` on the matte blurred and thresholded at 0.5, then `approxPolyDP` (ε ≈ 1.5 px at 1/2 res). Normalised coordinates.
- `analysis/blobs.json`: per frame, up to 12 boxes `{x,y,w,h,score,id}`. Modes:
  - `bright`: V + 0.6·S above the frame's 97.5th percentile, dilated 9 px.
  - `motion`: |f − f−3| blurred above 18, closed 25 px, split into ~90 px cells.

  Keep ids stable across frames by greedy IoU matching, so labels don't hop between boxes.
- `analysis/rain.json`: a deterministic letter simulation, stepped from frame 0 with a fixed seed. Letters fall at a constant speed and stop on the first matte pixel below them (the contour's upper edge). They release when the support disappears for 3 frames. Store per-frame `[char, x, y, colorIdx]`.

**Renderer, per kind** (all in the text layer, so they show in overlay exports):
- `blob-lyrics` / `motion-blobs`:
  - Corner brackets per box, with the current line's words as labels in reading order (sorted by x).
  - Thin connector lines between them.
  - Optional tiny normalised coords.
  - The subject's box is highlighted in the accent colour.
  - The box opens with `spring()` on word start.
- `contour`: glyphs along `contours.json`, offset outward by 0.03·H. The marquee moves at `params.speed` px/s, which defaults to one character per beat if `beats.json` exists.
- `rain`: draw `rain.json`.
- `fill`: tile the line's text (hero font) and clip it to the matte (`globalCompositeOperation='destination-in'` with the matte frame). Glyph brightness follows the footage's luminance. `params.invert` = text everywhere except the body.
- `glyph`: cell grid (cell = 0.018·H) inside the matte, filled with the line's letters in order. Colour comes from the footage's luminance. The background is darkened to `params.bg`.
- `echo`: outlines from frames f−6, −12, −18, −24 at rising alpha, each labelled with the word that was current at that frame.

**Accept when:**
- Each kind renders in preview and export identically (pixel diff < 2% on 3 frames).
- With fx absent, the output is unchanged.
- `blob-lyrics` labels don't swap between boxes over 1 s of the night walk.
- `rain` letters visibly rest on the dancer's head and shoulders.

**Priority.** `fill`, `glyph`, `echo` and `contour` need only the matte plus `contours.json`, so do them first. `blob-lyrics` and `motion-blobs` come next. `rain` comes last.
