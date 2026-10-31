# Typeset editor and renderer

The React/Vite editor in `apps/web/` runs independently with a bundled synthetic twelve-second project, audio, foreground cutout, word timings and tracks. The synthetic subject is a moving capsule, not a real person. Sample words and music are generated in the repository.

## Run

```bash
cd apps/web
npm run dev -- --host 127.0.0.1 --port 5174
```

This machine already has another application on 5173, so Typeset uses **http://127.0.0.1:5174**. The default remains 5173 for clean installations. Set the server's `TYPESET_WEB_URL` to the actual editor URL before exporting. Vite proxies `/api` and `/files` to `http://localhost:8787` (override with `TYPESET_SERVER`).

The first view is the offline sample. Save stores edits in browser local storage. In **Media**, use New project and Add your footage to create a server project, or directly upload from the sample to create one. The server supplies persisted projects, transcription, subject isolation, generation and exports. The offline sample does not invoke backend jobs.

## Controls

- Select a word in the transcript or timeline; edit its text, start/end times, placement, motion preset, font, size, color and alignment in the inspector.
- Scrub or drag the timeline. Space toggles playback; arrow keys step one frame. Audio starts muted and has a mute toggle.
- The waveform is decoded from actual project audio. Empty/audio-free projects show an absent-waveform state.
- Line position, anchor offsets and alignment apply to words sharing the selected word's line and placement. Other style edits affect only the selected word. Lines shrink to fit the composition width.
- Behind placement requires a foreground cutout; Anchor requires tracks. Media → Isolate subject prepares both. Missing tracks hold the last point for at most six frames, then hide the anchored line.
- In-world words are excluded from the deterministic text layer and appear through a generated shot. Select In-world, provide a shot direction and Generate with LTX. Pending/failed shots do not pretend to be complete.
- Export requests an MP4 composite and MOV/WebM transparent text overlays. Completed files are linked from the status bar using backend-returned paths.

## Renderer contract

`#/render?project=<id>&layer=text|composite&server=http://127.0.0.1:8787` loads project/assets/fonts and exposes `window.__typeset` with `ready`, `frames`, and asynchronous `renderFrame(i)`. The single `#stage` canvas uses project pixel dimensions; no CSS scaling or background is applied in render mode. Screenshot with device scale factor one and transparent background.

`text` includes all non-inworld text with transparency. `composite` draws background or active generated shot, behind text, foreground cutout, then overlay/anchor text. A generated shot suppresses the original foreground cutout. Additional `text-behind` and `text-front` modes are available for external compositors.

All motion uses timeline time. Pop combines a closed-form damped spring with deterministic glyph offsets. Karaoke highlights the active word, typewriter reveals glyphs, and HUD draws the tracked label frame. Video sources seek before painting the visible canvas, avoiding half-composited frames. Rendering the same frame before and after a distant seek checks frame-order independence.

## Verification

```bash
cd apps/web
npm run build
# From repo root, with local web server and Playwright installed:
TYPESET_WEB_URL=http://127.0.0.1:5174 server/.venv/bin/python apps/web/scripts/check_browser.py
```

Browser checks cover word editing, playback, repeatable random seeking, alpha text including actual Playwright screenshots with transparent HTML/body backgrounds, opaque composites, and the six-frame track hold boundary. Screenshots go to `outputs/web-check/`. The server owns integration checks for export codecs and foreground/overlay ordering. Avoid editing web source during exports served by Vite; HMR can reload the renderer. A production build avoids that development-only issue.

Regenerate the sample with `server/.venv/bin/python apps/web/scripts/make_sample.py`. Bundled fonts retain OFL license files in `apps/web/public/fonts/`.

## v2 (2026-10-31): auto-placement, surfaces, reframe, preset polish

Implements SCHEMA v2 §A–§C in the browser. Code: `src/placement.ts` (occupancy + auto-place), `src/geometry.ts` (homography mesh warp, crop helpers, client virtual camera), `src/reframe.ts` (client-side reframe/re-layout), `src/renderer.ts` (all drawing), `src/App.tsx` (editor tools). Everything stays a pure function of frame index; preview equals export.

### Auto-placement (§B)
- Occupancy source, in priority order: `analysis.occupancy` (server), `/fixtures/<id>/occupancy.json` (local fixture), coarse grid from `tracks.json` bboxes. Reframed projects resample source-space occupancy through the per-frame crop.
- `isAutoPlaced(word)`: `autoPlace` if set; otherwise **on for every `behind` line** (deviation from the schema, which says "without explicit position") and for `overlay` lines without a `position`. For behind lines an explicit `position` becomes the *preferred spot* (distance penalty), so existing projects keep their composition unless the subject would hide the text. That is how the proof projects were fixed without editing their data.
- Scoring per line (one position for the whole span): the box is cut into 8 vertical slices; a slice is "blocked" from 10% to 40% subject coverage; loss = 0.5 × mean over ≤24 sampled frames + 0.5 × worst frame. Tolerance grows with type size (huge titles may be partly covered, which is the "behind" look; captions need clean space). Then thirds preference (no hint) or distance to the hint, repulsion from other lines visible at the same time, title-safe margins (4.5% / 5.5%). Coverage integrals use summed-area tables, so it is fast enough to recompute on every edit (cached by a word/style signature).
- If nothing fits, it shrinks (1, .86, .74, .62, .52). If a **behind** line is still unreadable everywhere (a full-frame close-up), it is **promoted to the front layer** at full size in the least-intrusive spot ("keep visible").
- Lines wrap into stacked rows when one row would shrink below 45% (landscape) / 85% (portrait).
- Editor: Inspector → "Find readable space" checkbox (line-wide). `#/render?...&autoplace=0` renders authored positions (before/after).

### Surfaces (§A)
- `placement:'surface'` + `surfaceId`. Text is laid out on an offscreen canvas with the key-frame quad's aspect, then warped with a 12×12 piecewise-affine mesh of the homography (exact at vertices). Drawn in the behind layer. Track: `surface.track` JSON, hold ≤6 frames, then hide; without a track, the static corners. Non-convex quads are skipped.
- `Surface.material` (web addition): `paint` (default; seeded value-noise erosion + hard-light blend so the plate texture shows through), `neon` (glow + tube outline + hot core, screen blend), `flat`. Blend modes apply only in `composite`; the text layers use normal alpha.
- Editor: "▱ Place on surface" in the preview toolbar (or Placement → Surface). Click TL, TR, BR, BL on the paused stage; drag handles; a perspective grid previews the plane; "Place “…” here" creates the Surface at the current frame, moves the selected line onto it, saves, and calls `POST /api/projects/{id}/surfaces/{sid}/track` (polls; on 404/405 shows "Tracking unavailable"; the static quad is kept). Inspector: choose surface, material, Redraw corners, Track.

### Reframe (§C)
- With `frame.crop`, bg/matte are drawn through the per-frame crop window; tracks, occupancy and surface corners are mapped source→output. Surface lines hide when the quad leaves the crop.
- "▯ Make vertical" (header) → `POST /api/projects/{id}/reframe {aspect:'9:16'}` → poll → opens the new project. If the endpoint is missing, it falls back to the client preview.
- "Preview 9:16" toggle: side-by-side original | client-side 9:16 (`reframeProject` + `cropFromTracks`: zero-phase smoothed follow of person0 with a dead zone). In a reframed project the toggle shows the source alongside. `#/render?...&reframe=9:16` renders the client reframe.

### Presets
- Pop: each word is invisible until its own start, then springs in (true per-word stagger).
- HUD: min 5% of frame height; corner-bracket box over a dark backdrop; monospaced tag `PERSON0 · F0042 · 0.93` (track id, frame, pseudo-confidence); a leader line + target dot to the tracked point; deterministic jitter for 3 frames after each word onset; the box is clamped on screen.
- Behind words: dark legibility edge (soft shadow + thin outline), `style.shadow` 0..1, default 0.5 for behind (Inspector → Edge shadow).

### Fixtures and verification
- `apps/web/scripts/make_occupancy_fixture.py <id>…` builds occupancy from matte PNGs → `public/fixtures/<id>/occupancy.json` (only used when the project has no `analysis.occupancy`).
- `apps/web/scripts/make_surface_fixture.py <id> <sid> <keyFrame> TL TR BR BL`: an LK + RANSAC planar tracker into `public/fixtures/<id>/surfaces/<sid>.json`.
- `public/fixtures/walk-surface-{paint,neon,flat}.project.json`, `walk-surface-server-track.project.json`: copies of the walk project with a surface line; load with `#/render?project=<id>&src=/fixtures/<file>`. `assetUrl` passes paths starting with `/` through as web-origin URLs.
- `apps/web/scripts/verify_frames.py <id> <prefix> <frames…> [--src=…] [--reframe=9:16] [--autoplace=0]` → PNGs in `apps/web/.verify/`; `scripts/sheet.py` tiles them.
- `apps/web/scripts/check_v2_editor.py [id]`: drives the surface tool, auto-place toggle, 9:16 preview and the reframe fallback against a real project with PUT/track/reframe intercepted (no writes), and checks render-order determinism for surface and reframe.

### Known gaps
- In 9:16 the client crop (`cropFromTracks`) and the server's `crop.json` differ slightly; the server's wins whenever `frame.crop` exists.
- Surface text in a reframed project uses the key-frame aspect from source space; very oblique walls may look compressed. No auto-quad from depth yet.
- Promotion to the front ignores faces specifically (it only minimizes coverage); a face detector term would help in close-ups.

## v3 (2026-10-31): looks / art direction

Contract: `docs/SCHEMA.md` → "v3 additions". Code: `src/looks.ts` (presets, fonts, API for the studio UI; see the TODO block at its top), `src/renderer.ts` (look styling, layout units, optics), `src/placement.ts` (`avoidKey`/`corner`/`noShrink`/`strict`), `src/geometry.ts` (`drawMapped` mesh warp for lens bend).

- Looks: `red-glow`, `lens-bound`, `paper-cut`, `ticker`, `flat-card` (+ `default` = none). Fonts added (all verified OFL / Apache, licences in `public/fonts/`): Big Shoulders Display, Permanent Marker, Instrument Serif (+italic), Rubik Wet Paint, Archivo Narrow, Silkscreen. `loadFonts()` registers every face in `FONTS` with the FontFace API, so the render route doesn't depend on studio CSS.
- No look → v2 code path, pixel-identical (checked on walk/talk/surface frames).
- P1 shipped: lens warp (text only), fake extrusion on surface text (`optics.extrude`, on in lens-bound), `write` preset (jittered left→right reveal). Not shipped: text on a path, card mode/beats, P2.
- Render route: `&look=<id>` previews a look without saving.
- Checks: `scripts/check_looks_api.py` (API + quiet + hero rules), `scripts/check_hero_acceptance.py <id> [look]` (hero behind, satellites ≤10% overlap), `scripts/check_preview_export.py <id> <look>` (studio canvas vs `#/render`, 3 frames), `scripts/measure_optics.py` (P0b cost).

## Studio v3 (2026-10-31): stage-first editor

The editor (`#/studio`) was rebuilt as an instrument-like studio. Code lives in `apps/web/src/studio/` and is **lazy-loaded** from `App.tsx`, so the `#/render` export route never imports studio code. A studio syntax error cannot break exports. `RenderPage` and `window.__typeset` are unchanged.

Layout (1440×900 and 1920×1080): top bar · [Pipeline / Media | Stage | Look + Line] · Arrangement · status.

- **Stage** (`Studio.tsx`, `StageOverlay.tsx`): the composition is fitted exactly to the free space, and overlays share its pixel box. Guides: **Regions** (R) shows each visible unit's solved box, the auto-place clearance pad, coverage %, "promoted to front", the preferred spot with a leader line, and tracked wall quads. **Subject** (O) shows an occupancy heatmap with its source (ComfyUI matte, fixture, or track-box fallback). **Anchor** shows the HUD head point. Drag a box to move the line: overlay/behind lines set the preferred `position`, starting from where the line is currently drawn, and HUD lines change `anchor.dx/dy`. Boxes come from the renderer's `units()` (hero/satellite split under looks), with a fallback to `lines()`. **Place on surface** (W) works as before. **Preview 9:16** shows the side-by-side view.
- **Looks** (`LookPicker.tsx`): consumes `LOOKS`, `setLook`, `setLineMeta`, `setWordHero`, `wordIsShown`, `lineIsHook`, `heroWordId` and `FONTS` from `looks.ts`. Thumbnails are rendered live by a second `StageRenderer` at the playhead, one pass per look once the playhead settles (paused only). Keys 1–6 switch looks. **⊞ Looks** or G opens a 3×2 compare sheet over the stage.
- **Line inspector** (`LineInspector.tsx`): role (Caption = overlay, Behind, HUD = anchor + hud preset, Wall = surface, In-world), hook and visible flags (`lineMeta`), hero word (★ uses `setWordHero`), Find readable space, X/Y position and alignment, edge shadow, wall material/redraw/track, motion preset (incl. `write`), and line-wide font/size/fill. Word text, in/out, word colour, hide word and remove sit behind the **Word details** disclosure.
- **Arrangement** (`Timeline.tsx`): one lane per line, coloured by role, with hook (pink) and hidden lanes. A line is a region with a title strip: drag the strip to move the line, drag the right edge to set when it leaves, and drag a word clip to slip its onset. Clips end at the next word's onset, so they never stack. When clips get too narrow, the lane shows the line text over onset ticks. The ruler has a loop strip (drag to set; L loops the selected line), a map band (beats.json sections and hook spans), time ticks and a beat grid (downbeats stronger). Quiet stretches (≥ 0.5 s with nothing visible) are hatched across the lanes. Snap targets beats, word edges and frames (Shift bypasses snap). Zoom with the slider or ⌘/Ctrl+scroll. The audio lane is a min/max peak waveform and stays pinned.
- **Pipeline** (`PipelinePanel.tsx`, `pipeline.ts`): Words, Subject matte, Occupancy, Planar track, Reframe, Beats and In-world shot, each with an LED state, engine, the path that ran, timing, a node chain and Run/Re-run. State comes from project analysis fields plus `GET /api/jobs?projectId=` (`result.engine` is `comfy` or `fallback`, plus `elapsedSeconds`). Older jobs without `engine` show as an "in-process run". The header shows `/api/health` (ComfyUI version/URL) and how many Comfy workflows ran. **Workflow ↗** opens a node view of the API JSON. Copies of `workflows/*.api.json` are served from `public/workflows/`. Re-copy them when a workflow changes.
- **Output** (top bar): frame/aspect, ▯ Make vertical, side-by-side preview, format checkboxes (MP4 composite, MOV/WebM alpha text layers), Export with progress, and recent export jobs with file links.
- **Saving**: autosave is a debounced PUT (1.2 s). It is suppressed while a job runs, and every job's result is re-fetched before the next PUT (docs/server.md). The sample still saves to localStorage.
- Keys: Space, ←/→ (frame), ⇧←/→ (1 s), Home/End, L, H (hide line), G, O, R, W, 1–6, Esc.

Verification: `check_browser.py` (opens Word details before editing) and `check_v2_editor.py` (selects through arrangement clips; Make vertical sits in Output). `scripts/shoot_studio.py <name> [project] --do=looks|timeline|pipeline|surface|output|occupancy [--look=N --frame=F --w --h]` intercepts every PUT/POST and writes `apps/web/.verify/studio/<name>.png`. Finals: `final_overview.png` (lens-bound), `final_looks.png`, `final_timeline.png` (demo song with ComfyUI beats/sections), `final_pipeline.png` (BiRefNet matte graph), `final_surface.png`.

Known gaps: no undo. Stage boxes for `constellation`/`stack` units follow the renderer's units, but dragging a satellite moves the whole line's hint. There is no per-role lane view yet. Look thumbnails pause during playback.
