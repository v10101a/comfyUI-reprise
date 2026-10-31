# Demo video: shot list (≤ 2:00)

The target is **Most Viral**, plus the **MiniMax H3** bonus. The rules say the jury judges "the work, not your video editing", and the best demo "shows your work in action with an explanation of how it was built". So every claim below is shown on screen.

**Against MOTNGRFX** (the closest entry: type behind the subject, generated footage, NVIDIA), we differentiate in five ways, all shown:
- words *on tracked walls* and *on a head*, not only behind the subject;
- exact, editable type, with preview equal to export;
- one-click looks and one-click 9:16;
- it works on **your own footage** (Fall For Me);
- the studio runs on a Mac.

We never say "first" or "nobody has done this".

## Prep

- **Audio bed:** the hero song is ACE-Step and already muxed into the hero exports. Duck it under the voiceover. The Fall For Me segment uses its own audio.
- **Screen recordings:**
  - studio at `http://127.0.0.1:5174/#/studio?project=<id>`, recorded at 1920×1080, browser zoom 90%, with the pipeline panel open;
  - ComfyUI at `http://127.0.0.1:8188`.
  - Close other studio tabs; the studio autosaves.
- **Project ids:**
  - hero 16:9 `54da2790-92c6-4737-bc43-81a207e47ab5`
  - hero 9:16 `cb4de765-9043-4540-953b-8f017fc28a87`
  - dancer `7854af4e-6500-415f-b924-ed4720dcc4f5`
  - Fall For Me `14ef9e95-1d22-4bc1-8e42-5a1db01368ee`
- **Export for upload:** 1920×1080 H.264. Keep the 9:16 segment pillarboxed on a dark background, and also cut a 9:16 version of the cold open for social.

## Shots

| # | Time | Picture (source file or screen action) | Voiceover |
|---|---|---|---|
| 1 | 0:00–0:05 | `outputs/hero/hero_export.mp4` 4.2–7.0 s: she walks past the wall and the stencil EVERY SIGN / REPEATS / YOUR NAME passes behind her head. Speed-ramp in at 4.2 s. | *(no VO, song only)* |
| 2 | 0:05–0:09 | `outputs/hero/hero_export.mp4` 11.4–13.4 s: the drop. HOLD and ON land on the plaza walls on the beat, and the D tucks behind her shoulder. | *(no VO)* |
| 3 | 0:09–0:16 | `outputs/hero/hero_export.mp4` 16.4–18.7 s: tunnel, LET IT / SHOW as green neon tubes on both walls. Small title over the end: **Typeset: words that live in the scene.** | "This is Typeset. The words aren't stickers on top of the video. They're in the scene: behind her, on the walls, in the tunnel." |
| 4 | 0:16–0:24 | Studio, hero project: scrub to f165, toggle the matte layer on and off, then show the surface quad on the wall following the camera, with the tracked corners visible. | "Video models can't spell, so every letter is real type. ComfyUI cuts her out of every frame and tracks the wall's plane, and Typeset composites the words into that space. You can edit any word and get the same frame in export." |
| 5 | 0:24–0:31 | Studio, scrub to f230: the HUD box and leader line ride her head, and the 4-3-2-1 count-in hits the beats. Click a word on the timeline and drag its timing. | "Lyrics come from Whisper and are aligned to the lyric sheet. The HUD locks to her head, and everything stays editable on the timeline." |
| 6 | 0:31–0:44 | Studio look picker over the drop (f300): click `lens-bound` → `red-glow` → `paper-cut`, a real-time screen recording with instant switches. Then cut to the side-by-side still `outputs/hero/three_looks_hero_f300.jpg` for 2 s. | "A look is one setting. Change it and the whole video restyles: font, colour, texture, glow, lens. The placement and tracking don't move." |
| 7 | 0:44–0:50 | `outputs/hero/dancer_export_redglow.mp4` 2.0–6.0 s: the same character dancing, with a huge red LOUDER behind her. | "Same engine, different clip: a dance take in red glow." |
| 8 | 0:50–1:04 | Studio: show the header "Make vertical" button, then open the 9:16 project `cb4de765…`. Play `outputs/hero/hero_export_9x16_auto.mp4` 11.4–16.3 s (drop → LOUDER pan), then 18.9–22.4 s (EVERY / WORD / I / KNOW). Do not press the button live: the LOUDER pan needs a focus region that was set when this project was reframed. | "One click for vertical. The crop follows her, walls that fall outside become title rows, ON steps in front of her, and the text keeps clear of her face and the edges. The neon sign is too wide for a phone, so the camera pans across it." |
| 9 | 1:04–1:20 | Before/after on the LOUDER beat. First the S1 street frame (`outputs/hero/hero_16x9.mp4` at 4.9 s, which is the frame that was edited), held 2 s. Then the same street with LOUDER written in: the Qwen edit still `outputs/hero/gen/qwen_louder/qwen_louder_00001_.png` (edited from S1 at 4.9 s), held 2 s. Then `outputs/hero/hero_export.mp4` 13.9–16.3 s, the sign lit and moving. Lower-third: *Qwen-Image-Edit → MiniMax H3*. | "Some words should *be* the scene. Typeset takes a frame, an image model writes the word into it, and MiniMax H3 brings it to life, so the sign glows and the street turns pink. H3 also shot all of this footage: same face in every shot, from one reference image." |
| 10 | 1:20–1:34 | ComfyUI at :8188: open `workflows/showcase/typeset_analysis.json` and pan across LoadVideo → BiRefNet → MaskToTracks / TypesetOccupancyGrid / TypesetPlanarTrack / TypesetReframeCrop and LoadAudio → TypesetBeatGrid. Cut to the studio pipeline panel, showing each workflow with its status and time. | "Under the hood it's a ComfyUI node pack: words, beats, matte, readable space, planar tracking, reframe. The studio runs these graphs through comfy-sdk and shows you every step." |
| 11 | 1:34–1:50 | `outputs/ffm/ffm_final.mp4`: 17.0–24.0 s (lyrics popping in on piano-roll note blocks), then 31.4–34.5 s (FALL / FOR ME behind the stars). Pillarbox the 1080×1280 frame. Caption: *own footage, made in TouchDesigner*. | "And it's not just generated footage. This is my own TouchDesigner clip, with the lyrics riding note blocks, and the title sliding behind the stars." |
| 12 | 1:50–1:58 | `outputs/hero/hero_export_9x16_auto.mp4` 18.9–22.4 s (EVERY / WORD / I / KNOW) beside `outputs/hero/hero_export.mp4` at the same time. End card: **Typeset**, the repo URL, "open source · MIT · ComfyUI node pack + studio". | "Typeset. Your footage, your words, in the scene. Open source, built on ComfyUI." |

Total: 1:58.

## Notes

- **If time runs long:** cut shot 7 (dancer) first, then trim shot 5 to 4 s. Keep shots 1–3 untouched: the first 16 s are the hook.
- **Hold every on-screen claim to what's shown:**
  - the HUD anchors to the matte's tracked region (don't say "face tracking");
  - looks change style only;
  - 9:16 is one reframe plus a focus region for LOUDER.
- **Raw sources for shot 9:**
  - the raw H3 clip is `outputs/hero/gen/gen_louder/gen_louder_00001-audio.mp4`;
  - the prompts and seeds are in [HERO.md](HERO.md), row G1.
- **Social cut** (for the post, ≤ 30 s, 9:16): shots 1–3 taken from `hero_export_9x16_auto.mp4`, then shot 8, then the end card.
