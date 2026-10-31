# Studio restyle plan (v3 → paper skin, viola.city sentiment)

**Read first: `DESIGN_LANGUAGE.md` → "Rule #1: NO UNNECESSARY TEXT". Overrides anything below that adds copy.**

Scope: `apps/web/src/studio/studio.css` (all selectors scoped under `.studio`), plus label text in `Studio.tsx`, `Timeline.tsx`, `LookPicker.tsx`, `PipelinePanel.tsx` and `LineInspector.tsx`. Token source: `docs/design/tokens.css`. Copy table: `DESIGN_LANGUAGE.md § Copy voice`.

The approach is mostly a **token swap**. studio.css already routes most colour through `--bg --p1..3 --ln --tx --lime …`, so step 1 re-points those variables and steps 2 onward fix the hard-coded hexes and idioms.

## 0. Setup

- Import the fonts. Either copy the `@import` line from tokens.css into `style.css`, or (better for offline and render mode) bundle `IBMPlexMono-{Regular,Italic,Medium,SemiBold}.ttf`, `Newsreader[opsz,wght].ttf` and `Newsreader-Italic[opsz,wght].ttf` into `public/fonts` with `OFL-*.txt`, and add `@font-face` rules next to the existing ones.
- `style.css :root`: font-family `var(--font-mono)`, background `#c7c7c7`, colour `#2e2e2e`. Repoint `--lime` to `#2e00fd`. This keeps showcase and boot screens consistent, and `.primary` / `.brand-mark` pick it up. Scrollbar thumb: `#8e8e8e`, radius 0.
- Theme toggle: a sun/moon icon button in the top bar sets `data-theme` on `<html>` and stores it in localStorage (that's what she does). Default to light.

## 1. Re-point the studio variables (`.studio{…}`, line 2)

```css
.studio{
  --bg:#c7c7c7; --p1:#c7c7c7; --p2:#cacaca; --p3:#cacaca;          /* panels share the page grey; hover = bright */
  --ln:#76767666; --ln2:#767676;                                    /* used as dotted */
  --tx:#2e2e2e; --tx2:#5e5e5e; --mut:#8e8e8e; --dim:#a3a3a3;
  --lime:#2e00fd; --lime2:#6c76ff;                                  /* name kept to avoid touching TSX; it's the accent */
  --warn:#a15c00; --err:#d1001f;
  --r-caption:#2e2e2e; --r-behind:#7a3fd1; --r-hud:#2e00fd; --r-anchor:#2e00fd; --r-wall:#00837a; --r-inworld:#b0428f;
  --mono:"IBM Plex Mono",ui-monospace,monospace; --serif:"Newsreader",Georgia,serif;
  font-family:var(--mono); font-size:12px;
}
:root[data-theme=dark] .studio{
  --bg:#1b1f11; --p1:#1b1f11; --p2:#3b4028; --p3:#3b4028; --ln:#76767655; --ln2:#767676;
  --tx:#c7c7c7; --tx2:#a3a3a3; --mut:#7d847d; --dim:#53554b; --lime:#b2a2cd; --lime2:#949bfb;
  --r-caption:#c7c7c7; --r-behind:#b2a2cd; --r-hud:#949bfb; --r-wall:#7fc8b8; --r-inworld:#cda8cd;
}
```
Then search-and-replace the hard-coded dark hexes: `#0d0f0b #0e100c #121410 #141910 #1a2010 #1f2614 #232b14 #262b20 #1a1f13 #141a0c #1b1f17 #242a1d #2d3a14` become `var(--p2)` (or `transparent` for inputs). `#141a06` (text on lime) becomes `#fff`, and `#d8ff62xx` alphas become `color-mix(in srgb,var(--lime) xx%,transparent)`.

## 2. Global controls

| Selector | Change |
|---|---|
| `.studio button` | `background:transparent; border:1px solid transparent; border-radius:0; font:italic 12px var(--mono); color:var(--lime)`. This is her link-pill. |
| `.studio button:hover` | `background:var(--p2); box-shadow:inset 0 0 5px 5px #0000ff1a,0 0 30px #c8c8ff80; border-radius:.125rem; font-style:normal`. Hover un-italicises (sampled). |
| `.studio button.primary` | `background:var(--lime); color:#fff; font-style:normal; font-weight:500; border-radius:0`. Hover: `box-shadow:0 0 25px #c8c8ffe6`. **One primary per screen** (render). |
| `button.ghost`, `button.link` | Same as the base button; drop the underline and use italic blue. |
| `input, select, textarea` | `background:transparent; border:0; border-bottom:1px dotted var(--ln2); border-radius:0; font:12px var(--mono)`. Focus: `border-bottom:1px solid var(--lime)`. |
| `kbd` | `font:10px var(--font-pixel, Silkscreen); border:1px solid var(--ln2); border-radius:0; background:var(--p2)` |
| `.fld>label, .lbl, .sec-head>span:first-child, .tg-label, .op-h, .tl-title b, .word-details summary` | Remove `text-transform:uppercase; letter-spacing`. Use `font:italic 11px var(--mono); color:var(--mut)`. Add a trailing `/` via CSS (`::after{content:'/'}`) for section heads. |
| `.seg button.active`, `.tool-group button.active`, `.tl-tools .tog.on`, `.op-btns button.on` | `background:var(--p2); color:var(--tx); box-shadow:inset 0 0 5px 5px #0000ff1a; border-color:transparent` (her `.pill.active`). |
| `accent-color` everywhere | `var(--lime)` (now blue). |
| `@keyframes pulse` | Replace with the glow: `text-shadow` alternating between `#949bfb` and `#c7c7c7` over 1s (her clock). |

## 3. Top bar (`.s-top`, `.s-brand`, `.s-studio`, `.s-proj`, `.s-save`, `.comfy-pill`)

- Height stays 44px. Use `border-bottom:2px dotted var(--ln2)` and a `transparent` background.
- **Brand:** replace the Anton "T" mark with `typeset` in `var(--serif)` 20px blue. `.s-studio` becomes `studio ✦` in `italic 11px mono`, `color:var(--mut)`, no border.
- **Project name input:** Newsreader 16px, ink colour, dotted underline on hover only.
- **`.s-save`:** text `saved 10:22` (mono 11px, mut). When dirty, show `unsaved ·` with the dot in blue and no lime glow.
- **`.comfy-pill`:** lowercase `comfyui ●`. The dot gets the glow-pulse animation when busy.
- **Render button:** the only `.primary`, labelled `render →`. Output popover: `background:var(--bg); border:2px dotted var(--ln2); border-radius:0; box-shadow:0 10px 15px -3px #0000001a`. `.op-sec` uses dotted dividers. `.op-ar` (aspect swatch) gets a `1.5px solid var(--lime)` border.
- **Theme toggle** (new): a 32px square with `--shadow-float`, showing ☀ or ☾ in blue or lavender, placed at the far right.

## 4. Left panel: tabs, pipeline, media

- **`.s-tabs`:** turn into a tree header. Buttons read `pipeline/ media/ projects/` in italic mono. Active: `color:var(--tx); font-style:normal; border-bottom:2px dotted var(--lime)`. `.s-left` gets `border-right:2px dotted var(--ln2)`.
- **Pipeline as a `tree` listing.** In `PipelinePanel.tsx`, swap the LED rail (`.step-rail/.step-led/.step-wire`) for a text prefix: `├──` for each step and `└──` for the last (`color:var(--mut)`). State is a single glyph in front of the title: `✓` blue (done), `↺` warn (fallback), `✕` err (failed), `●` with glow-pulse (running), `○` mut (idle). CSS-only fallback: hide `.step-led`, give `.step-wire` `width:0; border-left:1px dotted var(--ln2)`, and set the `.st-done .step-title` colour to var(--lime).
- `.comfy-head`: no gradient and no box. It becomes a status block like her "Current Whereabouts":
  ```
  comfyui
  v0.3.x · 127.0.0.1:8188 · local
  3 workflows ran · 41 s of model time
  ```
  Use mono 12px with a dotted rule below.
- `.eng` badges: Silkscreen 9px with no border. `.eng-comfy` is blue text, not a filled chip.
- `.step-nodes span`: transparent background, no border, italic mut, joined by ` → `.
- `.step-progress`: a 2px blue bar plus the message in mono 11px, with no box.
- **Media.** `.upload-zone` gets `border:2px dotted var(--ln2) !important; background:transparent !important`. On drag-over, apply `--glow-hover`. Copy: `drop a video or a song here` / `stays on this computer`. In `.media-card`, the type badge becomes Silkscreen 9px blue, and thumbnails use `filter:var(--img-rest)` until hovered.

## 5. Stage (`.s-stage`, `.stage-bar`, `.stage-border`, overlays)

- `.s-stage` background: flat `var(--bg)` with no radial gradient. A mid grey is also the right neutral for judging footage colour.
- `.stage-border`: `box-shadow:0 4px 6px -1px #0000001a` (shadow-md), plus `outline:1px solid rgba(20,20,17,.25)`.
- `.stage-bar` / `.tool-group`: italic-mono tool buttons. Separators become `border-right:1px dotted var(--ln2)`. Remove the glyph-prefix clutter (`↖ ▱ ▯ ⊞`) or keep it only in `title`.
- `.stage-label`: `background:var(--lime); color:#fff; font:500 10px var(--mono); letter-spacing:0`.
- `.stage-look` (look name in the corner): `font:italic 13px var(--serif); background:none; color:#fff; text-shadow:0 0 6px #000`.
- SVG guides: `.g-line.sel .g-box` stroke `var(--lime)` with fill `#2e00fd0a`, and `.g-knob` fill blue. `.g-label` uses `font-family:var(--mono)`, weight 500, no letter-spacing. Set the dashed default to `stroke:#ffffff88; stroke-dasharray:2 3` (dotted feel).
- `.loading` / `.stage-loading`: grey veil (`#c7c7c7d0`) with `loading…` in blue mono and a glow pulse.
- `.surface-bar`: `background:var(--p2); border-top:2px dotted var(--ln2)`.
- **Transport.** `.time-display` uses mono 13px ink with the frames part in `var(--mut)`. `.play-button` becomes a 30px **square** (`border-radius:0`), blue, with a white glyph. Hover gets the lavender halo.

## 6. Right panel: look picker + inspector

- `.panel-sec`: `border-bottom:2px dotted var(--ln2)`. `.sec-head>b` (current look or line name) is `font:400 18px var(--serif); color:var(--lime)`, the same as her project titles.
- **Look cards** are her project cards in miniature.
  - `.look-card`: transparent, no border, square.
  - `.look-thumb img`: `filter:var(--img-rest)` at rest, then `filter:none` on `.look-card:hover` or `.active` with `transition:filter .2s`. Add `url(#noisy)` if the SVG filter is mounted. This is the signature move: the active look is the only one in focus.
  - `.look-card:hover`: `background:var(--p2); border-radius:.75rem; box-shadow:inset 0 0 20px 20px #6464c81a,0 0 25px #c8c8ffe6`.
  - `.look-card.active`: `outline:1px solid var(--lime); outline-offset:2px`. Drop the lime fill.
  - `.look-name`: `font:400 13px var(--serif); color:var(--lime)`. On card hover, apply `filter:blur(2px)` to the name (sampled, playful; skip it if it hurts usability).
  - `.look-swatch i`: 7px squares (`border-radius:0`).
  - `.look-thumb kbd`: Silkscreen.
- Looks sheet: `background:#c7c7c7f2; backdrop-filter:none`. The head `b` is Newsreader 24px. Use `see them all →` and `same frame, every look. 1–8 to pick.`
- **Inspector.** `.line-words` gets `background:transparent; border:0; border-bottom:2px dotted var(--ln2)`. The word buttons use **Newsreader 20px**, `.hero` is ink colour and the rest are mut. `.selected` is `background:var(--lime); color:#fff`. `.star` uses ✦ instead of ★, in blue when on. `.flag.on` is blue text with a `#0000ff1a` inset rather than a filled chip. `.delete-button:hover` uses `var(--err)`.
- `.word-details summary::before`: `├─` / `└─` instead of ▸ / ▾.

## 7. Timeline (`.tl*`, `.word-chip`, `.playhead`)

- `.tl`: `background:var(--bg); border-top:2px dotted var(--ln2)`. `.tl-head` / `.tl-ruler`: `background:var(--bg)`, with `border-right` set to `1px dotted var(--ln2)`.
- `.tl-tick`: mono 10px mut with `border-left:1px dotted var(--ln2)`. `.tl-beat` is `#2e2e2e10`, and `.down` is `#2e2e2e26`.
- `.tl-loop.on` and `.tl-live` are blue.
- **Regions:** `.tl-region` gets `border-radius:0; background:color-mix(in srgb,var(--c) 10%,transparent); border:1px dotted color-mix(in srgb,var(--c) 60%,transparent)`. `::before` (the colour cap) becomes a **3px left bar** (`left:0;top:0;bottom:0;width:3px;height:auto`), like her guestbook rows. `.tl-region-label` uses ink colour with no text-shadow.
- **Word chips:** `border-radius:0; font:11px var(--mono); background:color-mix(in srgb,var(--c) 14%,var(--bg)); border:1px solid color-mix(in srgb,var(--c) 45%,transparent); color:var(--tx)`. `.hero` gets `font-style:italic; border-left-width:3px`. `.selected` is `background:var(--lime); color:#fff`. `.quiet` uses opacity 0.35 with no stripes (or her dotted texture: `background-image:radial-gradient(#7676764d 1px,transparent 1px) 0 0/4px 4px`).
- `.hero-dot`: replace with `✦` via `::before{content:'✦'}`.
- `.hook-tag` / `.tl-hookmark`: blue `#2e00fd` with `color:#fff` and lowercase `hook`. Drop the pink `#ff5a8a`, which is a second accent.
- **Playhead:** a 1px blue line, with the head as a 7px **square** (her cursor) instead of the pentagon: `width:7px;height:7px;left:-3px;clip-path:none`.
- `.tl-section` colours come from role tokens, with labels in lowercase mono and no uppercase.
- `.tl-quiet`: dotted texture instead of diagonal stripes.
- `.tl-keys` / `.tl-hint`: mono 11px mut, kbd in Silkscreen.
- The audio waveform canvas draws in `var(--tx2)` (light) or `#a3a3a3` (dark), not lime. The colour is set in Timeline.tsx and has to be read from a CSS variable.

## 8. Status bar + workflow sheet

- `.statusbar`: `background:var(--bg); border-top:2px dotted var(--ln2)`. Left side: `currently: transcribing ✧` (mono 11px). Right side: `last updated 10:22 · [source]`, with `[source]` linking to the project JSON. The `i` dot is blue and pulses while busy.
- `.wf-sheet`: `background:var(--bg); border:2px dotted var(--ln2); border-radius:0`. `.wf-graph` uses her dotted grid, `radial-gradient(#76767640 1px,transparent 1px) 0 0/16px 16px`, as on rect.repair. `.wf-node` is `background:var(--p2); border:1px solid rgba(20,20,17,.25); border-radius:0; box-shadow:shadow-md`. `.wf-node.key` gets a blue outline and `.wf-cls` uses Silkscreen 10px for the class name. Empty and idle state: a single small `✧˚.⋆` above a dotted rule.

## 9. Layout changes (small)

- Keep the 3-column plus timeline grid. Widen the gutters with `.panel-sec` padding of 16px instead of 12px.
- Right column order: line inspector **above** looks when a line is selected, and looks first otherwise (she leads with the thing in focus).
- Left column header: a `projects/` tree listing of recent projects (`├── song-a`, `└── song-b`), replacing the `<select>` project switch. Optional.

## 10. Proposed look presets (same shape as `PRESETS` / `LOOKS` in `looks.ts`)

These need `'grey-noise'|'night-code'` added to `LookId` in `types.ts`, and the `Newsreader` + `IBM Plex Mono` TTFs added to `FONTS`, `public/fonts` and `style.css`. Names follow the file's rule: they describe rules, not artists.

```ts
// Soft grey grade + grain on the footage; blue serif words, lowercase, crisp on top of soft. Hook lines go italic
// and huge; verses sit small and low like burned-in subtitles. Her project-card idiom (blurred noisy image, blue serif title).
'grey-noise':{id:'grey-noise',
  font:{hero:'Newsreader',body:'IBM Plex Mono',heroWeight:400,bodyWeight:400,heroCase:'lower',bodyCase:'lower',heroStyle:'italic'},
  palette:{text:'#2e00fd',accent:'#2e00fd',shadow:'#c8c8ff',outline:'#ffffff'},outlineWidth:0,halo:.45,
  texture:'grain',optics:{grain:.4,glow:.15},grade:{tint:'#c7c7c7',amount:.45},
  layout:'line',quiet:'none',heroFill:'accent',verse:{max:.04,keepPosition:true}},

// Night mode / livecode set: olive-black grade, lavender mono text that pulses like her pixel clock, one pixel
// display word per hook. Verses stay as quiet terminal lines.
'night-code':{id:'night-code',
  font:{hero:'Sixtyfour',body:'IBM Plex Mono',bodyWeight:500,heroCase:'lower',bodyCase:'lower'},
  palette:{text:'#c7c7c7',accent:'#b2a2cd',shadow:'#1b1f11',note:'#949bfb'},halo:.3,
  texture:'grain',optics:{glow:.55,grain:.2,chroma:.15},grade:{tint:'#1b1f11',amount:.35},
  layout:'line',quiet:'hooks-only',heroFill:'accent'},
```

```ts
{id:'grey-noise',name:'Grey noise',description:'Footage greyed and grained; lowercase blue serif hooks in italic, mono verses set like subtitles.',swatch:['#c7c7c7','#2e00fd','#c8c8ff'],fonts:['Newsreader Italic','IBM Plex Mono']},
{id:'night-code',name:'Night code',description:'Olive-black grade, lavender pixel hooks that glow; only hooks speak, set like a livecode screen.',swatch:['#1b1f11','#b2a2cd','#c7c7c7'],fonts:['Sixtyfour','IBM Plex Mono']},
```

Notes. `Sixtyfour` needs bundling (OFL, Google Fonts). If you skip it, set `hero:'Silkscreen'` (already bundled). `heroStyle:'italic'` relies on a Newsreader Italic file. Pressing 1–8 means the LookPicker hint text and the `kbd` range must cover 8 looks.
