# Lyric alignment: open-weights options for word timing on sung vocals

Researched and tested 2026-10-31 by agent W for Typeset. Scope: word-level timestamps on sung vocals in full mixes, with lyrics known (forced alignment) and with lyrics unknown (transcription). Open weights only.

## TL;DR

1. **What breaks the current results is the window, not the model.** Every model I tried put "stop" around 6–8 s, inside the "instrumental" intro, when it was given the whole clip. That includes MMS CTC, Whisper-turbo alignment and Qwen3-ForcedAligner. The intro has pitched, voiced content that survives even BS-RoFormer separation. The same MMS CTC aligner, started 0.3 s before the first ASR-detected sung word, put "stop" at **17.18 s**, against the ear-check's ~17.2 s. Its error went from −11.7 s to −0.02 s. A should anchor the alignment window from ASR or vocal activity first, then force-align.
2. **For known lyrics, MMS CTC on a RoFormer vocal stem, inside ASR-anchored windows, was the most accurate setup tested.** It hit the ear-confirmed "FALL FOR ME" within −0.06 s. Whisper-based alignment (stable-ts) is robust, even on the raw mix, but runs about 0.3–0.6 s **late** on line starts. Use it as the fallback, and as the commercially clean path.
3. **For unknown lyrics, use Whisper large-v3-turbo for the text and NVIDIA parakeet-tdt-0.6b-v3 on the vocal stem for timing and vocal activity.** Parakeet put the first sung word at 17.12 s, with no hallucination in the intro, in 1.7 s. However, it returns nothing at all on the full dense mix. Qwen3-ASR-1.7B produced the best lyric text ("a little silly"), but its timestamps collapsed to 0.0 and it peaked at a 14.7 GB footprint. Not for this hackathon.

## Ranked recommendation

### Known lyrics (forced alignment)

| Rank | Pipeline | Why |
|---|---|---|
| **1** | Vocal stem (BS-/Mel-RoFormer, else HTDemucs) → vocal activity and an ASR anchor (parakeet-v3 or Whisper-turbo first and last word, plus line anchors) → **MMS CTC aligner per window** (ctc-forced-aligner `MahmoudAshraf/mms-300m-1130-forced-aligner`, or torchaudio `MMS_FA`, which is what A already has) → word-duration caps → onset snap on the **stem** | Best of everything tested on Fall For Me: "stop" −0.02 s, "fall for me" −0.06 / +0.12 s, and line-start error ≤0.2 s on 8 of 10 lines. Fast: 5 s for 20 s of audio on CPU. Caveat: the MMS weights are **CC-BY-NC 4.0**. They are open, but not for commercial use. |
| 2 | **stable-ts `model.align()`** with Whisper large-v3-turbo (MLX on Mac, faster-whisper or PyTorch on the 4090), on the mix or the stem, with the same anchored window | Most robust on the raw mix, needs no separation, and everything is MIT (code and Whisper weights). Line starts run consistently +0.3 to +0.6 s late. Within that offset it is reliable, so onset snapping can pull the starts back. |
| 3 (untested upgrade) | Lyrics-specific DALI-trained aligner: Huang, Benetos & Ewert (ICASSP 2022), with its multilingual follow-up in [jhuang448/LyricsAlignment-Multilingual](https://github.com/jhuang448/LyricsAlignment-Multilingual/) | The only open-weights (MIT, checkpoint in the repo) aligner trained on singing with published Jamendo numbers: word MAE about **0.23 s**, PCO 94 % ([DAFx 2025, Table 1](https://staff.aist.go.jp/m.goto/PAPER/DAFX2025cheng.pdf)). It is a small CRNN that runs on CPU, but it expects separated vocals and phonemized lyrics. Worth trying after the hackathon. I did not test it here. |

Do **not** use Qwen3-ForcedAligner on songs. Every word collapsed to 0.00 s on the 37 s clip (CPU and MPS, fp16 and fp32). Trimmed to start at 15 s, it still dumped "stop thinking for a" at 15.00 s.

### Unknown lyrics (transcription)

| Rank | Pipeline | Why |
|---|---|---|
| **1** | **Whisper large-v3-turbo** (mlx-whisper on M5, faster-whisper on the 4090) on the **mix** for text, with segments cut by **RMS-VAD on the vocal stem** | Best open WER on Jam-ALT comes from Whisper with stem-RMS segmentation: 20.35 % long-form ([Syed et al. 2025](https://arxiv.org/abs/2506.15514)). In the test, turbo heard more of the words than parakeet did, and its line starts were within 0.7 s. It still hallucinates. "I'm gonna make you fall for me" appeared at 16 s, and "Thank you." at 30 s on Neon Rain. |
| 2 | **parakeet-tdt-0.6b-v3** (CC-BY-4.0; `parakeet-mlx` on Mac, NeMo on the 4090) on the **vocal stem**, used for timing, vocal activity and anchors | Best onsets of any ASR in the test: the first word landed at 17.12 s, matching the ear. Fast: 1.7 s and 1.9 GB. Its words are weaker ("a little city", "besides the cooking"), and it **returns empty on the full mix**, so it needs the stem. |
| 3 | Then **re-align the transcript** with rank-1 known-lyrics CTC | Recognised text plus CTC timing beats Whisper's DTW word times, as the known-lyrics results below show. |

Not now: Qwen3-ASR-1.7B (Apache-2.0). It had the best text, but broken timestamps and a 14.7 GB peak. CrisperWhisper weights are non-commercial, it is speech-tuned, and it has no singing results. LyricWhiz needs ChatGPT, so it is not open.

## Practical test: Fall For Me, 126.857–164.0 s of the master (37.17 s)

**Reference.** Line starts come from `outputs/ffm/NOTES.md`. They were hand-merged, are only good to ±0.1–0.2 s, and were not verified at word level.

- The ear-confirmed points are "stop" at ≈17.2 s ("currently way too early") and "FALL FOR ME" at 31.6 s.
- The second "fall for me" is at 34.8 s.
- The reference starts of "for a minute" (18.3 s) and "the stars" (21.6 s) are themselves doubtful. Every model and a stem onset put "the stars" at about 22.1 s.

All tests ran in separate venvs in the scratchpad, never ComfyUI's or the server's.

| Run | "stop" err | "fall for me" err (31.6 / 34.8) | Line-start MAE (max) | Time / peak mem |
|---|---|---|---|---|
| **Current app** (faster-whisper small + difflib) | **−9.24 s** | −0.08 / missing | 1.54 s (9.2) | n/a |
| MMS CTC (ctc-forced-aligner), raw mix | −12.54 | −2.68 / −1.76 | 7.23 (12.5) | 6 s / ~5 GB RSS |
| MMS CTC, HTDemucs stem, whole clip | −11.44 | +0.84 / +0.14 | 2.57 (11.4) | 6 s |
| MMS CTC, BS-RoFormer stem, whole clip | −11.70 | −0.06 / +0.12 | 2.48 (11.7) | 8 s |
| stable-ts align (turbo, MLX), mix | −10.50 | +0.32 / −0.66 | 1.39 (10.5) | 6 s / 2.1 GB |
| stable-ts align, RoFormer stem | −10.60 | +0.28 / −0.10 | 1.58 (10.6) | 11 s |
| stable-ts align + Silero VAD, mix | **all words at 37.17** (failed) | n/a | n/a | n/a |
| Qwen3-ForcedAligner-0.6B, mix or stem | all words at 0.00 (collapsed) | n/a | n/a | 4–75 s / 3–6 GB |
| **Anchored: CTC on RoFormer stem from 16.8 s** (the first parakeet word was at 17.12 s) | **−0.02** | **−0.06 / +0.12** | 0.44 (2.46 on the doubtful "for") | 5 s |
| Anchored: stable-ts on the mix from 16.8 s | +0.48 | +0.28 / −0.08 | 0.31 (0.66) | 2 s |
| Anchored: stable-ts on the stem from 16.8 s | +0.68 | +0.32 / −0.12 | 0.51 (2.06) | 2 s |

Transcription (no lyrics given):

| Run | Text heard | First-word time | Line MAE on matched lines | Time / mem |
|---|---|---|---|---|
| Whisper large-v3-turbo (mlx), mix | "I'm gonna make you fall for me / the stars are looking… / come to me, I let them see me / I'll make you happy / I'll make you fall for me / fall for me" | 16.02 (early) | 0.32 s | 2 s warm / 1.9 GB |
| Whisper turbo, HTDemucs stem | similar, more errors | 13.08 (early) | 0.89 s | n/a |
| parakeet-tdt-0.6b-v3 (mlx), RoFormer stem | "I'll make you fall for me / one minute / besides the cooking here waiting / come to me, a little city / I'll make you happy / I'll make you fall for me / fall for me" | **17.12** | 0.36 s | 1.7 s / 1.9 GB |
| parakeet v3, mix | **empty** | n/a | n/a | n/a |
| Qwen3-ASR-1.7B + Qwen3-FA, mix | "…come to meet. I'm a little silly. I'll make you happy…" (best text) | all at 0.00 | n/a | 149 s / **14.7 GB** footprint |

**Lyric check for the user.** Three independent ASRs (Whisper, Parakeet and Qwen3-ASR) all hear **"(I'll) make you fall for me"** at 17.1–18.8 s, where the lyric sheet has "Stop thinking / For a minute". It could be a misheard pickup, or the line could really differ. Worth a listen. If it really is the hook, that explains why every aligner struggles with line 1.

**Separation.**
- HTDemucs (CPU) took 41 s and 2.0 GB for 37 s of audio.
- BS-RoFormer `model_bs_roformer_ep_317_sdr_12.9755` via audio-separator (MPS) took 144 s wall time, about 60 s of which is model load, with a 4.5 GB peak. The download is 624 MB.
- In the first 4 s, RoFormer's stem sits at −80 to −180 dBFS, where HTDemucs's is at −42 to −48. HTDemucs leaks the intro synth.
- Both stems still contain voiced material from 5–16 s, so separation alone does not fix "stop".
- For full songs, plan for RoFormer taking several minutes on MPS, or run it on the 4090.

**Neon Rain (32 s, generated).**
- No hand ground truth exists, so only consistency could be checked.
- CTC, Whisper and Parakeet agree on the verse and chorus to within about 0.3 s.
- With the whole clip given, CTC dragged the **last** words ("I know") out to 30.0–31.9 s. On the mix, the outro "Every" landed at 30.68 s, where Whisper heard it at 24.2 s. This tail stretch mirrors the head problem: it needs an end anchor and a word-duration cap.
- Whisper hallucinated "Thank you." at 30 s.

Scripts and outputs are in `/private/tmp/claude-501/-Users-lh1783-dev-comfy/59cc99f2-780f-48e6-8009-ac6481ebc005/scratchpad/scripts/` and `/private/tmp/claude-501/-Users-lh1783-dev-comfy/59cc99f2-780f-48e6-8009-ac6481ebc005/scratchpad/t/`. They are temporary, so copy anything you want to keep. The scripts are `ctc_test.py`, `sts_test.py`, `mlxw_test.py`, `pk_test.py`, `qwen_test.py`, and `cmp.py`, the scorer.

## Comparison table

"Singing accuracy" lists only published numbers for sung audio. Most tools have none, and say so.

| Tool / model | License (code / weights) | Word timing on singing, published | Runtime / memory (observed or claimed) | Apple MPS / CPU | Integration effort for Typeset |
|---|---|---|---|---|---|
| **MMS_FA** (torchaudio) / **ctc-forced-aligner** (MMS-300m-1130) | BSD-2 / **CC-BY-NC 4.0** | None published. Tune Studio's singing fine-tune of the same base improved syllable F1 from 0.788 to 0.875 ([card](https://huggingface.co/tuneperfect/tunestudio-aligner)) | ~5–8 s per 37 s on CPU, ~5 GB RSS at batch 4 (fp32; lower with batch 1 / fp16). The README claims ≥5× less memory than torchaudio's API | CPU yes; MPS should work, but I ran CPU | A is already doing it. Add windowing, `<star>` tokens and caps. Low effort |
| **WhisperX** | BSD-2; Whisper MIT; aligner wav2vec2-base-960h (fairseq, MIT) | None on singing. Speech-only paper ([arXiv 2303.00747](https://arxiv.org/abs/2303.00747)) | faster-whisper + wav2vec2, ~1–3 GB | Whisper part runs on CPU only on Mac (CTranslate2 has no MPS); aligner on CPU | Medium. Same CTC idea as MMS but with an English LibriSpeech model, so likely worse on singing. Its VAD (pyannote) is tuned for speech |
| **stable-ts** | MIT / Whisper MIT | None. The [MAVL dataset paper (2025)](https://arxiv.org/abs/2505.18614) chose it for lyric alignment | 2–11 s per 37 s, 2.1 GB (MLX turbo) | **Yes, MLX backend** (`load_mlx_whisper`), plus HF and faster-whisper backends | Low. `model.align(audio, lyrics)`. Measured lag: +0.3–0.6 s. Avoid `vad=True` on music |
| **whisper-timestamped** | **AGPL-3.0** code / Whisper MIT | None | Whisper-sized | CPU/MPS through PyTorch Whisper | Low, but the AGPL is awkward and stable-ts covers the same ground |
| **Whisper large-v3 / turbo, DTW word timestamps** | MIT | Text only: Jam-ALT WER ~20–23 % long-form ([Syed et al. 2025](https://arxiv.org/abs/2506.15514)). No word-timing results. [arXiv 2509.09987](https://arxiv.org/abs/2509.09987) gets better word timing by filtering alignment heads and teacher-forcing characters (speech only) | Turbo on MLX: 2 s warm, 1.9 GB; first download ~1.6 GB | MLX on Mac; faster-whisper int8 on CPU | Already integrated (small). Switching to turbo is a one-line model change in faster-whisper |
| **CrisperWhisper 2.0** | MIT code / **non-commercial** weights | None (speech: ~30 ms on TIMIT, vendor-reported) ([repo](https://github.com/nyrahealth/CrisperWhisper)) | Whisper-sized | Transformers backend on CPU/MPS | Medium. Not for the open-weights prize framing |
| **parakeet-tdt-0.6b-v3** | NeMo Apache-2.0 / CC-BY-4.0 per NGC (the build.nvidia card says "NVIDIA Open Model License", so verify) | NVIDIA *claims* lyrics robustness, with no number ([NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/-/collections/parakeet-tdt-0.6b/-)). Observed: best onsets, **empty on the full mix** | 1.7 s, 1.9 GB (parakeet-mlx); 2.5 GB download | **parakeet-mlx on Mac**; NeMo on the 4090 | Low via `parakeet-mlx`. NeMo is heavy, and the 4090 has only 3.6 GB of disk free |
| **Canary-1b-v2** | CC-BY-4.0 | None on singing | ~1B params | NeMo; no MLX port I could confirm | Medium. No advantage shown over parakeet for this |
| **NeMo Forced Aligner (NFA)** | Apache-2.0 / CTC models CC-BY-4.0 | None on singing. On speech, Qwen reports NFA at 101–130 ms AAS ([Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)) | Parakeet-CTC-sized | CPU possible; CUDA preferred | Medium-high (NeMo install). This is the **commercially clean CTC alternative** to MMS |
| **Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B** | Apache-2.0 | ASR: EntireSongs-en WER 14.6, M4Singer 5.98. Aligner: speech only (32 ms AAS); **failed on songs here** | 149 s, 14.7 GB footprint (ASR + FA, MPS fp32) | Runs on MPS/CPU through transformers | Not tonight. Revisit the ASR-only path on the 4090 |
| **Huang/Benetos/Ewert lyrics aligner** (DALI-trained) | MIT, checkpoint in repo | **Jamendo word MAE 0.23 s, PCO 94 %** ([DAFx25 Table 1](https://staff.aist.go.jp/m.goto/PAPER/DAFX2025cheng.pdf); [repo](https://github.com/jhuang448/LyricsAlignment-Multilingual/)) | Small CRNN, CPU OK | CPU | Medium: needs phonemizer + separated vocals. Untested |
| Other lyrics aligners | varies | Cheng, Nakano & Goto (DAFx 2025): MAE 0.216 / MedAE 0.041 (code release not confirmed). Durand, Stoller & Ewert (Spotify, 2023): first <0.2 s AAE on Jamendo, **weights not released** ([arXiv 2306.07744](https://arxiv.org/abs/2306.07744)). Stoller 2019 end-to-end: 0.35 s. [schufo/lyrics-aligner](https://www.github.com/schufo/lyrics-aligner) (phoneme-level, MUSDB-trained). [SOFA](https://github.com/spicytigermeat/SOFA) (singing phoneme FA, for synth datasets). [Tune Studio aligner](https://huggingface.co/tuneperfect/tunestudio-aligner) (MMS fine-tuned on 669 UltraStar songs, CC-BY-NC, ONNX: **the most interesting drop-in** for A's MMS path). [SongTrans](https://arxiv.org/abs/2409.14619) and [STARS](https://arxiv.org/abs/2507.06670) (Chinese-focused, singing-synthesis annotation) | n/a | n/a | Tune Studio's ONNX aligner is a direct swap for the MMS emissions, with the same 20 ms frames and the same windowing |
| **Separation: HTDemucs / HDEMUCS_HIGH_MUSDB_PLUS** | MIT | ~8.4 dB vocal SDR (MUSDB) | 41 s per 37 s on CPU, 2 GB | CPU/MPS | A's current choice. Leaks synth in the intro here |
| **Separation: BS-RoFormer / Mel-RoFormer** | Code MIT (audio-separator, lucidrains, ZFTurbo); community checkpoints have **mixed or unclear licenses** | Mel-RoFormer 11.2 dB / BS-RoFormer 10.8 dB vocal SDR on MUSDB18HQ ([arXiv 2310.01809](https://arxiv.org/abs/2310.01809)). The ISMIR 2025 LBD finds alignment accuracy rises with separation quality ([Huang & Benetos](https://ismir2025program.ismir.net/lbd_412.html)) | 144 s per 37 s on MPS incl. load, 4.5 GB peak | MPS yes (audio-separator auto-selects) | Low via `audio-separator`, or **ComfyUI-MelBandRoFormer** (kijai) |

## Existing ComfyUI nodes

- [kijai/ComfyUI-MelBandRoFormer](https://comfy.org/cloud/supported-nodes/ComfyUI-MelBandRoFormer.md): `MelBandRoFormerModelLoader` + `MelBandRoFormerSampler` (vocals and instrumental out). The weights are [Kijai/MelBandRoFormer_comfy](https://huggingface.co/Kijai/MelBandRoFormer_comfy), a safetensors copy of KimberleyJSN's model. It is preinstalled on Comfy Cloud, and Comfy.org hosts an [official workflow](https://comfy.org/workflows/audio_melbandroformer_audio_separation-99aec65eea89/). **This is the easiest upgrade from HTDemucs inside ComfyUI.** Set `stereo=True` for stereo input.
- [AIFSH ComfyUI-WhisperX](https://www.runcomfy.com/comfyui-nodes/ComfyUI-WhisperX/WhisperX): transcription, alignment and diarization for subtitles. It is speech-oriented and was last updated around April 2025.
- [yuvraj108c ComfyUI-Whisper](https://www.runcomfy.com/comfyui-nodes/ComfyUI-Whisper): segment and word timestamps. [jhj0517 ComfyUI-faster-whisper](https://www.runcomfy.com/comfyui-nodes/ComfyUI-faster-whisper/faster-whisper-transcription) has a `word_timestamps` option.
- [ComfyUI-WordPop](https://github.com/Codebreakers-Studio/ComfyUI-WordPop) (from `research/verified-assessment.md`) is faster-whisper with lyrics input.
- I found **no ComfyUI node that does lyrics-specific forced alignment.** Typeset's aligner node would be the first, which also makes a good demo point.

## What A should change

1. **Anchor before aligning (the big fix).** Never force-align the whole song in one pass.
   - Get the vocal-activity regions from the stem: RMS above about −35 dBFS for ≥150 ms, as in Syed et al.'s RMS-VAD.
   - Get ASR word times: parakeet-v3 on the stem is the best for onsets. Whisper-turbo also works, but distrust its first word in each segment, which runs early.
   - Fuzzy-match the ASR words to the lyric lines, as the current difflib code already does, to get **line anchors**. Then run CTC per window, from the previous anchor's end to the next anchor's start, ±0.3 s.
   - At minimum, start the first window ~0.3 s before the first confidently matched sung word, and end the last window ~0.5 s after the last one.
   - On Fall For Me this alone moved "stop" from −11.7 s to −0.02 s.
2. **Use `<star>` wildcard tokens around each window and between lines.** ctc-forced-aligner's `preprocess_text(..., star_frequency="segment")` lets unlisted vocals, such as ad-libs, echoes and intro chops, be absorbed instead of stretching real words over them. If A stays on torchaudio `MMS_FA`, add a `<star>` column to the emissions as ctc-forced-aligner does (`alignment_utils.py`: the "adding a star token dimension" line).
3. **Cap word durations, and clamp line-edge words.**
   - Cap a single word at about 1.5 s, or 2.5 s for a held vowel. If a line-initial word exceeds the cap, move its start to the **latest stem onset** in [end − cap, end].
   - Do the mirror for line-final words: Neon Rain's "I know" stretched about 6 s into the tail.
   - Then snap each word start to a vocal-stem onset within ±80–120 ms, not to mix onsets. A's onset snapping should use librosa `onset_detect(backtrack=True)` on the stem.
4. **Separation: prefer Mel-/BS-RoFormer over HDEMUCS when available.**
   - Use kijai's ComfyUI node or `audio-separator`. Keep HDEMUCS_HIGH_MUSDB_PLUS as the low-memory fallback, at 2 GB on CPU.
   - Don't run the separator and the aligner models at the same time on MPS. Free each before loading the next. The two OOMs suggest serializing these jobs.
   - The 4090 has only 3.6 GB of disk, which is enough for the 624 MB BS-RoFormer checkpoint plus the 1.2 GB MMS model, but not for NeMo + Qwen.
5. **Detect missing lyric lines.** The project's lyric list has one "Fall for me", but two are sung. CTC then squeezes both into one, and the earlier aligner put its "for" at 35.26 s. Before alignment, diff the ASR text against the lyrics. When the ASR has a repeated hook that is missing from the lyrics, insert it, or bracket it with `<star>`.
6. **Licensing note for the "Open Weights" prize.** MMS (`MMS_FA`, `mms-300m-1130`) weights are open but **CC-BY-NC**. If a commercial-clean story matters, offer stable-ts + Whisper (all MIT) or NeMo NFA with a parakeet-CTC model (CC-BY-4.0) as the alternative backend. Mention this in the submission.
7. **Use the CTC per-word scores.** Expose them as `confidence` in words.json, so the studio can highlight words that need an ear-check, such as "stop", "minute" and "silly".
8. **Upgrade the default ASR from small to large-v3-turbo.** It costs about the same as Whisper medium, and the faster-whisper model id is `large-v3-turbo`. Pass `language="en"`, `condition_on_previous_text=False` and `vad_filter=False` on music, because Silero VAD drops singing. stable-ts with `vad=True` failed completely on the mix.

## Sources

- Jam-ALT benchmark: [arXiv 2311.13987](https://arxiv.org/abs/2311.13987), [readability-aware v2, arXiv 2408.06370](https://arxiv.org/abs/2408.06370), [dataset card](https://huggingface.co/datasets/jamendolyrics/jam-alt/blob/main/README.md) ("not time-aligned at the word level; use JamendoLyrics for alignment")
- Syed, Meresman Higgs, Cífka & Sandler, *Exploiting Music Source Separation for ALT with Whisper* (ICME-W 2025): [arXiv 2506.15514](https://arxiv.org/abs/2506.15514), [code](https://github.com/jaza-syed/mss-alt). Whisper large-v2. RMS-VAD on separated vocals gives a Jam-ALT WER of 20.35 (open SOTA); LyricWhiz EN is 23.70.
- Cheng, Nakano & Goto, *Improving Lyrics-to-Audio Alignment Using Frame-wise Phoneme Labels with Masked CE Loss* (DAFx 2025): [PDF](https://staff.aist.go.jp/m.goto/PAPER/DAFX2025cheng.pdf). Jamendo MAE 0.216 s, MedAE 0.041. Its Table 1 covers GC 0.22, HBE 0.23, KGLW 0.20, and HX-IH 0.16 (trained on 67k in-house songs).
- Durand, Stoller & Ewert, *Contrastive Learning-Based Audio to Lyrics Alignment for Multiple Languages* (2023): [arXiv 2306.07744](https://arxiv.org/abs/2306.07744)
- Kick, *Contrastive Lyrics Alignment with a Timestamp-Informed Loss* (JamendoLyrics++; code and checkpoints claimed): [ETH](https://www.research-collection.ethz.ch/server/api/core/bitstreams/1569974e-3b0f-46cf-b622-92411f1f7e26/content)
- Huang & Benetos, *Evaluating Lyrics Alignment under Source Separated Conditions* (ISMIR 2025 LBD): [abstract](https://ismir2025program.ismir.net/lbd_412.html), [code](https://github.com/jhuang448/LyricsAlignment-Multilingual/)
- Stoller, Durand & Ewert, *End-to-end Lyrics Alignment for Polyphonic Music* (ICASSP 2019): [PDF](https://www.audiolabs-erlangen.de/media/pages/resources/aps-w23/papers/6a672c705f-1663763415/2019_StollerEwert_LyricsCTC_ICASSP_arXiv.pdf)
- MIREX: I could not find 2024 or 2025 lyrics-alignment results pages. The MIREX 2017 numbers are the last widely cited ones ([Stoller ICASSP 2019 slides](https://sigport.org/sites/default/files/docs/ICASSP%202019%20Slides%20v2_0.pdf)). The field now reports on Jamendo, as above. Metrics: [mir_eval.alignment](https://mir-eval.readthedocs.io/latest/api/alignment.html).
- WhisperX: [arXiv 2303.00747](https://arxiv.org/abs/2303.00747). Forced-alignment comparison of modern ASR methods: [arXiv 2406.19363](https://arxiv.org/abs/2406.19363). *Whisper Has an Internal Word Aligner*: [arXiv 2509.09987](https://arxiv.org/abs/2509.09987)
- stable-ts: [GitHub](https://github.com/jianfch/stable-ts). Used for lyrics in MAVL: [arXiv 2505.18614](https://arxiv.org/abs/2505.18614)
- ctc-forced-aligner: [GitHub](https://github.com/MahmoudAshraf97/ctc-forced-aligner) (BSD-2 code, CC-BY-NC weights, `<star>` tokens)
- Tune Studio singing aligner: [HF](https://huggingface.co/tuneperfect/tunestudio-aligner). SingAlign: [HF](https://huggingface.co/pymaster/SingAlign). SOFA: [GitHub](https://github.com/spicytigermeat/SOFA). lyrics-aligner: [GitHub](https://www.github.com/schufo/lyrics-aligner)
- CrisperWhisper: [GitHub](https://github.com/nyrahealth/CrisperWhisper)
- Parakeet TDT 0.6B: [NGC collection](https://catalog.ngc.nvidia.com/orgs/nvidia/-/collections/parakeet-tdt-0.6b/-), [v3 card](https://build.nvidia.com/nvidia/parakeet-tdt-0_6b/modelcard), [parakeet-mlx](https://github.com/senstella/parakeet-mlx)
- Qwen3-ASR / Qwen3-ForcedAligner: [GitHub](https://github.com/QwenLM/Qwen3-ASR), [tech report summary](https://hyper.ai/en/papers/Qwen3-ASR)
- SongTrans: [arXiv 2409.14619](https://arxiv.org/abs/2409.14619). STARS: [arXiv 2507.06670](https://arxiv.org/abs/2507.06670). LyricWhiz: [arXiv 2306.17103](https://arxiv.org/abs/2306.17103)
- Mel-Band RoFormer: [arXiv 2310.01809](https://arxiv.org/abs/2310.01809). ZFTurbo MSST: [README](https://github.com/ZFTurbo/Music-Source-Separation-Training). audio-separator: [GitHub](https://github.com/nomadkaraoke/python-audio-separator)
- ComfyUI nodes: [ComfyUI-MelBandRoFormer](https://comfy.org/cloud/supported-nodes/ComfyUI-MelBandRoFormer.md), [workflow](https://comfy.org/workflows/audio_melbandroformer_audio_separation-99aec65eea89/), [Kijai weights](https://huggingface.co/Kijai/MelBandRoFormer_comfy), [ComfyUI-WhisperX](https://www.runcomfy.com/comfyui-nodes/ComfyUI-WhisperX/WhisperX), [ComfyUI-Whisper](https://www.runcomfy.com/comfyui-nodes/ComfyUI-Whisper), [ComfyUI-faster-whisper](https://www.runcomfy.com/comfyui-nodes/ComfyUI-faster-whisper/faster-whisper-transcription)

Not verified: CC-BY-4.0 vs the NVIDIA Open Model License for parakeet v3 (the sources conflict), the licenses of individual community RoFormer checkpoints, and the Kick paper's venue and numbers (OpenReview was blocked).
