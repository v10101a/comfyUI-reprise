# Open Source Higgsfield: entries inventory, Higgsfield catalog, gap map, ideas

Research date: 2026-10-30 (evening ET). Sources are linked inline; GitHub numbers were pulled live via the GitHub API today.

## TL;DR

1. **Deadline reality.** The online submission window closed **today, Oct 30, 9 AM PT** ([rules](https://www.comfy.org/open-source-higgsfield)). The **NYC Build Night (Mon Nov 2, 5:30–10:30 PM ET, The Yard, 106 W 32nd St)** says "in-person attendees will be eligible to submit until the end of the event day" and are "eligible for special in-person awards" ([Luma](https://luma.com/nyc-yjfm)). Whether a Nov 2 in-person entry also competes for the $10k / RTX 5090 main prizes is **not stated anywhere**; ask Allyson Toy at the door. Winners announced Nov 6.
2. **Legal noise.** Higgsfield sent Comfy a cease-and-desist on Oct 28–29; Comfy refused and the challenge continues ([ComfyUI on X](https://x.com/ComfyUI/status/2115928993623109648), [Yoland Yan](https://x.com/yoland_yan/status/2115923819001192794)). Avoid Higgsfield branding/CEO likeness in your app.
3. **Field size.** jutsuhq curates **96 challenge entries** (+6 older alternatives) ([list](https://github.com/jutsuhq/open-source-higgsfield)); the GitHub topic tag has 24 repos, the hyphenated tag 18 more, and a keyword search finds **~176 repos** created since Oct 14. Only **17 entries have ≥10 stars; 38 have 0**. One entry (D3voz/openjutsu, 605★) is effectively Comfy's own.
4. **Saturated:** all-in-one "Higgsfield clone" studios (25), camera / reshoot / previs (15), Genjutsu character swap (14), film/music-video generators (11), one-tap VFX presets (~10), node canvases (10).
5. **Thin or empty:** sound design / music / SFX as a product (0 dedicated apps; Higgsfield itself only has voice), typography/captions/lyric video (0), live/performable/realtime (1: cue-the-boom), audio-reactive beyond beat-cutting (1: Xenoform), NLE/compositor integration (2: justae-flow for EffectCraft, Spool inside ComfyUI), video relight + color grade as standalone tools (0 dedicated), storyboard/Popcorn (1 mock + 1 partial), upscale/restore app (0), virality/hook analysis (0), transitions (1: Seam, good).
6. **Typical entry:** Python (57%) or TypeScript (26%) web app; `workflows/*.api.json` filled by the Comfy SDK (`@comfyorg/sdk` or `comfy-sdk`) through `comfy-api-proxy` to a local ComfyUI, with Comfy Cloud as the alternate backend; 70% have a `workflows/` dir, 62% link a demo video, demo videos converge on **≤2:00**; only 26% have a deployed link.
7. **Mac reality (36 GB M5 Max):** LTX-2.5 22B is not local (21.5 GB int8 DiT + 15.4 GB Gemma encoder); LTX-Video 2B/13B (0.9.x) run on MPS (Toybox Director verified on an M5 Max 128 GB); image models (FLUX 3 Image Klein 5.6B, Qwen-Image 2.1, Z-Image Turbo) and audio (ACE-Step 3.5B native in ComfyUI, Whisper, TTS) are fine locally. Anything LTX-2.5/H3 needs Comfy Cloud or a rented GPU (entries report ≈$0.05–0.80 per clip on Comfy credits).
8. **Judges' stated values:** "Build a working app that makes it easy for someone else to create their own"; "a recognizable output"; Most Innovative "must explain why" in the video; "we're judging the work, not your video editing." Their last challenge rubric scored **novelty, workflow quality, community value** and rewarded openness and clean, learnable workflows ([H3 Sync Sound recap](https://blog.comfy.org/p/comfy-h3-sync-sound-challenge-the)). No public reposts/highlights of specific entries were found.
9. **Top 3 ideas for you:** (1) a **sound-design / score / foley room** for any cut (biggest gap, pure audio strength, mostly local); (2) a **kinetic typography & lyric/caption composer** where FLUX-generated type animates on word timestamps (zero coverage, UI-heavy, Most Viral + FLUX bonus); (3) a **performable / live VFX bridge** (ComfyUI → TouchDesigner/NDI, audio/MIDI-triggered LTX alpha elements) for Most Innovative + LTX bonus.

---

## 1. Entries inventory

### 1.1 Method and counts

- Primary list: jutsuhq `projects.json` (102 rows: 96 challenge entries + 6 "beyond") read directly from the repo; metadata (stars, language, license, homepage, last push) via GitHub API on 2026-10-30; READMEs and top-level trees of all 102 repos downloaded and scanned for stack/model/polish signals; 41 launch posts on X fetched to measure demo-video length.
- The jutsuhq page says it excluded "empty repositories and clones" and that stars are "a popularity signal, not a quality one" ([jutsustudio.com](https://jutsustudio.com/open-source-higgsfield/)).
- GitHub topic `opensourcehiggsfield`: 24 repos; topic `open-source-higgsfield`: 18 repos (8 not in the curated list, added below as 1.3). Keyword search (`opensourcehiggsfield OR "open source higgsfield"` in readme/description, created after Oct 14): 176 repos.

**Aggregate stats (95 curated entries with a README):**

| Signal | Share |
|---|---|
| Primary language: Python / TypeScript / JavaScript | 57% / 26% / 12% |
| Mentions Comfy SDK / comfy-api-proxy / Comfy Router | 46% / 42% / 19% |
| Mentions ComfyUI App Mode | 17% |
| Ships custom nodes or a node pack | 63% |
| Has a `workflows/` directory | 70% |
| Models mentioned: LTX / Qwen-Image / FLUX / MiniMax H3 / Wan / Seedance / Kling | 58% / 58% / 54% / 49% / 23% / 21% / 14% |
| Audio-ish: TTS 27%, music 29%, lip-sync 20%, Whisper 23%, ACE-Step 9%, MMAudio 1% | |
| README links a demo video (YouTube or mp4/webm) | 62% |
| Deployed/hosted link in repo metadata | 26% |
| Mentions tests | 76% (many READMEs have a "Tests" section; CI badges are common) |
| Stars ≥10 / 1–9 / 0 | 17 / 39 / 38 |
| License MIT / Apache-2.0 / GPL-3 / AGPL-3 / none | 61 / 17 / 7 / 4 / 5 |
| Launch-post video length on X (27 videos) | median 75 s, mean 65 s, max 118 s |

Categories (jutsuhq): studios 25, camera/reshoot/previs 15, character swap 14, films/music video/stories 11, canvases/front ends/tools 10, effects/VFX 10 (9 + neuregex), characters/datasets 5, ads/UGC 7.

### 1.2 Inventory table (all 96 curated entries, grouped)

Legend. Stack: Next = Next.js, R+V = React+Vite, FA = FastAPI, nodes = ComfyUI custom node pack, App = ComfyUI App Mode workflow, 3js = Three.js. Run: L = local ComfyUI via comfy-api-proxy, C = Comfy Cloud/Developer Platform deployment, R = Comfy Router/partner (closed) models. Polish: ★ stars (2026-10-30), vid = demo video, dep = deployed link. UI line is taken from README screenshots/captions and descriptions.

**Character swap (Genjutsu)**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [D3voz/openjutsu](https://github.com/D3voz/openjutsu) | Genjutsu object/character swap, relight, "from picture" | Next.js + nodes (`comfyui-h3-oneclick-swap`), `@comfyorg/sdk` | L, C | MiniMax H3, SAM 3.1, Qwen3-VL 8B describer, FLUX.3 Klein relight | 605★, embedded video, 5 screenshots | Single-page: drop video + photo, Generate; advanced "who becomes who" picker; paint mask for object swap; 17 light looks grid |
| [Comfy-Org/comfy-openjutsu](https://github.com/Comfy-Org/comfy-openjutsu) | Official clonable swap template | Next.js, SDK server-side | C | H3 + Akatz swap LoRA, SAM 3.1, GPT Image 2.5 via Router (optional) | 68★, no media | Form (clip, image, 5–15 s part, quality) → player; `components/app-runner.tsx` |
| [jutsuhq/swapjutsu](https://github.com/jutsuhq/swapjutsu-seedance-character-swap) | Recast/Viggle-style swap, Mac app | SwiftUI, Core ML/MLX prep | C (Seedance) or L (Wan 2.2 Animate) | Seedance 2.5 or Wan 2.2 Animate | 6★, 13 images, site | Native macOS window, before/after |
| [lucataco/open-source-higgsfield](https://github.com/lucataco/open-source-higgsfield) "Body Double" | Genjutsu recast, plate-preserving | Python CLI + scripts, core nodes only | L | SAM 3.1, FLUX 3 Klein, SCAIL-2 | 24★, 30 s demo clip, CI | CLI-first; demo is split-screen original/recast |
| [SydFloyd/openjutsu](https://github.com/SydFloyd/openjutsu) | Genjutsu, open weights | FA + SDK/proxy | L (DGX Spark/24 GB) | Wan, SAM, depth | 1★ | Web form; README is mostly setup |
| [fetchloom/OpenJutsu](https://github.com/fetchloom/OpenJutsu) | Genjutsu motion transfer + click-to-swap | Node web app, mock backend | L | Wan 2.1 VACE (graphs "not yet run on a GPU") | 0★ | Web UI with before/after; workflows unverified |
| [Ex8-ca/openjutsu](https://github.com/Ex8-ca/openjutsu) | Genjutsu motion transfer | FA + web, SDK/proxy | L, C | H3 + H3 Fun ControlNet | 0★, 8 video links | "Object Swap, honestly" section; daemon + proxy + web UI |
| [demoncase/kagami](https://github.com/demoncase/kagami) | Genjutsu | Python app + terminal | R (Router) | FLUX, H3, Seedance, Fish Audio TTS | 1★, 90 s X video, 12 clips | App + terminal modes |
| [LLannnn/OSHCharacterStudio](https://github.com/LLannnn/OSHCharacterStudio) | Genjutsu character work | Python web, 18 tests | C (Cloud jobs) | H3 | 0★, 5 GIFs | Step wizard: select clip/characters → review prompt → check masks/skeleton |
| [regiellis/utsushi](https://github.com/regiellis/utsushi) | Motion transfer, object swap, style, long video | Go server | L, C, R | LTX, Wan Animate 2, Wan 3.0, H3, Qwen, Seedance | 0★, no media | Clip editor + engines table; README 26 KB |
| [SvetimFM/openjutsu-cat](https://github.com/SvetimFM/openjutsu-cat) | Motion transfer from Kinect/depth; LTX camera studio | Python + API workflows | L (8 GB VRAM) | Wan 2.2 5B control GGUF, LTX, Depth Anything | 0★, 5 clips | Scripts; depth-performance capture |
| [D3voz/comfyui-h3-oneclick-swap](https://github.com/D3voz/comfyui-h3-oneclick-swap) | Node pack behind Openjutsu | nodes only | L | H3, SAM, Qwen, FLUX | 1★ | Node graph only |
| [Bambushu/h3-recast](https://github.com/Bambushu/h3-recast) | Recast up to 3 people | App Mode workflow JSON only | L (16 GB) | H3 + BFS LoRA, Qwen, Whisper | 35★, 2 videos, GIF | ComfyUI App Mode form, top to bottom |
| [lvsas/OpenJutsuStudio](https://github.com/lvsas/OpenJutsuStudio) | Swap + "continue the story" + vertical reel export | Python + nodes, SDK/proxy | L, C | LTX, FLUX, H3 | 2★, 1 GIF | "Create. Swap. Continue. Share." take-based studio |

**All-in-one studios**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [wexloops/openfield](https://github.com/wexloops/openfield) | Whole Higgsfield (Create/Direct/Transform/Finish) | R+V + Express, 3js Stage, SDK/proxy, nodes, MCP | L, C | LTX, FLUX.2, H3, Qwen, Z-Image, SAM, SeedVR2, TTS, lip-sync | 115★, 8 screenshots, 565-like X post (118 s video) | Explore grid of app cards; Director panel (genre/camera/light/era scrubber); 3D Stage blocking; Mirror (phone motion → character) |
| [thePloggy/CreatorOS-Studio](https://github.com/thePloggy/CreatorOS-Studio) | One recurring character → reel; camera moves, effects, avatars, editor | R+V + server, nodes, MCP | L, C | LTX, Wan, FLUX, H3, Qwen, TTS, lip-sync | 40★, 9 screenshots, public demo | Setup wizard; persona JSON; multi-tab studio |
| [rk0neki/OpenKatana](https://github.com/rk0neki/OpenKatana) | Katana (agent-driven edit) + typography + music | Python engine, nodes (Comfy Registry), CLI, MCP | L, C | LTX, Blender/WebGL for 3D, music | 17★, 3 YT + 4 mp4, GIFs | Code-authored edits; "Aura Farm Koji" and MOTIF product film |
| [kevin9327/OpenSourceHiggsfield](https://github.com/kevin9327/OpenSourceHiggsfield) | Cinematic Studio + Reshoot + Openjutsu 3-in-1 | FA backend + static frontend, nodes, SDK v0.5.0, proxy, MCP | L, C | LTX-2.5 22B, FLUX.3, DepthAnything/MoGe, TRELLIS-2 | 9★, 4 videos, 7 images, "13/13 tests" | Four workspaces; heavy badge/jargon README ("Sim(3) Verification") |
| [Arfolomew/backlot](https://github.com/Arfolomew/backlot) | Higgsfield on a 16 GB card | Python app, SDK/proxy | L, C | H3, Krea 2, Qwen 2.1, LTX, TTS | 4★, 2-min demo, 95 s X video | Moves / Cinema Studio / Apps; "what this costs elsewhere" table |
| [synthetic-ape/comfield](https://github.com/synthetic-ape/comfield) | Higgsfield studio (cloud or open) | React + server, SDK, Router | L, C, R | LTX-2, H3, Seedance, Kling, Veo, FLUX, Qwen | 5★, 12 images | Tabbed studio; example outputs grid |
| [RahmelJackson/frameforge-studio](https://github.com/RahmelJackson/frameforge-studio) | Creative studio + local AI guide + MCP plugin | JS app, App Mode, MCP | L, C | LTX, FLUX, H3, TTS | 3★, 110 s X video | 20+ planning .md files in root; "Start here" |
| [sintetizacom/easycomfee](https://github.com/sintetizacom/easycomfee) | Image, video, LTX VFX, lip-sync, music, voice | R+V + FA, one-click installer (Windows) | L (16 GB), C | LTX, Wan, FLUX, H3, Qwen, ACE-Step, TTS | 3★, 6 GIFs | Before/after strips; Blender blockout → shot |
| [NeoMarcoPolo/marcostudio](https://github.com/NeoMarcoPolo/marcostudio) | 13 image/video tools | Vite + Python, nodes | L (+hosted) | H3, Qwen | 2★, 9 images, hosted app | Tool grid, each a form |
| [rossaai/rosesfield](https://github.com/rossaai/rosesfield) | 25+ apps incl. LTX VFX, audio, 3D | Bun/React monorepo, Cloudflare Workers, SDK, Router, MCP | C, R (+L) | LTX, Qwen, Z-Image, SAM, TTS | 2★, 13 images, rosesfield.com | "Rosesfield and Higgsfield, app by app" comparison table |
| [codyclack/opensfield](https://github.com/codyclack/opensfield) | 146 tools + all 83 Higgsfield apps (nav clone) | FA + static app shell, App Mode, SDK | C (renders on Cloud) | LTX, Wan, Qwen, FLUX, Seedance, Kling, ACE-Step | 1★, 118 s demo, "mock mode" | Pixel-level Higgsfield nav clone (Explore/Image/Video/Audio/Genjutsu/Cinema Studio/Soul/Viral/Marketing/Apps); "Status (honest summary)": most tools unrendered |
| [MajoorWaldi/HyperKut-Studio](https://github.com/MajoorWaldi/HyperKut-Studio) | Katana/Genjutsu-style create/remix/edit | FA + frontend, nodes, SDK/proxy | L, C | music + unspecified | 4★, 9 videos, 9 GIFs | Windows install; demo-heavy README |
| [dougliell/Cheapsfield](https://github.com/dougliell/Cheapsfield) | Shot Director, motion transfer, ref-to-video, spot edit, node canvas | Tauri (Rust) + React, SDK/proxy | L (Windows) | LTX, Wan, FLUX, H3, Qwen, SAM | 2★, 15 images | Desktop app with 4 tools + canvas |
| [Jubzh-29/montagio](https://github.com/Jubzh-29/montagio) | Viral effects, camera moves, avatars, motion transfer, trend remix | Next.js monorepo, nodes, SDK/proxy, MCP | L | 19 open models (Wan 2.2 Fun Camera, LTX, H3, Qwen, MMAudio, ACE-Step, TTS) | 0★, static showcase, X video | "Click like a one-click app, open the hood like ComfyUI"; "Proof, measured" table |
| [baney75/hildegard](https://github.com/baney75/hildegard) | Video, voice (ElevenLabs alt), characters, 3D | Tauri + Rust, MCP | L (no Apple Silicon path) | LTX, Wan, FLUX, Qwen, TTS | 0★ | Tray app + studio window; README notes LTX int8/fp8 kernels missing on Apple |
| [norioversoul/susano](https://github.com/norioversoul/susano) | Openjutsu + Tsukuyomi + Cinematic + Influencer, shared cast | Next.js, nodes, SDK | L, C | FLUX, H3, Qwen | 1★ | Four apps, one cast |
| [GETHUK-BIGEMPEROR/OpenIllusion](https://github.com/GETHUK-BIGEMPEROR/OpenIllusion) | Any workflow → one-click template (`.illusion`) | Python server + UI, Docker | L, C, R | FLUX, H3, Qwen, Seedance, Kling | 3★, 7 images, 4 YT | Template picker: drop photo/clip/sound, Run |
| [leonardofrito/Directors-Cut](https://github.com/leonardofrito/Directors-Cut) | Asset library + reference-to-video | Python + web, SDK/proxy, MCP | L | Qwen-Image 2.1, H3 | 12★, 4 YT, installer | Characters/props/locations library → video |
| [designn2future/hoodsfield-ai](https://github.com/designn2future/hoodsfield-ai) | Idea → finished video: script, images, video, lip-sync, timeline, loops | React + FA, nodes, MCP | L | FLUX 3, H3, LTX, Wan, TTS | 0★, 6 images, YT | Windows .bat launchers; timeline editing; "H3 prompt coach" |
| [IBFolding/haggs](https://github.com/IBFolding/haggs) | Script-to-screen with per-shot price | Next.js + Supabase, Vercel, MCP | C, R | LTX, FLUX, H3, Seedance, Kling, Veo | 0★, haggs.vercel.app | Price-per-shot in view |
| [E5EnclaveInc/liberty-cut](https://github.com/E5EnclaveInc/liberty-cut) | Cast lock + shots + relight hour | small web studio over ComfyUI API | L (A10 24 GB) | LTX-Video 13B, FLUX.1-dev, PuLID | 0★, BUILD_LOG.md | Two modes; honest verification note |
| [stellartune-studio/vision-orchestrator](https://github.com/stellartune-studio/vision-orchestrator) | LLM director grows a production blueprint | R+V + server, SDK/proxy | L | Wan, Qwen | 0★, 98 s X video, no license | Approve/sign-off flow |
| [MachineLearningAmateur/cinestudio](https://github.com/MachineLearningAmateur/cinestudio) | Scene control for LTX-2.5 renders from Blender shots | Python + bpy jobs, MCP | L, C | LTX-2.5, Qwen, Z-Image, ACE-Step | 0★, 3 images, 75 s X video | Queue + Blender |
| [Niutonian/Comfyui_Darius_OS](https://github.com/Niutonian/Comfyui_Darius_OS) | Workspace: image/video boards, local chat, voice | Next.js + FA, Router, MCP | L, C, R | FLUX, H3, Qwen, TTS | 0★, 8 images, hosted demo, no license | Boards + chat |
| [szprivate/agentY](https://github.com/szprivate/agentY) | Agent inside ComfyUI picks/builds/runs workflows; viewer for 3D/splats | Python agent + UI, MCP | L | FLUX, Qwen, splats, Ollama | 37★, YT | Chat + canvas + built-in viewer |

**Effects and VFX**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [neuregex/freefield](https://github.com/neuregex/freefield) | Higgsfield menu: 117–120 apps (Create/Edit/Motion/Templates/Audio) | Node web + server (SDK) → gateway → proxy → ComfyUI; Modal deploy; `apps/*/app.json` manifests | L, Modal | FLUX 3 Klein, Z-Image, Krea 2, Qwen Edit, LTX-2.5 22B, H3, SCAIL-2, Wan Animate 2, Wan 2.2 Fun Camera, MiniMax Music 3, Stable Audio 3, SeedVR2, BiRefNet, MoGe-2, FILM | 327★, 2-min YT, 7 images, 710/733 tests across 48 GPU runs | Higgsfield-style Explore with video cards; per-app form drawn from manifest; "How it works" tab with per-model VRAM/time |
| [PhatStraw (droppedmyza)/freefield](https://github.com/PhatStraw/freefield) | Viral effects (Earth Zoom, Product Freeze, Comic Bonk) | Python package + workflows, SDK/proxy | L, C | Wan, FLUX, Qwen, depth | 3★, 7 GIFs, 12 images, 78 s X video | Gallery; one photo in, one clip out |
| [Orazen/conjure](https://github.com/Orazen/conjure) | One-tap VFX (gold statue, inflate, disintegrate, earth zoom-out) with sound | React web + server, App Mode, nodes, SDK/proxy, mock mode | L, C | FLUX 3, LTX-2.5 | 0★, no license | Recipe-based effects; "Make your own effect" |
| [Kainotomic/one-take-vfx](https://github.com/Kainotomic/one-take-vfx) | Effects on a phone clip (disintegrate, levitate, fire, portal, time-freeze) | FA app + preset node, workflows | L (39 GB models) | LTX 2.5 distilled int8 + IC-LoRA (Canny control) | 0★, GIF, demo outputs | Minimal web app; pipeline ASCII diagram |
| [chinesepowered/hack-comfy](https://github.com/chinesepowered/hack-comfy) "LiDAR Lab" | LiDAR scan, clones, vanish, bullet time, CPU-only | nodes + FA gallery, SDK/proxy | L (CPU) | SAM, depth, Whisper, splats | 1★, 3 videos, 4 GIFs | Gallery app at :7860 |
| [marciano71/forkfield](https://github.com/marciano71/forkfield) | Effects where every clip carries its recipe ("fork any video") | Node server + web | C (+L) | Qwen-Image-Edit, LTX-2.5 | 1★, YT + 2 videos | Recipe format; fork button |
| [audriu/fxjutsu](https://github.com/audriu/fxjutsu) | VFX presets on own footage (Vanish, Day-to-Night, Flood, Alpha, Fire, Clay/Anime, Hologram, Ghost) | Next.js, nodes, SDK/proxy | L (24 GB), C | LTX-2.5 + IC-LoRAs (Clean-Plate, Day-to-Night, Water, Alpha-Gen, Fluid, Union Control) | 0★, 1:51 demo mp4, 12 before/after images, no license | Preset grid; before/after pairs |
| [TusharTechs/platelock](https://github.com/TusharTechs/platelock) | Plate-preserving VFX (bit-identical pixels outside the effect; alpha + emissive element for Nuke/AE/Resolve) | FA app + node pack, SDK/proxy | L, C (L40S) | LTX-2.3 distilled fp8 | 2★, 1:58 YT, live gallery, PSNR table | Logo lockup, X-ray matte image, "Honest notes" |
| [jdnichollsc/seam](https://github.com/jdnichollsc/seam) | Transitions (smoke, water bend, whip pan…) between two shots/3D models; sequences | React web + FA, 3js, SDK/proxy, CLI, MCP plugin | L, C | LTX-2.5 (open), H3/Kling optional | 15★, 2-min YT, 22 images, project site | Shots left, take right, gallery below; "Surprise me" |
| [Burgstall-labs/ComfyUI-SpEdE](https://github.com/Burgstall-labs/ComfyUI-SpEdE) | Click object in a Gaussian splat → remove/replace/extract | nodes + FA web Studio, 3js, SDK/proxy, pytest | L | SAM 3.1, Qwen-Image 2.1, MoGe-3, TripoSplat, gsplat | 15★, 9 images, AGPL | Splat viewer; gated pipeline (G1–K1) |

**Camera, reshoot and previs**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [Tekholms-LW/ReAngle](https://github.com/Tekholms-LW/ReAngle) | Reshoot from a new angle | Vite + FA, 3js, nodes | L (16 GB), C | LTX-2.5, depth, splats | 3★, 4 videos, GIF, site | 3D camera widget → render |
| [pyoonpyoon/open-higgsfield](https://github.com/pyoonpyoon/open-higgsfield) "Reshoot" | Cinema Studio + Reshoot for a photo | Next.js + 3js, SDK/proxy | C or L (GGUF ≈22–40 GB for Apple Silicon) | Qwen-Image-Edit angles, LTX-2 19B + official camera LoRAs, LTX-2.3 CrossView | 1★, 4 images, Vercel | Floating composer with Subject/Angle/Lens/Movement/Palette cards; drag-to-orbit globe with live preview; FOV-compensated dolly zoom preview |
| [ylchen333/comfy-dial](https://github.com/ylchen333/comfy-dial) | Camera move that checks itself (measure, regenerate drift) | R+V + 3js, nodes | C (+L) | LTX, FLUX, depth | 0★, 1 video | 3D draw-a-move; results table |
| [bolttmade/shot-director](https://github.com/bolttmade/shot-director) | Camera-move studio: presets, coverage board, A/B, reel export; simulated previs | FA + web, SDK/proxy, Router | L, C, R | LTX, FLUX, H3, Seedance | 0★, GIF, 9 images, HF Space, 12 tests | "Real vs simulated outputs" labelled |
| [MVOlekhno/previz2shot](https://github.com/MVOlekhno/previz2shot) | Blender playblast → styled shot (Layout-to-Render) | Blender addon + CLI | C (+L) | FLUX.2 Klein 4B, LTX-2.5 22B IC-LoRA L2R | 0★, demo.mp4 | CLI; 2 KB README |
| [mahdi-salmanzade/toybox-director](https://github.com/mahdi-salmanzade/toybox-director) | Block with toys on a 3D stage, keyframes → LTX | R+V + 3js + Express, `@comfyorg/sdk`, bundled runtime | L (**verified on M5 Max 128 GB, MPS**) | LTX-Video 2B (drafts 512×320) / 13B (1024×576), Qwen-Image-Edit | 0★, 2 images, 10 s X video | 3D stage, keyframe strip, edit-keyframe-in-words bar |
| [navarisun1982/comfyui-motion-previs-studio](https://github.com/navarisun1982/comfyui-motion-previs-studio) | 3D Jutsu-style previs: dual viewports, 24 fps timeline, gait engine, lens deck | Electron + Vite + 3js | L | H3 ref2va, LTX, Wan, Qwen | 11★, 7 videos, 5 images | "Cinematic Command Center 2026": very dense UI |
| [LaytonGott/open-cinema](https://github.com/LaytonGott/open-cinema) | Change the lens afterwards (physically based DoF) | nodes ("Open Optics") + director app, SDK/proxy | L | LTX-2, depth | 0★, 2 videos, GIF, 10 tests | Node pack + small app |
| [metababe-eth/hero-frame-rig](https://github.com/metababe-eth/hero-frame-rig) | Refocus a clip after the fact; "area sequence" | Gradio + node pack, SDK/proxy, CPU replay | L, C | LTX, FLUX, depth, ACE-Step, TTS | 1★, YT + 2 videos, 63 s X video | Gradio |
| [apsolut/one-shot-multicam](https://github.com/apsolut/one-shot-multicam) | One selfie take → 3-camera edit cut on word boundaries | React + FA, Electron option, App Mode, Fly.io | C (≈$0.055/insert) or L | LTX-2.3 + CrossView IC-LoRA, Qwen-Image-Edit 2511 angles + LTX-2.3 ID LoRA, faster-whisper | 2★, 1:55 demo, live app, 33 video links, 46 KB README | Result player + cut-list editor (click shot to switch cam/re-roll); angle presets + cost estimate |
| [Alvinvision/360-Scout-to-Film-Consistency](https://github.com/Alvinvision/360-Scout-to-Film-Consistency) | 360 location refs → multi-shot video | nodes + scripts | L (partner nodes; tested on Apple Silicon) | H3, Seedance 2.5 (partner) | 3★, 1 video | Workflow-centric |
| [ArcSolver/shot-board](https://github.com/ArcSolver/shot-board) | One scene → six shots; pick hero, redraw cuts | FA + web, SDK/proxy | L (SSH to worker) | SDXL, Qwen-Image-Edit, depth | 0★, 7 images, GH Pages "try without GPU" | Board grid |
| [junco3/motion-guard](https://github.com/junco3/motion-guard) | Verify AI video vs 3D motion reference before upscale | nodes + server + web | L, C | LTX | 0★, YT + 2 videos, 7 tests | Checker report |
| [soft-jelly/shotcheck](https://github.com/soft-jelly/shotcheck) | CPU-only camera-motion checker (MATCH/MISMATCH/INCONCLUSIVE) | Python app + node + CLI, SDK/proxy | L (CPU) | none (analysis) | 0★, 2 images, 11 tests | Drop clips, pick move |
| [EmmanuelRiveros/TimeFlight](https://github.com/EmmanuelRiveros/TimeFlight) | Drone flights over real places back in time (geodata → depth → LTX) | Python + Blender + nodes, Colab | L + Colab | LTX-2.5 depth-guided, FLUX, OSM | 3★, 2 YT + 4 videos, 8 tests | Pipeline-centric; hero Tenochtitlan |

**Films, music videos and stories**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [hodgemann/mondo-music-video](https://github.com/hodgemann/mondo-music-video) | Song → music video; beat-aware shot planning; actors that dance/lip-sync; Worlds | Python webapp, `comfy-sdk`/proxy, MCP, "Open Actor/Prop Protocols" | L, C, R | H3, Seedance, lip-sync, Whisper, LLM | 10★, 118 s X video, 20 KB README, no screenshots | Card/fold-based director form; dark mode default |
| [tysonfarrington-cmyk/xenoform](https://github.com/tysonfarrington-cmyk/xenoform) | Song → morph chain on the beat; stems drive light; MIDI rides picture | Python + web (FA), `comfy-sdk` 0.5.0 + proxy, MCP, .bat launcher | L | LTX-Video + LTX-2.5, FLUX, Z-Image, ACE-Step, depth | 1★, <2:00 YT + 8-min walkthrough, 105 s X video, 40 KB README | One desk: Song → Vibe → Prototype → Refine → Share; 3 s animatic preview; 4 knobs |
| [smithysw7/openreel](https://github.com/smithysw7/openreel) | Logline → character-consistent short film (storyboard, casting, cut) | Next.js, nodes, Router option | L (RTX 5060 Ti 16 GB) | Z-Image Turbo, H3, Qwen, TTS | 1★, webm demo | Pipeline steps |
| [DialloWill/storyboard-studio](https://github.com/DialloWill/storyboard-studio) | Cinema Studio for music-video storyboards (stills per song section + CSV) | Flask | mock only (Comfy "implemented at build night") | — | 0★, placeholder screenshot | Form; **weak** |
| [thaohienhomes/oneliner](https://github.com/thaohienhomes/oneliner) | One line → cinematic trailer | Next.js, SDK/proxy, ffmpeg.wasm, Vercel | C, R | LTX, Qwen, Z-Image | 1★, 4 videos, cost guards | Hosted beta |
| [Editorenbici/leafreel](https://github.com/Editorenbici/leafreel) | Document → narrated explainer in 8 styles (2 nodes) | Python CLI + nodes, SDK/proxy, MCP | L | LTX, FLUX, Qwen, ACE-Step, TTS, Whisper | 0★, 2 videos, GIF, site, 81 s X video | CLI + site |
| [spiritform/herosjourney](https://github.com/spiritform/herosjourney) | Monomyth experience starring you | JS server + agent | C, R | FLUX, H3, Qwen, Seedance (Nano Banana) | 0★, YT | Mockup-driven |
| [chenthedesignmaker/ComfyUI-Picky](https://github.com/chenthedesignmaker/ComfyUI-Picky) | Cinema Studio alternative for H3: takes, lineage, cast, prompt linter | ComfyUI node pack + browser editor (inside ComfyUI), agent skill | L | MiniMax H3, Krea 2, Qwen, music | 15★, 2-min YT, browser demo, GIFs | Media library + program monitor + timeline; prompt versions keep takes |
| [GiveMePrompts/crew-cut](https://github.com/GiveMePrompts/crew-cut) | Party game that makes a movie (phones = characters) | Node server + web, SDK/proxy | L (MacBook, GGUF) | LTX, FLUX, Qwen | 0★, 5 videos | TV + phones |
| [Nemont3/cat-tapes](https://github.com/Nemont3/cat-tapes) | Lo-fi VHS cat home videos | Python app ("tape deck"), SDK/proxy, Router opt. | L, C | LTX-2.5, ACE-Step, Qwen, Z-Image | 0★, YT (40 s tape) | Tape deck metaphor |
| [bgstratt/seriesmith](https://github.com/bgstratt/seriesmith) | Series config + markdown scripts → episodes, any model | Python + nodes + editor, SDK, Router | L, C, R | LTX, Wan, FLUX, H3, Qwen, Seedance, Kling, Veo | 1★, 2 videos, 9 tests | Document-driven editor |

**Ads and UGC**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [jhoard/open-ads-studio](https://github.com/jhoard/open-ads-studio) | Ads Studio: label-exact, compliance-checked product shots | Next.js, App Mode, nodes, SDK/proxy, Vercel | L, C | LTX-2, H3, Qwen, BiRefNet | 0★, 12 images, 2 videos, live | Brand from URL → shots |
| [moonz-1/open-ad-studio](https://github.com/moonz-1/open-ad-studio) | AI creative agency | R+V, SDK | C | LTX, FLUX, Qwen | 0★ | Minimal |
| [ergophobian/comfyfield](https://github.com/ergophobian/comfyfield) | Insert product into proven viral formats; schedule posting | Node server + Vite, SDK, Router, MCP, Docker | C, R | LTX, FLUX, H3, Seedance, TTS | 1★, 5 videos, 33 s X video | Format picker → cheap frame approval → render |
| [kingofmit/ComfyUI-HiggsOpen](https://github.com/kingofmit/ComfyUI-HiggsOpen) | Diffuse: topic → 4-scene LTX video + TTS + TikTok captions | — | — | LTX-2.5 | 0★, **empty repo (10-byte README), no license** | **weak** |
| [vidyabharadwaj03/reelmatch](https://github.com/vidyabharadwaj03/reelmatch) | Campaign brief + photos → UGC ad draft; model matching | Python app, render.yaml | C, R | LTX, Wan, FLUX, H3, Seedance, Kling, Veo, TTS | 0★ | "Honest limits" section |
| [untitledxdamage/comfyui-personalized-ad-spots](https://github.com/untitledxdamage/comfyui-personalized-ad-spots) | Lip-synced personalized greetings + ad spot | — | — | — | **repo 404 (removed)** | — |
| [jk-automations/urban-cuts](https://github.com/jk-automations/urban-cuts) | Urban Cuts: photo + outfits + music → beat-cut 9:16 reel | ComfyUI App Mode + nodes (Rust helper) | L + partner run | Seedance/Kling (paid demo), music | 0★, 5 videos, 7 images | App Mode form |

**Characters and datasets**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [ToxicLizard99/Dataset-Forge](https://github.com/ToxicLizard99/Dataset-Forge) | One face → LoRA dataset | App Mode workflow + nodes | L | FLUX, Qwen, SAM, Krea 2 LoRAs | 0★, 4 images | App Mode panel |
| [ZhuEvgeny/Character-lock-comfy](https://github.com/ZhuEvgeny/Character-lock-comfy) | Lock a character look from one ref | nodes + app | L | PuLID + FLUX Schnell | 1★, 3 videos | Small |
| [Soussa4535/SoulPersonEnhance](https://github.com/Soussa4535/SoulPersonEnhance) | Enhance each person separately (Soul-style skin) | 2 custom nodes, App Mode | L | FLUX, Qwen, SDXL, SAM | 0★, video + GIF, 85 s X video | Click who to enhance |
| [0xMisterBailey/Boson](https://github.com/0xMisterBailey/Boson) | "Studios instead of presets": taste as git files | nodes + Python | L (CPU ok) | LTX, FLUX, Qwen, LLM | 0★, 15 images, 22 KB README | Concept-heavy |
| [fixed-42/comfyui-sameface](https://github.com/fixed-42/comfyui-sameface) | Measure face drift after edit and move it back (optical flow) | custom node | L | GroundingDINO, SAM, RAFT | 5★, 2 images, 5 tests | Node pack |

**Canvases, front ends and tools**

| Entry | Clones | Stack | Run | Models | Polish | UI |
|---|---|---|---|---|---|---|
| [jtydhr88/ComfyArt](https://github.com/jtydhr88/ComfyArt) | Higgsfield Canvas / design tool: infinite tldraw canvas + design agent | ComfyUI extension (React + tldraw), `dist/` committed, MCP | L, C | FLUX, H3, Qwen, Z-Image, SAM, ACE-Step, TTS, Whisper | 401★, 38 s promo, docs site, 150-like X post | Figma-like canvas: artboards, layers, pen tool, rich text, generate panel, timeline |
| [raph651/open-source-canvas](https://github.com/raph651/open-source-canvas) | Higgsfield Canvas (node canvas) | R+V + server, Router opt. | L, R | LTX, Wan, FLUX, H3, Seedance, Kling, Veo | 76★, 2 videos, GIF, 5 images, 510-like X post | Node canvas |
| [FrameDeptCo/freavy](https://github.com/FrameDeptCo/freavy) | Local-first node canvas | R+V monorepo, App Mode, MCP | L | H3, Qwen, upscale | 6★, video + GIF | Canvas |
| [HomoLapis/justae-flow](https://github.com/HomoLapis/justae-flow) | ComfyUI inside EffectCraft (open AE-like compositor): generate into timeline slots, fill gaps, reframe, upscale, cutout, extend | TypeScript plugin for EffectCraft (8.2k★ Rust compositor) | L, C | LTX-2.3/2.5, Wan, H3, Qwen, Z-Image, SAM | 2★, 2-min demo mp4, 7 images, GPL | Panel beside the timeline; Workflow tab turns any saved workflow into a form; Comp tab |
| [doubletwisted/ComfyUI-Spool](https://github.com/doubletwisted/ComfyUI-Spool) | Video timeline inside ComfyUI: shots, takes per shot, assemble; OTIO/Resolve export; Deadline farm | ComfyUI extension (JS + Python), Comfy Registry | L, C, farm (**tested on Apple Silicon**) | model-agnostic | 3★, launch film YT, studio screenshot | 8-shot timeline, 4 takes beside viewer, workflow inputs on right |
| [viriato68/open-studio-for-affinity](https://github.com/viriato68/open-studio-for-affinity) | Affinity (Photo) AI edit/expand via ComfyUI | Python bridge + nodes, MCP | L | FLUX Kontext, SDXL | 0★, 3 images | Affinity bridge |
| [welski3/framecommander](https://github.com/welski3/framecommander) | H3 web UI on RunningHub | static JS + Netlify Drop | RunningHub API | H3, Gemini opt. | 1★, 2 YT | Hosted form |
| [obaidiDev/openfield](https://github.com/obaidiDev/openfield) "Blender MCP" | Higgsfield Blender MCP stack made local-first | Python gateway + Blender add-on | L | FLUX, lip-sync | 0★ | Blender |
| [mhaihq/hana-comfy-hack](https://github.com/mhaihq/hana-comfy-hack) "Ask Higgsy" | Video-call an animated guide that explains Higgsfield | Next.js, Vercel | C | LTX, Qwen, Z-Image, TTS, lip-sync | 1★, hosted | Avatar call (risky given C&D) |
| [crystalattice/CBI_RenderRepo](https://github.com/crystalattice/CBI_RenderRepo) | Workflow/dependency package manager | Python, 16 tests | L | — | 1★ | CLI |

**Beyond the challenge (older, mostly cloud front ends)**: [Anil-matcha/Open-Generative-AI](https://github.com/Anil-matcha/Open-Generative-AI) (31.9k★, Muapi cloud, Electron, sd.cpp Metal local images), [wide-trace/open-higgsfield](https://github.com/wide-trace/open-higgsfield) (5.1k★, Next.js, needs platform key), [SegFault42/HeliosGen](https://github.com/SegFault42/HeliosGen) (3.2k★, Tauri, kie.ai), [BeatAPI/BeatDesign](https://github.com/BeatAPI/BeatDesign) (281★, canvas + timeline, BeatAPI), [Lightricks/LTX-Desktop](https://github.com/Lightricks/LTX-Desktop) (2.2k★, Electron NLE-style LTX app, Apache-2.0), [jutsuhq/kawarimi](https://github.com/jutsuhq/kawarimi-local-character-swap) (Rust/Tauri Wan 2.2 Animate swap, Win/Linux).

### 1.3 Extra entries found only under the hyphenated topic (not in the curated list)

| Entry | What | Notes |
|---|---|---|
| [harlixay7/Kinoloom](https://github.com/harlixay7/Kinoloom) 19★ | Local film studio for an 8 GB NVIDIA + 64 GB RAM Windows PC; joins LTX-2.5 links into 16 s takes | Showcase GIF/mp4 |
| [grzenio22/cue-the-boom](https://github.com/grzenio22/cue-the-boom) 0★ | **Generate the effect once with LTX-2.5, then perform it with your voice** on your hand, a clip, or live webcam; no new generation | 1:54 demo, HF Space, "Why it's new" section. Closest thing to a live/performable entry |
| [U-N-B-R-A-N-D-E-D/comfyui-helm](https://github.com/U-N-B-R-A-N-D-E-D/comfyui-helm) 4★ | Training-free activation-steering "dial" node (16–22 KB axis files) | Comfy Registry, 77 tests; novel custom-node-pack angle |
| [RickBL99/gobo](https://github.com/RickBL99/gobo) 0★ | One line → film on Comfy Router; grading in Rust | Partner models |
| [mojomast/open-higgsfield-skills](https://github.com/mojomast/open-higgsfield-skills) 1★ | 37 agent skills that turn one prompt into a short film via open-weight workflows | Workflows "checked statically" only |
| [wilsonhj/Open-Frame-Studio](https://github.com/wilsonhj/Open-Frame-Studio) 1★ | Product shoots / marketplace listings (FLUX.2 Klein + BiRefNet) | Image-only ads |
| [MarzuwqLion/portraius-studio](https://github.com/MarzuwqLion/portraius-studio), [natalinoalmeidajoaovitor-arch/CharacterLock-Studio](https://github.com/natalinoalmeidajoaovitor-arch/CharacterLock-Studio) 0★ | Generic studio; character production studio | Low signal |

### 1.4 What a typical entry is

**Repo layout (the modal shape, seen in ~70% of repos):**

```
README.md  LICENSE  THIRD_PARTY_NOTICES.md  .env.example
workflows/           # 1–6 ComfyUI "Workflow (API)" JSON exports, e.g. swap.api.json, analyze.api.json
app/ or web/ + server/   # Next.js (app/api/*/route.ts) or Vite+React client + Express/FastAPI server
lib/comfy.ts | comfy_client.py   # maps form fields -> node ids in the API JSON, uploads inputs, polls, downloads
custom_nodes/ or comfy-nodes/    # optional node pack (63% ship one; many are 1–3 helper nodes)
docs/media/          # screenshots, before/after jpgs, a GIF, sometimes the demo mp4
build/model-files.md | MODELS.md # exact weights, folders, HF links, licenses
tests/               # unit tests against a mock backend; CI badge
AGENTS.md / CLAUDE.md            # present in roughly a quarter of repos (agent-written code is the norm)
```

**How workflow JSON and the SDK are wired** (following Comfy's reference apps [comfy-reshoot](https://github.com/Comfy-Org/comfy-reshoot) and [comfy-openjutsu](https://github.com/Comfy-Org/comfy-openjutsu)): the workflow is exported from ComfyUI as "Workflow (API)"; a thin server module loads it, sets inputs by **node id** (e.g. "node 30: the clip, node 9: the character image, node 31: quality, node 801: prompt/seed"), uploads files with the SDK, submits, streams progress, downloads outputs from `/api/jobs/<id>/outputs/<name>`. The same client code points at Comfy Cloud, a serverless deployment, or a local ComfyUI behind [`comfy-api-proxy`](https://github.com/Comfy-Org/comfy-api-proxy) by changing `COMFY_BASE_URL` ([TypeScript SDK](https://github.com/Comfy-Org/comfy-typescript-sdk) `@comfyorg/sdk`; [Python SDK](https://github.com/Comfy-Org/comfy-python-sdk) `comfy-sdk`). Roughly a sixth of entries skip the web app entirely and ship a **ComfyUI App Mode** workflow (a form rendered by ComfyUI itself; e.g. h3-recast, Dataset-Forge, urban-cuts), and a few ship a ComfyUI **extension** that adds a tab inside ComfyUI (ComfyArt, Spool, Picky).

**What the README contains** (median 10.7 KB; p25 7.7 KB, p75 15.6 KB): one-line pitch; "Demo video (1:xx)" link + hero image/GIF; "What it does" bullets; "How it works" ASCII pipeline; Models table (file, folder, size, HF link, license); Requirements (VRAM; "tested on RTX 4090 / L40S / 16 GB"); Quick start (proxy in terminal 1, app in terminal 2); "Honest notes" / "Status (honest summary)" / "Known limits"; Licenses (code vs weights); credits to Comfy reference apps. "Honest" is practically a genre convention this round, probably because judges said they judge the work.

**Demo videos:** the convention is **≤2:00** ("Watch the 2-minute demo" appears verbatim in freefield, Seam, Picky; PlateLock 1:58, fxjutsu 1:51, multicam 1:55, cue-the-boom 1:54, OpenSfield 118 s, justae-flow 2 min). X launch clips: median 75 s, 10 of 27 are 105–118 s. ComfyArt's promo is 38 s; Xenoform adds an 8-minute walkthrough.

**Three strong entries and why**

1. **neuregex/freefield (327★)**: breadth with proof. 117–120 apps, each a folder with `app.json` + API workflow; UI, runner, downloads, VRAM map and tests are all generated from manifests; 710/733 tests across 48 Modal GPU runs; every example shows its runtime and peak VRAM; a per-app "How it works" tab. It wins on verifiability and on being laid out exactly like Higgsfield.
2. **TusharTechs/platelock (2★ but the sharpest thesis)**: one real VFX-pro insight (generative tools repaint the whole frame; a compositor generates the element, pulls a matte, layers it over the plate) turned into a node pack + app, with a PSNR table proving "bit-identical outside the effect", alpha/emissive elements exportable to Nuke/AE/Resolve, a 1:58 demo and a live gallery. Exactly what "LTX VFX bonus" wants.
3. **apsolut/one-shot-multicam (2★)**: one clear recognizable output (a selfie becomes a 3-camera edit cut on word boundaries over the real audio), a live app with free runs, cost shown before spending, a cut-list editor UI (click a shot to switch cam / re-roll), a 1:55 demo and a measured-cost section. Also notable for polish: **jdnichollsc/seam** (logo, 2-min demo, project site, 3D models as input, sequences), **D3voz/openjutsu** (Comfy's own; 605★; the UI bar everyone copies), **wexloops/openfield** (Explore/Director/Stage; 565 likes on launch).

**Three weak/typical ones**

1. **DialloWill/storyboard-studio**: Flask form, mock image generator, "the Comfy generator is implemented at build night", placeholder screenshot. This is what a build-night entry looks like when the time runs out.
2. **kingofmit/ComfyUI-HiggsOpen**: an ambitious description (topic → 4-scene LTX video + TTS + captions) and a 10-byte README with no code or license. Roughly 40% of entries have 0 stars and several are description-only.
3. **codyclack/opensfield**: a pixel-level clone of Higgsfield's navigation (146 tools, all 83 apps) where the "Status (honest summary)" admits most tools are unrendered and the app ships in "mock mode". Also typical: **kevin9327/OpenSourceHiggsfield**, which buries a real 3-in-1 app under badge soup and phrases like "CVGEO1 Point-Cloud Warp & Sim(3) Verification"; **fetchloom/OpenJutsu**, whose graphs were "drafted from node schemas, not yet run on a GPU".

---

## 2. Higgsfield's feature catalog (as of Oct 2026)

Fetched from higgsfield.ai pages, blog and help center. Items marked † were not found on the current site and come from 2025 coverage or third-party mappings.

| Product / app | Input → Output | Notes / source |
|---|---|---|
| **Cinema Studio 4.0** | Prompt with `#camera` tags, up to 50 references, AI Cast (genre/era/archetype/physique), characters + emotions, locations/props, Project Brief, script (Mr. Higgs breaks it into shots), per-shot engine choice → **edited scene up to 60 s in 4K** with cuts applied | Controls: Genre (General/Action/Epic/Drama/Comedy/Horror/Noir), Era decade slider (1960–2020 regrades film stock/halation), Montage Pacing (Chaotic/Dynamic/Calm/Single Shot), stacked camera moves, color grading. "30+ presets" (Pan Left, POV, Robot Arm, Helicopter…), lenses (Clean Sharp, Anamorphic, Vintage Anamorphic, Warm Vintage, Halation Vintage), camera body (Modern, 35mm, 8mm, DV Camcorder), aperture f/1.4–f/11, lighting (Soft Cross, Overhead Fall, Contre-jour, Window, Practicals, Silhouette). [page](https://higgsfield.ai/cinematic-video-generator), [camera guide](https://higgsfield.ai/blog/ai-video-camera-control) |
| **Genjutsu** (+ Genjutsu Lite) | Reference video 4–30 s + up to 30 reference images + prompt → video keeping motion/camera/timing with new cast/look/location (**Motion Transfer**) or only selected elements changed (**Object Swap**); multiple variations | Lite: cheaper, up to 30 s at 720/1080p. [page](https://higgsfield.ai/genjutsu) |
| **Recast / Character Swap 2.0 / Video Face Swap / Face Swap** | Image or video + reference → swapped character/face | Apps grid. [apps](https://higgsfield.ai/apps) |
| **Soul / Soul 2.0, Soul ID, Soul Cast, Soul Cinema** | Soul: fashion-grade image model with presets, HEX color control, moodboards. Soul ID: ≥20 photos → trained identity usable across images/video (~3 min). Soul Cast: reusable AI actors. Soul Cinema: cinematic stills from a scene description | [blog index](https://higgsfield.ai/blog), help center "Models" |
| **Popcorn** | Up to 4 image refs + prompt → **storyboard of up to 8 consistent frames** (Auto/Manual), frames feed Kling/Veo as start frames | [help](https://higgsfield.ai/creator-hub/help-center/ai-models/how-do-i-use-popcorn) |
| **DoP** (Higgsfield's own I2V model) | Keyframe image + prompt + preset → 3 or 5 s clip | Preset categories: Effects (VFX), Basic / Epic Camera Control, Catch the Pulse, Mix. [help](https://higgsfield.ai/creator-hub/help-center/ai-models/how-do-i-use-dop) |
| **Viral / Effects presets** | One photo (no prompt) → short clip, 480p–4K, vertical options | Living paintings (Pearl Earring, Monet Muse…), Impossible rides (Dolphin Ride, Skatedog…), Cinematic reveals (Agamemnon, Bullet Time), plus Effects library named by entrants: Fire Element, Air Bending, Explosion, Thunder God, Earth Zoom, Product Freeze, Comic Bonk, Gold statue, Inflate, Disintegrate, Melt, Levitation. [viral presets](https://higgsfield.ai/blog/how-to-make-viral-videos-viral-presets) |
| **Apps** (marketplace, 40+ visible) | Category examples: Professional (Virality Predictor, Expand Image, Angles 2.0, **Shots** (1 image → 9 shots), **Transitions**); Enhance & Style (Skin Enhancer, AI Stylist try-on, Relight, Outfit Swap, Style Snap); Video Editing (ClipCut selfie→outfit reel, **Urban Cuts** beat-synced outfit video, Video Background Remover, Breakdown, Japanese Show); Ads (Click to Ad from a product link, Billboard, Truck Ad, Bullet Time Scene/White); Games & Characters (Game Dump, Nano Strike/Theft, Simlife, Plushies); Extras (Meme Generator, Micro-Beasts, Signboard, Paint App); Trending templates (On Fire, Skibidi, Mukbang, Cloud Surf, Idol); hidden: 3D Rotation, 3D Render, Mugshot, Sticker Match Cut, 3D Figure, Behind the Scenes | [apps](https://higgsfield.ai/apps) |
| **Higgsfield Apps builder** (no-code) | Chat description → deployed app at name.higgsfield.app (types: Custom/Simple/Studio/Preset; styles: Higgsfield/Y2K/Modern) | Users pay with their own credits. [blog](https://higgsfield.ai/blog/introducing-higgsfield-apps) |
| **Lipsync Studio / Speak** | Character image or video + text/audio + model (Veo 3.1, Kling 2.6 Lipsync, Wan 2.5 Speak, Kling Avatars 2.0, Higgsfield Speak 2.0, Infinite Talk, Sync Lipsync 3) + scene template (Selfie, Podcast, Car Talking) → talking clip | [help](https://higgsfield.ai/creator-hub/help-center/ai-models/how-do-i-use-lipsync-voiceover-and-aspect-ratios) |
| **Audio** | Voiceover (TTS from script, voice clone from MP3/WAV), Change Voice, Translation (18 languages). Models: Seed Audio 1.0, Eleven v3, Qwen Audio 3.0, MiniMax Speech 2.8 HD, Seed Speech, VibeVoice. **No standalone music or SFX generator** (ambience only via Seed Audio). Audio-first path: attach audio as reference to Cinema Studio/Seedance/Kling | [blog](https://higgsfield.ai/blog/higgsfield-audio) |
| **Video Relight** & **Color Palette** (standalone editing tools) | Clip (+ reference image) → relit clip (6 presets + up to 2 custom lights with color/brightness/diffuse/angle, or prompt) / regraded clip (50+ grade presets, custom); 135 credits per 15 s each | [blog](https://higgsfield.ai/blog/video-relight-color-palette-higgsfield) |
| **Upscale** (image & video), **Inpaint** (Nano Banana Pro), **Expand**, **Reframe†**, **SDR→HDR†**, **Extend video†**, **Dub†** | Standard editing utilities | Blog; † per freefield's Higgsfield mapping |
| **Marketing Studio / Ads Studio / Ad Multiplier / UGC** | Product URL or image → UGC-style and professional ads with native lip sync; one ad → many variations | [help](https://higgsfield.ai/creator-hub/help-center/tools/which-higgsfield-tool-should-i-use) |
| **Content Factory** | "What if…" topic + tone + 50+ presets + optional TikTok/IG reference link → faceless narrated video 15 s–5 min, 1–4 episodes, 9:16 | [blog](https://higgsfield.ai/blog/higgsfield-introduces-content-factory) |
| **AI Influencer Studio** | Game-style attribute picker → consistent virtual character; "Higgsfield Earn" monetization | help center |
| **3D Jutsu** | Prompt (+ refs, GLB/Mixamo) → editable 3D scene with camera path/timeline → MP4, frame, GLB; chat-refined | [blog](https://higgsfield.ai/blog/higgsfield-3d-jutsu) |
| **Katana** | Reference edit (or preset) + up to 5 photos + instructions → rebuilt edit matching shot structure/pacing/cuts-on-music, via Claude MCP | [help](https://higgsfield.ai/creator-hub/help-center/integrations/how-do-i-use-katana) |
| **Canvas** | Node board chaining models; saved as templates | help center |
| **Supercomputer agent** (GPT-6 Astra), **MCP for Claude**, **CLI + skills**, **API**, **Blender plugin**, **Playable** (prompt → mobile game), **Games 2.0**, **Virality Predictor** | Platform/agent surfaces | homepage, blog |
| **Draw-to-Video†**, **Click-to-Video†**, **Mixed Media†**, **Fashion Factory†**, **UGC Factory†**, **Product-to-Video / Sketch-to-Video†** | 2025-era names. Draw-to-Video (Aug 2025): sketch actions/labels on a frame → video. "Click-to-Video" was the Series A headline. Not on the current nav | [curiousrefuge](https://curiousrefuge.com/blog/how-to-use-higgsfield-draw-to-animation), [pulse2](https://pulse2.com/higgsfield-50-million-series-a-raised-to-transform-ai-video-creation) |
| Models offered | Seedance 2.5, Kling 4.0, Sora 2, Veo 3.1, Nano Banana, MiniMax H3, FLUX 3, Krea, Genjutsu, DoP, Soul ("30+ models") | homepage |

---

## 3. Gap map

### 3.1 Higgsfield feature × competition coverage

Coverage: entries that make the feature their primary product (secondary mentions in parentheses). Quality: subjective, from READMEs/demos.

| Higgsfield feature | # entries (primary) | Quality of best | Verdict |
|---|---|---|---|
| Genjutsu / Recast / character swap | 14 (+ in most studios) | High: D3voz/openjutsu, Body Double, h3-recast, Swapjutsu | **Saturated**; Comfy's own entry owns it |
| Cinema Studio (camera/lens/light controls, cast, scenes) | ~10 (OpenField Director, Picky, Backlot, pyoonpyoon, cinestudio, Liberty Cut, comfy-cinematic-studio) | Medium-high | **Crowded** |
| Reshoot / new angle / camera-move verification | 15 | Medium-high (multicam, ReAngle, comfy-dial, ShotCheck) | **Crowded**, with a verification sub-niche already taken |
| 3D Jutsu / previs / stage blocking | 5 (Toybox, Motion Previs Studio, OpenField Stage, previz2shot, SpEdE) | Medium | Covered |
| VFX / Effects presets | ~10 (fxjutsu, PlateLock, One-take, Conjure, freefield×2, Forkfield, LiDAR Lab, Montagio) | High (PlateLock, fxjutsu) | **Crowded**; plate-preservation already done |
| Transitions | 1 (Seam) | High | Covered well by one strong entry |
| Shots (1 image → 9 shots) / coverage | 2 (Shot Board, OpenField Coverage) | Medium | Thin but low-value |
| Popcorn storyboards (consistent multi-frame) | 1 mock (storyboard-studio) + partial (OpenReel, Shot Board, Picky) | Low | **Gap** (image-only, local-feasible) |
| Soul / Soul ID character consistency, datasets | 5 (Dataset-Forge, Character Lock, SameFace, Boson, Soul Person Enhance) + "cast" in studios | Medium | Covered |
| Lipsync / Speak / talking avatars | 0 dedicated (feature inside Montagio, OpenField "Speak", CreatorOS, easycomfee, hoodsfield) | Low-medium | **Thin as a product**, but GPU-heavy (InfiniteTalk needs 24–48 GB) |
| Audio: voiceover / voice change / translation | 0 dedicated (hildegard = "ElevenLabs alternative" inside a studio) | Low | **Thin** |
| Music / SFX / foley (Higgsfield itself lacks it) | 0 dedicated (ACE-Step as a sub-feature in 9; MMAudio in 1) | — | **Empty** |
| Video Relight / Color Palette (standalone) | 0 dedicated (relight as a step in openjutsu, fxjutsu day-to-night, Liberty Cut hour, Gobo grades) | Low | **Gap** |
| Upscale / restore | 0 dedicated (SeedVR2 step in freefield/OpenField) | — | Gap, but heavy models and Nvidia VFX nodes already exist |
| Inpaint / Expand / background removal (image) | in studios and ComfyArt | Medium | Covered by canvases |
| Ads Studio / UGC / Click-to-Ad / Urban Cuts | 7 | Medium (Open Ads Studio, ComfyField) | Covered, moderately |
| Content Factory / Diffuse (topic → narrated faceless video) | 2 (LeafReel, HiggsOpen empty) | Medium | Thin |
| Katana (reference-edit recreation) | 2 (OpenKatana, HyperKut) | Medium | Thin |
| Canvas | 4 (ComfyArt, open-source-canvas, freavy, BeatDesign) | High (ComfyArt 401★) | Covered |
| Apps builder (no-code app from a workflow) | 3 (OpenIllusion, freefield manifests, Montagio presets) + ComfyUI's own App Mode | Medium | Covered by Comfy itself |
| Virality Predictor / hook analysis | 0 | — | Empty (but gimmicky) |
| Playable / games | 1 (Crew Cut party game) | Medium | Thin, off-brief |
| AI Influencer | 2–3 (Susano, Cheapsfield, CreatorOS) | Medium | Covered |
| Supercomputer / MCP / CLI agent surfaces | 25 entries expose MCP; OpenKatana, agentY, Vision Orchestrator agent-first | High (agentY 37★) | Crowded |
| Draw-to-Video (sketch actions on a frame) | 0 explicit (Toybox "block it" is the nearest) | — | **Gap**, local-feasible with LTX 2B guides |
| Blender plugin | 3 (openfield-MCP, previz2shot, cinestudio) | Medium | Covered |

### 3.2 Gaps that are not Higgsfield features but fit the Comfy ecosystem

Feasibility is for 3 days on a 36 GB M5 Max with LTX-Video 2B (0.9.x) locally and optional Comfy Cloud/RunPod. Fit columns: Viral / Innovative / Open Weights / LTX bonus; "You" = fit to TouchDesigner + editing + audio + UI skill.

| Gap | In the competition | In the wider ComfyUI ecosystem | Feasibility (Mac + cloud) | Prize fit | You |
|---|---|---|---|---|---|
| **Sound design / foley / score for a cut** (synced SFX, stems, mix, export) | None. Comfy's own prior challenge was about sync sound ([recap](https://blog.comfy.org/p/comfy-h3-sync-sound-challenge-the)) | [kijai/ComfyUI-MMAudio](https://github.com/kijai/ComfyUI-MMAudio) 581★, HunyuanVideo-Foley wrappers, ACE-Step 3.5B is **native in ComfyUI** ([docs](https://docs.comfy.org/tutorials/audio/ace-step/ace-step-v1)), Stable Audio, Whisper, Chatterbox/Kokoro TTS. No *app* glues them into a sound-design workflow | **High**: audio models are small; ffmpeg mixing is local; risk is MPS support for MMAudio/Foley wrappers (CUDA-first) → fall back to Cloud for V2A | Innovative ✔, Open Weights ✔, Viral ◐, LTX ✗ | **Very high** |
| **Typography / captions / lyric video inside generated video** | OpenKatana mentions typography in code-authored edits; HiggsOpen (empty) promised TikTok captions | No ComfyUI node pack for kinetic type; text rendering via FLUX 3 Klein / Qwen-Image is strong for stills; LTX 2B can animate a still | **High**: Whisper word timestamps + FLUX Klein (runs on Mac) + WebGL/Canvas compositor + ffmpeg, all local | Viral ✔✔, Open Weights ✔, FLUX bonus ✔ if FLUX 3 is core, Innovative ◐ | **Very high** (UI + editing) |
| **Live / realtime / performable (TouchDesigner, OSC, NDI, webcam)** | cue-the-boom (voice triggers a pre-rendered LTX element), LiDAR Lab (CPU effects) | [ComfyUI-TD](https://github.com/JiSenHua/ComfyUI-TD) 168★ (WebSocket to TD, images/video/3D/audio), [livepeer/comfystream](https://github.com/livepeer/comfystream) (NVIDIA/Linux only), KJNodes SoundReactive, [RyanOnTheInside](https://github.com/ryanontheinside/ComfyUI_RyanOnTheInside) 867★ (audio/MIDI/motion reactivity) | **Medium**: generation of alpha elements needs LTX-2.5 on cloud; playback/triggering is local; TD is closed-source but free, app itself open | Innovative ✔✔, LTX ✔ (if LTX generates elements), Viral ◐, Open Weights ✔ | **Very high** (home turf) |
| **Audio-reactive generation** (stems/MIDI drive parameters, not just cuts) | Xenoform (stems drive light, MIDI rides picture) is the only one; Mondo/Urban Cuts beat-cut | Yvann-Nodes 715★, RyanOnTheInside; LTX-2.5 has an **audio-to-video** pipeline (video conditioned on an audio file) nobody used | Medium (A2V is in `ltx-pipelines`, ComfyUI support unclear; 22B → cloud) | Innovative ✔, LTX ✔ | High, but you're pivoting away from beat-sync |
| **NLE / compositor integration** (Resolve, Premiere, AE panels) | justae-flow (EffectCraft, an AE-like open compositor), Spool (timeline inside ComfyUI, OTIO/Resolve export), Open Studio for Affinity | Runway sells Resolve/Premiere/AE plugins; no open ComfyUI panel found; LTX-Desktop is NLE-ish; [EffectCraft](https://github.com/storytold/effectcraft) 8.2k★ | Medium-low: Resolve external scripting needs Studio; Premiere UXP is slow to build; models aren't the point | Innovative ◐, Viral ✗ | High (editing) but weak "app" story |
| **Video relight + grade with pro tools** (scopes, LUT export, reference match) | None dedicated | LTX IC-LoRAs (Day-to-Night, Union Control), Nvidia VFX nodes (SDR→HDR), color-transfer nodes; no grading UI | Medium: grading local; relight on cloud LTX | LTX ✔, Innovative ◐ | High (editing) |
| **Popcorn-style storyboard editor with consistent cast** | 1 mock | Hub has 13 storyboard workflows; FLUX Klein + Qwen-Image-Edit consistency | High (image-only, local) | Open Weights ✔, Viral ✗ | Medium |
| **Draw/scribble-to-video** (sketch motion paths on a frame) | None | LTX guides (`LTXVAddGuide`), depth/canny IC-LoRAs; Toybox proves keyframe-guided LTX 2B on Mac | High-medium | Innovative ◐, LTX ✔, Viral ◐ | Medium-high (UI) |
| **Datamosh / glitch / analog lab** | cat-tapes (VHS look via prompts) | [DJZ-Nodes](https://github.com/MushroomFleet/DJZ-Nodes) datamosh V2–V6, GlitchNodes | High (CPU) | Viral ◐, Innovative ✗ | Medium |
| **Consistent world / multi-shot from one scene** | Picky, OpenReel, 360-Scout, LTX-2.5 native multishot in Kinoloom | LTX-2.5 "native multi-shot" | Low on Mac (22B) | — | Low |
| **Archival restoration / photogrammetry / splats** | SpEdE (splat editing), LiDAR Lab | SeedVR2, TripoSplat, gsplat | Low-medium | — | Low |
| **Activation steering / model-control nodes** | comfyui-helm | — | Medium (image models local) | Innovative ✔ | Low |

Honest read: the "app over a workflow" format is saturated for anything Higgsfield already sells. The open lanes are the ones where Higgsfield is weak or absent (**sound, typography, live/performance, pro post tools**) and where a TouchDesigner/editing/audio person has an unfair advantage.

---

## 4. Ideas, ranked (gap × feasibility × fit to you × prize fit)

1. **Foley Room: sound design and score for any cut.** Drop a silent AI clip (or a sequence/folder of shots) → MMAudio/Hunyuan-Foley generate synced SFX per shot, ACE-Step writes a score to the cut length with stem separation, a mixer UI shows waveform lanes per shot (SFX / ambience / score / VO), auto-ducking under dialogue, per-lane re-roll, export WAV + mixed MP4 + the ComfyUI workflow. Why: zero entries, Higgsfield has no music/SFX at all, Comfy's own last challenge was about sync sound, and you can build a DAW-grade UI nobody else in this field can. Downsides: MMAudio/Foley nodes are CUDA-first, so V2A may have to run on Comfy Cloud/RunPod while ACE-Step and mixing stay local; judges may ask "H3/LTX already generate audio" (answer: for any footage, any model, and iterative control); no LTX/FLUX/H3 bonus.
2. **Type Set: kinetic typography and lyric/caption composer.** Whisper gives word timestamps; FLUX 3 Image Klein renders each word/phrase as a designed asset (neon, ice, cut paper, chrome) with alpha via BiRefNet; LTX-Video 2B animates the type (or a WebGL compositor does, for a free CPU path); words land on their timestamps over the video; presets ("TikTok caption", "lyric video", "title card"), export MP4 + SRT. Why: no entry does on-screen text, Higgsfield only has captions inside Content Factory, the output is instantly shareable (Most Viral), and FLUX 3 as core model qualifies for the FLUX bonus. Downsides: diffusion typography still misspells sometimes (mitigate with Qwen-Image for text-heavy words, or pass real glyph masks as control); the "AI" part has to be obviously central or it reads as a CapCut feature; FLUX bonus is API credits, not cash.
3. **Stage Hand: performable VFX bridge for live shows.** Generate a bank of alpha VFX elements with LTX-2.5 IC-LoRAs on cloud (fire, smoke, sparks, portals: the fxjutsu/PlateLock recipe), then a local app plays them on a webcam/NDI feed, triggered and shaped by audio onsets, MIDI/OSC, or voice, and streams to TouchDesigner via ComfyUI-TD/NDI/Syphon. Why: the live/realtime lane is empty except cue-the-boom, it's genuinely "never been done" in this field (Most Innovative), LTX is the core generator (LTX bonus), and the demo writes itself if you perform it on the NYC stage. Downsides: two-part system is harder to explain in 2 minutes; generation costs credits; overlap with cue-the-boom's "perform with your voice" (differentiate with TD/OSC/MIDI and multi-element compositing); live demos break.
4. **Grade & Relight: standalone video relight + color palette tools with scopes.** Clone Higgsfield's two editing tools: relight via LTX IC-LoRAs (cloud) with a draggable light rig UI; grading locally with reference-image color matching, 50 LUT-style looks, waveform/vectorscope, `.cube` export. Why: no dedicated entry, pro-post framing fits Comfy's VFX push (Nvidia VFX nodes, "AI post production" events), LTX core qualifies for the VFX bonus. Downsides: relight quality from IC-LoRAs is coarse and slow; grading alone is "not AI"; low viral potential.
5. **Scribble Director: draw-to-video on your own frame.** Upload a frame, draw motion paths/arrows and label them, stage 3–8 keyframes with Qwen-Image-Edit, LTX-Video 2B renders locally with `LTXVAddGuide` (Toybox's proven Mac path), HD pass on cloud. Why: Draw-to-Video is a real Higgsfield feature with zero clones; fully local demo on your Mac; drawing UI is your strength. Downsides: Toybox Director and Comfy-Dial are adjacent; LTX 2B output quality is modest, so the demo looks less impressive than cloud entries.
6. **Resolve Script Panel for ComfyUI.** A Resolve/Fusion Python script (or Premiere UXP) that sends the clip under the playhead and a prompt to a Comfy workflow (Seam-style transition, PlateLock-style effect, re-shoot) and drops the result back on a track above. Why: no open ComfyUI NLE panel exists, Runway's are proprietary, and it fits the "AI post production" conversation Comfy has been running. Downsides: Resolve external scripting requires Studio, Premiere panels are a time sink, no new model work, hard to make viral, and judges said they want "apps that make it easy for someone else to create".
7. **Storyboard (Popcorn) editor with a locked cast.** Image-only, fully local on FLUX Klein + Qwen-Image-Edit; a proper panel editor (8 frames, consistent characters, shot-list export, hand-off to Toybox/LTX). Downsides: low viral, Hub already lists 13 storyboard workflows, OpenReel/Shot Board overlap.
8. **Analog Lab: datamosh/VHS/CRT effects as an App Mode pack with a tactile UI.** DJZ datamosh nodes + your own glitch shaders + LTX 2B for "dream" frames; CPU-friendly. Downsides: low innovation, cat-tapes and many TikTok filters cover the aesthetic, weak Higgsfield tie.

If you want one sentence: **build #1 or #2; if you want the 5090 for Most Innovative and you're willing to spend credits, build #3.**

---

## 5. Judges' signal

- **Rules page** ([comfy.org/open-source-higgsfield](https://www.comfy.org/open-source-higgsfield)): "Build a working app that makes it easy for someone else to create their own"; start from "a recognizable output, such as a performance effect, a cinematic camera move, or a music-video transformation"; Most Innovative = "never been done" or "novel custom node packs", and the "demo video must explain why the submission is innovative"; Most Viral = "delightful to use and made to be shared"; Open Weights Only = "no partner nodes or closed-source APIs"; demo video "not judged on production quality… we're judging the work"; entries are featured on comfy.org/hub with credit; each entry can win one main category plus one model-provider bonus.
- **Launch post** ([Allyson Toy, Oct 15](https://blog.comfy.org/p/higgsfield-promised-to-open-source)): the only features named are Genjutsu and Cinema Studio; "try the example apps on the Hub, see how they're built, then make your own". Partners named on X: NVIDIA, RunPod, MiniMax, LTX, BFL ([ComfyUI on X](https://x.com/ComfyUI/status/2111290899342950687)).
- **Comfy's own entry** ([OPENjutsu post, Oct 26](https://x.com/ComfyUI/status/2114843030364795231)): "Run it on Comfy, run it locally, or plug in a paid model if you want higher quality" — they explicitly value the local/cloud/paid tri-mode that the SDK enables.
- **Previous challenge rubric** ([H3 Sync Sound recap](https://blog.comfy.org/p/comfy-h3-sync-sound-challenge-the)): eight Comfy creative technologists scored **novelty, workflow quality, community value**; winners were praised for "clean, approachable workflows that others can follow", openness (sharing full repos/logs), a custom node pack "singled out", and end-to-end MCP use. Guest judges were POM (Banodoco), Emma Catnip (AV artist), Yachimat.
- **Reposts/highlights:** none found. Neither the Comfy blog archive ([blog.comfy.org/archive](https://blog.comfy.org/archive)) nor accessible X posts highlight specific community entries so far; the Hub "Apps" section still lists only Comfy's three official apps ([comfy.org/hub](https://www.comfy.org/hub)). The jutsuhq list and press (artrealmai on freefield) are the only "coverage" signals.
- **Crowded vs thin (by jutsuhq's own counts and this read):** crowded = studios (25), camera (15), swap (14); thin = characters/datasets (5), ads (7), and the non-Higgsfield lanes above (audio, typography, live).
- **Context you should know:** Comfy's recent product pushes are Comfy Agent, Comfy API (deploy workflows as production APIs), Comfy Router, Nvidia VFX nodes for VFX professionals, and "AI post production" livestreams ([blog archive](https://blog.comfy.org/archive), [events](https://comfy.org/events/)). Entries that connect to pro post workflows or to agents (MCP) match where the company is heading.
- **NYC specifics** ([Luma](https://luma.com/nyc-yjfm)): hosts include Allyson Toy (Comfy), ZeroSpace, Xuelong Mu, Eric Tang, Sahar Mor, Georgia Limcaoco; presented by NYC Creative AI; agenda 5:30–8:30 build, 8:30–9:00 ComfyUI + RunPod presentations, 9:00–9:30 demos. Bring a laptop; RunPod presence suggests GPU credits may be available on the night.

---

## Appendix: feasibility notes for a 36 GB M5 Max

- **LTX-2.5 22B**: int8 distilled transformer 21.5 GB + Gemma 4 12B int8 encoder 15.4 GB + VAEs ([one-take-vfx model table](https://github.com/Kainotomic/one-take-vfx)); not locally feasible. Hildegard's README notes "LTX needs int8 or fp8 kernels Apple lacks" ([hildegard](https://github.com/baney75/hildegard)).
- **LTX-Video 0.9.x 2B/13B** run on MPS; Toybox Director's bundled runtime was "verified on macOS with Apple Silicon (M5 Max, 128 GB, MPS)" with 2B drafts at 512×320 and 13B at 1024×576 ([toybox-director](https://github.com/mahdi-salmanzade/toybox-director)); on 36 GB expect 2B comfortably, 13B tight.
- **LTX-2.3 on Mac outside ComfyUI**: [ltx-video-mac](https://github.com/james-see/ltx-video-mac) (445★) ships LTX-2.3 Distilled Q4 (~22 GB) and a "12 GB RAM optimized" pack, 32 GB RAM minimum, with a local REST API, no ComfyUI integration; MLX conversions exist on HF (FrankDase/LTX-2.3-MLX, LTX-2.5-MLX).
- **Image**: FLUX 3 Image Klein 5.6B open weights ([Comfy blog](https://blog.comfy.org/p/flux-3-image-klein-in-comfyui-56b)), Qwen-Image 2.1, Z-Image Turbo: fine on Mac.
- **Audio**: ACE-Step 3.5B native in ComfyUI; Whisper; Chatterbox/Kokoro TTS; MMAudio/Foley wrappers are CUDA-first (test early; have a Cloud fallback).
- **Cloud costs reported by entrants**: ≈$0.055 per 5 s LTX-2.3 re-shoot insert on Comfy Cloud (multicam), ≈80¢ for a 4-shot FLUX+Wan film via Router (Gobo), ≈$4 total for Liberty Cut's A10 runs. The first 200 sign-ups got free credits; RunPod is at the NYC event.
