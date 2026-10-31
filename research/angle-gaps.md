# Angle gaps: realtime, typography, sound, NLE, "looks" — what's covered, what's open

Researched 2026-10-30 for the Comfy Org "Open Source Higgsfield" competition. Every claim links to the page it came from. Where I could not find evidence I say so.

## TL;DR

1. **Deadline flag.** comfy.org says the online submission window closed **Oct 30, 9am PT**, winners Nov 6, build nights SF 10/28 + LA 10/29. No NYC / Nov 2 event appears on any official page; the Comfy blog only says "IRL in SF, NYC & LA". Verify your Nov 2 path before building. ([rules](https://comfy.org/open-source-higgsfield/), [wiki](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield), [blog](https://blog.comfy.org/p/higgsfield-promised-to-open-source))
2. **Field so far:** 24 repos on the GitHub topic, ~100 on the community awesome-list. Zero realtime/live entries, zero typography-first entries, zero NLE plugins, zero "sound design for a cut" entries. Generative "one-tap VFX preset" apps are **crowded** (Conjure, FXjutsu, FreeField, Forkfield, Montagio, PlateLock, One-take VFX). ([topic](https://github.com/topics/opensourcehiggsfield), [list](https://github.com/jutsuhq/open-source-higgsfield))
3. **Sound is the cleanest verified gap.** Higgsfield's own July-2026 audio post: "there's no dedicated music or sound-effects generator working independently of dialogue yet." No competition entry does foley/SFX/music-bed/stems. Mac-feasible with ACE-Step 1.5 (official MLX support), Stable Audio Open (native ComfyUI), Kokoro/Chatterbox (MPS). Video-to-audio models (MMAudio, HunyuanFoley) have **no Mac reports** — treat as risk.
4. **Typography is a real gap** and Mac-feasible: Qwen-Image (LongText-Bench EN 0.943 vs FLUX.1-dev 0.607), Qwen-Image-Edit-2511 edits in-scene text preserving font, Z-Image-Turbo bilingual text at ~4 GiB. Only one tiny node (WordPop, 7 stars) does kinetic captions in ComfyUI. Closed tools (Higgsfield/Runway/Pika/Kling) have no lyric/caption feature I could find.
5. **Realtime on Mac is honest-but-thin:** best published Apple number is 22.7 fps SDXS-512 via CoreML on M3 Ultra; StreamDiffusion on MPS is 2.5–4 fps. Daydream Scope / StreamDiffusionV2 / Krea Realtime own the NVIDIA high end. OSC/MIDI nodes exist (VrchStudio), Syphon output for Mac does not.
6. **NLE angle just got harder:** DaVinci Resolve 21.1 (Sept 2026) removed Python scripting from the free edition entirely; the new Resolve MCP server is Studio-only. Premiere UXP can export frames/import clips but no ComfyUI panel exists. Spool (OTIO export, tested on M3 Max) is the only timeline-ish entry.
7. **"segcam" / "lofi scifi" could not be identified.** @lofiscifi on Instagram exists (display name "Tyson Plastic", 45 posts) but content isn't indexable; "segcam" has no public footprint beyond unrelated repos. Working hypothesis: a segmentation-camera look (flat per-class fills, outlines, labels). Ask the user for a link.
8. **LTX bonus:** rule text is "LTX must be the core video model in the workflow." LTX-2.3 Foley V2A LoRA needs the 22B base (not Mac-feasible). LTX-Video 2B as the i2v engine in a typography app is the cheaper, safer way to qualify.

---

## Competition facts that shape the choice

| Item | Fact | Source |
|---|---|---|
| Main prizes | $10k Best Overall (every entry considered); RTX 5090 each for Most Innovative ("never been done, novel custom node packs or uses of ComfyUI"), Most Viral ("delightful to use and made to be shared"), Open Weights Only ("no partner nodes or closed-source APIs"); 10 × $250 credits | [comfy.org](https://comfy.org/open-source-higgsfield/) |
| LTX bonus | "$2,000 cash. VFX Workflow Built with LTX. LTX must be the core video model in the workflow to qualify." | same |
| Other bonuses | FLUX 3 must be core model ($1k/$500/$250 credits); MiniMax H3 ($1k credits). One main + one bonus per entry. | same |
| Requirements | Working app with usable UI + example outputs; built on Comfy API / Router / SDK; OSS license + setup; ≤2-min demo video; post with #OpenSourceHiggsfield | [wiki](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield) |
| Dates | Build 10/15–10/30; submissions close **10/30 9am PT**; winners 11/6 | [comfy.org](https://comfy.org/open-source-higgsfield/), [Luma LA](https://luma.com/73q6c0ln) |
| SDK | `comfy-sdk` (PyPI) / `@comfyorg/sdk` (npm); `comfy-api-proxy` fronts local ComfyUI (8188 → v2 API on 8189); SDK + API v2 are beta 0.1.x | [docs](https://docs.comfy.org/development/api-development/sdks) |
| App Mode | App Mode / App Builder / ComfyHub launched Mar 2026 — Comfy itself is pushing "workflow → app" | [docs](https://docs.comfy.org/interface/apps), [press](https://www.globenewswire.com/news-release/2026/03/10/3253141/0/en/ComfyUI-Launches-App-Mode-App-Builder-and-ComfyHub-Enabling-Anyone-to-Run-AI-Workflows-Without-Touching-a-Node-Graph.html) |

**Competition entries by angle** (from the [topic page](https://github.com/topics/opensourcehiggsfield) + [jutsuhq list](https://github.com/jutsuhq/open-source-higgsfield)):

| Angle | Entries found | Notes |
|---|---|---|
| Realtime / live / TD / OSC | **none** | Xenoform mentions a "VJ live page" + MIDI as a side feature ([repo](https://github.com/tysonfarrington-cmyk/xenoform)) |
| Typography / captions / lyrics | **none typography-first** | Mondo Music Video exports `lyrics.srt` / burns lyrics in ([repo](https://github.com/hodgemann/mondo-music-video)); Conjure makes a "before/after reel with captions" |
| Sound design pass | **none** | easycomfee (music+voice), cat-tapes (ACE-Step bed), Xenoform (Demucs stems drive lighting) — all music/voice, no foley/SFX at cuts |
| NLE plugin | **none** | Justae Flow = panel for EffectCraft (OSS compositor), not AE ([repo](https://github.com/HomoLapis/justae-flow)); open-studio-for-affinity (Affinity MCP bridge, Windows/NVIDIA); Spool = timeline inside ComfyUI with OTIO export ([repo](https://github.com/doubletwisted/ComfyUI-Spool)) |
| VFX presets | **crowded (7+)** | Conjure (22 presets, LTX-2.5 + FLUX 3 Klein, comfy-sdk, recipes shareable via URL/JSON/PR, photo→video only) ([repo](https://github.com/Orazen/conjure)); FXjutsu (v2v on your footage, LTX-2.5 IC-LoRA, 5 s clips, 2–3 min on a 4090) ([repo](https://github.com/audriu/fxjutsu)); FreeField (Wan 2.2, preset folders, comfy-sdk) ([repo](https://github.com/droppedmyza/freefield)); Forkfield (recipe embedded in MP4 metadata, Qwen-Image-Edit + LTX-2.5) ([repo](https://github.com/marciano71/forkfield)); Montagio, PlateLock, One-take VFX, SpEdE |
| Segmentation | SpEdE (click object in Gaussian splat → remove/replace) | 3D-splat scoped, not a footage look |

---

## A. TouchDesigner ↔ ComfyUI / realtime

### What exists

| Tool | What it is | Platform / maturity | Source |
|---|---|---|---|
| ComfyUI-TD (JiSenHua; descends from olegchomp's TDComfyUI) | Nodes streaming images/JPEG/video/audio/point clouds/3DGS from ComfyUI → TD over WebSocket; `LoadTDImage` for TD → Comfy. No OSC/MIDI. Needs ComfyUI2TD.tox. | 168★, AGPL-3.0, Windows paths, Mac unstated, docs partly Chinese | [repo](https://github.com/JiSenHua/ComfyUI-TD) |
| StreamDiffusionTD (dotsimulate) | TD operator wrapping StreamDiffusion; img2img/txt2img/vid2vid; local or via Daydream API | Windows 10/11 + CUDA only; "Mac and Linux aren't supported"; Patreon-gated | [II blog](https://interactiveimmersive.io/blog/artificial-intelligence/using-streamdiffusion-with-touchdesigner/), [Derivative workshop](https://derivative.ca/workshop/ai-workshop-%E2%80%93-introduction-streamdiffusion-td-may-ai-%E5%B7%A5%E4%BD%9C%E5%9D%8A-streamdiffusion-td-%E5%85%A5%E9%96%80%E6%93%8D%E4%BD%9C-%E4%BA%94%E6%9C%88%E4%BB%BD%E5%A0%B4%E6%AC%A1), [Livepeer](https://blog.livepeer.org/builder-story-dotsimulate-x-daydream) |
| ComfyStream (Livepeer) | Runs a ComfyUI API-format graph per frame on live video; 15–30 fps target with TensorRT | CUDA/TensorRT, Docker | [docs](https://docs.livepeer.org/v2/developers/ai-inference-on-livepeer/comfystream), [stream-pack](https://github.com/livepeer/comfyui-stream-pack) |
| Daydream Scope | Self-hosted runtime for realtime autoregressive video (StreamDiffusionV2, LongLive, Krea Realtime 14B, RewardForcing, MemFlow); WebRTC + Spout + NDI out; VACE control | Apache-2.0; no Mac/Syphon mention; community alpha Nov 2025 | [README](https://huggingface.co/daydreamlive/scope/blob/main/README.md), [BusinessWire](https://www.businesswire.com/news/home/20251106860538/en/Daydream-Launches-Scope-and-Expands-StreamDiffusion-with-SDXL-Support-Advancing-the-Open-Source-Real-Time-AI-Video-Ecosystem) |
| StreamDiffusionV2 | Wan-based 1.3B / 14B streaming pipeline, Apache-2.0, MLSys 2026 | NVIDIA | [repo](https://github.com/hacksider/StreamDiffusionV2) |
| Krea Realtime 14B | Open weights, Wan 2.1 14B Self-Forcing distill; ~11 fps on a single **B200** | NVIDIA datacenter | [ThursdAI](https://thursdai.news/companies/krea), [review](https://plisio.net/fr/ai/krea-ai) |
| VrchStudio comfyui-web-viewer | "real-time AI-generated interactive art framework": OSC, MIDI, gamepad, keyboard, mic/audio, WebSocket inputs; streams image/flipbook/video/audio to browsers; example workflows for OSC+LivePortrait, IC-Light | 359★, MIT, 1,050 commits; "Agentic VJ" announced for CES 2026 — unverified it shipped | [repo](https://github.com/VrchStudio/comfyui-web-viewer) |
| RyanOnTheInside pack | Audio/MIDI/motion/depth feature extraction → modulate any param; FeatureOscillator. No OSC. | widely used | [listing](https://www.comfyonline.app/comfyui-nodes/RyanOnTheInside) |
| comfyui-NDI | NDI in + out | needs ndi-python | [listing](https://www.comfyonline.app/comfyui-nodes/comfyui-NDI) |
| decadetw spout-syphon-im-vj | Spout out on Windows; **Syphon/Mac "later", author had no M-series Mac** | unfinished for Mac | [listing](https://www.comfyonline.app/comfyui-nodes/ComfyUI-decadetw-spout-syphon-im-vj) |
| SaltAI_AudioViz | audio-reactive nodes for VJs | May 2024 | [listing](https://www.runcomfy.com/comfyui-nodes/SaltAI_AudioViz) |

### What Apple Silicon actually does

| Setup | Number | Source |
|---|---|---|
| SDXS-512 + CoreML + 3-thread camera pipeline, **M3 Ultra** | **22.7 fps @ 512²** (best published Apple realtime figure). Quantization gave no speedup; Neural Engine "unsuitable"; CUDA tricks don't transfer | [paper](https://www.alphaxiv.org/abs/2605.16259) |
| StreamDiffusion img2img on MPS | ~2.5 fps M1 Max; ~3–4 fps M3 (anecdotal); maintainers: MPS unsupported | [gist](https://gist.github.com/fbarretto/e61dbf5bb25fd5e98975a42fc7dd5295), [issue](https://github.com/cumulo-autumn/StreamDiffusion/issues/34) |
| StreamDiffusion-Mac fork (SD-Turbo default, img2img only) | "interactive speeds", no numbers; 14★ | [repo](https://github.com/patrickhartono/StreamDiffusion-Mac) |
| SDXL-Turbo 1-step 512² ComfyUI | 71 s cold on base M1; ~3 s/run cached on base M2 mini | [mybyways](https://mybyways.com/blog/go-even-faster-with-sdxl-turbo) |
| Z-Image-Turbo (Draw Things) | 6-bit ≈ 4 GiB RAM; per-step only 1.01–1.23× faster than FLUX.1-dev; one M3 Max user got blank output | [Draw Things](https://releases.drawthings.ai/p/quantify-z-image-turbo-efficiency) |
| FLUX.2 Klein 9B 1024² | 85 s M4 Max / 105 s M3 Max / 145 s M2 Max (table; methodology not given); Klein 4B 30–40 s on M1 Max via mflux | [lilting.ch](https://lilting.ch/en/articles/flux2-klein-apple-silicon) |
| Qwen-Image-2.1 | ~13 s/step 1024² on M4 Pro 48 GB (≈5 min/img); mflux bf16 on M5 Max 78 s/img **peak 46 GB** | [modelfit](https://modelfit.io/blog/qwen-image-2-1-mac-apple-silicon/), [laozhang](https://blog.laozhang.ai/en/posts/qwen-image-2-1-local) |
| General | "ComfyUI is 3× slower than Draw Things for the same model" on Mac (claim) | [insiderllm](https://insiderllm.com/guides/stable-diffusion-mac-mlx/) |

### Gap verdict (A)
- **Open:** no competition entry is realtime; no polished open "live visuals from ComfyUI" app with OSC/MIDI/audio-reactive control; **no Syphon output exists for Mac at all**.
- **But:** realistic Mac quality is SD-Turbo/SDXS-class at 512² at single-digit fps through ComfyUI/MPS (CoreML ~20 fps requires bypassing ComfyUI). Scope/Daydream/Krea own the "wow" tier on NVIDIA. `comfy-sdk` is request/response — a streaming loop would talk to ComfyUI's WebSocket directly, which weakens the "built on the Developer Platform" story. A realtime demo risks looking like 2023.

---

## B. Text / typography / captions

### B1. Which open models render text

| Model | Text evidence | Size / Mac | Source |
|---|---|---|---|
| **Qwen-Image** (20B, Apache-2.0) | LongText-Bench **EN 0.943 / ZH 0.946** vs FLUX.1-dev 0.607 / 0.005; CVTG-2K ≈0.83; "only Qwen-Image and GPT Image 1 render such long text clearly" | bf16 ~40 GB → needs GGUF Q4/Q5 on 36 GB; ~13 s/step M4 Pro; `mps` noted on card | [tech report](https://arxiv.org/pdf/2508.02324), [LongCat table](https://arxiv.org/pdf/2512.07584), [HF card](https://huggingface.co/Qwen/Qwen-Image), [Mac](https://modelfit.io/blog/qwen-image-2-1-mac-apple-silicon/) |
| **Qwen-Image-Edit-2511** | "add, delete, or modify bilingual text directly, keeping original size, font, and style" — the tool for text-as-object-in-scene | same family; GGUF | [Comfy docs](https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511) |
| **Z-Image / Z-Image-Turbo** (6B, Apache-2.0, 8 steps) | "strong bilingual text rendering" claim; no public LongText numbers in abstract | <16 GB; Draw Things 6-bit ≈4 GiB; MLX 4-bit fits 16 GB Mac | [paper](https://arxiv.org/abs/2511.22699), [MLX build](https://huggingface.co/avlp12/CyberRealistic-Z-Image-Turbo-v4-mflux-4bit) |
| FLUX.2 [flex] / FLUX.2 | [flex] marketed as the typography-focused variant (API); base FLUX.2 rated 4.0/5 typography by img.ly | API; Klein 4B/9B open (9B non-commercial) | [img.ly](https://img.ly/ai-benchmarks/models/flux-2.md), [Pruna](https://www.pruna.ai/blog/flux2flex-3-faster) |
| **FLUX 3 Image Klein** (5.6B, open Oct 15 2026, gated, Kommunity License) | **No text-rendering measurement found**; comparison blog: "strongest documented reason to prefer Qwen-Image over Klein is text rendering" | 11.2 GB bf16 / 5.6 GB fp8 (fp8 not on MPS) | [VentureBeat](https://venturebeat.com/technology/black-forest-labs-opens-flux-3-image-klein-weights-with-free-commercial-use-limited-to-smaller-businesses), [BFL notes](https://docs.bfl.ml/release-notes), [groundy](https://groundy.com/articles/flux-3-klein-vs-qwen-image-2-1-which-open-weights-model-fits-an-8gb-gpu/) |
| HunyuanImage 3.0 | 80B MoE (13B active); qualitative "poster titles, infographic text"; ≥3×80 GB | **not Mac-feasible** | [NVIDIA](https://docs.nvidia.com/nemo/automodel/model-coverage/diffusion/tencent/HunyuanImage-3.0.md), [wiki](https://comfyui-wiki.com/en/news/2025-09-27-tencent-open-source-hunyuan-image-3-0) |
| Video: LTX-2.x / Wan 2.2 / 2.5 | No text-legibility benchmark exists; LTX-2 "may struggle with precise text rendering within generated video" | — | [Wikipedia](https://en.wikipedia.org/wiki/LTX_(text-to-video_model)), [LTX-2 paper](https://arxiv.org/pdf/2601.03233) |

Implication: render text with an **image** model (Qwen-Image / Qwen-Edit / Z-Image), then animate with i2v (LTX-Video 2B locally) or composite; don't ask a video model to spell.

### B2. Kinetic typography / captions tooling

| Tool | What | Maturity | Source |
|---|---|---|---|
| ComfyUI-WordPop | Word-level animated subtitles: pop, karaoke, bounce, typewriter (libass), kinetic-wobble (Pillow, audio-linked jitter); faster-whisper; outputs transparent WebM/MOV overlay; lyrics.txt + beat JSON inputs; Demucs optional | **7★**, 11 commits; wobble = CPU, ~10 min per 5 min 1080p; manual macOS install | [repo](https://github.com/Codebreakers-Studio/ComfyUI-WordPop) |
| ComfyUI-WhisperX / ComfyUI_WhisperSRT / ComfyUI-Whisper / ComfyUI_ASR | SRT/transcription; Whisper (yuvraj108c) burns subtitles onto frames; no kinetic typography | mature-ish | [WhisperX](https://github.com/AIFSH/ComfyUI-WhisperX), [ASR](https://www.runcomfy.com/comfyui-nodes/ComfyUI_ASR) |
| Remotion template-tiktok + @remotion/captions | whisper.cpp → `createTikTokStyleCaptions` paged word captions; React-rendered | 272★; company license for some entities | [template](https://github.com/remotion-dev/template-tiktok), [docs](https://www.remotion.dev/docs/captions/transcribing) |
| tiktokcaptions (PyPI) | Whisper + ffmpeg word-highlight captions, MIT | small | [PyPI](https://pypi.org/project/tiktokcaptions) |

### B3. Closed platforms
No lyric-video, caption-generation or text-animation feature found for Higgsfield, Runway, Pika or Kling; comparison: "you sync the song and assemble the video yourself" ([Atlabs](https://www.atlabs.ai/blog/5-best-ai-tools-to-create-lyrical-music-videos-in-2026)). Higgsfield's guide mentions static overlays via "Screenshot and Timeline tools" only ([Segmind guide](https://blog.segmind.com/higgsfield-ai-video-effects-generators-guide/)).

### B4. Competition
None typography-first. Mondo exports/burns `lyrics.srt` ([repo](https://github.com/hodgemann/mondo-music-video)); Xenoform has no lyric typography ([repo](https://github.com/tysonfarrington-cmyk/xenoform)).

### Gap verdict (B)
**Real and Mac-feasible.** Both halves are open: (1) *kinetic/lyric typography* — only WordPop (7★) in ComfyUI; Remotion is the serious OSS stack; (2) *text as a physical object in the shot* — Qwen-Image-Edit-2511 + Z-Image + LTX-Video 2B i2v makes "put the lyric on the billboard / neon / wet pavement and animate it" possible locally. Downside: diffusion text-in-video is unreliable past a few words; typographic compositing can read as "not AI" to judges unless the generative part is visible.

---

## C. Sound design for video

### Models

| Model | Open weights? | Size / VRAM | Mac / MPS | ComfyUI nodes | License | Source |
|---|---|---|---|---|---|---|
| **LTX-2.3 Foley V2A LoRA** (Lightricks, Oct 2026) | yes (gated HF); rank-32 LoRA, ~227 MB | needs **ltx-2.3-22b-dev** base + Gemma 3 12B encoder; trained 960×544, 89 f @24 fps; frame cap 169 (~7 s), window longer clips; audio guidance 6–8; strength 0.8–1.0; negative "No music / No speech"; not validated on 2.5 | **not feasible** on 36 GB M5 Max (22B, fp8 unsupported on Metal) → rented GPU | ComfyUI-LTXVideo (`LTXVSetAudioVideoMaskByTime`, `MultimodalGuider`) + VHS | LTX-2 community | [HF](https://huggingface.co/Lightricks/LTX-2.3-22b-LoRA-Foley-V2A), [docs](https://docs.ltx.io/open-source-model/feature-guides/audio/video-to-audio-foley), [blog](https://ltx.io/blog/bring-silent-videos-to-life-foley-lora), [X](https://x.com/ltx_io/status/2077749626766250370) |
| **MMAudio** (large_44k_v2) | yes | ~6 GB VRAM 16-bit; 8 s default; 44k | **no Mac reports found**; "tested only on Ubuntu", CUDA builds | Kijai ComfyUI-MMAudio (581★, 232K downloads, "WIP") | code MIT, **weights CC-BY-NC 4.0** | [repo](https://github.com/hkchengrex/MMAudio), [Kijai](https://github.com/kijai/ComfyUI-MMAudio), [registry](https://registry.comfy.org/nodes/comfyui-mmaudio) |
| HunyuanVideo-Foley | yes | XXL 20 GB / 12 GB offload; XL 16 / 8 GB offload; fp8 NVIDIA-only | no Mac reports | if-ai, phazei (v1.2.6 May 2026), Vantage | Tencent community (territory limits) | [repo](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley), [phazei](https://github.com/phazei/ComfyUI-HunyuanVideo-Foley), [Vantage](https://github.com/vantagewithai/Vantage-HunyuanFoley) |
| ThinkSound (Any2Audio) | yes | unspecified | none | ComfyUI-ThinkSound | code Apache-2.0 but "commercial use NOT permitted"; bundles Stable Audio VAE | [repo](https://github.com/FunAudioLLM/ThinkSound) |
| AudioX | yes | unspecified; 10 s examples | CPU fallback only | jinxishe/ComfyUI-AudioX | CC-BY-NC, watermarked | [repo](https://github.com/ZeyueT/AudioX), [node](https://github.com/jinxishe/ComfyUI-AudioX) |
| FoleyCrafter | yes | — | — | smthemex/ComfyUI_FoleyCrafter | — | [node](https://github.com/smthemex/ComfyUI_FoleyCrafter) |
| **ACE-Step 1.5** (music) | yes | 24 GB+ recommended (CUDA); MLX 8-bit XL-Turbo claims 30 s track in ~4 s on M-series (vendor claim) | **official Mac support** (macOS launch script, MLX backend; MPS/CPU); M2 Air 16 GB write-up | **native ComfyUI template** (Audio) | — | [repo](https://github.com/ace-step/ACE-Step-1.5), [Comfy blog](https://blog.comfy.org/p/ace-step-15-is-now-available-in-comfyui), [MLX](https://huggingface.co/ddalcu/ACE-Step-1.5-XL-Turbo-MLX-Serve-8bit), [M2](https://en.bioerrorlog.work/entry/ace-step-15-local-m2-macbook) |
| Stable Audio Open 1.0 (1.1B) | yes | light; 47.6 s clips | native ComfyUI, standard nodes (no explicit MPS report found) | native | Stability Community | [Comfy docs](https://docs.comfy.org/tutorials/audio/stable-audio/stable-audio-1) |
| Stable Audio Open **Small** (341M) | yes | runs on **Arm CPU**, <8 s for 11 s audio on a phone; English prompts, no vocals | yes (CPU) | — | Stability Community (<$1M rev) | [gigazine](https://www.gigazine.net/news/20250515-stable-audio-open-small/) |
| DiffRhythm / YuE | yes | YuE heavy, VRAM unlisted | — | ComfyUI_DiffRhythm (last release Mar 2025), ComfyUI_YuE | — | [DiffRhythm](https://runcomfy.com/comfyui-nodes/ComfyUI_DiffRhythm) |
| TTS: Chatterbox | yes | small | **"CPU and Mac MPS supported"** (May 2025) | FL ChatterBox, wildminder | MIT | [repo](https://github.com/filliptm/ComfyUI_Fill-ChatterBox) |
| TTS: Kokoro (82M) | yes | tiny | CPU/ONNX fine | GeekyGhost, stavsap, MW, BS_Kokoro-onnx | Apache | [repo](https://github.com/GeekyGhost/ComfyUI-Geeky-Kokoro-TTS) |
| TTS: F5-TTS | yes | — | unverified | niknah (15 s cutoff) | — | [repo](https://github.com/niknah/ComfyUI-F5-TTS) |
| TTS: VibeVoice 1.5B / 7B | 1.5B yes (~6 GB fp16); 7B pulled by MS, mirrors only | — | wrapper claims Apple Silicon | VibeVoice-ComfyUI, TTS-Audio-Suite | — | [listing](https://www.runcomfy.com/comfyui-nodes/VibeVoice-ComfyUI), [guide](https://localaimaster.com/blog/vibevoice-local-setup-guide) |
| TTS: Higgs Audio v2 (3B-base) | yes | ~13 GB fp16 est. | — | TTS-Audio-Suite | non-commercial | [Spheron](https://www.spheron.network/tools/gpu-recommender/bosonai/higgs-audio-v2-generation-3B-base/) |
| Closed partner nodes | Mirelo SFX 2.0 (video→SFX, returns mix + separate dialogue), ElevenLabs text-to-SFX, Sonilo music, Sony Woosh template | cloud credits | — | — | closed → disqualifies Open-Weights | [Mirelo](https://docs.comfy.org/tutorials/partner-nodes/mirelo/mirelo-sfx), [ElevenLabs](https://docs.comfy.org/tutorials/partner-nodes/elevenlabs/text-to-sound-effects.md) |

### Does anything do a "sound design pass"?
- **Higgsfield Audio (Jul 31 2026):** six models, **all speech** (Seed Audio 1.0, Eleven v3, Qwen Audio 3.0, MiniMax Speech 2.8 HD, Seed Speech, VibeVoice) + Change Voice + Translation. Quote: "there's no dedicated music or sound-effects generator working independently of dialogue yet." No stems. ([post](https://higgsfield.ai/blog/higgsfield-audio))
- **ComfyUI ecosystem:** SFX/foley nodes exist; **nothing** does cut detection → per-shot foley → transition hits → ambience → music bed → **stems to DAW/NLE**. ([search](https://docs.comfy.org/tutorials/partner-nodes/mirelo/mirelo-sfx))
- **Competition:** none (see table above).

### LTX bonus interaction
Rule: "LTX must be the core video model in the workflow." In a Foley-V2A pipeline LTX-2.3 is the *only* generative model (video latents frozen, audio generated) — literally the core model, but the output is audio and the category is named "VFX Workflow". Judges' call; I'd treat it as a stretch. It also forces a rented GPU (RunPod is a sponsor) and Comfy Cloud API nodes are unlikely to expose a custom LoRA. Safer: use LTX-Video 2B for any *video* generation in the app and keep foley as a separate engine.

### Gap verdict (C)
**Strongest verified gap**, matches the user's Ableton background, and most of the stack is Mac-native. Risk: the video-to-audio models (MMAudio/HunyuanFoley) have zero Mac/MPS reports; plan a fallback (VLM shot captions → Stable Audio Open text-to-SFX). License caution: MMAudio weights CC-BY-NC, ThinkSound/AudioX non-commercial — fine for Open-Weights-Only ("open weights"), note it in the README.

---

## D. NLE / editor integration

| Host | What exists | Maturity | comfy-sdk? | Source |
|---|---|---|---|---|
| **DaVinci Resolve** | barckley75 `comfyUI_DaVinciResolve` (SaveImage/SaveAudioToDaVinci; needs Studio API); "ComfyUI Export for DaVinci Resolve" (DNxHR/ProRes nodes); "ComfyUI-SecondUnit" (YouTube only, no repo found) | small | no | [node](https://comfy.icu/extension/barckley75__comfyUI_DaVinciResolve), [civitai](https://civitai.com/articles/36343/comfyui-export-for-davinci-resolve), [YT](https://www.youtube.com/watch?v=hVPWA6_Ydug) |
| Resolve API status (**new**) | **21.1 (Sept 2026) removed Python scripting from the free edition**: "The Python API was being used to hack studio features into the free version." 21.1 also adds a **native MCP server — Studio only** — for Claude/Codex to organize media, cut reels, batch render. API supports static values, not keyframes; `AddRenderJob` returns None | — | — | [Puget](https://www.pugetsystems.com/blog/2026/09/10/how-davinci-resolve-free-v21-1-scripting-changes-affect-puget-bench/), [CineD](https://www.cined.com/davinci-resolve-21-1-released-ai-assistant-integration-via-mcp-individual-hdr-trims-and-python-scripting-moves-to-studio/), [API notes](https://pypi.org/project/dvr/1.6.2/) |
| **Premiere Pro (UXP)** | UXP DOM: sequences/tracks/clips/markers; sequence **frame export** (EXR fixed 2025); `importFiles(bin)`; trackItem in/out edits; networking/fs/shell APIs; **no** EDL/AAF/OTIO export; version gating (UXP 8.2 vs Premiere 25.6). **No ComfyUI UXP/CEP panel found.** | — | — | [Adobe](https://developer.adobe.com/premiere-pro/uxp/resources/fundamentals/apis), [forum](https://forums.creativeclouddeveloper.com/t/update-of-uxp-apis-inside-of-premiere-pro/10384) |
| After Effects | AppMana `appmana-comfyui-after-effects-plugin`: WIP native effect plugin, 10★, 5 commits, Windows build only | WIP | no | [repo](https://github.com/AppMana/appmana-comfyui-after-effects-plugin) |
| "AE-like" OSS | Justae Flow: ComfyUI panel inside **EffectCraft** (OSS compositor); storyboard, transitions, VACE reframe, SeedVR2/LTX Refine, SAM 3 cutout, LTX-2.5 extend; local / Comfy API / Cloud | 83 commits, 2★, GPL-3 | no (direct HTTP/WS) | [repo](https://github.com/HomoLapis/justae-flow) |
| Nuke | vinavfx `nuke_comfyui` (ComfyUI nodes inside Nuke via server; ~331★ claim) | real users | no | [profile](https://github.com/vinavfx), [meetup](https://www.alexanderrichtertd.com/post/comfyui-in-nuke-td-meetup) |
| Blender | AIGODLIKE ComfyUI-BlenderAI-node; alexisrolland ComfyUI-Blender; Texturaizer | mature | no | [AIGODLIKE](https://www.github.com/AIGODLIKE/ComfyUI-BlenderAI-node), [ComfyUI-Blender](https://www.runcomfy.com/comfyui-nodes/ComfyUI-Blender) |
| Krita (exemplar) | Acly krita-ai-diffusion: local or remote ComfyUI, auto-installs needed custom nodes, live painting, v1.43 | gold standard | no (own client) | [repo](https://github.com/Acly/krita-ai-diffusion) |
| Final Cut Pro | nothing found | — | — | — |
| Affinity (entry) | open-studio-for-affinity: Affinity MCP + Desktop folder exchange; Flux Kontext GGUF; Windows/NVIDIA only; 0★ | toy | no (direct 8188) | [repo](https://github.com/viriato68/open-studio-for-affinity) |
| Timeline (entry) | ComfyUI-Spool: timeline inside ComfyUI, takes compare, soundtrack, **OTIO export to Resolve/Premiere**, tested Apple Silicon (M3 Max) | v0.1.0, 3★, GPL-3 | no | [repo](https://github.com/doubletwisted/ComfyUI-Spool) |
| Commercial reference | Magnific plugin for Resolve/Premiere/AE | closed | — | [Magnific](https://www.magnific.com/plugins/comfyui) |

### Gap verdict (D)
No competition entry is an NLE plugin and **no host integration uses comfy-sdk** — a genuine gap. But feasibility in 3 days on a Mac dropped: Resolve free lost scripting (Sept 2026), so a Resolve panel needs Studio; Premiere UXP is possible (frame export + import + networking) but you'd be writing an Adobe plugin, a ComfyUI roundtrip and a UI in 72 hours. The pragmatic version is a **sidecar app with OTIO/FCPXML round-trip** (Spool-shaped), which is less of a "wow".

---

## E. "VFX style across platforms" — segcam / lofi scifi

### Identification attempt
- `@lofiscifi` on Instagram exists; search snippet shows display name **"Tyson Plastic"**, 359 followers, 45 posts; the profile page itself isn't readable without login. ([IG](https://www.instagram.com/lofiscifi/))
- "segcam" has **no** public footprint as an aesthetic: hits are unrelated — cverrier/segcam (YOLOv8-seg realtime webcam contour overlay, Apple Silicon supported), npm `seg-cam` (BodyPix), SegmeCam (Linux webcam). ([segcam](https://github.com/cverrier/segcam), [seg-cam](https://store.boilerplate.com/product/npm/seg-cam))
- Note: Xenoform's author is `tysonfarrington-cmyk` ("Tys") — possibly the same Tyson, unconfirmed; Xenoform mentions neither segcam nor segmentation. ([repo](https://github.com/tysonfarrington-cmyk/xenoform))
- **Working hypothesis:** "segmentation camera" look — flat per-class/per-instance color fills, contour outlines, class labels/HUD, the machine-vision aesthetic (Cityscapes/SAM auto-mask visualizations). The cverrier repo is a decent visual reference if so. **Ask the user for a post link before building around it.**

### Signature-look building blocks in ComfyUI

| Block | Nodes | Source |
|---|---|---|
| Video segmentation | Kijai ComfyUI-segment-anything-2 (`Sam2VideoSegmentation`, `Sam2AutoSegmentation`), Florence2SAM2, LayerStyle `SAM2VideoUltra`, SAMURAI | [Sam2Video](https://www.runcomfy.com/comfyui-nodes/ComfyUI-segment-anything-2/Sam2VideoSegmentation), [Florence2SAM2](https://github.com/rdancer/ComfyUI_Florence2SAM2) |
| Datamosh / glitch / pixel sort | DJZ-Nodes `DjzDatamoshV6`; GlitchNodes (19 nodes: DitherMe halftone, LineScreen, Interference); Fill-Nodes `FL_PixelSort`; post-processing `PixelSort`; Vextra | [DJZ](https://runcomfy.com/comfyui-nodes/DJZ-Nodes/djz-datamosh-v6), [GlitchNodes](https://www.runcomfy.com/comfyui-nodes/GlitchNodes) |
| Halftone / riso | GlitchNodes DitherMe/LineScreen; no dedicated riso node found | same |
| Relight | IC-Light (Kijai) video relight workflow w/ depth; Light-A-Video; IC-Light V2 (fal API) | [RunComfy](https://www.runcomfy.com/comfyui-workflows/comfyui-ic-light-workflow-for-video-relighting), [Light-A-Video](https://www.runcomfy.com/comfyui-nodes/ComfyUI_Light_A_Video/light-a-video-loader) |
| Rotoscope / "Scanner Darkly" | no dedicated node; = SAM2 masks + flat shading + edge lines (deterministic) or Wan-VACE/AnimateDiff restyle (heavy) | — |

### Higgsfield's preset catalogue (what "VFX preset" means to judges)
Launched with 23 VFX presets (Thunder God, Levitation, Disintegration, Melting…); Packs 3–6 added Sand Storm, Freezing, Diamond, Duplicate, Powder Explosion, Clone Explosion, Fire Breath → 40+ by Jul 2025; "Effects Mix" stacks several. All generative i2v, not graded looks. ([launch](https://higgsfield.ai/blog/Higgsfield-Effects-Mix-Lets-You-Tell-Bigger-Stories), [Pack 4](https://higgsfield.ai/blog/Higgsfield-Effects-Pack-4-Blockbuster-VFX), [Pack 6](https://higgsfield.ai/blog/Higgsfield-Effects-Pack-6-Unleashes-Five-New-VFX-Tools))

### Gap verdict (E)
"One-click VFX presets, shareable" is **the most crowded angle** in the competition (Conjure already does URL-shareable recipes; Forkfield embeds recipes in the MP4). What **nobody** has: a deterministic, Mac-runnable, flicker-free **look engine** (segmentation/depth/edge-driven stylization + glitch + relight) with presets that apply to any footage in minutes, not 22B-model renders at 2–3 min per 5 s. Downside: judges may read it as "filters" unless a generative element is visible (e.g., per-segment restyle of a keyframe with Z-Image/Qwen-Edit, propagated by masks).

---

## F. Conspicuously missing for editors / motion designers / musicians

| Need | What exists | Gap | Source |
|---|---|---|---|
| Workflow/project versioning | comfyui-workspace-manager (save history, versions, revert); Manager per-node version pinning (2026); Boson (style-as-git-files, entry); RenderRepo (workflow package manager, entry) | no cross-workflow *project* model; "missing node" pain persists | [workspace-manager](https://github.com/JMaiGC/comfyui-workspace-manager), [Runflow](https://www.runflow.io/blog/comfyui-custom-nodes), [review](https://aiindigo.com/blog/comfy-workflows-review-the-community-bridge-for-comfyui-in-2026) |
| Timeline / shots / takes | Spool (0.1.0, OTIO) | only one, early | [Spool](https://github.com/doubletwisted/ComfyUI-Spool) |
| Asset management | Director's Cut (entry: local asset library) | nothing standard | [list](https://github.com/jutsuhq/open-source-higgsfield) |
| Review / comments / annotate frames | **nothing found** | open | [search](https://www.runcomfy.com/comfyui-nodes/ComfyUI-RvTools_v2/project-folder-video-rv-tools) |
| Batch processing UI | node-level only (RvTools Project Folder, Dream Video Batches `For Each Filename`, Load Videos From Folder) | no batch *app* | same |
| Realtime I/O on Mac | NDI nodes; Spout (Win); **Syphon none** | open | [decadetw](https://www.comfyonline.app/comfyui-nodes/ComfyUI-decadetw-spout-syphon-im-vj) |
| Audio ↔ DAW | none (no stems export, no Ableton/Reaper session writer, no OSC clock) | open; user has AbletonMCP locally | — |
| App packaging | App Mode / App Builder / ComfyHub (Mar 2026) | Comfy is solving this itself — don't compete | [docs](https://docs.comfy.org/interface/apps) |

---

## Ranked app concepts

Scoring: verified gap × Mac feasibility × prize fit × fit with user's strengths (audio, TD, UI craft). Deadline caveat applies to all.

### 1. Foley Desk — "sound design pass for a cut" (TOP PICK)
**What:** Drop in a silent cut (MP4, or OTIO/FCPXML from Spool/Premiere). It detects shots + motion events, generates per-shot foley, transition whooshes/impacts at cut points, an ambience bed, and an ACE-Step music bed, then exports **stems** (WAV per layer) + an Ableton Live Set / Reaper RPP / OTIO with audio tracks so the mix finishes in a DAW. The UI is a mini-DAW lane view under the video (your Ableton/TD UI chops).
**Why a gap:** Higgsfield explicitly lacks it ([quote](https://higgsfield.ai/blog/higgsfield-audio)); zero competition entries; ComfyUI has SFX nodes but no pass/stems concept.
**Models / nodes (Mac 36 GB):** PySceneDetect (CPU) for cuts; Florence-2 or Qwen3-VL (small) for shot captions; **Stable Audio Open 1.0 (native ComfyUI) / Open Small (CPU)** for text-to-SFX and ambience — Mac-safe; **ACE-Step 1.5** music bed — official Mac/MLX, native Comfy template; **Kokoro/Chatterbox** for scratch VO (MPS). Stretch: **MMAudio via Kijai nodes** for true video-synced foley — *untested on MPS*, budget half a day to try, keep the caption→SFX path as fallback. Optional "LTX Foley" engine (rented GPU) as a toggle.
**Prize fit:** Most Innovative; Open Weights Only (all engines open). LTX bonus only via the 22B Foley engine on a rented GPU — ambiguous "VFX workflow" wording.
**Honest downside:** judges are video people; MMAudio weights CC-BY-NC; sync quality from text-to-SFX is approximate (mitigate: align hits to detected onsets/cuts, not to semantics).
**3-day scope:** D1 cut/shot detection + ACE-Step bed + Stable Audio SFX through comfy-sdk/proxy; D2 lane UI, stems export, Live Set/RPP writer; D3 MMAudio attempt, demo cut, README.

### 2. Type Scene — lyric & kinetic typography engine with text-in-the-world shots
**What:** Paste a song/VO + lyrics (or auto-Whisper), pick a type style, and get a lyric/caption video where words are either (a) kinetic 2D type (karaoke/pop/wobble, Remotion- or libass-rendered) or (b) **physically in the shot** — Qwen-Image-Edit-2511 writes the lyric onto a billboard/neon/pavement in a generated or user plate, then **LTX-Video 2B** i2v animates it; exported as transparent overlays + burn-in.
**Why a gap:** no typography-first entry; closed platforms lack it; WordPop is 7★; video models can't spell, so the image-model-first pipeline is the non-obvious trick.
**Models (Mac):** Z-Image-Turbo (≈4 GiB) for plates; Qwen-Image-Edit-2511 GGUF (slow, minutes/frame — use sparingly); FLUX.2 Klein 4B (30–40 s/img); LTX-Video 2B 0.9.8 i2v; faster-whisper; ffmpeg/libass or Remotion.
**Prize fit:** Most Viral (lyric videos are share-native); **LTX bonus plausible** (LTX 2B is the only video model); Open Weights Only.
**Honest downside:** two halves can feel like two apps; text-in-i2v drifts past ~2–3 s; Remotion has a company-license wrinkle (use libass/Pillow to stay clean).
**3-day scope:** D1 Whisper → word timings → 3 kinetic styles + export; D2 "text in the world" plate pipeline via comfy-sdk (Z-Image → Qwen-Edit → LTX 2B); D3 polish UI, presets, demo.

### 3. Look Engine — "segcam"-class signature looks that apply to any footage
**What:** A preset = JSON recipe of deterministic passes (SAM2/Florence-2 segmentation → per-segment fills/outlines/labels, depth-based relight/fog, halftone/riso, datamosh/pixel-sort) plus an optional generative keyframe restyle (Z-Image/Qwen-Edit on a keyframe, propagated through masks). One click on any clip; presets shareable as files/URLs; runs in minutes on a Mac.
**Why a gap:** VFX presets are crowded but all generative and GPU-heavy; nobody ships a fast, flicker-free look system; Mac-native is itself a differentiator.
**Models/nodes (Mac):** SAM2 small/base-plus via Kijai nodes (MPS OK for small), Depth Anything V2, Florence-2, GlitchNodes/Fill-Nodes/DJZ datamosh, IC-Light optional; Z-Image-Turbo for keyframe restyle.
**Prize fit:** Most Viral / Open Weights Only. No LTX unless you add LTX 2B i2v for "motion extension" of looks.
**Honest downside:** "segcam" is unconfirmed — get the reference; risk of reading as filters; per-frame generative restyle flickers (keep generative to keyframes).
**3-day scope:** D1 segmentation + 4 deterministic looks + preset format; D2 UI, preset sharing, batch; D3 generative keyframe pass, demo.

### 4. Comfy Live — OSC/MIDI/audio-reactive live visuals from ComfyUI (Syphon/NDI out)
**What:** A performance app: audio in (mic/Ableton), OSC/MIDI mappable to prompt weights/seeds/ControlNet strength, continuous img2img loop, output to Syphon (Mac) / NDI for TD/Resolume; VrchStudio-style control but packaged.
**Why a gap:** zero realtime entries; nodes exist, no app; **no Syphon output exists for ComfyUI on Mac**.
**Models (Mac):** SD-Turbo / SDXS-512 / LCM at 512² — expect 2–5 fps via ComfyUI-MPS, ~20 fps only via a CoreML side path outside ComfyUI ([paper](https://www.alphaxiv.org/abs/2605.16259)).
**Prize fit:** Most Innovative (if Syphon node is novel); Open Weights Only.
**Honest downside:** output quality is 2023-grade next to Scope/Krea; streaming bypasses comfy-sdk's request model (platform-compliance story weakens); a laggy live demo can hurt.
**3-day scope:** D1 Syphon output node (pyobjc/Metal) + OSC/MIDI mapping; D2 loop + UI; D3 TD demo patch, video.

### 5. Cut Bridge — NLE round-trip sidecar (Premiere UXP panel or OTIO/FCPXML)
**What:** Select a range in Premiere/Resolve, send to a Comfy app (restyle, clean plate, extend with LTX 2B, foley), result lands back on a track above with markers. Premiere via UXP (frame export, importFiles, trackItem edits); Resolve via OTIO/FCPXML since free-edition scripting is gone.
**Why a gap:** no NLE-plugin entries; no comfy-sdk host integration anywhere.
**Honest downside:** Resolve 21.1 killed the free-edition path; writing a UXP plugin + roundtrip + UI in 3 days is tight; demo depends on Adobe licensing; lower "viral" potential.
**Prize fit:** Most Innovative; LTX bonus if LTX 2B does the generation.

### 6. Shot Review — takes, contact sheets, comments
**What:** Review/annotate/compare takes across ComfyUI outputs with frame comments and a shareable review page.
**Why:** nothing exists (F). **Downside:** utility software — weak demo, weak prize fit. Fold into #1 or #2 as a feature instead.

### 7. Recipe Hub for looks + sounds
Shareable presets across #1–#3. Conjure/Forkfield already own "recipe sharing" for VFX; only worth it as a feature, not an app.

**Recommendation:** build **#1 (Foley Desk)**, with #2's kinetic-caption lane as a stretch feature if time allows (same Whisper/ffmpeg plumbing). If the user's "segcam" reference turns out to be a strong, specific look, swap #3 in for the stretch.
