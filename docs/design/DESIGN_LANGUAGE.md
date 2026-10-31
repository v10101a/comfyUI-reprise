# Typeset design language (from viola he / v10101a)

Tokens: `docs/design/tokens.css`. Restyle plan: `docs/design/studio-redesign.md`. Screenshots: `docs/design/refs/`.

## Evidence

| Source | What it showed |
|---|---|
| https://viola.city/ (`refs/viola-city-home.png`, `-full`, `-dark`, `-card-hover`) | Flat **#c7c7c7 grey** page. Body text is **IBM Plex Mono**, and project titles are **Newsreader** serif in **#2e00fd electric blue**. Links in the nav, pills and buttons are *italic mono*. Dividers are **2px dotted #767676**. Thumbnails are **blurred, grayscale and grained** (`blur(4px) grayscale(90%)` plus an SVG `feTurbulence` filter) and come into focus and colour on hover. On hover, a title **blurs out** (`blur(2px)`), the card rounds to 0.75rem and gets a **lavender halo** (`0 0 25px #c8c8ffe6`). The cursor is a small blue square. Hanging pixel stars sway along the top edge. Desktop "gadgets" sit at the bottom right (pixel clock, CD, OK dialog). The right rail is a status block ("Current Whereabouts", "Things on my Mind ⇢", "Last Updated 08/06/26 10:22 [source]") and a guestbook with coloured left bars. A sun/moon toggle switches to night mode. |
| viola.city night mode (`html.dark`) | Olive-black **#1b1f11**, text #c7c7c7, links **lavender #b2a2cd**, raised surface #3b4028. Images also get `invert(60%)`. |
| https://viola.city/projects/qzone-museum/ (`refs/viola-city-project-qzone.png`) | The left nav is a **`tree` listing** (`projects/ ├── … └──`) in muted mono. Pages use a serif title with a dotted rule. Meta reads like `Web ✦ 2026`, and links like `site ↗`. Prose is serif on very open leading (about 2), with a **blue serif drop cap**. Personal, lowercase-leaning voice ("It was also where I first learned html."). |
| https://viola.city/music/ (`refs/viola-city-music.png`) | A Webamp (Winamp skin) shell with Hydra live code (`osc(2, fft, 0.9).kaleid(4).out()`) over a soft grey→sky→mint gradient. Early-2000s software is treated as a material. |
| CSS (`/_astro/cv.BMG_Rbjb.css`) | Theme vars `--color-neutral:#c7c7c7`, `--color-bright:#cacaca`, `--color-dark:#1b1f11`, `--color-dark-bright:#3b4028`, `--color-dark-text:#b2a2cd`, `--color-blue-text:#2e00fd`, `--font-mono:IBM Plex Mono`, `--font-serif:Newsreader`, `--font-sixtyfour:Sixtyfour`. Silkscreen is used for the clock, Workbench is imported, and transitions run 0.15 to 0.3s on `cubic-bezier(.4,0,.2,1)`. |
| Page `<title>` and meta | Title `✧˚.⋆ ⊹ ♡ !! ✦`, description `你好欢迎来我家` ("hello, welcome to my home"). Kaomoji appear inline in the bio. |
| https://www.instagram.com/v10101a/ (login wall; grid only partly visible) | Bio: "computer art" plus kaomoji and music notes; "1/4 of @rect_repair, 1/2 of @computerartllc, 1/1 of @v10101a". The grid was dimmed: a live performance photo with a mic and gear, an LED dot-matrix wall, and a street scene with **lowercase burned-in subtitles** ("the artists and the art…"). I could not open individual posts or captions. |
| https://rect.repair/ (`refs/rect-repair.png`, her collective) | Light grey dotted-grid desktop with cut-out object icons. Labels are **red bold italic**. Year headers are blurred neon-yellow numerals, with kaomoji as headings and `new!` pixel badges. |
| https://qrmrc.vercel.app (`refs/qrmrc.png`, her drum machine) | Pixel font (Tiny5), a violet QR grid, a `!PLAY!` button, and lots of white space. |
| https://github.com/v10101a | 🍉, "im making a new portfolio website!" Lowercase and casual. |

Not accessed: individual Instagram posts and reels (login wall), and Vimeo/YouTube performance video. The Chrome extension was offline, so I captured screenshots with headless Chrome instead.

## Principles

1. **Grey is the canvas, blue is the voice.** Use a flat mid-grey ground with one saturated accent (#2e00fd) for anything you can act on. No gradients in chrome and no second accent.
2. **Mono for doing, serif for naming.** Plex Mono carries every control, number and label. Newsreader names things: projects, looks, the current line. Pixel faces (Silkscreen, Sixtyfour) are seasoning, at most one moment per screen.
3. **Dotted, not boxed.** Divide with 2px dotted rules and leave space. Use few borders, few cards and no heavy panels.
4. **Soft until touched.** Media rests blurred, grainy and desaturated, and sharpens into colour on hover or selection. Hover gives a lavender glow; it doesn't darken. Reserve full clarity for the thing in focus.
5. **The computer as a personal place.** Show status like a diary ("currently: transcribing"), use tree listings, timestamps and `[source]` links, and expose live code and node graphs instead of hiding them.
6. **Lowercase, terse, a little funny.** Use sentence fragments and arrows (→ ⇢ ↗). Kaomoji and sparkles (✧ ✦) appear rarely and only in idle or empty states, never in errors.
7. **Light by default, night as a mode.** Night mode is olive-black with lavender, not neutral black with neon.
8. **Y2K software as material, not pastiche.** Borrow its honesty (visible windows, pixel clocks, tree views) but keep the layout calm.

## Tokens (summary; full values in tokens.css)

- **Fonts.** `IBM Plex Mono` 400/500/600 plus italic for the UI, `Newsreader` (opsz 6..72) 400/500 plus italic for titles, `Silkscreen` for pixel badges, and `Sixtyfour` for a rare display moment. Load them from `https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Silkscreen&family=Sixtyfour&display=swap`. All are OFL. Silkscreen is already bundled in `apps/web/public/fonts`.
- **Type scale.** 11 / 12 / 14 / 16 / 18 / 24 / 60 (drop cap). Studio density: 12px mono body, 11px meta, 18px serif section names. Line height 1.1 for lists, 1.45 for panels, 2 for prose. Mono is never letter-spaced and labels are never uppercase.
- **Light colours.** Background #c7c7c7, surface #cacaca, ink #2e2e2e / #5e5e5e / #8e8e8e, rule #767676 (dotted), accent #2e00fd, glow #949bfb / #6c76ff / halo #c8c8ffe6.
- **Night colours.** Background #1b1f11, surface #3b4028, ink #c7c7c7, accent #b2a2cd, halo #647864e6.
- **Spacing.** 4px base (4, 8, 12, 16, 24, 32).
- **Radii.** 0 by default, 2px for active pills, 4px for icons. A card reaches 12px **only while hovered**.
- **Borders.** `2px dotted #767676` for section dividers and `1px dotted` for dense rows. A solid 1px `rgba(20,20,17,.25)` frames media only.
- **Motion.** 150ms `cubic-bezier(.4,0,.2,1)` for UI and 200ms for image focus. Hover can scale to 1.05. The live/busy indicator uses a 1s glow pulse (alternate) instead of a spinner.

## Copy voice

Rules: lowercase sentence case, short, verbs first, no "AI" boasting, arrows instead of chevrons, numbers in mono. Make status personal ("currently") and keep errors plain with no cuteness.

| Now | Her voice |
|---|---|
| `typeset` + `STUDIO` badge | `typeset` (serif, blue) + `studio ✦` (italic mono) |
| `Pipeline` / `Media` / `Projects` tabs | `pipeline/` `media/` `projects/` (tree-style) |
| `Output` | `export ↗` |
| `Render` | `render →` |
| `Save` / "Save now (autosave is on)" | `saved 10:22` (click to save) |
| `+ New project` | `+ new` |
| `Add your footage` / "Video or audio · stored locally" | `drop a video or a song here` / `stays on this computer` |
| `Lyrics / script` + "Optional: paste the words you expect to hear. Whisper aligns to them." | `lyrics (optional)` + `paste what they sing. whisper lines it up.` |
| `Transcribe` / `Isolate subject` / `Detect beats` | `listen` / `cut out the subject` / `find the beat` |
| `Re-run` | `again ↺` |
| `Workflow ↗` | `see the graph ↗` |
| `ComfyUI` · "3 Comfy workflows ran for this project" | `comfyui · connected` · `3 workflows ran · 41 s of model time` |
| "server offline" | `server's asleep. start it with npm run dev` |
| `Look` + `Compare all ⤢` | `look` + `see them all →` |
| `Looks` sheet: "Same footage, same frame, one click…" | `same frame, every look. 1–8 to pick.` |
| `Arrangement` | `arrangement` |
| `No lines yet` / "Transcribe in the Pipeline panel, or add a word." | `nothing here yet ✧` / `listen to the song first, or + word` |
| "Select a line on the stage or in the arrangement." | `pick a line on the stage or below.` |
| `Hook` / `HOOK` tag | `hook` (blue italic) |
| `Hide word` / `Remove word` | `hide` / `remove` |
| `Find readable space` | `find a quiet spot` |
| `Generate in ComfyUI · LTX` | `generate a shot (ltx) →` |
| `Make vertical` | `make it 9:16` |
| `Loading composition…` | `loading…` with a pixel-clock glow |
| `Back to showcase ↗` | `← showcase` |

## Do / don't

**Do:** keep a grey ground and one blue accent; use Plex Mono everywhere functional; use serif for names; use dotted rules; rest media blurred and grainy and sharpen it on hover; use an italic-mono link style; give hover a lavender glow; show timestamps and status like a diary; use tree listings (`├──`); put one pixel or kaomoji moment in an empty state; offer a night mode in olive and lavender.

**Don't:** use lime or neon on near-black (the current studio look); uppercase letter-spaced micro-labels; glassmorphism or gradients in panels; rounded cards everywhere; more than one accent hue for UI state; sparkle emoji in errors; "AI-powered" or "magic" copy; drop shadows heavier than tw `shadow-md`; Inter for UI.
