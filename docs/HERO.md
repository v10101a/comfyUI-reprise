# Hero — "Neon Rain" (Concept A)

22.4 s, 16:9 (1344×768, 24 fps), original song (ACE-Step), one character in 6 generated shots + 1 generative beat, typography built entirely in the Typeset app via the API.

| | path |
|---|---|
| Footage master (plates cut on the bar grid + song) | `outputs/hero/hero_16x9.mp4`, EDL `outputs/hero/hero_16x9.edl.txt` |
| **Final export (app, composite)** | `outputs/hero/hero_export.mp4`, sheet `outputs/hero/sheet.jpg` |
| Vertical reframe export (app) | `outputs/hero/hero_export_9x16.mp4`, sheet `outputs/hero/sheet_9x16.jpg` |
| Project (16:9) | `54da2790-92c6-4737-bc43-81a207e47ab5` (`outputs/hero/project.json`) |
| Project (9:16, one-click auto, demo step 4) | `cb4de765-9043-4540-953b-8f017fc28a87` (`outputs/hero/project_id_9x16_auto.txt`), lens-bound + LOUDER pan |
| Project (9:16, hand-tuned fallback) | `b80d28d3-88af-46af-ac40-35dc2bf864a4` (`outputs/hero/project_9x16.json`) |
| Strongest stills | `outputs/hero/still_f165.jpg` (stencil on the wall), `outputs/hero/still_f300.jpg` (HOLD | ON at the drop), also `still_f425.jpg` (tunnel neon), `still_f60.jpg` (RAIN behind her head) |
| Iterations (spec + export + sheet per pass) | `outputs/hero/spec_v1..v6.json`, `outputs/hero/iter/` |
| Scripts | `scripts/content/` (see bottom) |

## Character (verbatim in every prompt)

> a woman in her late twenties with a sharp jaw-length black bob haircut with straight blunt bangs, pale skin, small silver hoop earrings, wearing an oversized glossy cobalt-blue nylon bomber jacket over a plain white t-shirt and black trousers.

The verbatim description alone was **not** enough: three t2v shots gave three different women (same clothes). What fixed it: the 4090 has **`MiniMaxH3ReferenceToVideo`** (`ref_images`, `<Picture 1>` tag). I cropped her from S1 (`outputs/hero/plates/ref_character.png`) and generated S2/S3/S5 as reference-to-video ("The woman from <Picture 1>, same face, same bob…"). Identity holds across all of them. The cobalt jacket is a deliberate choice: one saturated object that reads at any size and against every plate.

## Shot list (all MiniMax H3 on the remote RTX 4090, 1344×768×124 f)

| id | how | seed | prompt gist (full prompts in `scripts/content/hero_shots.json`, `hero_ref_shots.json`) | why (typography) | time |
|---|---|---|---|---|---|
| S1 open | t2v | 1101 | handheld backing away, she walks down the middle of an empty wet street, dark sky in the upper half, no readable text | huge words behind her head (negative space above) | ~160 s |
| S2 wall | **ref2v** | 2212 | lateral dolly, profile, long blank pale concrete wall, "no posters, no graffiti, no text" | the `surface` wall | 168 s |
| S3 head | **ref2v** | 3313 | 85 mm close-up, magenta/cyan neon sweeps across her face, dark space above | HUD on the head; colour changes on the build | 259 s |
| S4 drop | t2v | 4404 | locked-off tripod, symmetrical, she stands still in an empty plaza in front of a huge flat wall under one light | the static beat on the drop; the wall is a surface | ~160 s |
| S5 tunnel | **ref2v** | 5515 | walking toward camera in a concrete underpass, one-point perspective, fluorescent tubes | two oblique walls → neon surfaces | 167 s |
| G1 LOUDER | Qwen-Image-Edit-2511 (local, 471 s, 1024×576, seed 11) on S1 @4.9 s → MiniMax i2v (177 s, seed 1313) | | edit: "an enormous glowing magenta-pink neon tube sign spanning the facades above the street…"; motion: "sign stays fixed and keeps spelling exactly LOUDER… pulses in rhythm" | the generative beat | |

Discarded: t2v S2/S3 (wrong face; kept in `outputs/hero/plates/s2_wall`, `s3_head`). The t2v S4 kept: its face is close to S1 and is tiny in frame. No regenerations were otherwise needed (every kept clip passed contact-sheet review on the first take).

## Timing map (song: 100 BPM, beat 0.6 s, bars every 2.4 s from 1.93 s; drop at 11.52 s)

| song time | shot | words (placement · preset · style) |
|---|---|---|
| 0.00–4.33 | S1 open | one huge word at a time **behind** her head: WALK / THROUGH / NEON / RAIN (Anton .40, bone #F3EEE4, pop, auto-place off so the head cuts the word) |
| 4.33–7.33 | S2 wall | **surface ×3** (rows of one wall, tracked f104–175, conf .91–.96), `paint`: EVERY SIGN / REPEATS / YOUR NAME in near-black Bebas Neue stencil, word-by-word pop; she walks through it |
| 7.33–11.50 | S3 head | **anchor HUD** on `person0`: "your name" → "hold on" (Space Mono, lime); session readout top-left; lime **4-3-2-1 count-in** on the beats 9.13/9.73/10.31/10.94 |
| 11.50–13.92 | S4 drop (static) | **surface ×2** (static quads, `flat`): HOLD left, ON right (on "on", 12.38); quads overlap her by 5 % so the D tucks behind her shoulder |
| 13.92–16.33 | **G1 LOUDER (generated)** | the word is in the plate; only the subtitle |
| 16.33–18.75 | S5 tunnel | **surface ×2** `neon` pink on the tunnel walls (tracked f392–449): HOLD | ON → LET IT | SHOW |
| 18.75–22.42 | S4b static bookend | **behind**: EVERY WORD / I KNOW around her (Anton .30), last word on 21.02; audio fade 0.9 s |
| always | — | constant mono **subtitle track** bottom-left (Space Mono .032, karaoke, lime active word) |

Design system: BIG = one display word = the moment; SMALL = the constant reading line; surfaces carry lines that belong to a wall; lime = machine (HUD, counter, karaoke), pink = neon/the generated world, bone/ink = paint.

Word timings come from the app's words job with lyric alignment (fixed Whisper's "say the soul"/"Loud as under"). One override: the aligner put "Every" (line 6) at 19.88; raw Whisper has 18.94 (a long sung "eeevery"), which matches the ear, so the spec uses 18.94.

## Generated vs deterministic

- **Generated (models):** all background footage (MiniMax H3), the character identity (reference-to-video), the LOUDER shot (Qwen edit spells it; MiniMax lights and moves it), the song (ACE-Step).
- **Deterministic (Typeset):** every other letter on screen: word timing (Whisper + lyric alignment), matte (BiRefNet, 538 frames), occupancy, surface tracking (OpenCV, homography per frame), perspective warp + paint/neon/flat materials, HUD, karaoke, reframe crop. Preview == export.
- "Video models can't spell, so we ask them to light": the one generated word is spelled by an image model and held for 2.4 s; everything else is real type.

## Iterations (taste, not just correctness)

1. v1: auto-place pulled RAIN off her head (lost the occlusion) → locked S1 positions. Wall line too small/pale → three stacked stencil rows in ink. `paint` erosion on the dark plaza wall looked like camouflage → `flat`. Tunnel neon tiny → bigger quads. HUD 2 sat on her hair → moved into dark space.
2. v3: HOLD re-centred when ON appeared (jump) → split the plaza into two half-surfaces; tunnel one short word per wall.
3. v4: D now hides behind her; full export revealed a dead second at 18.8–19.9 → EVERY at 18.94; the 4-s HUD section under-energised → beat count-in + session readout.
4. v6: subtitle lines overlapped at 18.94 → fixed. Final.
5. 9:16: server reframe + re-layout, then hand-tuned (see below).

## Honest notes

- Works: identity via ref2v; the wall stencil (tracked, occluded, eroded paint), the drop composition, tunnel neon in perspective, the HUD with leader line, cuts on bars. Surface tracking stopped exactly at the cuts on its own.
- Weak: G1 LOUDER is stylized (the street turns magenta and the sign floats in the sky); it reads as a "world answers" beat, not continuity. The paint material is a bit clean on the S2 wall's left edge. Neon on the tunnel walls is outline-only and skewed (correct perspective, but some will read it as a decal). Plates are 1344×768, not 1080p.
- 9:16: the automatic re-layout was not demo-ready (the plaza surfaces left the crop, the 2×2 ending scrambled into "WORD / KNOW / I", auto-placed subtitle collided with HOLD). Hand-tuned in project `b80d28d3…`: drop = HOLD behind above her head + ON **in front** over her torso; ending = EVERY WORD behind + I KNOW in front; subtitle pinned bottom. Still cropped: the S2 wall stencil (surface layout stays at the landscape quad's aspect) and the LOUDER sign (in the plate).

## Looks — what is final vs. what gets restyled

Per the coordinator revisions (`research/kinetic-type-feature-brief.md`), final styling comes from R's one-click looks. **Final:** footage, cut, song sync, the generative beat, word timing, placements, surfaces + tracks, the 9:16 crop. **Looks applied (Oct 31):**
- Night walk `54da2790…` → `look: {id: 'lens-bound'}`. Per-word `style` reduced to `fontSize` + `align` (the look owns face, weight, fill, case, spacing). `lineMeta.hook: true` on `s1-*` (WALK/THROUGH/NEON/RAIN behind her head), `s3-count*` (4-3-2-1) and `s6-*` (EVERY/WORD/I/KNOW); without it those non-repeating lines drop to the small green verse register. Ending words resized 0.30 → 0.20 (Inter 900 is wider than the Anton they were placed for). Preview: `outputs/hero/iter/lensbound_frames.jpg`, `outputs/hero/iter/lensbound_end.jpg`. Pre-look state kept: `outputs/hero/project_prelook_v6.json` (PUT it back to revert) and `outputs/hero/iter/hero_export_prelook_v6.mp4`. **`outputs/hero/hero_export.mp4` is the lens-bound v8 export** (also `outputs/hero/iter/v8_lensbound_green.mp4`; v7 kept at `outputs/hero/iter/v7_lensbound.mp4`). v8 differs from v7 only in the tunnel: neon surfaces now take the look's accent, so LET IT / SHOW are green filled tubes (chosen over v7 white, which read as decals, and over pink, which needs `look.overrides.palette.accent` and also recolours every active karaoke word; comparison `outputs/hero/iter/tunnel_white_green_pink.jpg`). No other placement shifted (frame diff ≈ grain level).
- Companion dancer clip (`outputs/hero/plates/d1_dance_ref/`, ref2v seed 6616, 192 f, same character, static wide, teal wall, big turns, freeze at the end) → `outputs/hero/dancer_chorus.mp4` (song 11.40–19.40 s muxed) → project `7854af4e-6500-415f-b924-ed4720dcc4f5` with `look: {id: 'red-glow'}` (hero layout comes with the look). **Export: `outputs/hero/dancer_export_redglow.mp4`** (8 s, 1344×768, audio); frames `outputs/hero/iter/dancer_redglow_frames.jpg`; pre-look state `outputs/hero/project_dancer_prelook.json`.
- "Same clip in 3 looks": the HOLD | ON drop (frame 300) via `#/render?…&look=<id>`, labelled with PIL → **`outputs/hero/three_looks_hero_f300.jpg`** (lens-bound / red-glow / paper-cut). Third look swapped from flat-card (its #101010 text on the dark plaza wall with no card behind surface text barely reads; R is fixing it; old tile `outputs/hero/iter/three_looks_hero_f300_flatcard.jpg`). Paper-cut chosen over ticker (`outputs/hero/iter/thirdlook_candidates.jpg`): ticker's marquee leaves ON half off-frame in a still; paper-cut reads fully and its matte, eroded finish contrasts with red-glow's bloom. Dancer version (R): `apps/web/.verify/three_looks_dancer_f070.jpg`.
- 9:16 automatic reframe v3 (R's v3.3: edge margins ≥6% measured after lens-bound's warp, hero/title rows never over the face, HUD labels clear of the meta line; S's focus modes): project `cb4de765-9043-4540-953b-8f017fc28a87` (`outputs/hero/project_id_9x16_auto.txt`), created with `POST /api/projects/54da2790…/reframe {aspect:'9:16', focus:[{start:13.917, end:16.375, box:[0.19,0.05,0.81,0.31], mode:'pan', label:'LOUDER sign'}]}`. Comparison with hand-tuned `b80d28d3…`: `outputs/hero/iter/vert_auto_vs_hand_v3.jpg` (top auto, bottom hand; f60/165/190/230/300/345/375/400/470/520). Earlier rounds: `outputs/hero/iter/vert_auto_vs_hand.jpg` (v1, `4c7e6a75…`), `outputs/hero/iter/vert_auto_vs_hand_v2.jpg` (v2, `dd8eb45f…`).
  - Auto wins: LOUDER (pan scans LOU → DER at full height; the clipped sign is baked into the generated plate, so pan is the only fix; chosen over the `auto` letterbox), the HUD (clean label, meta row clear).
  - Ties: the drop (HOLD title row above her, ON over her torso, same as hand), the count-in, the ending (EVERY behind at top, WORD / I / KNOW below her chin, face clear), the wall beat (only REPEATS reads, small, same in both; OK as a passing beat, the subtitle carries the line), the tunnel (neon lost in both).
  - Only artistic difference: auto puts RAIN top-left with a clean margin instead of behind her head (hand). Acceptable.
  - **Verdict: demo step 4 is now the one-click "Make vertical".** `b80d28d3…` stays as a fallback.

## 2-minute demo script (Mon Nov 2)

1. **0:00 Before/after (20 s).** Play `hero_16x9.mp4` (raw plates + song) for 4 s, then `hero_export.mp4` full. Say: "Same footage. Every letter you see is real type, placed in the scene."
2. **0:25 The thesis (10 s).** "Video models can't spell. So we don't ask them to. Typeset renders words with real fonts and lets ComfyUI decide where they belong — behind her, on her head, on the wall. When a word should become part of the world, an image model writes it once and a video model lights it." (Pause on LOUDER.)
3. **0:35 Live edit in the app (40 s).** Open project `54da2790…` at 4.5 s (the wall). Change a wall word (e.g. NAME → your own name), scrub: it stays on the wall, she walks through it. Toggle material paint → neon. Jump to the drop, drag HOLD's timing onto the beat. Show the words came from the song with pasted lyrics (aligned, not misheard).
3b. **1:10 Same clip, 3 looks (10 s).** One click each on the look picker over the drop (lens-bound → red-glow → paper-cut), then play the pre-rendered side-by-side. "Looks are one field; the placement, tracking and timing don't change."
4. **1:20 Reframe to vertical (15 s).** One click on header "Make vertical" from the lens-bound hero (result = `cb4de765…`; pass the LOUDER pan focus, or open `cb4de765…` if the button does not expose focus yet). Play the drop, LOUDER and the ending in 9:16: "One click. The crop follows her, the walls become title rows, ON steps in front of her, and the generated sign gets a camera pan instead of being cut off." Fallback: hand-tuned `b80d28d3…`.
5. **1:35 Export layers (20 s).** Export → show the text-overlay ProRes 4444/WebM alpha landing in a folder; "drop it in Resolve or TouchDesigner — it's a layer, not a bake."
6. **1:55 Close.** "All open weights: MiniMax H3, Qwen-Image-Edit, BiRefNet, Whisper, ACE-Step, running in ComfyUI."

Fallback if anything is slow live: the exports and sheets are in `outputs/hero/`.

## Reproduce

```bash
server/.venv/bin/python scripts/remote_minimax.py --jobs scripts/content/hero_shots.json --out outputs/hero/plates    # t2v S1, S4
server/.venv/bin/python scripts/content/minimax_ref.py --jobs scripts/content/hero_ref_shots.json --out outputs/hero/plates  # ref2v S2, S3, S5
~/ComfyUI/.venv/bin/python scripts/qwen_wall_word.py --frame outputs/hero/gen/s1_f490.png --text LOUDER --prompt "…" --out outputs/hero/gen/qwen_louder --width 1024 --height 576 --seed 11
server/.venv/bin/python scripts/remote_minimax.py --name gen_louder --seed 1313 --upload-first-frame outputs/hero/gen/qwen_louder/qwen_louder_00001_.png --out outputs/hero/gen --prompt "…"
python3 scripts/content/cut_hero.py                                   # EDL scripts/content/hero_edl.json -> hero_16x9.mp4
server/.venv/bin/python scripts/content/hero_project.py create        # project + media + lyrics + words + matte
python3 scripts/content/hero_spec.py v6 && server/.venv/bin/python scripts/content/hero_project.py apply outputs/hero/spec_v6.json
server/.venv/bin/python scripts/content/hero_project.py export v8_lensbound_green     # -> outputs/hero/hero_export.mp4 (+ iter/v8_lensbound_green.mp4)
scripts/content/frames.sh <tag> <frames…>                             # quick frame review through #/render
```
Helpers: `scripts/content/sheet.sh` (contact sheets), `scripts/content/fetch_remote.py` (download a remote output by prefix).
