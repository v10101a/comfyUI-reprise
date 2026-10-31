# Kinetic type in footage: references, patterns, and what Typeset should do next

Research for improving the Typeset workflow and making better hero examples (2026-10-31). The user's verdict on the current examples is that they're too *normal*. The concepts are right (text behind the body, text on architecture), but the aesthetics aren't there yet.

Frames for the four user references were pulled at low resolution for analysis only. They stay in the session scratchpad and are **not** committed (copyright).

---

## 1. The four user references, frame by frame

### Hozier, "Eat Your Young" (Keo, kinetic typography)
- **The type is the set.** The letters become platforms that a silhouette runs and climbs across. "PULL UP" turns into a ladder, the scales of justice weigh "THERE'S MONEY" against "TO BE MADE", and a gun and a bomb carry the words "SELLIN'" and "PUTTIN' FOOD ON THE TABLE".
- **Strict palette and a single family**: red, cream and black with a rough, condensed, hand-cut display face, plus paper grain and torn edges.
- **Extreme scale.** Words bleed off the frame ("HOZIER", "WARDRUM"). Some are tiny ("honey" drifts alone on an empty red field), and the jump from tiny to huge creates the rhythm.
- **Words follow paths** ("smell the dinner cooking" runs along an S-curve), and motion-blurred whip transitions link the cards.
- *Lesson:* the meaning of each line becomes one visual metaphor. The animation is simple, but the art direction does the work.

### The Weeknd & Playboi Carti, "Timeless" (official lyric video)
- **Real concert footage with one rule**: every word uses the same heavy condensed sans in saturated red with a soft glow/bloom, over desaturated cyan footage.
- **Hierarchy layout.** Each line has one HERO word (MAIN, SIDE, BANK, FLOCK, DAY, LEGIT) at 30–50% of frame height, and its satellites are tiny and spread out to the corners or the top and bottom. Nothing is a centered caption line.
- **Words live in negative space**: the empty sky, the dark crowd, the area beside the performer. Some sit behind the body.
- **Words drop out completely**, leaving long stretches of footage with no text. Silence makes the next word land harder.
- Stacked vertical lists (EVER / SINCE / I WAS / A …) and an echoed title (TIMELESS ×3, ghosted).
- *Lesson:* the treatment is cheap (one font, one color, glow), but composing against the footage makes it look expensive. **This is the closest to what Typeset can do today.**

### All-American Rejects, "Bite Back" (lyric video)
- **A fixed container.** A hand-drawn mouth outline sits in the same place for the whole video, and the lyrics are written *between the teeth* in cyan handwriting.
- Collage background (scanned paint, halftone, scribbles) that changes under a constant motif, plus occasional breaks (repeated mouths, a smeared red frame).
- *Lesson:* the opposite of slick. A recurring object plus handwriting gives the video an identity, and the handwriting is fine as long as the *container* stays consistent.

### Yeat, "On tha line" (~1:49)
- **The text bends with the lens.** In the fisheye shots, "COULDNT EVEN TELL EM" and "CUZ I DONT KNOW HOW" curve over the car roof following the barrel distortion. The words look as if the same camera filmed them.
- **3D extruded type planted on architecture.** "TURN UP THE BEAT" is a chunky slime-green extruded word on a Paris facade, with a silhouette in front of it. "BLAZING" slams in orange and stacked words collide ("TILL IT'S" squeezed between them). The frame is a CRT/TV-shaped vignette.
- **Optics everywhere**: heavy motion blur, whip pans, datamosh, chromatic aberration, a green rim light traced around the subject's edge, and green light-trail type smeared through the street.
- **Two text registers.** Loud in-world words for hooks and a tiny lowercase green karaoke subtitle at the bottom for verses.
- End card: "YEAT" in liquid iridescent chrome, a generated/3D *material*, not a font.
- *Lesson:* text gets the same camera artifacts as the footage (distortion, blur, smear), so it feels **shot** rather than **overlaid**.

### What all four share (and our examples lack)
| Trait | References | Typeset today |
|---|---|---|
| One art-direction **rule** for the whole piece | always | presets are motion verbs (pop/karaoke/typewriter/HUD), with no look |
| 1 font, 2–3 colors, a texture | always | Inter/Bebas/Anton in clean white |
| **Scale extremes**, with type bleeding off the frame | always | ~8% of frame height, centered lines |
| Hierarchy within a line (hero word + satellites) | Timeless, Hozier, Yeat | all words in a line the same size |
| Text inherits the **camera's optics** | Yeat, Timeless (bloom) | flat vector over the video |
| Text means something visually (metaphor, container) | Hozier, Bite Back | none |
| Silence (sections with no text) | Timeless, Yeat | every word gets a caption |
| Two registers (hook vs. verse) | Yeat, Timeless | one register |

**Diagnosis:** our motion is fine. What's missing is **art direction and composition**. The good news is that these are mostly renderer and layout features, not model features.

---

## 2. Wider reference library

### Music videos and lyric videos
- **Prince, "Sign o' the Times" (1987).** The original kinetic lyric video: words, shapes and color only.
- **Bob Dylan, "Subterranean Homesick Blues" (1965).** Handheld cue cards, with text as a *physical prop* in the shot.
- **Charli XCX, *brat* (2024).** Lowercase blurred Arial Narrow on slime green. Ugly by design, endlessly memed (the brat generator). This one is about **virality**: a look simple enough that anyone can copy it.
- **Bon Iver, *22, A Million* lyric visuals (Eric Timothy Carlson).** Glyphs and symbols mixed with words, so typography becomes a private language.
- **Lyrical Lemonade / Cole Bennett.** Hand-animated doodles and scribbles tracked onto rap footage. Lo-fi, playful, *drawn on the world*. ([Rolling Stone profile](https://www.rollingstone.com/music/features/meet-cole-bennett-soundclouds-favorite-video-director-w486759))
- **Fred again.. visuals.** Diaristic phone footage with typed names, dates and notes-app text. Intimacy through text as *documentation*.
- **Playboi Carti / Opium visuals** (as in Timeless). Glowing red condensed type with heavy bloom, a recognizable house style.

### Film titles (text placed *in the world*)
- **Panic Room (2002, Picture Mill).** Giant 3D credits floating among Manhattan buildings, reflected in office windows, tracked to the plates. This is *the* reference for "text on architecture". ([Art of the Title](https://artofthetitle.com/title/panic-room))
- **North by Northwest (Saul Bass).** The title grid turns into the glass facade of a skyscraper, so text and architecture share one grid.
- **Se7en (Kyle Cooper).** Scratched, jittering, hand-made type on film. Damage as a style.
- **Enter the Void (Gaspar Noé / Tom Kan).** Strobing full-frame type cards in clashing fonts at club tempo, an attack on the eye.
- **Zombieland.** The "rules" are 3D text in the scene that characters crash through and blood splatters on. Text with *collision*.
- **Napoleon Dynamite.** Credits written in ketchup, on food, on objects. Text as *material*.
- **Stranger Than Fiction (MK12)** and **Sherlock (BBC).** HUD and text messages floating next to people and objects, anchored and calm.
- **Scott Pilgrim vs. the World.** Comic-style sound-effect words embedded in the action.

### Art (text on buildings and bodies)
- **Jenny Holzer.** Xenon projections of text on facades, rivers and bodies, and LED tickers. Text as *light*, which suits a night city.
- **Barbara Kruger.** White Futura Bold Oblique on red bars over found photos. Extremely strong and repeatable rules.
- **Lawrence Weiner / Robert Montgomery.** Text as sculpture or as light poems installed in a place.

### Content and social video
- **Hormozi/MrBeast captions** (Submagic, Captions app, CapCut auto-captions): one to three words at a time, a highlighted keyword, center frame. This is now *the default*, which is why it reads as "normal".
- **Text-behind-subject** has been a CapCut template since at least 2025 ([CapCut how-to](https://www.capcut.com/resource/how-to-put-text-behind-a-person-in-capcut), [template](https://www.capcut.com/template-detail/textbehindsubject/7507937836256070973)). The effect alone **isn't novel anymore**. What sets a video apart is *what you do with* the depth.
- **Johnny Harris / Vox explainers.** Text printed on paper, maps and photos, filmed or animated in 3D space. The "physical desk" look.
- **Edit culture** (velocity edits, phonk edits, corecore): flash-frame text, glitch, beat-locked cuts.

### Motion-design studios worth browsing
- **DIA Studio**: kinetic type systems built on variable width/weight stretch.
- **Universal Everything**: generative, figure-based motion.
- **Studio Dumbar**: rule-based identity motion.
- **ManvsMachine and Buck**: 3D type as object.

---

## 3. A map of text↔scene relationships

Use this to pick a *distinct* position for each example instead of three variations on "caption".

**Where the text lives** (less → more integrated):
`screen caption` → `depth-layered (behind subject)` → `body-attached (follows head/hand)` → `on a surface (wall plane)` → `object in the world (extruded, casts shadow, collides)` → `text is the world (Hozier)` → `text as light/material (Holzer projection, chrome, neon smear)`

**What the text inherits from the camera:** nothing (vector) → motion blur → lens distortion (Yeat) → exposure, bloom and grain (Timeless) → scene lighting, shadows and reflections (Panic Room) → generated material.

**Layout logic:** centered line → **hero + satellites** (Timeless) → **constellation in negative space** → **on a path** (arc, body contour, fisheye curve) → **fills a container** (Bite Back mouth) → **full-frame card** (Hozier, Enter the Void).

**Legibility contract:** always readable → readable on the hook only → deliberately broken (bleeding off frame, overlapped, smeared).

Typeset today covers columns 1–4 of "where", column 1 of "inherits", column 1 of "layout", and only the "always readable" contract.

---

## 4. Better hero examples: six stylized directions

Each one has a single **rule**, a **look**, and a feature it showcases. Footage notes refer to the clips already generated for the project (walk at night, dancer, talking close-up).

1. **"Lens-bound"** (Yeat). *Night walk footage.* White heavy grotesk, lowercase green karaoke for verses, and a loud extruded word for hooks. Verse words arc with the lens, the hook word is planted in 3D on the facade with the walker passing in front, and every word gets motion blur matched to the camera's motion plus chromatic aberration.
   *Showcases:* surface tracking + extrusion + optics pass. **Fits Concept A ("Neon Rain") directly**, so this is a style upgrade, not a new concept.
2. **"Red constellation"** (Timeless). *Dancer footage.* One condensed font in red with glow, cyan-graded footage, one hero word per line at 40% of frame height behind the dancer, satellites auto-placed in the emptiest cells, and bars with no text.
   *Showcases:* occupancy auto-placement + behind matte + hierarchy. **Cheapest to build.**
3. **"Type world"** (Hozier). *Any footage with a clean matte.* Replace the background with a flat red, cream and black typographic set and keep the real person as a cutout walking *across* giant letters, with a drop shadow on the letters. Lines become platforms, and the camera pans with the walker.
   *Showcases:* the matte used *creatively* (not just for occlusion). Real human plus graphic world is a striking before/after.
4. **"Holzer facade"** (Holzer + Panic Room). *Wall / architecture footage.* An LED-ticker or xenon-projection look on the tracked wall: text scrolls across the surface, spills light onto the surroundings, and is *projected onto the walker's body* as they cross it (text masked by the matte and displaced by luminance).
   *Showcases:* surface tracking + matte, text as light.
5. **"Container"** (Bite Back + Lyrical Lemonade). *Talking close-up or hands.* A recurring tracked object (mouth, palm, phone screen, fogged window) is the frame, and the lyrics are written into it stroke by stroke in handwriting, with scribble doodles tracked to the head.
   *Showcases:* the anchor track + write-on preset + handwritten fonts.
6. **"brat-mode captions"** (content side). *Talking-head content.* A strong one-color card style, with blur, stretch and a hero word per sentence, that you can switch per project. This is the *viral/meme* angle. The real pitch: "Hormozi captions, but with taste, and they understand the depth of your shot".
   *Showcases:* auto-captioning with a *look* system, and reframe to vertical.

For the demo, **1 + 2 + 3** gives three very different looks from one pipeline. 1 is the hero (it's Concept A), 2 proves the look/hierarchy system, and 3 is the jaw-drop "how did they do that".

---

## 5. What this means for the workflow (ranked for Nov 2)

### P0: a few hours each, biggest visual return
- **`Project.look`: art-direction packs.** Font + palette + texture (paper/grain/halftone) + optics settings + default layout mode. Ship 4–5 looks named after *rules*, not artists, e.g. `red-glow`, `paper-cut`, `lens-bound`, `ticker`, `brat`. Switching the look should restyle the whole project in one click. This is the demo moment.
- **Hierarchy layout.** For each line, pick a hero word (longest content word, or the word on the strongest audio onset, or a manual override) and size it at 0.3–0.6 of frame height, which may bleed off the frame. Satellites at 0.03–0.05 are placed in free occupancy cells away from the hero. Extend `autoPlace` to `layout: 'line' | 'hero' | 'constellation' | 'stack' | 'card'`.
- **Optics pass in the renderer** (all deterministic):
  - Glow/bloom.
  - Grain.
  - Chromatic offset.
  - Motion blur along the anchor's velocity (from tracks/surfaces).
  - Optional match-grade (tint the footage toward the look's palette, as Timeless does with cyan).
- **Expressive OFL fonts.** The current four are all "neutral". Add:
  - **Anybody** or **Big Shoulders Display**: a variable width axis, for stretch animation.
  - **Permanent Marker** or **Rock Salt**: handwriting.
  - **Instrument Serif** or **DM Serif Display**: an editorial serif.
  - **UnifrakturMaguntia**: blackletter.
  - **Silkscreen**: pixel.
  - **Rubik Glitch** or **Rubik Wet Paint**: textured display.

  Verify each license before bundling.
- **Silence.** A per-line `show: false`, plus a look-level rule such as "only show the hooks". Fewer words make the piece read as *edited*.

### P1: about half a day each
- **Text on a path**: an arc, a circle around the head track, or the matte contour (text running along the body's outline).
- **Lens-matched text**: apply a barrel/fisheye warp (one parameter, or estimated from the footage) to the text layer only.
- **Fake extrusion on surfaces**: draw N offset copies along the surface normal, darkened, under the face. This gives a cheap Yeat/Panic Room 3D word with no 3D engine.
- **Card mode**: full-frame flat-color type cards cut on beats (beat grid from librosa or from the existing waveform analysis), interleaved with footage (Hozier / Enter the Void).
- **Write-on preset**: reveal handwriting along the stroke direction (cheap approximation: a left→right wipe with a jittered edge).

### P2: worth it if time allows
- **Background replace → "type world"** (direction 3): matte cutout over a generated or deterministic typographic set, plus a contact shadow.
- **Text as light**: project the text onto the subject (matte-masked, displaced by luminance) and spill it onto the wall (multiply/screen with blur).
- **Generative material end card**: the hook word as chrome, liquid or smoke via the existing `inworld` / MiniMax path (Yeat's ending). This is the right *purposeful* use of generation: one beat, not the whole piece.

### Story for judges
"CapCut can put text behind you. Typeset gives your words a **look**, a **place** and a **camera**: it composes them against your shot, lets them inherit the lens and the light, and restyles the whole video with one click." Show the same footage in three looks, side by side.

---

## 6. Tracking-driven text: more possibilities (added 2026-10-31)

The user asked for more possibilities in the "blob tracking" direction. The common idea: **the computer-vision data is the typography**. Detections, outlines, motion and light decide where the words go and what shape they take.

Seven of these were prototyped as stills on our own footage (Neon Rain walk, dancer chorus) with about 30 lines of OpenCV each. They are shown on the research board. The build spec is in the addendum of `research/kinetic-type-feature-brief.md`.

Status key:
- **matte** = renderer-only with the matte we already compute
- **cv** = a small new OpenCV analysis
- **model** = needs a new model (pose, hands, face mesh, depth)

### Machine-vision / HUD
| Idea | What it looks like | Needs |
|---|---|---|
| **Blob lyrics** *(prototyped)* | Bright or saturated regions (lights, posters, signs) get corner-bracket boxes. The labels are the lyric in reading order instead of coordinates, joined by thin lines. | cv |
| **Motion blobs** *(prototyped)* | Whatever moves gets a box and a word, so the dancer's limbs carry the line. Boxes flash on onsets. | cv |
| **Surveillance tag** | The subject's box carries an ID tag that is the lyric, with a "confidence %" ticking to the beat. | have (tracks) |
| **Lyric graph** | Boxes persist through a line, and connectors build the sentence as a constellation that collapses at the line end. | cv |

This is a strong current trend. TouchDesigner's Blob Track TOP drove the "viral blob tracking" edits ([Derivative tutorial](https://derivative.ca/community-post/tutorial/make-viral-blob-tracking-effect-touchdesigner-free/74680)). A free open-source **AE Blob Tracker** (brightness/colour/motion modes, coordinate labels, Voronoi) shipped in Aug 2026 ([CGWorld](https://cgworld.jp/flashnews/01-202608-AE-BlobTracker.html), [3dart.it](https://www.3dart.it/en/free-blob-tracker-plugin-for-after-effects-motion-design-tracking-tool-2/)). There are also web tools ([effect.app](https://effect.app/effects/blob-tracker), [Framer component](https://www.framer.com/marketplace/components/blob-tracker/)).

**Our twist:** everyone else labels boxes with numbers. We label them with *the lyric, timed to the vocal*. The data becomes the words.

### Silhouette (uses the matte we already have)
| Idea | What it looks like | Needs |
|---|---|---|
| **Contour marquee** *(prototyped)* | The line runs around the body's outline like a ticker, moving one character per beat. | matte (+ contours.json) |
| **Text rain** *(prototyped)* | Letters fall and pile on the head, shoulders and raised arms, then drop when the person moves. This is Camille Utterback & Romy Achituv's [*Text Rain*](https://camilleutterback.com/projects/text-rain/) (1999), where the letters land on anything darker than a threshold. | matte + small sim |
| **Body fill** *(prototyped)* | The person is made of the line, and the background stays photographic. Inverse version: a wall of words with a person-shaped hole. | matte |
| **Glyph-ize / ASCII** *(prototyped)* | The subject is drawn in the song's own letters, with brightness from the footage. Lineage: Vuk Ćosić / Alexei Shulgin ASCII music videos and Yoshi Sodeoka's *ASCII Rock* ([Rhizome](https://rhizome.org/editorial/2003/sep/5/can-you-spell-rock/)). | matte |
| **Echo outlines** *(prototyped)* | Ghost outlines from 6/12/18/24 frames ago, each carrying the word that was sung then. A long exposure of the lyric. | matte (+ contours.json) |
| **Body as eraser / brush** | Words show only where the body has passed (accumulated matte), or the body wipes a wall of words clean. | matte |

### Motion / optical flow
| Idea | What it looks like | Needs |
|---|---|---|
| **Flow-pushed letters** | Letters scatter in the "wind" of a movement and settle back. In TouchDesigner this is optical flow → particlesGPU ([Interactive & Immersive HQ](https://interactiveimmersive.io/blog/touchdesigner-lessons/touchdesigner-gpu-particles/)). | cv (Farneback, low res) |
| **Datamosh words** | On the drop, the hook's pixels are dragged along the motion vectors and smear into the scene. | cv |
| **Slit-scan lyric** | Each text row samples a different moment, so words stretch through time. | renderer |

### Light (made for night footage)
| Idea | What it looks like | Needs |
|---|---|---|
| **Lights speak** | Each lamp, headlight or sign in the frame "emits" one word, with bloom and flare. Same detector as blob lyrics. | cv |
| **Light-trail writing** | The word follows the trajectory of a moving light (a passing car) as a ribbon. | cv (blob ids over time) |
| **Shadow type** | The text casts a skewed, blurred shadow on the ground or wall from a chosen light direction. | renderer |

### Face, hands, pose (new models; MediaPipe nodes exist locally, weights unverified)
| Idea | What it looks like | Needs |
|---|---|---|
| **Mouth emission** | Each word leaves the mouth and drifts away. | model (face landmarks), or approximate it from the head box |
| **Word in hand** | The word sits between the hands and stretches on a variable-width axis as they separate. | model (hands) |
| **Skeleton labels** | Joints are labelled with words, and bones are thin lines (the HUD aesthetic on a body). | model (pose) |
| **Face-mesh text** | The lyric is wrapped onto the face like a mask. Codrops has a MediaPipe face-mesh texture tutorial ([link](https://tympanus.net/codrops/2026/09/06/building-a-real-time-3d-face-mask-with-mediapipe-threlte-and-three-js/)). | model |

### Depth and audio
- **Depth-sliced text:** words sit *between* scene layers, e.g. behind a lamp post but in front of a wall. Uses Depth Anything in ComfyUI. `Project.analysis.depth` is already in the schema.
- **Depth of field:** text defocuses with its depth to match the lens.
- **Loudness → type:** variable-font weight or width follows the RMS of the vocal, and boxes flash on onsets.

### Which to build
The cheapest high-impact four are `fill`, `glyph`, `echo` and `contour`: the matte is already there and each one is an obvious "how did they do that". Next comes **blob lyrics**, the on-trend one with our twist, which needs a small blobs.json job. Text rain is the art-historical crowd-pleaser.
