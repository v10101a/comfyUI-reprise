export type Placement = 'overlay'|'behind'|'anchor'|'inworld'|'surface';
export type Preset = 'pop'|'karaoke'|'typewriter'|'hud'|'write'|'none';
/** shadow: 0..1 strength of the dark legibility edge (default 0.5 for behind words, 0 otherwise). */
export type TextStyle = {fontFamily:string;fontWeight:number;fontSize:number;fill:string;stroke?:string|null;strokeWidth?:number|null;letterSpacing?:number|null;align:'left'|'center'|'right';shadow?:number|null;
  /** 'italic' selects the italic face of the family (e.g. Instrument Serif Italic). Absent = upright, unchanged. */
  fontStyle?:'normal'|'italic'|null};
export type Word = {id:string;text:string;start:number;end:number;lineId:string;placement:Placement;preset:Preset;position?:{x:number;y:number}|null;anchor?:{trackId:string;dx:number;dy:number}|null;style?:Partial<TextStyle>|null;shotId?:string|null;surfaceId?:string|null;autoPlace?:boolean|null;hero?:boolean|null;hidden?:boolean|null;
  /** MIDI note block: the word rides on a piano-roll note (e.g. "D4", "bb3"), drawn from its onset; lanes follow the pitch
   *  relative to the line's mean noted pitch. Server stores it as an extra field. Absent = no block. */
  note?:string|null};
export type MediaRef = {path:string;duration:number;width?:number;height?:number;fps?:number;hasAudio?:boolean};
export type GenShot = {id:string;wordIds:string[];start:number;end:number;prompt:string;plate?:string;video?:string;status:'pending'|'running'|'done'|'failed';workflow:string};
export type Point = [number,number];
/** SCHEMA v2 §A. `material` is a web-side addition (deterministic look of the text on the wall). */
export type SurfaceMaterial = 'flat'|'paint'|'neon';
export type Surface = {id:string;label?:string;keyFrame:number;corners:Point[];track?:string|null;status?:'drawn'|'tracking'|'tracked'|'failed';material?:SurfaceMaterial;
  /** Hand-drawn static wall: keep the drawn corners even if a track file exists (server extra field). */
  noTrack?:boolean|null};
export type SurfaceTrack = {fps:number;frames:{f:number;corners:Point[];conf?:number}[]};
export type Occupancy = {fps:number;cols:number;rows:number;step:number;frames:string[]};
export type CropFrame = {f:number;x:number;y:number;w:number;h:number};
export type CropData = {fps:number;aspect:string;frames:CropFrame[]};
export type Aspect = '16:9'|'9:16'|'1:1'|'4:5';
export type Project = {version:1;id:string;name:string;fps:number;width:number;height:number;duration:number;
  media:{video?:MediaRef|null;audio?:MediaRef|null;lyrics?:string|null};
  analysis:{words?:string|null;matte?:string|null;tracks?:string|null;depth?:string|null;occupancy?:string|null;
    /** Fields (TypesetFlowField / TypesetVoiceField): analysis/flow.json, analysis/voice.json. */
    flow?:string|null;voice?:string|null};
  style:TextStyle;words:Word[];shots:GenShot[];
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
  timing?:{leadMs?:number|null;vocalStart?:number|null}|null};
export type LookId = 'default'|'red-glow'|'lens-bound'|'paper-cut'|'ticker'|'flat-card'|'dreamy'|'grey-noise'|'night-code'|'xerox'|'scatter'|'neon'|'graffiti';
export type LookLayout = 'line'|'hero'|'constellation'|'stack';
export type Look = {
  id:LookId;
  font:{hero:string;body:string;heroWeight?:number;bodyWeight?:number;heroCase?:'upper'|'lower'|'as-is';bodyCase?:'upper'|'lower'|'as-is';heroStyle?:'normal'|'italic';bodyStyle?:'normal'|'italic'};
  /** outline: thin text outline colour (width outlineWidth × size); note: MIDI note-block fill (stroke/label use shadow). */
  palette:{text:string;accent:string;shadow?:string;card?:string;outline?:string;note?:string};
  outlineWidth?:number;
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
   *  voice = the vocal stem swells its weight, lifts it with the melody, wobbles it with vibrato. */
  fields?:{motion?:number;voice?:number}|null;
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
export type LineMeta = {hook?:boolean|null;heroWordId?:string|null;hidden?:boolean|null;pinTiming?:boolean|null};
export type Tracks = {fps:number;frames:number;tracks:{id:string;label:string;frames:{f:number;bbox:number[];cx:number;cy:number}[]}[]};
export type Job = {id:string;kind:string;status:'queued'|'running'|'done'|'failed';progress?:number;message?:string;result?:unknown;projectId:string};
export type Layer = 'text'|'composite'|'text-behind'|'text-front';
export type RendererAPI = {ready:Promise<void>;frames:number;renderFrame:(i:number)=>Promise<void>};
declare global {interface Window {__typeset?: RendererAPI}}
