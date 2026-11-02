# Showcase media

The demo page (`src/Showcase.tsx`) plays these files directly. To swap a piece, copy a new file over the old name. No code change is needed.

Pieces (name, file, project, alts) are listed in `src/showcase-pieces.json`, which both the page and the API read. A piece with an `encode` block re-renders itself: after a studio save of its project (5 s debounce; repeat saves during a render queue one more pass), `POST /api/projects/<id>/showcase` (server/app/showcase.py) renders the composite from a snapshot of the saved project, encodes it with the settings below plus the piece's `scale`/`fadeOut`/`audioFadeOut`, and swaps the file in by atomic rename (here and in `dist/showcase/` when present). Alts ("Original" layers) are never written. A dot beside Save in the studio shows a pending/running refresh. `GET /api/showcase` returns file mtimes, so the page loads the fresh clip.

| File | Piece | Source |
|---|---|---|
| `ffm-angel.mp4`, `ffm-angel-source.mp4` | Fall For Me · Angel / Original | Angel v3; project `b678f509-ca77-4423-a0a6-739869cb0030`, 26.533 s, Dreamy + pixels |
| `so-i-die.mp4` | So I Die | Project `48f2389d-1d2e-42ff-af86-f90b4d8c4600`, export `e8d05378-827b-4719-876a-f83e67def79c` (2026-11-02); 23 s at 24 fps, HUD + Film, encoded at 1280 wide. Studio saves refresh this piece. |
| `hero-16x9.mp4` | neon rain | `outputs/hero/hero_export.mp4` (re-encoded) |
| `hero-9x16.mp4` | neon rain · 9:16 (also the hero's 9:16 view) | `outputs/hero/hero_export_9x16_auto.mp4` |
| `hero-source.mp4` | neon rain › source view | `outputs/hero/hero_16x9.mp4` (no audio) |
| `hero-dark.mp4` | neon rain · night. **Optional:** the tile stays hidden until this file exists | dark hero restyle (in progress) |
| `ffm.mp4`, `ffm-source.mp4` | Fall For Me / Original | v9 edit (`scripts/content/ffm_v9.py`), 23.633 s, scaled to 720 wide; composite has a 0.65 s end fade |
| `louder-fields.mp4`, `louder-source.mp4` | DANCING / Original | project 42b7723d, 8 s; Glow type driven by motion and voice fields over `outputs/hero/dancer_big_9134.mp4` |
| `looks.jpg` | unused (replaced by the Looks section) | `outputs/hero/three_looks_hero_f300.jpg` |
| `kinetic.mp4`, `overlay.webm`, `neon*.{mp4,png}`, `morph*.{mp4,png}`, the study `*.png` files | earlier experiments | see git history of this file |

The page's re-encode keeps the files small. A raw copy also works, but it makes the build bigger:

```sh
ffmpeg -i IN.mp4 -c:v libx264 -crf 24 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart apps/web/public/showcase/NAME.mp4
```

Thumbnails are taken from the video itself (`#t=1`), so no poster files are needed. Rebuild (`npm run build`) to update `dist/`.

These compact, published demo files are intentionally tracked. Keep full-resolution exports, alternate takes, frame sequences and review captures in the ignored root `outputs/` or `data/` directories. Do not add a blanket video/image ignore rule: a fresh checkout needs these assets to play the front page without an API.

## Looks section (`src/LooksSection.tsx`)

`looks/<look>.mp4` and `looks/<look>--<grade>.mp4` each have a matching `.jpg` still. Every clip is the same 4.0 s shot, the hero's S2 wall (she walks left→right in profile past the long pale wall), 0.5 s longer at each end than the hero's 3 s cut: the hero only holds frames 104–175 of it, so the clip is cut from the S2 plate (`outputs/hero/plates/s2_wall_ref`, frames 17–112 = hero-time 3.83–7.83 s) into its own project a1aab922 (the hero 54da2790 is untouched). Wall text EVERY SIGN / REPEATS / YOUR NAME sits on three taller wall rows wall1–3 (bigger type, staggered to the right so each line lands clear of her and stays fully in frame while the camera follows her), on the hero's timing (last word at 2.75 s). All rows share one wall-plane track. The ticker clips use a copy of that project with narrower, smaller rows (712f70fb; LED band about 22% smaller than the wall rows, so the crawl is slower in pixels), so the LED sign stays a sign. HUD clips are rendered with `&overrides={"scale":1.25}` so the label reads at 720p (showcase only; the preset is unchanged). Flat-card clips use `&overrides={"wallScale":0.8,"wallBlend":0.6}` (smaller cards that take the wall's light and texture; showcase only). The ticker copy's rows are aligned under wall1 so the LED band stays a straight rectangle on the wall. The clips are rendered without the caption line (`&subs=0`). There are 8 looks (flat-card, paper-cut, graffiti, neon, hud, xerox, ticker, scatter) × 4 grades (none, mono, xerox, film); `none` is rendered with `&grade=none`, so it is ungraded (the project itself has a wash grade). `looks/source.*` is the raw footage of the same window. `looks/song.m4a` is the clips' shared song (audio of any look clip): the section plays it as the one clock and sound, and the clips are muted layers on top; re-extract it whenever the clips are re-rendered (`ffmpeg -i looks/flat-card.mp4 -vn -c:a aac -b:a 128k looks/song.m4a`).

The clips come from the read-only render route, `#/render?project=a1aab922…&layer=composite&look=<id>&grade=<id>&subs=0`, served from one frozen build of the app (`vite build` + `vite preview`) so the whole grid uses the same renderer. They are captured frame by frame and encoded at 720p CRF 26 with the song segment (Neon Rain 3.83–7.83 s, AAC 96k; identical audio in every clip). Stills are frame 72, just after YOUR NAME lands. The project itself is never modified.

Angel v3 is the lead piece (2026-11-01): `ffm-angel.mp4`, 796 frames at 30 fps, 26.533 s, Dreamy + pixels. Source project `b678f509-ca77-4423-a0a6-739869cb0030`; the Original layer uses the corrected v3 footage and extended song ending. Studio saves refresh this piece. Unverified pitch labels are hidden; note blocks remain.
