import type {ReferenceBoardState} from './studio/board';
export type Placement = 'overlay'|'behind'|'anchor'|'inworld'|'surface';
export type Preset = 'pop'|'karaoke'|'typewriter'|'hud'|'write'|'none';
/** shadow: 0..1 strength of the dark legibility edge (default 0.5 for behind words, 0 otherwise). */
export type TextStyle = {fontFamily:string;fontWeight:number;fontSize:number;fill:string;stroke?:string|null;strokeWidth?:number|null;letterSpacing?:number|null;align:'left'|'center'|'right';shadow?:number|null;
  /** 'italic' selects the italic face of the family (e.g. Instrument Serif Italic). Absent = upright, unchanged. */
  fontStyle?:'normal'|'italic'|null};
/** ink is an explicit word colour override; old style.fill remains the legacy base style. */
export type Word = {ink?:string|null;id:string;text:string;start:number;end:number;lineId:string;placement:Placement;preset:Preset;position?:{x:number;y:number}|null;anchor?:{trackId:string;dx:number;dy:number}|null;style?:Partial<TextStyle>|null;shotId?:string|null;surfaceId?:string|null;autoPlace?:boolean|null;hero?:boolean|null;hidden?:boolean|null;
  /** MIDI note block: the word rides on a piano-roll note (e.g. "D4", "bb3"), drawn from its onset; lanes follow the pitch
   *  relative to the line's mean noted pitch. Server stores it as an extra field. Absent = no block. */
  note?:string|null;
  /** Show the pitch name only after it has been checked against the music. Unverified notes remain visual blocks. */
  noteVerified?:boolean};
export type MediaRef = {path:string;duration:number;width?:number;height?:number;fps?:number;hasAudio?:boolean};
export type GenShot = {id:string;wordIds:string[];start:number;end:number;prompt:string;plate?:string;video?:string;status:'pending'|'running'|'done'|'failed';workflow:string};
export type Point = [number,number];
/** SCHEMA v2 §A. `material` is a web-side addition (deterministic look of the text on the wall). */
export type SurfaceMaterial = 'flat'|'paint'|'neon';
export type Surface = {id:string;label?:string;keyFrame:number;corners:Point[];track?:string|null;status?:'drawn'|'tracking'|'tracked'|'failed';material?:SurfaceMaterial;
  /** Hand-drawn static wall: keep the drawn corners even if a track file exists (server extra field). */
  noTrack?:boolean|null;
  /** Studio move of a tracked wall: its corners in the tracked quad's unit square (TL,TR,BR,BL), so the moved wall
   *  keeps following the track. Absent = the track itself. Baked into corners on re-track. */
  inPlane?:Point[]|null;
  /** Hand keyframes (frame, corners), smoothly interpolated, held before the first and after the last. When present they
   *  replace the track and inPlane. Cleared on re-track. */
  keys?:SurfaceKey[]|null};
export type SurfaceKey = {f:number;corners:Point[]};
export type SurfaceTrack = {fps:number;frames:{f:number;corners:Point[];conf?:number}[]};
export type Occupancy = {fps:number;cols:number;rows:number;step:number;frames:string[]};
export type CropFrame = {f:number;x:number;y:number;w:number;h:number};
export type CropData = {fps:number;aspect:string;frames:CropFrame[]};
export type Aspect = '16:9'|'9:16'|'1:1'|'4:5';
/** Seconds. in/out: song time; offset: project time where `in` plays (may be < 0: the head is cut). */
export type AudioClip = {in:number;out:number;offset:number};
/** Asset bin entry (docs/SCHEMA.md §1 assets): a video or still the layer stack can place. Paths are project-relative. */
export type AssetSource = {kind:'upload'|'comfy'|'workflow';workflowId?:string;promptId?:string;node?:string;filename?:string;subfolder?:string;type?:string;seed?:number;[k:string]:unknown};
export type Asset = {id:string;kind:'video'|'image';path:string;duration?:number;width?:number;height?:number;fps?:number;hasAudio?:boolean;name?:string;source?:AssetSource};
export type LayerBlend = 'normal'|'screen'|'multiply'|'add'|'overlay';
/** x/y: offset in fractions of the frame; scale: × cover-fit size; rotate: degrees. */
export type LayerTransform = {x?:number;y?:number;scale?:number;rotate?:number};
/** Keyframe at t seconds after the layer's start (moves with the clip); absent props keep the static value. */
export type LayerKey = LayerTransform&{t:number;opacity?:number};
/** A layer keeps each workflow's prompt/reference choices when switching workflows or reopening a project. */
export type WorkflowDraft = {inputs?:Record<string,unknown>;sources?:Record<string,string>;variants?:number;
  mediaFiles?:Record<string,{path:string;name:string;duration:number}>;
  postprocess?:{timeScale:number;trimStart:number;fps:number;audio?:string}};
export type LayerGeneration = {workflowId?:string;workflows?:Record<string,WorkflowDraft>};
/** A layer matte is stored in source coordinates/time; editing placement does not require another extraction. */
export type MatteSource = {layerId:string;assetId:string;path:string;kind:'image'|'video';in:number;out:number;width:number;height:number;fps:number};
/** Layer stack entry, bottom→top. plate = media.video (or the generated shot), graded; subject = the plate's matte cutout;
 *  text = where the behind / front lyrics are drawn; media = an asset: plays source [in,out) from project time `start`
 *  (images hold for out−in s). mask: subject/world = only inside / outside the plate's matte (matte 1 = subject).
 *  graded: the footage grade applies (default true). keys: transform/opacity keyframes, smoothly interpolated. */
export type SceneLayer = {id:string;name?:string;hidden?:boolean|null}&(
  {kind:'plate'}|{kind:'subject'}|{kind:'text';which:'behind'|'front'}|
  {kind:'media';assetId:string;start:number;in:number;out:number;transform?:LayerTransform|null;opacity?:number|null;blend?:LayerBlend|null;mask?:'subject'|'world'|null;graded?:boolean|null;keys?:LayerKey[]|null;takes?:string[];generation?:LayerGeneration});
export type MediaLayer = Extract<SceneLayer,{kind:'media'}>;
export type Project = {version:1;id:string;name:string;fps:number;width:number;height:number;duration:number;
  /** Prototype: 'placement' = a line's role only places it; styling comes from the look (renderer lookUnits). Unset = shipped. */
  roleModel?:'placement'|null;
  media:{video?:MediaRef|null;audio?:MediaRef|null;lyrics?:string|null;
    /** Non-destructive song clip (docs/SCHEMA.md): play song [in,out) starting at project time `offset`. Absent = whole song at 0. */
    audioClip?:AudioClip|null};
  analysis:{words?:string|null;matte?:string|null;matteSource?:MatteSource|null;tracks?:string|null;headTracks?:Record<string,string>;depth?:string|null;occupancy?:string|null;
    /** Fields (TypesetFlowField / TypesetVoiceField / TypesetAudioField): analysis/flow.json, analysis/voice.json,
     *  analysis/audio_<job>.json (low-band pulse of the mix). */
    flow?:string|null;voice?:string|null;audio?:string|null};
  style:TextStyle;words:Word[];shots:GenShot[];
  /** Asset bin and layer stack (bottom→top). Absent layers = plate, behind text, subject, front text (renderer DEFAULT_LAYERS). */
  assets?:Asset[]|null;layers?:SceneLayer[]|null;
  /** Spatial reference board; its layout is independent of composition transforms and timing. */
  board?:ReferenceBoardState|null;
  surfaces?:Surface[]|null;
  frame?:{aspect:Aspect;source?:{projectId:string}|null;crop?:string|null}|null;
  /** v3: art direction by reference to a preset in looks.ts (absent = v2 behaviour). Text only. */
  look?:LookRef|null;
  /** v4: footage grade, independent of the look (looks.ts GRADES). Absent = derived from the look as before v4
   *  (load-time migration, so older projects render unchanged); null = ungraded. */
  grade?:GradeRef|null;
  /** v3: per-line metadata keyed by lineId. */
  lineMeta?:Record<string,LineMeta>|null;
  /** Perceived sync: text leads the audio by leadMs (renderer only; word times are never rewritten). Absent = 0. */
  timing?:{leadMs?:number|null;vocalStart?:number|null;
    /** Timeline offset of the original footage/source-time analysis after fitting the edit's leading edge. */
    sceneOffset?:number|null}|null};
export type LookId = 'default'|'red-glow'|'lens-bound'|'paper-cut'|'ticker'|'flat-card'|'dreamy'|'grey-noise'|'night-code'|'xerox'|'scatter'|'neon'|'graffiti'|'hud'|'glyph'|'stitch';
export type LookLayout = 'line'|'hero'|'constellation'|'stack'|'hud';
export type Look = {
  id:LookId;
  font:{hero:string;body:string;heroWeight?:number;bodyWeight?:number;heroCase?:'upper'|'lower'|'title'|'as-is';bodyCase?:'upper'|'lower'|'title'|'as-is';heroStyle?:'normal'|'italic';bodyStyle?:'normal'|'italic'};
  /** outline: thin text outline colour (width outlineWidth × size); note: MIDI note-block fill (stroke/label use shadow). */
  palette:{text:string;accent:string;shadow?:string;card?:string;outline?:string;note?:string};
  outlineWidth?:number;
  /** White glow at each note block's onset, 0..1; absent = 1. */
  noteGlow?:number;
  /** Soft coloured halo (palette.shadow) behind every text unit, 0..1 (otherwise only behind words get one). */
  halo?:number;
  /** 'line' layout verse register: size cap (fraction of min(w,h), default .055); keepPosition: verse lines with an
   *  explicit position and autoPlace:false keep it (and their placement) instead of being auto-placed low. */
  verse?:{max?:number;keepPosition?:boolean};
  texture?:'none'|'grain'|'paper'|'halftone';
  /** Text optics. grain: legacy (pre-v4 composite grain; now Grade.grain) — read only by the migration. */
  optics:{glow?:number;grain?:number;chroma?:number;motionBlur?:number;lensWarp?:number;blur?:number;extrude?:number;sparkle?:number};
  /** Legacy (pre-v4 footage tint; now Grade.tint) — read only by the migration. */
  grade?:{tint:string;amount:number}|null;
  layout:LookLayout;
  quiet?:'none'|'hooks-only';
  /** Which colour the hero word / hook lines take. */
  heroFill?:'text'|'accent';
  /** 'marquee': lines scroll through their box (LED ticker). */
  motion?:'none'|'marquee';
  /** Flat colour card (palette.card) behind every text unit; with marquee it becomes a full-width band. */
  card?:boolean;
  /** 'neon': every text unit (and every wall) is drawn as glowing tubes in its fill colour. */
  finish?:'neon'|null;
  /** Fields that move the type, 0..1 each (absent/0 = off): motion = optical flow pushes and smears it;
   *  voice ("Audio" in the studio) = the song sizes the type. source: 'bass' (default) = the mix's low band
   *  (analysis.audio) pulses it; 'vocal' = the vocal stem's loudness (analysis.voice). Either falls back to the other. */
  fields?:{motion?:number;voice?:number;source?:'bass'|'vocal'}|null;
  /** Pop-in flicker 0..1 (words drop out on seeded frames for half a second after their onset). */
  flicker?:number;
  /** Size multiplier for look-sized text (hero, satellites, stack, hooks, verse cap). Default 1. */
  scale?:number;
  /** Entrance motion amount (pop spring travel/scale, HUD jitter), 0..2. Default 1. */
  intensity?:number;
  /** Legacy footage fields (pre-v4; now Grade.mono / Grade.flash) — read only by the migration.
   *  Photocopy grade on the footage (after grade): luminance with an S-curve (contrast, crush = black point), except
   *  pixels near `keep.hue` (degrees) with saturation ≥ keep.minSat, which keep their colour (one accent survives). */
  mono?:{contrast:number;crush?:number;keep?:{hue:number;width:number;minSat:number}};
  /** Exposure flash on the footage at each beat of analysis/beats.json (downbeats full, other beats × beat). */
  flash?:{amount:number;decay:number;beat?:number};
  /** 'poster': authored paint walls become wheat-pasted photocopy posters (repeated along the wall); flat and neon keep their material. */
  wall?:'poster'|'spray';
  /** Spray paint (wall:'spray'): drips per letter, 0..1 (grow after each word's onset). Default .5. */
  drips?:number;
  /** Neon (finish:'neon'): how much the signs light the scene — wall spill, wet-floor reflection, subject rim/cast. 0..1, default .8. */
  light?:number;
  /** v4.2 entrance/exit of the look's text, replacing the pop preset (absent = authored presets). wipe: cards wipe in
   *  with the words, wipe out; paste: pasted on with a small settle; spray: sprayed on left→right, stays; flicker: tubes
   *  flicker on (× flicker), power off; type: types on (HUD); fade: soft in/out; cut: hard cut. */
  enter?:'wipe'|'paste'|'spray'|'flicker'|'type'|'fade'|'cut';
  /** Wall (surface) text size multiplier; the text may grow past its wall quad. Default 1. */
  wallScale?:number;
  /** Wall text takes the wall's light and texture (shade + surface detail through the ink and cards), 0..1. Default 0. */
  wallBlend?:number;
  /** Entrance / exit length in seconds for every line (0 = none); lines may override (LineMeta.animIn/animOut). Absent = per-entrance default. */
  animIn?:number;animOut?:number;
  /** v4.3 glyph fill: filled lines are drawn as a fixed letter grid lit by the footage under it (the line's text tiled in
   *  reading order; a cell's letter never changes while the line runs; sung words light up, the word being sung takes
   *  the accent). region: subject = inside the matte, in front; world = everything but the subject, behind; frame =
   *  everything, in front. A filled line placed on a wall fills that wall instead (plane space). cell = cell width as a
   *  fraction of min(w,h) (default .014); backing = opacity of the card (palette.card) under the letters (default .85);
   *  gain = luminance gain (default 1.4); hooks = only hook lines fill, others keep the look's register (default true).
   *  Absent/null = off (the look renders as before). */
  fill?:{region:'subject'|'world'|'frame';cell?:number;backing?:number;gain?:number;hooks?:boolean}|null;
  /** v4.4 raster: the look's type (everything in the optics chain; the crisp subtitle register stays type) is drawn as
   *  a fixed screen grid of dots, after lens warp and before glow: a cell lights when the type covers it (soft
   *  threshold, so a drifting edge fades rather than pops) in the type's own colour. shape: square = stitched pixels
   *  (hard 1-bit, whole-pixel geometry), round = LEDs. dot = cell size as a fraction of min(w,h) (default .009); gap = empty fraction of the cell between
   *  dots (default .2). Absent/null = off. */
  raster?:{shape:'square'|'round';dot?:number;gap?:number}|null;
  /** false hides the MIDI note blocks behind noted words (the words keep their pitch stagger). Absent = shown, except
   *  on card looks (the card already boxes the line). */
  noteBlocks?:boolean;
  /** Card padding around the text, × the look's own (default 1). */
  cardPad?:number;
  /** Space between the cards of a wrapped line, × text size; > 0 gives each row its own card (default 0 = one block). */
  cardGap?:number;
};
export type LookRef = {id:LookId;overrides?:Partial<Omit<Look,'id'>>|null};
export type GradeId = 'none'|'mono'|'xerox'|'teal'|'film'|'wash'|'night';
/** Footage treatment (composite only: footage + subject cutout; grain and nothing else also covers the text). */
export type Grade = {
  /** 'color'-blend tint that keeps the footage's luminance, plus a light multiply (amount 0..1). */
  tint?:{color:string;amount:number}|null;
  /** Photocopy tone curve on luminance (contrast, crush = black point); keep: pixels near hue keep their colour. */
  mono?:{contrast:number;crush?:number;keep?:{hue:number;width:number;minSat:number}}|null;
  /** Exposure flash at each beat of analysis/beats.json (downbeats full, other beats × beat). */
  flash?:{amount:number;decay:number;beat?:number}|null;
  /** Seeded film grain over the whole frame (overlay), 0..1. */
  grain?:number;
  /** Warm bloom around highlights, 0..1. */
  halation?:number;
};
export type GradeRef = {id:GradeId;amount?:number|null;overrides?:Partial<Grade>|null};
/** pinTiming: the line keeps its exact times under timing.leadMs (e.g. lines placed on shot cuts). */
/** fill / karaoke / dim: per-line colours that win over the look (text colour, active karaoke word, upcoming karaoke
 *  words drawn at full opacity in that colour). Unset = unchanged rendering. */
/** Saved direction for a generated lettering shot. Exact words come from the selected line/word. */
export type GenerationDraft = {
  lettering?:string;motion?:string;camera?:'locked'|'push'|'pull'|'follow'|'custom';
  scope?:'line'|'word';start?:number;duration?:number;longEdge?:736|1344;seed?:number;
  referenceImage?:string;referenceName?:string;
};
export type LookParamKey='boxes'|'note'|'noteGlow'|'ink'|'accent'|'card'|'cards'|'font'|'body'|'case'|'layout'|'scale'|'motion'|'glow'|'flicker'|'drips'|'light'|'outline'|'halo'|'soft'|'tubes'|'scroll'|'hooks'|'flow'|'voice'|'fill'|'cell'|'backing'|'dots'|'dot'|'gap'|'pad'|'cardGap'|'wall'|'blend'|'in'|'out';
/** Attachment coordinates are relative to the tracked head box, before the clip's transform/crop. */
export type HeadSpot={u:number;v:number};
export type HudPointer={point?:HeadSpot|null;dot?:boolean;connector?:boolean;dotColor?:string|null;connectorColor?:string|null};
export type LineMeta = {
  hud?:HudPointer|null;
  /** Explicit clip appearance. Missing parameters continue to inherit the current Look. */
  appearance?:Partial<Record<LookParamKey,string|number|boolean>>|null;
  generation?:GenerationDraft|null;
  /** Explicit subtitle register; reframe preserves it so shrinking type does not change its look. */
  subtitle?:boolean;hook?:boolean|null;heroWordId?:string|null;hidden?:boolean|null;pinTiming?:boolean|null;fill?:string|null;karaoke?:string|null;dim?:string|null;
  /** Wall text size in the wall's plane (studio corner handles), about the plane centre. Absent = 1. Renderer: multiplies the surface fit. */
  scale?:number|null;
  /** Wall text offset in the wall's plane (studio nudge), fractions of the plane: u right, v down. Absent = centred. */
  u?:number|null;v?:number|null;
  /** Note blocks under this line's words: true = every word (noteless words get an unlabelled block, no pitch stagger),
   *  false = none, absent = words that carry a note, when the look shows blocks (Look.noteBlocks). */
  boxes?:boolean|null;
  /** Entrance / exit length in seconds (0 = none: cut in / cut out). Absent = the look's (Look.animIn/animOut, else its default). */
  animIn?:number|null;animOut?:number|null};
export type Tracks = {fps:number;frames:number;tracks:{id:string;label:string;frames:{f:number;bbox:number[];cx:number;cy:number}[]}[]};
export type Job = {id:string;kind:string;status:'queued'|'running'|'done'|'failed';progress?:number;message?:string;result?:unknown;projectId:string};
export type Layer = 'text'|'composite'|'text-behind'|'text-front';
export type RendererAPI = {ready:Promise<void>;frames:number;renderFrame:(i:number)=>Promise<void>};
declare global {interface Window {__typeset?: RendererAPI}}
