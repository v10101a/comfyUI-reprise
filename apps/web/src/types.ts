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
  analysis:{words?:string|null;matte?:string|null;tracks?:string|null;depth?:string|null;occupancy?:string|null};
  style:TextStyle;words:Word[];shots:GenShot[];
  surfaces?:Surface[]|null;
  frame?:{aspect:Aspect;source?:{projectId:string}|null;crop?:string|null}|null;
  /** v3: art direction by reference to a preset in looks.ts (absent = v2 behaviour). */
  look?:LookRef|null;
  /** v3: per-line metadata keyed by lineId. */
  lineMeta?:Record<string,LineMeta>|null};
export type LookId = 'default'|'red-glow'|'lens-bound'|'paper-cut'|'ticker'|'flat-card'|'dreamy';
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
  optics:{glow?:number;grain?:number;chroma?:number;motionBlur?:number;lensWarp?:number;blur?:number;extrude?:number;sparkle?:number};
  grade?:{tint:string;amount:number}|null;
  layout:LookLayout;
  quiet?:'none'|'hooks-only';
  /** Which colour the hero word / hook lines take. */
  heroFill?:'text'|'accent';
  /** 'marquee': lines scroll through their box (LED ticker). */
  motion?:'none'|'marquee';
};
export type LookRef = {id:LookId;overrides?:Partial<Omit<Look,'id'>>|null};
export type LineMeta = {hook?:boolean|null;heroWordId?:string|null;hidden?:boolean|null};
export type Tracks = {fps:number;frames:number;tracks:{id:string;label:string;frames:{f:number;bbox:number[];cx:number;cy:number}[]}[]};
export type Job = {id:string;kind:string;status:'queued'|'running'|'done'|'failed';progress?:number;message?:string;result?:unknown;projectId:string};
export type Layer = 'text'|'composite'|'text-behind'|'text-front';
export type RendererAPI = {ready:Promise<void>;frames:number;renderFrame:(i:number)=>Promise<void>};
declare global {interface Window {__typeset?: RendererAPI}}
