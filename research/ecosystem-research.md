# Ecosystem research for "Recut" (Open Source Higgsfield entry)

Research date: 2026-10-30. Hardware context: MacBook M5 Max, 36 GB unified memory, macOS 26. Target: in-person submission at the NYC Build Night, Nov 2, 2026.

Everything below is sourced; where a claim rests on one secondary source, it says so. Two facts were verified separately by the coordinator and are marked **[coordinator-verified]**.

---

## TL;DR

1. **Deadline reality check.** The online submission window closed **Oct 30, 9am PT** (today). The only remaining path is the **NYC Build Night (Mon Nov 2, 5:30–10:30 PM ET, The Yard, 106 W 32nd St)**, whose Luma page says "In-person attendees will be eligible to submit until the end of the event day" and are also eligible for "special in-person awards." Register now and confirm with hosts that in-person late entries compete for the main prizes, not only the in-person awards.
2. **Novelty is weaker than it sounds.** Beat-synced auto-cutting of existing footage inside ComfyUI already exists (ComfyUI-BeatCompile, SyntaxNodes "Beat Sync"); timeline-as-data in ComfyUI already exists (LTX Director 2.0 with 2.1k stars, Sonder Editor, ComfyUI-Spool, Element_easy's `ESD_INFO`, Easy-Media timelineEditor); OTIO export from a ComfyUI app already exists (ComfyUI-Spool). A competition entry, **Xenoform**, already does "song in → beat-grid cut → LTX-2.5 render → FCPXML/EDL export" with a lane UI, built on comfy-sdk + comfy-api-proxy.
3. **What is still genuinely open:** a footage-preserving, music-*structure*-aware editor (downbeats/sections drive cut density) where generative VFX is scheduled by musical events (the drop) and the result round-trips to an NLE via OTIO. Nobody found does exactly that combination. Claim the combination, not the parts.
4. **Hardware:** LTX-2.x on a 36 GB Mac is marginal. The native LTX-2.3 template needs a 29 GB fp8 checkpoint + 9.4 GB Gemma (fp8 is unsupported on Metal) **[coordinator-verified]**; GGUF paths hit an open MPS NaN bug filed from an M5 Max on macOS 26. Plan: develop locally on LTX-Video 2B 0.9.8 distilled, run LTX-2.x on a rented GPU behind comfy-api-proxy.
5. **Realistic prizes:** Most Viral (best fit: short, shareable, personal footage), LTX VFX bonus (if LTX is the *only* generative model and the VFX moments are central), in-person awards. Most Innovative is a stretch given prior art; Best Overall is unrealistic against 96+ entries incl. 500-star apps.
6. Rules allow a fully local stack (Comfy SDK + comfy-api-proxy counts as "Comfy SDK"); demo must be ≤2 min, app must have a usable UI, repo must be OSS-licensed with setup instructions, and content must be "free of unlicensed IP" — so **do not use copyrighted music in the demo**.

---

## Q1. Audio-reactive / music-sync ComfyUI node packs

| Pack | What it does | Beat / downbeat / section | Cuts existing footage? | Health |
|---|---|---|---|---|
| [ComfyUI_RyanOnTheInside](https://github.com/ryanontheinside/ComfyUI_RyanOnTheInside) | "Flex" features from audio (RMS, spectral centroid, onset, chroma), MIDI, motion (optical flow), depth, color, Whisper; drives masks/IPAdapter/particles | Onset detection only; no beat/downbeat/section nodes in README; a RhythmFeatureExtractor + FeaturePeakDetector exist per [third-party docs](https://www.instasd.com/comfyui/custom-nodes/comfyui_ryanontheinside/rhythmfeatureextractor) | No | 867 stars, MIT, 237 commits; actively adds ACE-Step 1.5 nodes |
| [ComfyUI_Yvann-Nodes](https://github.com/yvann-ba/ComfyUI_Yvann-Nodes) | Audio Analysis → per-frame weights (drums/vocals/full via Demucs/OpenUnmix), Audio Peaks Detection, IPAdapter transitions on peaks, Audio Prompt Schedule | Peak detection on weights; no downbeat/section | No (V2V workflow restyles, does not cut) | 715 stars, GPL-3.0, v2.0 Nov 2024 |
| [ComfyUI-AudioScheduler](https://www.runcomfy.com/comfyui-nodes/ComfyUI-AudioScheduler) (a1lazydog) | Amplitude → float schedules for FizzNodes; attack/hold/release shaping | No beat node found | No | Older, FizzNodes-era |
| [Deforum comfy nodes](https://runcomfy.com/comfyui-nodes/deforum-comfy-nodes/BeatDetectionNode) (XmYx) | Has a `BeatDetectionNode` (timestamps of beats) | Beats only | No | Last push ~May 2025, 199 stars (per [tracker](https://gittrend.io/repo/XmYx/deforum-comfy-nodes)) |
| [ComfyUI-BeatCompile](https://github.com/UnlimitedEditing/ComfyUI-BeatCompile) | **Cuts video clips to beats and energy**; labels sections (intro/build/drop/release/break/outro) from the energy curve; cuts shorten as energy rises; role grammar for clips; ffmpeg render; outputs MP4 + plan | Beats, tempo, per-beat energy, heuristic sections | **Yes** | 0 stars, 9 commits, no license shown; also a Graydient slash command |
| [ComfyUI-SyntaxNodes](https://github.com/SyntaxDiffusion/ComfyUI-SyntaxNodes) "Beat Sync" | Folder of same-res videos + audio → auto-edited video; needs VHS Combine | Undocumented | **Yes** | 9 stars, 6 commits, ~465 days stale |
| SaltAI_AudioViz, yukascomfy ATI_AudioReactive | Audio-reactive visuals/animation | n/a | No | Stale (2024) |

Verdict: audio-reactivity for *generation* is a crowded, mature space. Beat-synced *cutting of footage* exists in ComfyUI but only as two tiny, unmaintained packs. Nothing found does downbeat- and section-aware cut planning with a proper data model.

Useful libraries for the analysis layer (all run on CPU/Mac):
- librosa (BSD) for beats/onsets/energy — used by [beat-synced-edit](https://github.com/ZiadAbdelkarim/beat-synced-edit), [Xenoform](https://github.com/tysonfarrington-cmyk/xenoform), [One-shot Multicam](https://github.com/apsolut/one-shot-multicam).
- [Beat This!](https://pypi.org/project/beat-this/) (CPJKU, ISMIR 2024) — beats + downbeats without madmom's DBN; last push Apr 2026.
- [allin1](https://github.com/mir-aidj/all-in-one) — beats/downbeats/sections (intro/verse/chorus…), but depends on NATTEN (CUDA). Mac routes: [all-in-one-infer v3.0.0](https://github.com/openmirlab/all-in-one-infer/releases/tag/v3.0.0) (pure PyTorch, installs on Apple Silicon) or [natten-mps](https://pypi.org/project/natten-mps/).
- madmom: PyPI build only supports Python <3.10; its DBN is reported as patented/non-commercial ([search summary](https://pypi.org/project/beat-this/)). Avoid.

## Q2. Timeline / NLE-style editing in ComfyUI — does the "TIMELINE data type" novelty hold?

**No, not as stated.** Several packs already pass an edit/timeline as a custom type or JSON:

| Project | Timeline model | Edits existing footage? | Export | Health |
|---|---|---|---|---|
| [LTX Director 2.0](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI) (WhatDreamsCost) | Full timeline node: snapping, in/out points, multi-select, split at playhead, toggleable tracks, IC-LoRA track, audio track; timeline save/load to JSON | **Yes** — trim/split/combine/extend imported video; Retake (beta); audio inpainting ([ComfyUI Wiki, Jun 24 2026](https://comfyui-wiki.com/en/news/2026-06-24-ltx-director-20)) | Video | **2.1k stars**, GPL-3.0, v2.0.4 |
| [ComfyUI-Sonder-Editor](https://github.com/SonderSaid/ComfyUI-Sonder-Editor) | Projects → scenes → lanes (video, audio, prompt, guide/keyframe, driver, reference); move/trim/split/layer clips; render queue | Yes | Timeline export to file | 24 stars, v0.8.0, GPL-3.0 |
| [ComfyUI-Spool](https://github.com/doubletwisted/ComfyUI-Spool) (competition entry) | Shots on a timeline with multiple takes; `project.spool`; trims/rearranges | Yes (imported media) | **OpenTimelineIO for Resolve/Premiere** | 3 stars, GPL-3.0 |
| [comfyui-obvpm-timeline](https://github.com/chanon/comfyui-obvpm-timeline) | "Mini video editor" node: drag, reorder, trim, cut at playhead, split, gaps; take preview with seam rating | Yes (no re-encode on split) | MP4 | 248 stars, v0.1.4 (Oct 8 2026) |
| [ComfyUI_Element_easy](https://github.com/supElement/ComfyUI_Element_easy) "Element Load and Edit Video" | Single-track editor widget; PySceneDetect auto-split; manual cuts; drag/reorder/trim; outputs `ESD_INFO` (JSON with segment ranges, fps, path); `Element Video Clip` decodes a segment | Yes | via downstream nodes | Small |
| [ComfyUI-Easy-Media](https://github.com/yolain/ComfyUI-Easy-Media) `easy timelineEditor` | Prompt/image/audio tracks → "structured data" with segments; MultiTrack Editor for H3 | Scheduling for generation, not cutting | — | 256 stars, GPL-3.0 |
| [TimeUi](https://github.com/jimmm-ai/TimeUi-a-ComfyUi-Timeline-Node) | Timeline UI prototype | No usable node | — | 231 stars, abandoned |
| [KJNodes Spline Editor](https://comfyui-wiki.com/en/custom-nodes/ComfyUI-KJNodes/nodes/spline-editor) / [FizzNodes](https://github.com/FizzleDorf/ComfyUI_FizzNodes) | Curve/keyframe scheduling of floats and prompts | No | — | Mature |
| [VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | Load Video (frame_load_cap, skip_first_frames, select_every_nth), Video Combine (+audio), Split/Merge/Select batches | Frame-range trimming only; no cut list, no transitions, no timeline | MP4 | 1.9k stars, GPL-3.0 |

Outside ComfyUI nodes but ComfyUI-connected: [Velorn](https://github.com/VelornLabs/velorn) (Electron multi-track editor, 518 stars, talks to local ComfyUI, 100+ MCP tools), and [ComfyStudio](https://www.sourcepulse.org/projects/29922086) (desktop timeline editor over local ComfyUI).

What *is* still open in this space: none of the above derives the timeline from **music structure** (beats/downbeats/sections) — their timelines are hand-arranged or generation-scheduled. None exposes a timeline type that is simultaneously (a) built by analysis nodes, (b) editable in a UI, (c) rendered by ffmpeg and (d) exported to OTIO. A `TIMELINE` type is a reasonable engineering choice but must not be pitched as "the first timeline in ComfyUI."

## Q3. Shot detection / video analysis nodes

- [hndrr/Comfyui-SceneDetect](https://github.com/hndrr/Comfyui-SceneDetect): PySceneDetect 0.7.x; takes core `VIDEO` input (reads the compressed file, no full frame decode); methods content/adaptive/threshold/hash/histogram; outputs representative frames, `scenes_json` with start/end frame + timecodes, `scene_count`. MIT. 5 stars.
- zhinangubei fork ([comfy.icu](https://comfy.icu/extension/zhinangubei__Comfyui-ZNGB-SceneDetect)): also exports per-scene MP4 + JSON; pins scenedetect 0.6.x.
- [ComfyUI-Video-Segmentation](https://www.runcomfy.com/comfyui-nodes/ComfyUI-Video-Segmentation): TransNetV2 shot boundaries with OpenCV fallback.
- Element_easy (above) runs PySceneDetect ContentDetector on import inside an editor widget.
- Motion analysis: RyanOnTheInside has optical-flow motion features (Farneback, Lucas-Kanade); OpenCV frame-diff is what [beat-synced-edit](https://github.com/ZiadAbdelkarim/beat-synced-edit) uses to score motion/energy/brightness per scene.
- CLIP-based "best moment" selection: no dedicated ComfyUI node found. Practical substitutes are motion + sharpness + brightness heuristics (as beat-synced-edit does) or a generic CLIP/aesthetic scorer node.

Takeaway: shot detection is a solved component; wrap PySceneDetect (BSD-3) directly in your node rather than depending on a 5-star pack.

## Q4. How Comfy Hub "apps" are actually built; what counts as "built on the Developer Platform"

Hub definition: "A ComfyUI app puts one or more workflows behind a simple interface" ([comfy.org/hub/apps](https://www.comfy.org/hub/apps/)). Rules summary: the platform is "the Comfy API, Comfy Router, and/or the Comfy SDK" ([ComfyUI Wiki rules digest](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield)). A workflow export alone does not qualify; a usable UI + example outputs is required.

Official example apps (all MIT, Next.js + TypeScript, server-side Comfy SDK, API-format workflow JSON with inputs injected by node ID):
- [comfy-cinematic-studio](https://github.com/Comfy-Org/comfy-cinematic-studio): no workflow at all — calls Comfy Router (`bfl/flux-2-pro`) with a prompt builder.
- [comfy-reshoot](https://github.com/Comfy-Org/comfy-reshoot): `analyze.api.json` + `generate.api.json`; MiniMax H3 + MoGe + CrossView LoRA; requires a **Comfy Developer Platform deployment** (`comfy-cli build init/push`, `deploy`), tested only on a 96 GB GPU.
- [comfy-openjutsu](https://github.com/Comfy-Org/comfy-openjutsu): same pattern; patched `h3_character_swap` node pack bundled in `build/`; also calls GPT Image 2.5 via Router. Requires deployment + API key.

So the official pattern is: **custom web frontend + Comfy SDK + cloud deployment**, not ComfyUI's App Mode. App Mode exists (frontend ≥1.41.13, [docs](https://docs.comfy.org/interface/app-mode)) but share links are Cloud-only, and the sidebar [Apps](https://docs.comfy.org/interface/apps) catalog is just `.app.json` workflows.

Fully local counts. The SDK docs explicitly list "your own ComfyUI" as a target via [comfy-api-proxy](https://docs.comfy.org/development/comfyui-server/api-proxy) (`pip install comfy-api-proxy`, serves API v2 on :8189, `COMFY_BASE_URL=http://127.0.0.1:8189`). Community entries using exactly this: [Xenoform](https://github.com/tysonfarrington-cmyk/xenoform) (comfy-sdk 0.5.0 + proxy), [D3voz/openjutsu](https://github.com/D3voz/openjutsu) (@comfyorg/sdk + proxy 0.1.6, 597 stars), [Freefield](https://artrealmai.com/article/freefield-open-source-higgsfield-comfyui-117-apps) (ComfyUI 0.42 + proxy). The proxy docs also describe running it "in front of a ComfyUI on a rented GPU" with a bearer token — your cloud fallback.

SDK facts ([docs](https://docs.comfy.org/development/api-development/sdks), [comfy-python-sdk](https://github.com/Comfy-Org/comfy-python-sdk)): `comfy-sdk` (PyPI, Py 3.10+) / `@comfyorg/sdk` (npm, Node 22+), v0.5.0; workflows must be API-format; outputs typed `image|video|audio|text|file|latent`; `job.events()` streams progress/preview/output via SSE; each `submit()` mints a new idempotency key (don't naive-retry). The Router (`comfy.models`) is a separate partner-model API.

comfy-api-proxy limits ([README](https://github.com/Comfy-Org/comfy-api-proxy)): uploads buffered, **100 MB per request default** (raise it or register files under the ComfyUI base dir via zero-copy registration for large footage); one proxy per ComfyUI; 13 stars, MIT, no releases. Custom nodes are not addressed but the proxy just forwards the graph, so installed custom nodes work.

Registry/bundling: `comfy node init` writes `pyproject.toml` with `[tool.comfy]` (PublisherId, DisplayName, Icon); `comfy node publish`; `.comfyignore` ([docs](https://docs.comfy.org/registry/publishing)). Comfy "Builds" package custom nodes + models for deployment: `comfy build init --custom-nodes-dir ./custom_nodes` ([serverless quickstart](https://docs.comfy.org/es/development/serverless/quickstart.md)). For a 3-day build, ship the node pack as a folder in the repo with `pip install -r requirements.txt` instructions; registry publishing is optional polish.

## Q5. LTX lineup, license, Mac feasibility, VFX capabilities

Lineup (sources: [HF LTX-2](https://huggingface.co/Lightricks/LTX-2), [HF LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5), [Comfy LTX-2.3 tutorial](https://docs.comfy.org/tutorials/video/ltx/ltx-2-3), [Comfy LTX-2.5 tutorial](https://docs.comfy.org/tutorials/video/ltx/ltx-2-5), [Comfy day-0 blog](https://blog.comfy.org/p/ltx-25-day-0-support-in-comfyui), [ComfyUI Wiki](https://comfyui-wiki.com/en/news/2026-08-11-ltx-2-5-open-weights-release)):

| Model | Params | Variants | Audio | Notes |
|---|---|---|---|---|
| LTX-Video 0.9.x (2B/13B) | 2B / 13B | distilled 0.9.8 | No | Only thing that comfortably fits a 36 GB Mac **[coordinator-verified]**; IC-LoRA/keyframe conditioning via `LTXVAddGuide` ([docs](https://docs.comfy.org/built-in-nodes/LTXVAddGuide)) |
| LTX-2 (19B) | 19B | dev bf16/fp8/nvfp4, distilled 8-step, distilled LoRA, spatial/temporal upscalers, camera-control LoRAs (dolly/jib/static) | **Yes** (joint AV) | Jan 2026 |
| LTX-2.3 (22B) | 22B | dev fp8, distilled fp8, Gemma 3 12B fp4-mixed encoder, IC-LoRA Union Control (depth/pose/canny), ID-LoRA, FLF2V, IA2V, editing IC-LoRAs (subtitle/object removal, restoration, outpainting) | Yes | Native ComfyUI templates; "LTX-2.3 Style Transition" (ltx2.3-transition LoRA) template exists in ComfyUI 0.43 **[coordinator-verified]** |
| LTX-2.5 (22B) | 22B | dev/distilled bf16, ComfyUI-only int8 convrot, nvfp4 (Blackwell only), Gemma 4 12B encoder, duration head, DFR | Yes | T2V/I2V/FLF2V templates; multishot; 4K HDR; auto duration; V2V/A2V. Open weights reported Aug 11 2026 (ComfyUI Wiki); coordinator verified an Oct 22 2026 Lightricks release of 2.3 + 2.5 with VFX IC-LoRAs (Relight, Clean-Plate, Alpha-Gen, Day-To-Night, Colorization, Motion-Track-Control, Union-Control) **[coordinator-verified]** |

License: **LTX-2.x Community License** — free commercial use under $10M annual revenue (entity-wide incl. affiliates); paid license above; redistributors must pass terms on ([HF 2.5 card](https://huggingface.co/Lightricks/LTX-2.5), [scancode entry](https://scancode-licensedb.aboutcode.org/ltx-2-cla-2026.html)). Not OSI open source, but "open weights." The competition itself lists LTX as an open-weights partner and Open-Weights-Only entries (e.g. Freefield) use LTX-2.5, so **LTX weights run locally/self-hosted are almost certainly fine for "Open Weights Only." LTX-2.5 Fast/Pro *partner nodes* are not** (they are hosted APIs).

VRAM reality: ComfyUI-LTXVideo lists "CUDA GPU with 32GB+ VRAM" ([repo](https://github.com/Lightricks/ComfyUI-LTXVideo)); int8 distilled is ~21.5 GB + 15.4 GB int8 Gemma; community reports 24 GB as practical minimum, 12–16 GB only with heavy offload and ~7 min/clip ([search digest](https://ltxworkflow.com/models/ltx25-distilled-int8)). GGUF DiTs exist: Q4_K_M 13.6 GB, Q8_0 22.8 GB (Unsloth figures via [modelfit](https://modelfit.io/blog/ltx-2-5-on-mac/)).

Apple Silicon evidence:
- fp8 does not exist on Metal → fp8 checkpoints/encoders fail outright ([lilting.ch M1 Max test](https://lilting.ch/en/articles/ltx2-wan22-mac-local-video-gen)). The native LTX-2.3 template (29 GB fp8 + 9.4 GB Gemma) is therefore out **[coordinator-verified]**.
- bf16 LTX-2.x on MPS produces NaN/black video intermittently: [ComfyUI issue #15804](https://github.com/Comfy-Org/ComfyUI/issues/15804), filed Aug 22 2026 **from an M5 Max on macOS 26** (your exact platform), still open; LTX-2.5 i2v failed 8/8 runs before the reporter's local patches (`baddbmm` on `torch.empty` → `zeros`; add bf16→fp32 upcast). [HF discussion #58](https://huggingface.co/Lightricks/LTX-2.5/discussions/58): workaround = KJ loaders at fp32 + SDPA + GGUF Q8; one M4 Max 36 GB user said the default workflow "worked just fine" (no numbers); an M1 Max 64 GB run took 478 s total at 6.26 s/it.
- MLX ports are the fastest Mac path but are not ComfyUI: M3 Max 128 GB LTX-2.5 704x480x97f in 620 s; M5 Max 128 GB LTX-2.3 Q4 512x512x121f in ~101 s; M5 Pro 24 GB LTX-2.3 int8 streamed 704x512x121f in 150 s / 14.5 GB peak ([modelfit summary](https://modelfit.io/blog/ltx-2-5-on-mac/), [gajesh MLX Q4 card](https://huggingface.co/gajesh/ltx-2.3-mlx-q4)). No published LTX-2.5 run at ≤36 GB.
- [LTX Desktop 1.3.x](https://github.com/Lightricks/ltx-desktop/releases) now generates locally on 32 GB Macs running macOS 26 (Retake, Extend, IC-LoRAs) — a possible emergency renderer for demo clips, but it isn't ComfyUI and would weaken the "built on Comfy" story.

Realistic answer to "3–6 s at 512–768 px in minutes on a 36 GB M5 Max": LTX-Video 2B/13B 0.9.8 distilled yes; LTX-2.5 distilled GGUF Q4 is *possible* (~25–28 GB resident) but you will likely spend your weekend on MPS NaNs. Run LTX-2.x on a RunPod/other GPU behind comfy-api-proxy (RunPod is a competition sponsor and has an [LTX-2 ComfyUI guide](https://www.runpod.io/articles/guides/comfyui-ltx-2-runpod)).

VFX capabilities usable as "key-moment" effects: I2V from the frame at the drop; **FLF2V** (first/last-frame) as a generative morph between the outgoing and incoming shot — native template, the most feasible "morph transition"; **LTX-2.3 Style Transition** template **[coordinator-verified]** for the "style flip on the drop"; IC-LoRA Union Control (depth/pose/canny) to restyle a real shot while keeping its motion; Relight / Day-To-Night / Clean-Plate / Alpha-Gen IC-LoRAs **[coordinator-verified]** for plate-preserving VFX; camera-control LoRAs (LTX-2 19B) for a dolly "push"; extension via `LTXVAddGuide` keyframes. Retake/extend are productized in LTX Director and LTX Desktop.

## Q6. Prior art and the competitive field

Open source beat-sync editors (non-Comfy): [beat-synced-edit](https://github.com/ZiadAbdelkarim/beat-synced-edit) (librosa + PySceneDetect + OpenCV motion scoring → energy-matched cuts → ffmpeg; JSON EDL; MIT; 13 stars) is nearly your analysis layer; [beatflow](https://github.com/Future-Insight/beatflow) (in-browser, MIT), [video_sync](https://github.com/fortil/video_sync), [CtrlBeat](https://github.com/ActArtech/CtrlBeat) (Rust/Tauri, AGPL), [BeatSync-Engine](https://github.com/Merserk/BeatSync-Engine) (Windows AMV tool), [OpenBeat](https://github.com/eimexdev/OpenBeat) (Resolve beat markers), GitHub topic [beat-sync](https://github.com/topics/beat-sync).

Commercial: CapCut Auto Cut / Beat Sync templates cut clips to detected beats ([CapCut help](https://www.capcut.com/help/how-to-use-auto-cut)); DaVinci Resolve 20 added AI beat detection markers with snapping ([Jayaretv](https://jayaretv.com/edit/davinci-resolve-ai-beat-detector-explained/), [20.0.1 notes](https://nofilmschool.com/davinci-resolve-20-0-1-update)); Premiere desktop has Remix (retiming) and OTIO but native beat detection only in the iPhone app ([Adobe help](https://helpx.adobe.com/ca/premiere/mobile/audio-editing/use-beat-detection-for-music-synced-edits.html)); third-party [BeatMarker](https://github.com/samaBR85/BeatMarker-PremierePlugin) (OSS UXP plugin). Neural Frames (stem-level reactivity, Autopilot) and Kaiber (Beat Sync module) generate visuals rather than cut footage ([2026 roundup, vendor-biased](https://freebeat.ai/articles/8-best-kaiber-alternatives-for-ai-music-videos-beat-synced-visuals-and-social-content-in-2026)).

Competition field (as of Oct 30): the curated [jutsuhq/open-source-higgsfield](https://github.com/jutsuhq/open-source-higgsfield) lists **96 challenge entries**; the [GitHub topic](https://github.com/topics/opensourcehiggsfield) shows 24. Leaders: [D3voz/openjutsu](https://github.com/D3voz/openjutsu) 597 stars, ComfyArt 396, [Freefield](https://github.com/neuregex/freefield) (117 apps, Open-Weights-Only). Higgsfield sent Comfy a cease-and-desist on Oct 29; Comfy said the challenge stays open ([X](https://x.com/ComfyUI/status/2115928993623109648), [coverage](https://explainx.ai/blog/higgsfield-cease-and-desist-comfy-open-source-higgsfield-challenge-48-hours-claimed-vs-verified-2026)).

Closest competitors to Recut:
- **[Xenoform](https://github.com/tysonfarrington-cmyk/xenoform)** — "Song in, music video out, on your own GPU." Reads beats, sections, the drop; plans cuts on the beat grid; Demucs stems; mostly generates (Z-Image stills → LTX morphs), but a "Your clips" mode cuts user footage to the beat; LTX-Video 0.9.5 drafts, LTX-2.5 finals; comfy-sdk 0.5.0 + comfy-api-proxy; FastAPI; lane UI with per-shot drawer; exports FCP7 XML / FCPXML / EDL bundle, 15 s hook, 720p share cut; MCP, MIDI, OSC. MIT. 1 star. **This is ~80% of Recut's pitch, already submitted.**
- **[Mondo Music Video](https://github.com/hodgemann/mondo-music-video)** — beats, downbeats, energy, sections → "montage grammars" → generated passages (H3/Seedance); synchronized score view with playhead. Apache-2.0, 10 stars. Generates, does not cut footage.
- **[One-shot Multicam](https://github.com/apsolut/one-shot-multicam)** — librosa beat-aligned inserts (music mode) between real and LTX-2.3 CrossView re-shot angles; Comfy Cloud.
- **[OpenKatana](https://github.com/rk0neki/OpenKatana)** — agent-driven editor, 85 ComfyUI nodes, "beat analysis" listed, Apache-2.0, 17 stars.
- **[ComfyUI-Spool](https://github.com/doubletwisted/ComfyUI-Spool)** — timeline + OTIO export inside ComfyUI.
- LTX-on-your-footage VFX entries: [FXjutsu](https://github.com/audriu/fxjutsu), [One-take VFX](https://github.com/Kainotomic/one-take-vfx), [PlateLock](https://github.com/TusharTechs/platelock), [Seam](https://github.com/jdnichollsc/seam) (two shots → one AI transition).

No entry found combines footage-preserving beat/section-aware cutting + generative VFX scheduled at musical events + OTIO round-trip + a node-level timeline type. That intersection is your lane.

## Q7. OpenTimelineIO

- Library: v0.18.1 (Nov 9 2025), Python 3.12/3.13 (VFX Platform 2026); core ships `otio_json`, `otiod`, `otioz`; FCPXML/FCP7 XML/AAF/CMX EDL moved to the `OpenTimelineIO-Plugins` package since 0.17 ([releases](https://github.com/PixarAnimationStudios/OpenTimelineIO/releases)). Writing a Timeline → Track → Clip(ExternalReference, TimeRange) with Markers from Python is a few dozen lines.
- NLE import: Resolve 18+ imports OTIO/OTIOZ in free and Studio ([OTIO wiki](https://github.com/PixarAnimationStudios/OpenTimelineIO/wiki/Tools-and-Projects-Using-OpenTimelineIO)); Premiere added OTIO import/export in the Jan 2026 release with caveats — clip names revert to filenames on round-trip, sequence settings may need manual fixing ([Adobe community](https://community.adobe.com/t5/premiere-pro-beta-discussions/now-in-beta-otio-import-and-export/m-p/15486920/highlight/true)); Resolve 20.2 rejected `file://`-prefixed media paths from Premiere exports ([Adobe community](https://community.adobe.com/t5/premiere-pro-beta-discussions/now-in-beta-otio-import-and-export/m-p/14985932)). Use plain absolute paths in `target_url` and test the import in Resolve before the demo.
- ComfyUI integration: ComfyUI-Spool already exports OTIO; Prism Pipeline has both OTIO and a ComfyUI plugin ([Prism](https://prism-pipeline.com/docs/latest/general/miscellaneous/opentimelineio/)). No standalone OTIO node pack found — a `TimelineToOTIO` node is a small, real contribution, but not a headline.

## Q8. Rules nuances

Sources: [competition page](https://www.comfy.org/open-source-higgsfield), [blog](https://blog.comfy.org/p/higgsfield-promised-to-open-source), [ComfyUI Wiki digest](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield), [SF Luma](https://luma.com/5mydmvu6), [NYC Luma](https://luma.com/nyc-yjfm), [frontend issue #21346](https://github.com/Comfy-Org/ComfyUI_frontend/issues/21346).

- **Deadline:** "Submission window closes: October 30 · 9am PT." Build window 10/15–10/30; winners 11/6. Some page copy omits the time (issue #21346). Comfy reiterated Oct 30 after the C&D.
- **NYC Build Night:** Mon **Nov 2, 2026, 5:30–10:30 PM ET**, The Yard, 106 W 32nd St (hosts: ZeroSpace, Xuelong Mu, ComfyUI/Allyson Toy, Eric Tang, Sahar Mor, Georgia Limcaoco). Agenda: 5:30–8:30 build, 8:30–9:00 ComfyUI + RunPod talks, 9:00–9:30 demos. Quote: "In-person attendees will be eligible to submit until the end of the event day" and "In-person entries are also eligible for special in-person awards." It is **not** on comfy.org's page (which lists only SF/LA). Action: register, and ask the hosts (Discord/Luma) whether in-person late entries are judged for the main categories.
- **Submission contents:** working app with usable interface + example outputs (workflow export alone does not qualify); repo with app code, workflow files, an open-source license, and setup instructions so others can run it; demo video **≤ 2 minutes** ("we're judging the work, not your video editing"); optional deployed link; encouraged social post tagged #OpenSourceHiggsfield. Entry form: [Typeform](https://form.typeform.com/to/V1dSQrkS).
- **Team size:** not stated anywhere. **Specific license:** any open-source license.
- **Categories:** each entry is eligible for one main category and one model-provider bonus. Most Innovative: "An app that's never been done, novel custom node packs or uses of ComfyUI" — the video "must explain why the submission is innovative." Most Viral: "Delightful to use and made to be shared." Open Weights Only: "No partner nodes or closed-source APIs, open-weights models only" — the rule is about models/nodes/APIs; non-generative OSS libraries (librosa, PySceneDetect, ffmpeg, OTIO) are plainly fine. A PR to the site clarified the Comfy API itself remains allowed in that category ([PR #21201](https://github.com/Comfy-Org/ComfyUI_frontend/pull/21201)).
- **LTX bonus:** "LTX must be the core video model in the workflow to qualify" ($2,000 cash). If LTX is the only generative video model you call, you satisfy the letter; make the VFX moments visibly central to satisfy the spirit.
- **Content:** entries must be "lawful, SFW, and free of unlicensed IP or likenesses." No explicit music clause, but copyrighted music is unlicensed IP → use your own track, CC0, or an ACE-Step 1.5 generated track (RyanOnTheInside ships ACE-Step nodes; ACE-Step is open weights).
- **Judging rubric:** none published. Winners featured on comfy.org/hub with credit.

---

## What's genuinely new vs. what exists

| Recut claim | Already exists? | Where | Honest framing |
|---|---|---|---|
| Beat-synced auto-cut of existing footage | **Yes** | ComfyUI-BeatCompile, SyntaxNodes Beat Sync, Xenoform "Your clips", beat-synced-edit, CapCut, Resolve 20 markers | "A maintained, open implementation" at best |
| Section/energy-aware cut density (shorter cuts toward the drop) | Yes | BeatCompile (energy heuristics), Mondo (downbeats + sections, generated) | Downbeat-aligned + section-aware on *real footage* is uncommon but not unprecedented |
| Shot detection + best-moment selection feeding the cut | Yes | beat-synced-edit (PySceneDetect + motion scoring); scene-detect nodes | Component, not novelty |
| TIMELINE data type passed between ComfyUI nodes | **Yes** | LTX Director JSON timeline, Element_easy `ESD_INFO`, Easy-Media timelineEditor, Sonder Editor, Spool | Do not claim "first." Claim "an analysis-derived timeline" |
| Timeline UI with beat snapping inside the app | Partly | LTX Director (snapping, in/out), Xenoform lanes, Mondo score view | Beat-grid snapping specifically is a small differentiator |
| Generative VFX only at musical key moments | **Not found** | Xenoform morphs on every beat (generated stills); FXjutsu/One-take VFX apply LTX effects without music logic | **Your strongest unique claim** |
| LTX FLF2V / Style Transition as the "drop" transition between two real shots | Partly | Seam (two shots → AI transition, no music), Style Transition template | Novel when triggered by song structure |
| OTIO export from a Comfy app | Yes | ComfyUI-Spool; Xenoform exports FCPXML/EDL | Nice polish, not novelty |
| Built on Comfy SDK + comfy-api-proxy, fully local | Yes (common) | Xenoform, D3voz/openjutsu, Freefield | Table stakes |

## Risks

**Rules / timing**
- The online deadline has passed; your entire eligibility rests on the NYC in-person clause. If the hosts say in-person entries only compete for in-person awards, your prize ceiling drops sharply. Confirm before investing the weekend. Demo slot is 9:00–9:30 PM; expect ~2 minutes live.
- Copyrighted music in the demo could disqualify under "unlicensed IP."

**Technical / hardware**
- LTX-2.x on the 36 GB Mac: fp8 unsupported on Metal; bf16/GGUF hits open MPS NaN bug #15804 (filed from an M5 Max/macOS 26). Budget zero demo-critical generation on the Mac with LTX-2.x. Use LTX-Video 2B 0.9.8 distilled locally for development and a rented GPU (RunPod) + comfy-api-proxy for LTX-2.x renders; cache renders.
- comfy-api-proxy's 100 MB default upload limit will bite with phone footage; raise it or point LoadVideo at files already under the ComfyUI base dir.
- The Comfy SDK rejects UI-format workflows; export API format and pin node IDs (the official apps hardcode IDs).
- Timeline UI in 3 days is where projects die. A canvas timeline with drag/snap is a multi-day job on its own.
- allin1 section detection needs NATTEN (CUDA) — use energy/novelty heuristics or all-in-one-infer v3 on Mac; test install early or drop it.

**Positioning**
- Xenoform already told the same story (beats/sections/drop → beat-grid cut → LTX → NLE export) using the same SDK/proxy stack. Judges who have seen it will discount "auto music-video" framing. Differentiate on *footage-preserving* editing and *musically-scheduled VFX*.
- Field is 96+ entries, several with hundreds of stars and weeks of work.

## Recommended scope (3 days, one person)

**Build (must-have):**
1. Analysis layer in plain Python, exposed as nodes *and* callable from the app: `AudioAnalyze` (librosa onsets/energy + Beat This! beats/downbeats; novelty-based section boundaries; "drop" = max energy jump at a downbeat) → `TIMELINE` JSON; `ShotDetect` (PySceneDetect ContentDetector + OpenCV motion/sharpness score per shot).
2. `BeatSyncCut`: place cuts on downbeats by default, subdivide to beats as section energy rises, pick shots by motion score with anti-repeat and source spacing (steal the logic shape from beat-synced-edit, cite it). Output: `TIMELINE` with clips (src, in, out, start) + markers (beats, downbeats, sections, drop).
3. `TimelineRender` via ffmpeg (trim+concat+mux track) and `TimelineToOTIO` via `opentimelineio` (clips on one video track, beat/section markers, plain absolute paths). Test the .otio in Resolve once.
4. **One** LTX VFX moment at the drop: FLF2V (last frame of outgoing shot → first frame of incoming) or the LTX-2.3 Style Transition template, run through comfy-sdk against comfy-api-proxy (local LTX-Video 0.9.8 while developing; LTX-2.x on a GPU box for the demo render). Insert the generated clip into the TIMELINE as a clip with `generated=true`.
5. App: small FastAPI/Next.js UI — upload footage + track → analysis view (waveform with beats/downbeats/sections, detected shots) → "Cut" → preview MP4 + download OTIO → toggle "VFX at drop". Keep the timeline *display* read-only with a few sliders (cut density, section sensitivity, VFX on/off, seed). That satisfies "usable interface."

**Cut:**
- Ableton/TouchDesigner-style editable multi-track timeline with drag and snapping (show a static beat-grid visualization instead).
- "Impossible camera push," morph transitions beyond FLF2V/Style Transition, IC-LoRA depth/pose control, Demucs stems, allin1, registry publishing, App Mode, Comfy Cloud deployment.
- Any claim of running LTX-2.x locally on the Mac.

**Claim in the demo:**
- "Recut treats the song as the edit's conductor: downbeats and sections set the cut grid, shot analysis picks the footage, and generative VFX (LTX) is spent only where the music earns it — then the cut leaves ComfyUI as OTIO so you finish it in Resolve or Premiere."
- "Open weights, fully local stack: Comfy SDK + comfy-api-proxy + custom node pack; the only generative model is LTX" (true only if you don't call partner nodes).

**Do not claim:**
- "First timeline data type in ComfyUI," "first beat-sync in ComfyUI," "first OTIO export from ComfyUI" (all false — LTX Director, BeatCompile, Spool).
- "Runs LTX-2.5 on a MacBook" unless you actually did and it was stable.
- "Never been done" in general — frame innovation as the *combination* and show the prior art you built on; judges reward honesty and Most Innovative requires an explanation anyway.

**Category targeting:** submit for **Most Viral** (15–30 s recut of your own phone footage with one striking drop moment is inherently shareable) plus the **LTX VFX bonus**; mention Open-Weights-Only compliance so judges can slot you there if they prefer. Be present at the NYC demos — in-person awards have no published competition.
