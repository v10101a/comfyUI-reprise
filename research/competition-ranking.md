# Open Source Higgsfield: who is likely to win (and where Typeset stands)

Research date: **2026-10-31**, refreshed from the Oct 30 inventory in [entries-and-gaps.md](entries-and-gaps.md). GitHub numbers come from the GitHub API today. X numbers come from the public fxtwitter mirror of each launch post linked in the [jutsuhq list](https://github.com/jutsuhq/open-source-higgsfield) (42 posts). Reddit and Discord could not be read: Reddit blocks this fetcher, and Discord isn't public. These are estimates from public signals, not knowledge of the judges' deliberations.

## 0. What changed since Oct 30 (read this first)

1. **The deadline moved.** The official page now says *"Build 10/15 – 11/3. Submission window closes: November 3rd 9am PT"* and *"Winners announced 11/10"* ([comfy.org/open-source-higgsfield.md](https://comfy.org/open-source-higgsfield.md)). The earlier dates were Oct 30 and Nov 6. Secondary sources ([comfyui-wiki](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield)) still show the old dates. **Implication: Typeset can submit online through the [entry form](https://form.typeform.com/to/V1dSQrkS) by Nov 3 at noon ET and compete for the main prizes.** The "only in-person awards" worry no longer applies. The page still says the online competition and the Build Nights are separate.
2. **Prizes are verified** as stated in the brief:
   - $10k Best Overall.
   - An RTX 5090 each for Most Innovative ("Demo video must explain why the submission is innovative"), Most Viral and Open Weights Only.
   - 10 × $250 runner-up credits.
   - Bonuses: LTX $2k cash ("LTX must be the core video model"), FLUX 3 $1k/$500/$250 credits, MiniMax H3 $1k credits.
   - **"Each entry can compete for one main category and one model-provider bonus."**
   - Winners are featured on comfy.org/hub.
   - There are no formal judging criteria. The Q&A says "We're judging the work, not your video editing… The best demo shows your work in action with an explanation of how it was built."
3. **No finalists, judge comments or winners** have been posted. There are no new Comfy blog posts since Oct 15 ([archive](https://blog.comfy.org/archive)).
4. **New entries since Oct 30.** jutsuhq added 10 from the r/comfyui thread ([commits](https://github.com/jutsuhq/open-source-higgsfield/commits/main)), now 101 challenge entries. More are under the topic tag or in a keyword search:
   - **[okkazoo/MOTNGRFX](https://github.com/okkazoo/MOTNGRFX)**, the direct Typeset competitor (§3).
   - **[Zitroffi/comfyui-element-forge](https://github.com/Zitroffi/comfyui-element-forge)**, a strong LTX VFX entry.
   - [thekhoma/pickups](https://github.com/thekhoma/pickups), a pro VFX app on LTX.
   - [kubakubkub/ComfyUI_KubaNodes](https://github.com/kubakubkub/ComfyUI_KubaNodes), projection mapping plus App Mode. The repo was created Sep 27.
   - [roadmaus/ComfyUI-Continuity](https://github.com/roadmaus/ComfyUI-Continuity), 138★. It was created Aug 8, so those stars predate the challenge.
   - [parametricparadigm/ComfyUI_Parametric_Studio](https://github.com/parametricparadigm/ComfyUI_Parametric_Studio).
   - [martinsbrezauckis/OpenJutsu3D](https://github.com/martinsbrezauckis/OpenJutsu3D).
   - [SasanSeyedi/singsync](https://github.com/SasanSeyedi/singsync) (lyric/beat-cut singing music videos; CLI only).
   - [A-Nobody4980/lip-service](https://github.com/A-Nobody4980/lip-service) (lipsync for singers).
   - [slit-company/viral-hit](https://github.com/slit-company/viral-hit) (Router/partner models).
   - About 10 more studios with 0★.
   - Expect a second wave before Nov 3 now that the window is open longer.
5. **Correction to the Oct 30 file:** [neuregex/freefield](https://github.com/neuregex/freefield) (now **361★ / 75 forks**) is *not* in the jutsuhq list. It is a real, widely covered entry ([artrealmai](https://artrealmai.com/article/freefield-open-source-higgsfield-comfyui-117-apps)).

### Traction snapshot (only data that is visible)

| Entry | ★ / forks (Oct 31) | X launch post: likes / views |
|---|---|---|
| [wexloops/openfield](https://github.com/wexloops/openfield) | 116 / 20 | **568 / 22.2k** ([post](https://x.com/strangelooptv/status/2115577068541125062)) |
| [raph651/open-source-canvas](https://github.com/raph651/open-source-canvas) | 89 / 21 | **543 / 20.4k** ([post](https://x.com/RaphaelLiu10/status/2115913910075449637); author has 67 followers, so this is organic reach) |
| [jtydhr88/ComfyArt](https://github.com/jtydhr88/ComfyArt) | 405 / 69 | 152 / 8.0k ([post](https://x.com/jtydhr88/status/2114927438518219073)) |
| [neuregex/freefield](https://github.com/neuregex/freefield) | 361 / 75 | no X post in list; press coverage |
| [D3voz/openjutsu](https://github.com/D3voz/openjutsu) | 657 / 101 | 3 / 732 (amplified by [ComfyUI's own post](https://x.com/ComfyUI/status/2114843030364795231)) |
| [hodgemann/mondo-music-video](https://github.com/hodgemann/mondo-music-video) | 10 | 21 / 3.7k |
| [RahmelJackson/frameforge-studio](https://github.com/RahmelJackson/frameforge-studio) | 3 | 21 / 1.2k |
| [lucataco/open-source-higgsfield](https://github.com/lucataco/open-source-higgsfield) | 26 | 14 / 1.1k |
| [apsolut/one-shot-multicam](https://github.com/apsolut/one-shot-multicam) | 2 | 5 / 278 |
| [okkazoo/MOTNGRFX](https://github.com/okkazoo/MOTNGRFX) | 0 | **0 / 9** (new account, 0 followers) |
| PlateLock, Element Forge, Pickups, Seam, Picky | 0–15 | ≤2 likes or no post found |

Most entries have fewer than 10 likes. Apart from three posts, social traction is essentially flat, so Most Viral will probably be judged on the product and its outputs more than on numbers.

---

## 1. Ranked top 15 overall (likelihood of winning *some* main prize; Best-Overall odds in brackets)

**Excluded from the ranking:**
- **D3voz/openjutsu.** Comfy presented it as their own ("A few of us built OPENjutsu as a side project", [ComfyUI on X](https://x.com/ComfyUI/status/2114843030364795231)). It's the bar to clear, not a likely winner.
- **Comfy-Org/comfy-openjutsu.** It is Comfy's own official template.

| # | Entry | Pitch | Why it could win | Weaknesses | Likelihood | Best prize fit |
|---|---|---|---|---|---|---|
| 1 | [neuregex/freefield](https://github.com/neuregex/freefield) | Higgsfield's catalog rebuilt as 117 open-weights apps, each a folder with a manifest and a workflow | Most complete and most verifiable: UI, runner, VRAM map and tests are all generated from manifests. 334 fixed-seed lab cases, CI that loads every workflow in a CPU ComfyUI, a hosted Modal demo, a 2-min [video](https://youtu.be/N7mv2v3Txeo), 361★/75 forks and press coverage. Strictly open weights | Breadth over novelty ("fixed prompts over a few pipelines", in its own words). Needs Modal or a big GPU (44 GB peak on some apps) | **High, ~35%** for a main prize [Overall ~22%] | Open Weights Only (or Overall) |
| 2 | [wexloops/openfield](https://github.com/wexloops/openfield) | Whole-Higgsfield studio: Create/Direct/Transform/Finish, a Three.js Stage, phone-motion "Mirror" | The biggest social reach in the field (568 likes, 22k views). Polished Explore grid, Director panel and 3D blocking. SDK/proxy, node pack, MCP | Only 5 commits (a code dump), so depth is hard to verify. "Clone everything" is a crowded category | **High, ~30%** [Overall ~12%] | Most Viral |
| 3 | [jtydhr88/ComfyArt](https://github.com/jtydhr88/ComfyArt) | A Figma-like tldraw design canvas *inside* ComfyUI with a design agent | The deepest "ComfyUI as platform" story: a frontend extension with artboards, layers, timeline and a generate panel. 405★, docs site, 152-like post | Canvases are a crowded category. **The author has 340 commits in Comfy-Org/ComfyUI_frontend** ([search](https://github.com/Comfy-Org/ComfyUI_frontend/commits?author=jtydhr88)). If staff or close to staff, it may be showcased rather than awarded (unverified) | **Med–high, ~22%** [Overall ~10%] | Most Innovative / Overall |
| 4 | [TusharTechs/platelock](https://github.com/TusharTechs/platelock) | Plate-preserving generative VFX: pixels bit-identical outside the effect, with alpha/emissive elements for Nuke/AE | The sharpest VFX-pro thesis, with proof (PSNR table). A 1:58 demo, a live gallery and a node pack. Exactly what "VFX workflow built with LTX" describes | 2★, no social traction. Needs an L40S or cloud | **Med, ~30% for LTX bonus**, ~8% main | LTX bonus, then Innovative |
| 5 | [Zitroffi/comfyui-element-forge](https://github.com/Zitroffi/comfyui-element-forge) **(new)** | LTX-2.5 fire, lightning, smoke and particles tracked, lit and occluded in your own footage, with scene-linear EXR passes | The comp-ready approach applied to real footage. Point, object and camera tracking, depth and normals, mask occlusion, 26 styles. Logo, release video, an app *and* nodes | 6★, 9 commits, posted late, with a direct overlap with PlateLock | **Med, ~25% for LTX bonus**, ~8% main | LTX bonus / Innovative |
| 6 | [raph651/open-source-canvas](https://github.com/raph651/open-source-canvas) | A Higgsfield-Canvas-style node board | 543 likes / 20k views from a 67-follower account: the only clearly organic hit. 89★ | Node canvas on top of ComfyUI, a node canvas, isn't novel. Uses Router partner models (Seedance/Kling/Veo), so it's out of Open Weights | **Med, ~20%** | Most Viral |
| 7 | [apsolut/one-shot-multicam](https://github.com/apsolut/one-shot-multicam) | One selfie take becomes a 3-camera edit cut on word boundaries | A clear, recognizable output. A [live app](https://multicam.apsolut.dev) with free runs, cost shown before spending, a cut-list editor and a 1:55 demo. 60 commits. LTX-2.3 core | Low traction (5 likes). The camera/reshoot category is crowded | **Med, ~15%** [Overall ~6%] | Most Viral or LTX bonus |
| 8 | [okkazoo/MOTNGRFX](https://github.com/okkazoo/MOTNGRFX) **(new)** | Song, images or a brief become a kinetic-type motion graphic: Gemma 4 designs it, LTX 2.5 shoots it, and LTX mattes put the type behind and through the subject | Novel and well built: a node pack plus an app served *from ComfyUI* (`/motngrfx`, using ComfyUI's own endpoints). Three VRAM tiers, measured timings, a 1:58 demo plus a 1:01 walkthrough, editable storyboard cards. Open weights. LTX core | 0★, 9 views, created Oct 30. Needs a 24 GB NVIDIA GPU and about 100 GiB of models. Generated footage only (no tracking of real footage) | **Med, ~12%** (LTX ~12%, Innovative ~8%) | Most Innovative / LTX bonus |
| 9 | [jdnichollsc/seam](https://github.com/jdnichollsc/seam) | Two shots in, one AI transition out (smoke, water bend, whip pan) | Polished: logo, [project site](https://jdnichollsc.github.io/seam/), 2-min video, sequences, 3D models as input, "Surprise me". LTX-2.5 open | Narrow. Little traction (2 likes) | **Med–low, ~12%** | LTX bonus / Most Viral |
| 10 | [thekhoma/pickups](https://github.com/thekhoma/pickups) **(new)** | A pro "pickups" app: remove, replace a person, weather, relight, previz to final, 4K HDR finish, delivered as ProRes | A post-production-grade pitch ("0 pixels changed outside the matte"), a take-based review screen, a 2-min [demo](https://www.youtube.com/watch?v=PdO-rVu2UkY). Mostly LTX | 2 commits, 3★. Very broad. Needs NVIDIA | **Med–low, ~10%** | LTX bonus / Overall |
| 11 | [chenthedesignmaker/ComfyUI-Picky](https://github.com/chenthedesignmaker/ComfyUI-Picky) | An H3 film studio inside ComfyUI: takes, lineage, cast, a prompt linter, a timeline | Deep ComfyUI integration (a node pack plus an in-ComfyUI editor), a 2-min video, open weights. 17★ | Low traction. Cinema-studio clones are crowded | **Med–low, ~10%** (H3 bonus ~25%) | MiniMax H3 bonus / Open Weights |
| 12 | [grzenio22/cue-the-boom](https://github.com/grzenio22/cue-the-boom) | Generate an LTX-2.5 effect once, then perform it on your hand with your voice, live | The only performable/live entry. A "Why it's new" section, a [HF Space](https://gshcloud-cue-the-boom.hf.space), a 1:54 demo, 456 commits | 0★, no post found. Live demos are fragile | **Low–med, ~8%** | Most Innovative |
| 13 | [kubakubkub/ComfyUI_KubaNodes](https://github.com/kubakubkub/ComfyUI_KubaNodes) **(new)** | Projection mapping and "pictures made of parts": regions, per-region diffusion, a director window and a show timeline in ComfyUI | Novel custom-node pack and a strong platform story: an in-ComfyUI director and timeline, two **App Mode** apps, versioned releases via the Manager. 10★ | The repo predates the challenge (Sep 27). A niche, installation-oriented audience | **Low–med, ~8%** | Most Innovative |
| 14 | [lucataco/open-source-higgsfield](https://github.com/lucataco/open-source-higgsfield) "Body Double" | Plate-preserving Genjutsu recast (SAM 3.1 + FLUX 3 Klein + SCAIL-2) | A well-known builder (11.6k X followers, Replicate), core nodes only, CI, 26★ | CLI-first with almost no app UI. Character swap is the most crowded category | **Low, ~6%** | Open Weights / FLUX bonus |
| 15 | [parametricparadigm/ComfyUI_Parametric_Studio](https://github.com/parametricparadigm/ComfyUI_Parametric_Studio) **(new)** | A suite with a 3D wall of real renders and "the real graph in 3D behind every frame", plus voiced help characters | A memorable front end, a [live demo](https://parametricparadigm.github.io/ComfyUI_Parametric_Studio/), a 2-min video, H3/LTX/Klein cores | 6 commits, 0★, a generic all-in-one | **Low, ~5%** | H3 bonus / Viral |

Next on the list (each ≤5%):
- [Bambushu/h3-recast](https://github.com/Bambushu/h3-recast): App Mode only, 36★, strong for the H3 bonus.
- [thePloggy/CreatorOS-Studio](https://github.com/thePloggy/CreatorOS-Studio): 42★.
- [hodgemann/mondo-music-video](https://github.com/hodgemann/mondo-music-video): 3.7k views.
- [szprivate/agentY](https://github.com/szprivate/agentY): pre-existing project.
- [U-N-B-R-A-N-D-E-D/comfyui-helm](https://github.com/U-N-B-R-A-N-D-E-D/comfyui-helm): activation steering, a pure Innovative node pack.
- [Kainotomic/one-take-vfx](https://github.com/Kainotomic/one-take-vfx), [audriu/fxjutsu](https://github.com/audriu/fxjutsu).
- [doubletwisted/ComfyUI-Spool](https://github.com/doubletwisted/ComfyUI-Spool), [HomoLapis/justae-flow](https://github.com/HomoLapis/justae-flow).
- [tysonfarrington-cmyk/xenoform](https://github.com/tysonfarrington-cmyk/xenoform).

**Uncertainty.** We can't tell who actually filed the entry form. Stars are partly pre-challenge (agentY, Continuity, KubaNodes). The judges are Comfy staff, who value "a working app that makes it easy for someone else to create their own", explained clearly. Polish and verifiability probably matter more than stars. The Nov 3 extension means late, strong entries are still coming.

## 2. Per-prize shortlists (top 3 each)

| Prize | 1 | 2 | 3 | Note |
|---|---|---|---|---|
| **Best Overall ($10k)** | neuregex/freefield (~22%) | wexloops/openfield (~12%) | jtydhr88/ComfyArt (~10%, affiliation caveat) | Alternates: one-shot-multicam, PlateLock. Comfy may favor the entry that best shows "ComfyUI as an app platform" |
| **Most Innovative (5090)** | jtydhr88/ComfyArt (~18%) | okkazoo/MOTNGRFX (~10%) / Zitroffi Element Forge (~10%) | grzenio22/cue-the-boom or KubaNodes (~8%) | The rule rewards "novel custom node packs or uses of ComfyUI" *and* a demo that explains why. Many entries miss the "why" |
| **Most Viral (5090)** | wexloops/openfield (~28%) | raph651/open-source-canvas (~20%) | apsolut/one-shot-multicam (~10%) | The only two entries with real reach. "Made to be shared" favors share-native *outputs*, and nothing strong exists there yet, which is Typeset's opening |
| **Open Weights Only (5090)** | neuregex/freefield (~35%) | ComfyUI-Picky (~10%) | MOTNGRFX / Element Forge (~8%) | Freefield's strict "no API or partner nodes" table makes it the default pick |
| **LTX bonus ($2k)** | TusharTechs/platelock (~28%) | Zitroffi Element Forge (~22%) | jdnichollsc/seam or MOTNGRFX (~12%) | Also in contention: one-take-vfx, fxjutsu, Pickups, one-shot-multicam |
| *(MiniMax H3 bonus, for Typeset)* | Bambushu/h3-recast | ComfyUI-Picky | Parametric Studio | D3voz/openjutsu is H3-core but Comfy's own |

## 3. Where Typeset stands

**What it is, honestly.**
- It's an editable typography compositor for footage. Words sit behind the subject (BiRefNet matte), on walls (planar tracking with a per-frame homography), or as head-anchored HUD.
- It has looks, a one-click 9:16 reframe with re-layout, a deterministic renderer (preview matches export), a React studio, and a ComfyUI analysis node pack (whisper words, lyric align, beats, matte, occupancy, surface tracks, text plates).
- It uses `comfy-sdk` and is MIT-licensed.
- The hero's footage is MiniMax H3 (ref2v for identity). The single generated word shot is Qwen-Image-Edit → MiniMax H3 ([docs/HERO.md](../docs/HERO.md)).
- **Not yet done:**
  - there is no git remote (the repo isn't public);
  - there is no ≤2-min demo video and no #OpenSourceHiggsfield post;
  - it hasn't been submitted;
  - the README still says "Early working prototype… previously explored… Recut".

**Best positioned for:**
- **Main category: Most Viral.** Lyric and kinetic-type clips in 9:16 with one-click looks are literally "made to be shared". No strong entry owns share-native *outputs*. The two viral leaders are an all-in-one studio and a canvas, and their reach comes from novelty of scope, not from the clips they make. Estimate **~8–12%** if shipped well, versus about 0% today.
- **Alternative: Most Innovative (~6–10%).** Only worth it if the demo spends 20–30 s explaining *why*: real footage, planar-tracked surfaces plus subject-anchored HUD, and deterministic editable type. MOTNGRFX already claims "type behind and through the subject" with LTX mattes, so "behind the subject" alone won't read as new.
- **Bonus: MiniMax H3 ($1k credits, ~20–25%).** The hero footage is H3-core, and the H3 field is thin outside Comfy's own entry.
- **LTX ($2k):** only if LTX becomes the core video model in the shipped workflow. Today LTX is an optional i2v path (local LTX 2B smoke tests), so claiming it would be weak against PlateLock and Element Forge. Pick one bonus: H3.
- **Open Weights:** Typeset qualifies (H3, Qwen, BiRefNet, Whisper and ACE-Step are open weights), but freefield dominates that category.

**Closest competitors:**
1. **[okkazoo/MOTNGRFX](https://github.com/okkazoo/MOTNGRFX).** It does the same thing: kinetic type behind and in front of the subject, Whisper lyrics, a node pack plus an app, open weights, LTX, and a 1:58 demo. Typeset's edge:
   - it works on **your own footage**, where MOTNGRFX mostly generates footage;
   - it has planar **wall tracking** and **head-tracked HUD**;
   - the type is exact and editable, rendered deterministically, with preview equal to export;
   - one-click looks and 9:16 re-layout;
   - it runs on a Mac (MOTNGRFX needs 24 GB NVIDIA and ~100 GiB).

   Its edge: LTX-native 3D depth cuts, a Gemma "director", and it was submitted on time. Neither has traction (0★ / 9 views).
2. **[Zitroffi/comfyui-element-forge](https://github.com/Zitroffi/comfyui-element-forge).** Same "elements that sit in the shot" grammar (tracked, occluded, comp-ready), but for VFX instead of words. The judges will see these as siblings.
3. **[wexloops/openfield](https://github.com/wexloops/openfield) / [raph651/open-source-canvas](https://github.com/raph651/open-source-canvas).** Not similar products, but they are what Typeset would have to beat for Most Viral.
4. Minor: [SasanSeyedi/singsync](https://github.com/SasanSeyedi/singsync) (lyric-timed cuts, CLI), [hodgemann/mondo-music-video](https://github.com/hodgemann/mondo-music-video) (burns in `lyrics.srt`), and [ComfyUI-WordPop](https://github.com/Codebreakers-Studio/ComfyUI-WordPop) (prior art, not an entry).

**What would most raise its odds before Nov 3, 9am PT (in order):**
1. **Ship the minimum required.**
   - Make the repo public with a README that drops "prototype/Recut", leads with a GIF, and links the demo.
   - Record a ≤2:00 demo video.
   - Post on X (and r/comfyui) with #OpenSourceHiggsfield.
   - **Submit the [entry form](https://form.typeform.com/to/V1dSQrkS)** with Most Viral as the main category and the H3 bonus.
   - Open a PR or comment so [jutsuhq](https://github.com/jutsuhq/open-source-higgsfield) lists it. Its maintainer pulls entries from the r/comfyui thread.
2. **Make the demo answer MOTNGRFX directly.**
   - Open on a *real phone clip* (not generated) and get words behind the subject, a tracked wall line and a HUD on a head within ~20 s.
   - Then one-click looks ×3 and a one-click 9:16, then the H3 "word as object" beat.
   - Say the "why" in one sentence: "video models can't spell, so the words are real type composited into the scene, editable and identical in preview and export".
3. **Lean into the ComfyUI platform.**
   - Show the node pack in a ComfyUI graph for about 10 s.
   - Ship at least one **App Mode** workflow, e.g. "Words behind subject" from matte + words + text plate. Comfy is pushing App Mode, and 17% of entries mention it.
   - Mention `comfy-sdk` and the API workflows.
4. **Seed sharing.**
   - Post 2–3 finished 9:16 lyric clips (the hero, the dancer in red-glow) as standalone posts; the outputs are the viral proof.
   - Get a few people at the NYC build night (Nov 2) to run it on their own clips, and post those.
   - Add a sample project and a "try it in 60 s" path so judges can reproduce it on a Mac without a GPU box.
5. **Avoid:** claiming the LTX bonus while H3 is the core video model, saying "nobody has done this" (MOTNGRFX, CapCut and WordPop exist), and any Higgsfield branding (cease-and-desist context in [entries-and-gaps.md](entries-and-gaps.md)).

## 4. Sources

- Rules, prizes, dates: [comfy.org/open-source-higgsfield.md](https://comfy.org/open-source-higgsfield.md) (fetched Oct 31), [entry form](https://form.typeform.com/to/V1dSQrkS), [Comfy blog archive](https://blog.comfy.org/archive), [comfyui-wiki](https://comfyui-wiki.com/en/news/2026-10-15-open-source-higgsfield) (outdated dates).
- Field: [jutsuhq/open-source-higgsfield](https://github.com/jutsuhq/open-source-higgsfield) (`projects.json`, 107 rows), GitHub topics [opensourcehiggsfield](https://github.com/topics/opensourcehiggsfield) (24) and [open-source-higgsfield](https://github.com/topics/open-source-higgsfield) (18), and a keyword search for repos created after Oct 29.
- Traction: GitHub API (stars, forks, commits, push dates); X launch posts via api.fxtwitter.com (likes, reposts, views, video length). Reddit and Discord were not readable.
- Press: [artrealmai on freefield](https://artrealmai.com/article/freefield-open-source-higgsfield-comfyui-117-apps), [ComfyUI OPENjutsu post](https://x.com/ComfyUI/status/2114843030364795231).
- Earlier context: [entries-and-gaps.md](entries-and-gaps.md) §1.2–1.4 and §5, [angle-gaps.md](angle-gaps.md), [verified-assessment.md](verified-assessment.md).
