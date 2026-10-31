# Typeset design language

Live tokens: `.studio` and `.showcase` custom properties in `apps/web/src/studio/studio.css` and `apps/web/src/showcase.css`. Those files are the source of truth. `tokens.css` and `studio-redesign.md` describe the v1 viola.city skin and are kept for history only.

## v2 direction (current)

**Professional first, with a little whimsy.** Typeset should feel like a polished creative tool, with the clarity of Figma, Linear or Ableton, set on a warm paper-grey ground. viola.city (viola he / v10101a) is loose inspiration only, for the paper calm and the one blue voice. We do not adopt its design language.

- **Type.** Inter is the UI face: 13px base, 12px labels, 14–16px values and titles. Plex Mono is only for numbers, timecode and code. The Newsreader serif is only for the wordmark and for project, look and piece names. Italics are for emphasis only. Labels are sentence case with no trailing slashes.
- **Hierarchy.** Panel titles are 12px semibold in muted ink. Values sit in ink. The one primary action per area uses the accent fill.
- **Structure.** Group with solid 1px hairlines and surface tones (bg, then panel, raised, field). No dotted rules and no tree glyphs. Spacing follows an 8px grid.
- **Controls look like controls.** Buttons are 28px high with 6px radius and a visible border. Segmented controls sit in a recessed well. Inputs are filled fields. Every hit area is at least 28px.
- **Colour.** One accent: #2e00fd by day, lavender #b8a8d6 by night. Role colours appear only in the timeline and role dots. Night mode is olive-black.
- **Media is sharp.** Look thumbnails, the filmstrip and demo-page tiles never blur. Hover lifts or outlines them.
- **Whimsy, deliberately rationed.** It shows up in three places only: the italic serif wordmark that leans on hover, the ink-drop playhead, and a faint paper grain on page backgrounds (never on panels or media).

## ⚠️ Rule #1: NO UNNECESSARY TEXT

The user's top priority. Every word on screen must earn its place.

- No helper sentences, explainers, subtitles, hints, or "what this does" copy. If a control needs a sentence to explain it, fix the control.
- One short label per control, or an icon. No label when the content is self-evident (a video thumbnail, a waveform, a word on the timeline).
- No status chatter, no repeated headings, no badges unless they change a decision. Empty states: one line max.
- Tooltips are allowed for detail; the default view stays quiet.
- Before adding any text, delete two.

## Timeline must show the video

The timeline gets a **filmstrip of video thumbnails** above the word and line lanes, so you can see what the words are aligned to (plus the waveform). Scrubbing shows the frame. Implementation: `apps/web/src/studio/Filmstrip.tsx`, all in the browser, cropped through the reframe for 9:16 projects.

## Copy voice

- Sentence case. Short. Verbs first ("Export", "Draw wall", "Make 9:16").
- Numbers in mono. No "AI" boasting, no "magic".
- Status is a toast that appears only when there is something to say: "Saved", "Exported", or an error. Errors are plain.
- Detail goes in tooltips, never in the default view.

## Do / don't

**Do:** use a paper-grey ground with one accent; Inter for UI; serif for names; solid hairlines and surface tones; clear buttons and segmented controls; sharp media; one or two whimsical moments.

**Don't:** use dotted rules everywhere, slash-suffixed labels, tree listings, italic mono for every control, blurred thumbnails in the editor, kaomoji or sparkles in the UI, stars, gadgets, guestbooks, gradients in panels, or a second accent hue.

## Appendix: v1 evidence (viola.city research)

Kept for reference. This is not a spec.

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
