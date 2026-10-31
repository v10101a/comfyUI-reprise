# MiniMax H3: audio-to-video and lip sync

Researched and tested 2026-10-31 by agent K for Typeset. The question was whether open-weights MiniMax H3, running on our remote RTX 4090 (ComfyUI 0.34), can drive video from an existing track: lip sync to a vocal, or a performance that follows the music. Test material: the hook of "Fall For Me" and the user's own likeness.

## TL;DR

1. **H3 cannot lip-sync a vocal you give it.**
   - On our remote, the mouth correlates with the user's vocal at r −0.35 to +0.10 at lag 0. The best r within ±0.5 s was 0.18–0.24. That held in all 5 runs, across:
     - guide and ref modes;
     - turbo and 20-step;
     - stem and mix.
   - A mouth that tracks a vocal should score about 0.5 or higher.
   - The audio does change how the person sings: shifting the window by 1 s gave a completely different mouth curve. But the motion does not follow the timing of the words.
2. **With the vocal stem as the guide, `MiniMaxH3AddGuide` keeps the user's own vocal as H3's soundtrack.**
   - Framewise chroma r was 0.95–0.98.
   - Likeness holds well: a frontal close-up of the user singing, in their own style.
   - With the **full mix** as the guide (test e), H3 replaced the song with its own audio (chroma r −0.03). Guide with the stem, and mux the mix back on afterwards.
3. **Use H3 for performance shots, not lip sync.**
   - Use singing, swaying close-ups and mediums where the mouth is not the subject, with the real track muxed on and Typeset's words behind the subject.
   - True lip sync needs a dedicated model. Options are LTX-2.3 image+audio-to-video, InfiniteTalk or Wan2.2-S2V on a GPU with disk space, or a paid API node (Sync, Kling lip sync). None is on the remote, which has ~3.6 GB free.

## What H3 supports for audio

- **H3 always generates audio itself.** The latent is joint video + audio (`EmptyMiniMaxH3LatentAV`). The sampler output feeds both `VAEDecode` (video VAE) and `VAEDecodeAudio` (`minimax_h3_audio_vae_fp32`). The output is 24 fps with 32 kHz stereo audio (voice, SFX and music in one pass). Every MiniMax clip in the repo already carries its own soundtrack.
- **There are two ways to feed it your own audio.** Both are in core ComfyUI (`comfy_extras/nodes_minimax_h3.py`, PR [#15224](https://github.com/Comfy-Org/ComfyUI/pull/15224), AddGuide in #15439):
  1. **`MiniMaxH3AddGuide`** takes `audio` + `audio_vae` at a `frame_idx`. The node says: "Soundtrack to anchor starting at the same frame index, cropped to the video's remaining duration." It can also anchor an image or a short clip with its soundtrack. The official use is **continuation**: the first 22 frames of a clip and their audio at frame 0, after which the model continues both streams ([docs](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)). The docs say: "This is conditioning, not video-to-video."
  2. **`MiniMaxH3ReferenceToVideo`** takes `ref_audios` (up to 3, each 2–15 s, ≤15 s in total). In the prompt they are `<Audio N>`. The official r2v template's prompt says "use `<Audio 1>` exactly as it is". The docs add "Audio carries timbre, not words" (for voice references) and "follow the timbre of `<Audio 2>`". The model card's example uses one track as background music and one as a voice-timbre reference. Ref2va is meant to run on its own weights (`minimax_h3_ref2va_*`, with a 4-step ref2v turbo LoRA, 20–25 steps without it).
- **There is no dedicated lip-sync or "speech-to-video" mode.** No audio encoder (wav2vec/Whisper) drives the face, unlike Wan S2V, InfiniteTalk or HuMo. The MiniMax model card does not list lip sync as a feature. H3's advertised lip sync is for speech it **generates itself** from the prompt: dialogue written in the prompt (community tip: `<d>[English] … </d>` and ≥1.2 s of lead-in) is spoken in sync because both streams are sampled together.
- **Community workflows:**
  - RunComfy's "MiniMax H3 Realistic Talking Avatars" is portrait + voice clip → `MiniMaxH3ReferenceToVideo`, prompted to "use your audio for the speaking voice". It claims robust sync but gives no metric and says nothing about singing. Its tips: 5–10 s of clean speech, frontal portrait, no music.
  - BennyDaBall/MiniMax-H3-Workflows (Apache-2.0 workflow files) covers T2VA turbo and a 2K face-region refine that keeps the draft's lip sync. Both are for H3's own generated speech, not an imported track.
  - None of these targets singing to a supplied song.
- **Recommended settings found:**
  - 24 fps. `length` snaps to 17k+5 frames (124 ≈ 5.17 s, 243 ≈ 10 s, 362 ≈ 15 s max).
  - 768 px short edge, multiples of 32. Native 16:9 is 1344×768.
  - `res_multistep`, 20 steps base (beta/normal scheduler for reference-heavy prompts), or 8 steps with the fl2v turbo LoRA (the template uses `simple`). `MiniMaxH3SigmaShift` defaults are 12 (video) and 3 (audio).
  - Guide strength: AddGuide has **no strength parameter**.
  - Audio sample rate: the node resamples. I fed 48 kHz stereo WAV.

## What the remote has

- **Models:** `minimax_h3_fl2va_pruned_int8_convrot`, the fl2v 8-step turbo LoRA, both H3 VAEs and the nvfp4 Qwen3-VL-32B encoder.
- **Missing:**
  - The ref2va weights and the ref2v turbo LoRA. Our `MiniMaxH3ReferenceToVideo` runs on the fl2va weights. This worked for identity in the hero, but it is off-spec for audio references.
  - Dedicated lip-sync stacks: Wan2.2-S2V, InfiniteTalk (`WanInfiniteTalkToVideo` exists, but there are no Wan 2.1 14B weights, no InfiniteTalk patch and no wav2vec encoder; `AudioEncoderLoader` has none), HuMo, LTX-2.3 (its `video_ltx2_3_ia2v` "Image Audio to Video, lip sync" template is the closest open alternative) and Wan Dancer.
  - With ~3.6 GB free on disk, none of these can be installed.
- **Templates on the box** (`GET /templates/<name>.json`): `video_minimax_h3_i2v`, `video_minimax_h3_r2v`, `video_minimax_h3_t2v`, `video_minimax_h3_i2v_continuation`.

## Tests

- **Setup:**
  - Face: the user's likeness ref `outputs/songs/viola-refs/vref_sid_close.png` (agent V's), cropped to a close-up and used as the first frame.
  - Audio: "Fall For Me", 29.0–34.17 s, 124 frames: "I'll make you happy, I'll make you fall for me".
  - The model is conditioned on the BS-RoFormer vocal stem unless noted. The full mix is muxed over every result.
  - Remote 4090, fl2va int8, one job at a time.
- **Sync measure** (`scripts/h3_sync_check.py`): MediaPipe `jawOpen` per frame vs the vocal-stem RMS. Pearson r is reported at lag 0 and at the best lag within ±0.5 s (positive = mouth late).
- **Fidelity:** framewise chroma correlation between H3's own output audio and the track it was given.

| run | how | size / steps | time | mouth vs vocal r (lag 0 / best) | output audio = our track? | notes |
|---|---|---|---|---|---|---|
| a `a_hook_vox_guide` | AddGuide (stem at frame 0) + first frame | 640×896, 8-step turbo, seed 7 | 76 s | −0.04 / 0.21 (+500 ms) | yes (chroma 0.95) | sings convincingly, out of time; vs word timings r −0.39 |
| b `b_hook_vox_ref` | ReferenceToVideo, stem as `<Audio 1>` "exactly as it is", + first-frame guide | same | 81 s | −0.01 / 0.20 (+500 ms) | partly (envelope r 0.41) | mouth curve 0.77 like a (same seed, same audio) |
| c `c_hook_vox_guide20` | as a, no turbo LoRA | 20 steps, beta | ~4 min | −0.06 / 0.18 (+500 ms) | yes (envelope r 0.70) | turbo is not the cause |
| d `d_shift_control` | as a, audio window starts 1 s earlier (28.0 s) | 8-step | ~80 s | −0.35 / 0.23 | yes (chroma 0.98) | mouth curve vs a: r 0.01, so the audio *does* change the motion, but not in sync. **Correction:** I first read a≈b as "the seed drives the mouth"; a and b shared the same audio, so that reading was wrong |
| e `e_perf_mix` | AddGuide with the **full mix**, medium shot, "nods and sways to the beat, sings the hook" | 1344×768, 8-step, seed 11 | 321 s | −0.10 / 0.24 (+458 ms) vs stem | **no** (chroma −0.03; H3 made its own audio) | **Verdict:** a usable performance plate (slow push-in, sways, sings, likeness holds) once the real mix is muxed on. But nothing follows the music, and the mouth does not match the words. |

- **Verdict:** none of the runs is in sync.
  - Played with the real audio, a, c and d read as "singing", but visibly off the words. Fine in a fast cut or a wide; not as a held close-up.
  - Each 5 s run took 76–81 s at 640×896 with turbo, and 321 s at 1344×768. Wait time on the shared queue came on top of that.

## How Typeset could use it

- **Hook performance close-up, words behind the subject.**
  1. Generate the shot with `remote_h3_audio.py` (guide mode, vocal stem, first frame from the likeness ref).
  2. Mux the mix back on.
  3. Run the existing matte so the hook words sit behind the head.
  4. Cut it so the lips are not read closely: ≤1.5 s per cut, profile or ¾ angle, backlit, or a medium shot.
  This uses H3's real strengths (likeness, natural singing motion, the real vocal as the soundtrack) and hides the weak sync.
- **Keep H3's own audio out of the export.** Typeset always lays the original song over the plate. H3's audio is a by-product.
- **Don't build a "lip sync" button on H3.** If the studio needs one later, route it to a lip-sync model behind the same "generate shot" path:
  - LTX-2.3 image+audio-to-video (closest open option, template `video_ltx2_3_ia2v`);
  - InfiniteTalk;
  - or the paid nodes already in ComfyUI (Sync, Kling).
- **Possible next experiments, not run:**
  - anchor the vocal at a later `frame_idx` with a 1 s lead-in;
  - H3's own generated singing of the lyric (its native sync) used only as a mouth guide;
  - the proper ref2va weights for the reference route.

## Licence

- **H3 weights:** MiniMax H3 Community License. The **United States, EU, UK and South Korea are "excluded territories"**: use there needs a separate licence from MiniMax (application form on the [model page](https://huggingface.co/MiniMaxAI/MiniMax-H3); LICENSE §I.3, §II, §V.4). Elsewhere:
  - commercial use is allowed, but products must display "MiniMax H3";
  - more than $20M of yearly revenue needs written authorization;
  - distributions need a NOTICE file;
  - outputs may not be used to train other models;
  - MiniMax claims no rights in outputs.
  - The team is in NYC, so check this before shipping anything beyond the competition, which is itself built around H3.
- **Turbo LoRA:** lightx2v/Minimax-h3-Turbo (follows the base licence).
- **Workflow files:**
  - ComfyUI core is GPL-3.0.
  - The Comfy-Org templates are in Comfy-Org/workflow_templates.
  - BennyDaBall's workflows are Apache-2.0.
- **Lip-sync check:** MediaPipe (Apache-2.0).

## Files

- `workflows/h3_lipsync.api.json`: fl2va i2v (first frame) + `MiniMaxH3AddGuide` (audio at frame 0) + 8-step turbo. Default 640×896×124.
- `scripts/remote_h3_audio.py`: CLI helper. Its options are in the module docstring and `--help`.
- `scripts/h3_sync_check.py`: MediaPipe FaceLandmarker `jawOpen` per frame vs the vocal-stem RMS. Reports r at lag 0, the best lag within ±0.5 s, and onset (diff) r. Needs mediapipe and its `.task` model, which are not in the project venvs.
- Results: `outputs/h3_audio/<run>/`. Play `<run>_mux.mp4` (the original mix). The other files are the inputs, H3's raw output with its own audio, a contact sheet and the sync measurements.
