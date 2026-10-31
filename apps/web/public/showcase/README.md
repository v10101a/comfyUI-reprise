# Showcase media

The demo page (`src/Showcase.tsx`) plays these files directly. To swap a piece, copy a new file over the old name. No code change is needed.

| File | Piece | Source |
|---|---|---|
| `hero-16x9.mp4` | neon rain | `outputs/hero/hero_export.mp4` (re-encoded) |
| `hero-9x16.mp4` | neon rain · 9:16 (also the hero's 9:16 view) | `outputs/hero/hero_export_9x16_auto.mp4` |
| `hero-source.mp4` | neon rain › source view | `outputs/hero/hero_16x9.mp4` (no audio) |
| `hero-dark.mp4` | neon rain · night. **Optional:** the tile stays hidden until this file exists | dark hero restyle (in progress) |
| `ffm.mp4` | fall for me | `outputs/ffm/ffm_final.mp4` (v7, 25.7 s), scaled to 720 wide |
| `looks.jpg` | unused (replaced by the Looks section) | `outputs/hero/three_looks_hero_f300.jpg` |
| `kinetic.mp4`, `overlay.webm`, `neon*.{mp4,png}`, `morph*.{mp4,png}`, the study `*.png` files | earlier experiments | see git history of this file |

The page's re-encode keeps the files small. A raw copy also works, but it makes the build bigger:

```sh
ffmpeg -i IN.mp4 -c:v libx264 -crf 24 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart apps/web/public/showcase/NAME.mp4
```

Thumbnails are taken from the video itself (`#t=1`), so no poster files are needed. Rebuild (`npm run build`) to update `dist/`.

## Looks section (`src/LooksSection.tsx`)

`looks/<look>.mp4` and `looks/<look>--<grade>.mp4` each have a matching `.jpg` still. Every clip is the same 2.4 s shot, the hero's plaza drop (HOLD | ON, frames 276–333, 11.50–13.92 s), so the loop lands on a bar. There are 8 looks (flat-card, paper-cut, graffiti, neon, xerox, ticker, lens-bound, scatter) × 4 grades (none, mono, xerox, film). Dreamy and grey-noise were dropped from the section (their clips deleted); graffiti and neon were re-rendered with the scene-look renderer. `looks/source.*` is the raw footage.

The clips come from the read-only render route, `#/render?project=54da2790…&layer=composite&look=<id>&grade=<id>`, captured frame by frame and encoded at 720p CRF 26 with the song segment. The project itself is never modified.
