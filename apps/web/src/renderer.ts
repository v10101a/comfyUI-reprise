import type {Project,Word,Tracks,Layer,TextStyle,Occupancy,CropData,CropFrame,SurfaceTrack,Surface,Point,Look,Grade,LineMeta} from './types';
import {assetUrl} from './api';
import {FlowField,drawMotion,type FlowDoc} from './flow';
import {songField,type SongField,type VoiceDoc,type AudioDoc} from './voice';
import {toSong,audibleAt,shiftOf,clipOf} from './audioClip';
import {at as atBase} from './base';
import {OccupancySource,autoPlace,type LineRequest,type LinePlacement,type Placed} from './placement';
import {cropAt,toOut,drawWarped,drawMapped,quadIsConvex,quadSize,squareToQuad,applyH,invertH,keyedOffset,warpSafeMargins} from './geometry';
import {FONTS,lookOf,lineLookOf,lookIsFrozen,gradeOf,wordIsShown,lineIsHook,heroWordId,applyCase,isSubtitleLine,lineIsFilled,fillOf,rasterOf,noteBlocksOn,RASTER_DEFAULTS,colorParts} from './looks';
import {GlyphFill,type FillLine} from './glyph';
import {assetOf,layerSourceTime,layerStateAt,placeLayer,BLEND_OP,image} from './layers';
import {matteLayer,matteTime,mattePoint,matteSignature,matteTracks} from './matte';
import {headSourceAt,sampleHead,headPoint,headSpotPoint} from './heads';
import {hudPointer,relativeHeadSpot} from './hud';
import type {MediaLayer,HeadSpot} from './types';

// Closed form damped step response: no mutable simulation state, stable across seeks.
export function spring(t:number){if(t<=0)return 0;return 1-Math.exp(-12*t)*(Math.cos(18*t)+(12/18)*Math.sin(18*t));}
type TrackPoint = {f:number;bbox:number[];cx:number;cy:number};
export function anchorAt(tracks:Tracks|undefined,id:string,frame:number):TrackPoint|undefined{
  const points=tracks?.tracks.find(track=>track.id===id)?.frames;if(!points)return undefined;
  let lo=0,hi=points.length-1,found=-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(points[mid].f<=frame){found=mid;lo=mid+1;}else hi=mid-1;}
  if(found<0||frame-points[found].f>6)return undefined;
  return points[found];
}
/** Sub-frame anchor (motion blur samples): linear between neighbouring tracked frames; integer frames = anchorAt. */
export function anchorAtT(tracks:Tracks|undefined,id:string,ft:number):TrackPoint|undefined{
  const f0=Math.floor(ft),a=anchorAt(tracks,id,f0);if(!a||ft===f0)return a;
  const b=anchorAt(tracks,id,f0+1);if(!b||b.f!==f0+1||a.f!==f0)return a;const k=ft-f0;
  return {f:a.f,bbox:a.bbox.map((v,i)=>v+(b.bbox[i]-v)*k),cx:a.cx+(b.cx-a.cx)*k,cy:a.cy+(b.cy-a.cy)*k};
}
/** Where a HUD line's head is when the person track has no point near this frame: between tracked frames, linear;
 *  before the first / after the last, held; no track at all → a virtual head in the upper middle (a screen label).
 *  Only used where anchorAt/anchorAtT give nothing, so tracked frames draw exactly as before. */
export type HeadState='tracked'|'held'|'none';
export const VIRTUAL_HEAD:TrackPoint={f:-1,bbox:[.42,.2,.58,.52],cx:.5,cy:.36};
export function headFallback(tracks:Tracks|undefined,id:string,ft:number):{point:TrackPoint;state:HeadState}{
  const pts=tracks?.tracks.find(track=>track.id===id)?.frames;if(!pts?.length)return {point:VIRTUAL_HEAD,state:'none'};
  let lo=0,hi=pts.length-1,found=-1;while(lo<=hi){const mid=(lo+hi)>>1;if(pts[mid].f<=ft){found=mid;lo=mid+1;}else hi=mid-1;}
  const a=found>=0?pts[found]:undefined,b=pts[found+1];
  if(a&&b&&b.f>a.f){const k=(ft-a.f)/(b.f-a.f);return {point:{f:Math.round(ft),bbox:a.bbox.map((v,i)=>v+(b.bbox[i]-v)*k),cx:a.cx+(b.cx-a.cx)*k,cy:a.cy+(b.cy-a.cy)*k},state:'held'};}
  return {point:(a||b)!,state:'held'};
}
/** HUD head at a (fractional, track-fps) frame: the tracked point when there is one, else headFallback. */
export function headAt(tracks:Tracks|undefined,id:string,ft:number,frame=Math.round(ft)):{point:TrackPoint;state:HeadState}{
  const point=anchorAtT(tracks,id,ft);if(point&&anchorAt(tracks,id,frame))return {point,state:'tracked'};return headFallback(tracks,id,ft);
}
/** Surface pose at a frame: tracked corners (hold ≤6 frames), else the static drawn corners. Fractional frames interpolate. */
export function surfaceCornersAt(s:Surface,track:SurfaceTrack|undefined,frame:number):Point[]|undefined{
  if(s.keys?.length){
    // Keyed wall: the base path (the track smoothed over ±6 frames, or the drawn corners) plus the keys' offsets from it,
    // interpolated — one drag moves the wall from there on without fighting the track, and the wobble is gone.
    const base=surfaceBaseAt(s,track,frame);if(!base)return undefined;
    const ks=s.keys.map(k=>({f:k.f,b:surfaceBaseAt(s,track,k.f),c:k.corners})).filter(k=>k.b);
    if(!ks.length)return base;
    const off=keyedOffset(ks.map(k=>k.f),ks.map(k=>k.c.map(([x,y],i)=>[x-k.b![i][0],y-k.b![i][1]] as Point)),frame);
    return base.map(([x,y],i)=>[x+off[i][0],y+off[i][1]] as Point);
  }
  if(!track)return s.corners;
  if(s.inPlane?.length===4){const q=surfaceCornersAt({...s,inPlane:null},track,frame);if(!q)return undefined;const H=squareToQuad(q);return s.inPlane.map(([u,v])=>applyH(H,u,v));}
  const at=(f:number)=>{const fr=track.frames;let lo=0,hi=fr.length-1,found=-1;
    while(lo<=hi){const mid=(lo+hi)>>1;if(fr[mid].f<=f){found=mid;lo=mid+1;}else hi=mid-1;}
    if(found<0||f-fr[found].f>6)return undefined;return fr[found];};
  const f0=Math.floor(frame),a=at(f0);if(!a)return undefined;if(frame===f0)return a.corners;
  const b=at(f0+1);if(!b||b.f!==f0+1||a.f!==f0)return a.corners;const k=frame-f0;
  return a.corners.map(([x,y],i)=>[x+(b.corners[i][0]-x)*k,y+(b.corners[i][1]-y)*k] as Point);
}
/** A keyed wall's base path at `frame`: its track (with any inPlane move) averaged over ±6 frames, else the drawn corners. */
export function surfaceBaseAt(s:Surface,track:SurfaceTrack|undefined,frame:number):Point[]|undefined{
  const raw={...s,keys:null};if(!track)return s.corners;
  const win:Point[][]=[];for(let k=-6;k<=6;k++){const c=surfaceCornersAt(raw,track,frame+k);if(c)win.push(c);}
  if(!win.length)return undefined;return win[0].map((_,i)=>[0,1].map(d=>win.reduce((a,c)=>a+c[i][d],0)/win.length) as Point);
}
/** Deterministic hash → [0,1). */
export function hash01(s:string){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}h^=h>>>13;h=Math.imul(h,0x5bd1e995);h^=h>>>15;return (h>>>0)/4294967296;}

let fontRegistration:Promise<void>|undefined;
export async function loadFonts(){
  // Stage and thumbnail renderers load concurrently. Both must await registration before caching text metrics;
  // a boolean lets the second caller proceed while the first is still downloading the other looks' faces.
  fontRegistration??=Promise.all(FONTS.map(async f=>{try{const face=new FontFace(f.family,`url("${atBase(`/fonts/${encodeURIComponent(f.file)}`)}")`,{weight:f.weight,style:f.style||'normal'});await face.load();document.fonts.add(face);}catch{/* keep going: CSS may already provide it */}})).then(()=>{});
  await fontRegistration;
  await Promise.all(['700 24px Inter','800 24px Inter','900 24px Inter','500 24px Inter','400 24px "Space Mono"','700 24px "Space Mono"','400 24px Anton','400 24px "Bebas Neue"'].map(font=>document.fonts.load(font)));await document.fonts.ready;
}
/** Studio preview proxy for a project video, from its project path or served URL: …/media/<name>.<ext> -> …/media/proxy/<name>.mp4
 *  (server/app/media.py proxy_rel). Anything without a media/ segment (sample fixtures, blob:) comes back unchanged. */
export function proxyPath(videoPath:string){return videoPath.replace(/(^|\/)media\/(?!proxy\/)([^/?#]+)$/,(_m,pre:string,name:string)=>`${pre}media/proxy/${name.replace(/\.[^.]+$/,'')}.mp4`);}
/** Full-size short-GOP studio copy (paused frames): …/media/<name>.<ext> -> …/media/proxy/<name>.full.mp4 (media.py seek_rel). */
export function seekPath(videoPath:string){const p=proxyPath(videoPath);return p===videoPath?p:p.replace(/\.mp4$/,'.full.mp4');}
function video(src:string):Promise<HTMLVideoElement>{return new Promise((resolve,reject)=>{const v=document.createElement('video');v.crossOrigin='anonymous';v.preload='auto';v.muted=true;v.playsInline=true;v.onloadeddata=()=>resolve(v);v.onerror=()=>reject(new Error(`Cannot load media: ${src}`));v.src=src;v.load();});}
/** Seek and wait until the frame at t is actually decoded and drawable. 'seeked' alone can fire while the
 *  previous frame is still the one drawImage paints, and the mp4 and the VP9-alpha matte lag by different amounts,
 *  so the cutout drifts off the person and text bleeds over them. requestVideoFrameCallback fires once the new
 *  frame is presented (short fallback where it never fires). */
export async function seek(v:HTMLVideoElement,t:number){
  const at=Math.min(Math.max(0,t),Math.max(0,v.duration-0.001));
  if(Math.abs(v.currentTime-at)<0.00001&&v.readyState>=2)return;
  const rvfc=(v as HTMLVideoElement&{requestVideoFrameCallback?:(cb:()=>void)=>number}).requestVideoFrameCallback?.bind(v);
  const presented=rvfc?new Promise<void>(resolve=>{rvfc(()=>resolve());setTimeout(resolve,250);}):Promise.resolve();
  await new Promise<void>((resolve,reject)=>{const timer=setTimeout(()=>{cleanup();reject(new Error('Video seek timed out'));},15000);const cleanup=()=>{clearTimeout(timer);v.removeEventListener('seeked',done);v.removeEventListener('error',error);};const done=()=>{cleanup();resolve();};const error=()=>{cleanup();reject(new Error('Video seek failed'));};v.addEventListener('seeked',done);v.addEventListener('error',error);v.currentTime=at;});
  await presented;
}
/** Sequential decode for exports (#/render?decode=seq). Seeking re-decodes from the last keyframe for every frame
 *  (~0.3-0.6 s on long-GOP footage and mattes); for the next few frames this plays forward instead and pauses on the
 *  presented frame, so the decoder never restarts. Same decoder, same frames as seek(): the target is the frame whose
 *  pts is floor(t*fps)/fps, exactly what seek(v,(f+.5)/fps) shows. Anything unexpected (no rVFC, overshoot, timeout,
 *  a jump back or far ahead) falls back to seek(). */
const SEQ_AHEAD=8;
/** Playback rate while advancing; overshoot (a frame presented past the target) falls back to seek. */
export const seqConfig={rate:1};
/** Counters for the export gate: frames reached by playing forward vs by seek fallback. */
export const seqStats={played:0,seeked:0,overshoot:0,timeout:0};
const seqAt=new WeakMap<HTMLVideoElement,number>();
export async function advance(v:HTMLVideoElement,t:number,fps:number){
  const at=Math.min(Math.max(0,t),Math.max(0,v.duration-0.001));const want=Math.floor(at*fps+1e-6);
  const have=seqAt.get(v);
  const rvfc=(v as HTMLVideoElement&{requestVideoFrameCallback?:(cb:(now:number,m:{mediaTime:number})=>void)=>number}).requestVideoFrameCallback?.bind(v);
  if(have===want&&v.paused)return;
  if(!rvfc||have===undefined||want<=have||want-have>SEQ_AHEAD||!v.paused){seqStats.seeked++;seqAt.delete(v);await seek(v,at);seqAt.set(v,want);return;}
  const ok=await new Promise<boolean>(resolve=>{
    let done=false,callback=0;
    const finish=(ok:boolean)=>{if(done)return;done=true;clearTimeout(timer);v.cancelVideoFrameCallback?.(callback);v.pause();resolve(ok);};
    const timer=setTimeout(()=>{seqStats.timeout++;finish(false);},4000);
    const onFrame=(_now:number,m:{mediaTime:number})=>{if(done)return;const k=Math.round(m.mediaTime*fps);
      if(k<want){callback=rvfc(onFrame);return;}if(k!==want)seqStats.overshoot++;finish(k===want);};
    callback=rvfc(onFrame);v.playbackRate=seqConfig.rate;void v.play().catch(()=>finish(false));
  });
  if(ok)seqStats.played++;else{seqStats.seeked++;seqAt.delete(v);await seek(v,at);}
  seqAt.set(v,want);
}
async function json<T>(url:string):Promise<T|undefined>{try{const r=await fetch(url);if(!r.ok)return undefined;return await r.json() as T;}catch{return undefined;}}

/** CSS font shorthand; an italic prefix only when fontStyle is 'italic' (so upright text keeps the exact v2 string). */
function fontOf(s:TextStyle,px:number){return `${s.fontStyle==='italic'?'italic ':''}${s.fontWeight} ${px}px "${s.fontFamily}"`;}
function setFont(ctx:CanvasRenderingContext2D,s:TextStyle,h:number){ctx.font=fontOf(s,s.fontSize*h);ctx.textBaseline='middle';ctx.textAlign='left';}
function measure(ctx:CanvasRenderingContext2D,text:string,spacing:number){return ctx.measureText(text).width+Math.max(0,[...text].length-1)*spacing;}

type Metric = {w:Word;text:string;style:TextStyle;spacing:number;width:number;gap:number;size:number};
type Row = {metrics:Metric[];width:number};
type Role = 'line'|'hook'|'verse'|'hero'|'sat'|'stack'|'surface'|'hud';
/** A drawable unit. Without a look, one unit = one line (words sharing lineId+placement), exactly as in v2.
 *  Under a look's layout a line can split into a hero unit and satellite units. total = widest row. */
type Line = {/** Extra space between rows (card looks: Look.cardGap), unit px; rows then get one card each. */rowGap?:number;sub?:boolean;key:string;lineId:string;role:Role;words:Word[];placement:Word['placement'];start:number;end:number;metrics:Metric[];rows:Row[];total:number;size:number;height:number;
  bleed?:boolean;auto?:boolean;req?:Partial<LineRequest>;card?:boolean;
  /** HUD layout: stacking slot (0 = top label: leader + readout; others: bracket only). */
  hudSlot?:number;
  /** HUD layout: offset of this slot below slot 0 (fraction of frame height; the stack is clamped as one). */
  hudOff?:number;
  /** Entrance / exit length, s (0 = none); undefined = the entrance's default (see animOf in looks.ts). */
  ain?:number;aout?:number};
const ROW=1.04;
/** Row pitch of a line: ROW × size plus the card gap. */
const pitch=(l:{size:number;rowGap?:number})=>l.size*ROW+(l.rowGap||0);

/** HUD labels are never smaller than this fraction of frame height (proof A: the tiny tag was unreadable). */
const HUD_MIN=.05;
function styleOf(p:Project,w:Word):TextStyle{
  const s={...p.style,...(w.style||{}),...(w.ink?{fill:w.ink}:{})} as TextStyle;
  for(const k of Object.keys(s) as (keyof TextStyle)[])if(s[k]===null)delete s[k];
  if(w.preset==='hud'&&s.fontSize<HUD_MIN)s.fontSize=HUD_MIN;
  return s;
}
/** Relative luminance of #rrggbb / #rrggbbaa (0..1; alpha ignored). */
function lum(hex:string){const m=/^#?([0-9a-f]{6})(?:[0-9a-f]{2})?$/i.exec(hex);if(!m)return 1;const n=parseInt(m[1],16);return (.2126*(n>>16&255)+.7152*(n>>8&255)+.0722*(n&255))/255;}
/** Preserve the chosen colours, including saturated blue/red and alpha. Brightness must not replace an edit with white. */
function hudInk(look:Look){return look.palette.text;}
function hudLine(look:Look){return look.palette.accent;}
const DEFAULT_WEIGHT:Record<string,number>={Inter:800,'Archivo Narrow':500,'Big Shoulders Display':900,'Space Mono':700};
/** Look styling: the look owns typeface, weight, colour, case and spacing; per-word size/alignment still apply. */
function lookStyle(p:Project,w:Word,look:Look,role:Role,size?:number):{style:TextStyle;text:string}{
  const s=styleOf(p,w);
  const mf=w.ink??p.lineMeta?.[w.lineId]?.fill;
  if(role==='hud'){const family=p.lineMeta?.[w.lineId]?.appearance?.font;
    return {style:{...s,...(family?{fontFamily:String(family),fontWeight:DEFAULT_WEIGHT[String(family)]??400}:{}),fill:mf??hudInk(look)},text:p.lineMeta?.[w.lineId]?.appearance?.case?applyCase(w.text,look.font.heroCase):w.text};}
  const heroish=role==='hero'||role==='hook'||role==='surface'||role==='stack';
  const family=heroish?look.font.hero:look.font.body;
  const weight=(heroish?look.font.heroWeight:look.font.bodyWeight)??DEFAULT_WEIGHT[family]??400;
  const fill=mf??(heroish?(look.heroFill==='accent'?look.palette.accent:look.palette.text):look.layout==='line'?look.palette.accent:look.palette.text);
  const italic=(heroish?look.font.heroStyle:look.font.bodyStyle)==='italic';const outline=look.palette.outline??(look.outlineWidth?look.palette.shadow??'#000000':undefined);
  const style:TextStyle={...s,fontFamily:family,fontWeight:weight,fill,stroke:outline??null,strokeWidth:outline?look.outlineWidth??.05:null,letterSpacing:family==='Silkscreen'?.04:-.01,shadow:null};
  if(italic)style.fontStyle='italic';else delete style.fontStyle;
  if(size!==undefined)style.fontSize=size;else if(look.scale!=null&&role!=='surface')style.fontSize*=look.scale;
  return {style,text:applyCase(w.text,heroish?look.font.heroCase:look.font.bodyCase)};
}
function buildUnit(ctx:CanvasRenderingContext2D,p:Project,key:string,lineId:string,role:Role,words:Word[],styler:(w:Word)=>{style:TextStyle;text:string},opts:{wrap?:'auto'|'never'|'each';placement?:Word['placement']}={}):Line{
  const metrics:Metric[]=words.map(w=>{const {style,text}=styler(w);setFont(ctx,style,p.height);const size=style.fontSize*p.height;const spacing=(style.letterSpacing||0)*size;return {w,text,style,spacing,width:measure(ctx,text,spacing),gap:size*.26,size};});
  const rowWidth=(ms:Metric[])=>ms.reduce((n,m,i)=>n+m.width+(i<ms.length-1?m.gap:0),0);
  const maxW=p.width*.88;let rows:Row[]=[{metrics,width:rowWidth(metrics)}];
  const placement=opts.placement||words[0].placement;
  if(opts.wrap==='each')rows=metrics.map(m=>({metrics:[m],width:m.width}));
  // Wrap when one row would have to shrink a lot: below 45% in landscape (titles stay on one line), 85% in portrait (stack).
  else if(opts.wrap!=='never'&&rows[0].width*(p.height>p.width?.85:.45)>maxW&&metrics.length>1&&placement!=='surface'){
    rows=[];let cur:Metric[]=[];
    for(const m of metrics){if(cur.length&&rowWidth([...cur,m])>maxW){rows.push({metrics:cur,width:rowWidth(cur)});cur=[];}cur.push(m);}
    if(cur.length)rows.push({metrics:cur,width:rowWidth(cur)});
  }
  const size=Math.max(...metrics.map(m=>m.size));
  return {key,lineId,role,words,placement,start:Math.min(...words.map(w=>w.start)),end:Math.max(...words.map(w=>w.end)),metrics,rows,total:Math.max(...rows.map(r=>r.width)),size,height:size*(1+(rows.length-1)*ROW)};
}
function groupWords(p:Project,filter:(w:Word)=>boolean){
  const groups=new Map<string,Word[]>();
  for(const w of p.words){if(w.placement==='inworld'||!filter(w))continue;const key=`${w.lineId}:${w.placement}`;const g=groups.get(key);if(g)g.push(w);else groups.set(key,[w]);}
  return groups;
}
/** v2 lines (no look). Kept exported for reframe.ts. */
export function lines(ctx:CanvasRenderingContext2D,p:Project):Line[]{
  return [...groupWords(p,w=>!w.hidden&&!p.lineMeta?.[w.lineId]?.hidden).entries()].map(([key,words])=>buildUnit(ctx,p,key,words[0].lineId,'line',words,w=>{const mf=w.ink??p.lineMeta?.[w.lineId]?.fill;return {style:mf?{...styleOf(p,w),fill:mf}:styleOf(p,w),text:w.text};}));
}
/** Units under a look: styling, quiet, and the layout split (hero/satellites, constellation, stack). */
function lookUnits(ctx:CanvasRenderingContext2D,p:Project,baseLook:Look,hasMatte:boolean):Line[]{
  // Prototype role model (Project.roleModel 'placement'): the role only places the line (front / behind / head / wall);
  // all styling comes from the look. Unset = the shipped behaviour, byte-identical.
  const pm=p.roleModel==='placement';const keepPl=(pl:Word['placement'])=>pm&&(pl==='overlay'||pl==='behind')?pl:undefined;
  const out:Line[]=[];const minDim=Math.min(p.width,p.height)/p.height;// font sizes are fractions of height
  const groups=[...groupWords(p,w=>wordIsShown(p,w)).entries()];
  // Hero layout shows one line at a time: a line yields when the next text line starts (no hero pile-ups).
  const starts=[...new Set(groups.filter(([,ws])=>(ws[0].placement==='behind'||ws[0].placement==='overlay')&&!isSubtitleLine(p,ws[0].lineId)).map(([,ws])=>Math.min(...ws.map(w=>w.start))))].sort((a,b)=>a-b);
  const yieldAt=(start:number)=>starts.find(s=>s>start+1e-6)??Infinity;
  const hudSlots:number[]=[];// end time per slot (-Infinity = free)
  if(baseLook.layout==='hud')groups.sort((a,b)=>Math.min(...a[1].map(w=>w.start))-Math.min(...b[1].map(w=>w.start)));
  for(const [key,raw] of groups){
    const look=lineLookOf(p,raw[0].lineId)??baseLook;const sc=look.scale??1,card=!!look.card;
    // Studio size for lines whose layout sets the size (looks.ts lineSizeMode 'scale'): lineMeta.scale (absent = 1).
    const lm=p.lineMeta?.[raw[0].lineId]?.scale??1,ls=sc*lm;
    // Subtitle/karaoke register keeps its authored placement, size and alignment under every look:
    // mono (unless the word names a family) in the palette's text colour; the active karaoke word takes the accent.
    if(isSubtitleLine(p,raw[0].lineId)){
      const family=p.lineMeta?.[raw[0].lineId]?.appearance?.font;
      const u=buildUnit(ctx,p,key,raw[0].lineId,'line',raw,w=>({style:{...styleOf(p,w),fontFamily:family?String(family):w.style?.fontFamily??'Space Mono',fontWeight:family?(DEFAULT_WEIGHT[String(family)]??400):w.style?.fontWeight??700,fill:w.ink??p.lineMeta?.[w.lineId]?.fill??(lum(look.palette.text)>.25?look.palette.text:hudLine(look)),stroke:null,strokeWidth:null,shadow:null,letterSpacing:w.style?.letterSpacing??0},text:p.lineMeta?.[w.lineId]?.appearance?.case?applyCase(w.text,look.font.bodyCase):w.text}));u.sub=true;out.push(u);continue;
    }
    // v4.3 glyph fill: a filled line is drawn as a letter grid (renderer drawFill), never as type.
    if(lineIsFilled(p,raw[0].lineId))continue;
    // HUD layout: every line becomes a head-locked HUD label (anchored to person0, bracket + leader + readout).
    // Lines alive at the same time stack downward in slots so labels never overlap.
    if(look.layout==='hud'){
      const start=Math.min(...raw.map(w=>w.start)),end=Math.max(...raw.map(w=>w.end));
      // Lowest free slot (a line never lands on a slot still in use), slots spaced by the real label box + a gap.
      let slot=hudSlots.findIndex(e=>e<=start+1e-6);if(slot<0)slot=hudSlots.length;hudSlots[slot]=end;
      const ws=raw.map(w=>({...w,placement:'anchor' as const,preset:'hud' as const,anchor:w.anchor??{trackId:'person0',dx:.24,dy:-.15},
        text:applyCase(w.text,look.font.heroCase),style:{...(w.style||{}),fontFamily:look.font.hero,fontWeight:look.font.heroWeight??500,fontSize:.05*ls,align:'left' as const}}));
      const u=buildUnit(ctx,p,`${key}:hud`,raw[0].lineId,'hud',ws,w=>lookStyle(p,w,look,'hud'));u.hudSlot=slot;
      if(!raw[0].anchor)u.hudOff=slot*(u.size*(1+.36+.3))/p.height;out.push(u);continue;
    }
    // Layouts that size words individually split multi-token words ("than the radio") into tokens sharing the timing.
    const split=look.layout!=='line'&&(raw[0].placement==='behind'||raw[0].placement==='overlay');
    const words=split?raw.flatMap(w=>{const toks=w.text.split(/\s+/).filter(Boolean);return toks.length<2?[w]:toks.map((tk,i)=>({...w,id:`${w.id}~${i}`,text:tk,hero:w.hero&&i===0?w.hero:null}));}):raw;
    const lineId=words[0].lineId;const placement=words[0].placement;
    if(placement==='anchor'){const u=buildUnit(ctx,p,key,lineId,'hud',words,w=>lookStyle(p,w,look,pm?'hook':w.preset==='hud'?'hud':'verse'));if(pm)u.card=card;out.push(u);continue;}
    if(placement==='surface'){
      // Neon walls take the accent (a tube colour, not body ink); a carded look puts its card on the wall too.
      const neon=p.surfaces?.find(x=>x.id===words[0].surfaceId)?.material==='neon';
      const u=buildUnit(ctx,p,key,lineId,'surface',words,w=>{const r=lookStyle(p,w,look,'surface');return neon?{...r,style:{...r.style,fill:w.ink??p.lineMeta?.[w.lineId]?.fill??look.palette.accent}}:r;});
      u.card=card;out.push(u);continue;}
    const hook=lineIsHook(p,lineId);
    // Flat Card is a title treatment; ordinary lines should not collapse into the small verse register.
    if(look.id==='flat-card'){
      const authored=words[0].autoPlace===false&&!!words[0].position;
      const placed=words.map(w=>({...w,position:authored?w.position:{x:.5,y:.5},autoPlace:false}));
      // Hooks keep their authored size exactly as before (× lineMeta.scale when set); other lines get the title minimum.
      // Stack layout: one card per word, stacked (Look.cardGap spaces them).
      const wrap=look.layout==='stack'?{wrap:'each' as const}:{};
      const u=hook?buildUnit(ctx,p,key,lineId,'hook',words,w=>lookStyle(p,w,look,'hook',lm!==1?styleOf(p,w).fontSize*sc*lm:undefined),wrap)
        :buildUnit(ctx,p,key,lineId,'hook',placed,w=>lookStyle(p,w,look,'hook',Math.max(styleOf(p,w).fontSize,.16*minDim)*ls),wrap);
      u.card=card;out.push(u);continue;
    }
    if(look.layout==='hero'){
      const heroId=heroWordId({...p,words:[...p.words.filter(w=>w.lineId!==lineId),...words]},lineId);const hero=words.find(w=>w.id===heroId)||words[0];
      const end=Math.min(Math.max(...words.map(w=>w.end)),yieldAt(Math.min(...words.map(w=>w.start))));
      // Hero: 0.30–0.60 of min(width,height); shrink until ≥60% of the word stays in frame (bleed allowed).
      let size=.45*minDim*ls;const probe=buildUnit(ctx,p,'probe',lineId,'hero',[hero],w=>lookStyle(p,w,look,'hero',size),{wrap:'never'});
      const maxW=p.width/.62;if(probe.total>maxW)size*=maxW/probe.total;
      const u=buildUnit(ctx,p,`${key}:hero`,lineId,'hero',[hero],w=>lookStyle(p,w,look,'hero',size),{wrap:'never',placement:keepPl(placement)??(hasMatte?'behind':'overlay')});
      u.end=end;u.bleed=true;u.auto=true;u.card=card;u.req={tolerance:.55,noShrink:true,canPromote:false,hint:{x:.5,y:p.height>p.width?.42:.5}};out.push(u);
      for(const w of words)if(w!==hero){
        const s=buildUnit(ctx,p,`${key}:sat:${w.id}`,lineId,'sat',[w],x=>lookStyle(p,x,look,'sat',.048*minDim*ls),{wrap:'never',placement:keepPl(placement)??'overlay'});
        s.auto=true;s.card=card;s.start=u.start;s.end=u.end;s.req={tolerance:.01,strict:true,canPromote:false,avoidKey:u.key,avoidR:u.height/p.height*1.05};out.push(s);
      }
      continue;
    }
    if(look.layout==='constellation'){
      for(const w of words){const s=buildUnit(ctx,p,`${key}:c:${w.id}`,lineId,'sat',[w],x=>lookStyle(p,x,look,'sat',.05*minDim*ls),{wrap:'never',placement:keepPl(placement)??'overlay'});
        s.auto=true;s.card=card;s.start=Math.min(...words.map(x=>x.start));s.end=Math.max(...words.map(x=>x.end));s.req={tolerance:.01,strict:true,canPromote:false};out.push(s);}
      continue;
    }
    if(look.layout==='stack'){
      const st=buildUnit(ctx,p,`${key}:stack`,lineId,'stack',words,w=>({...lookStyle(p,w,look,'stack',.085*minDim*ls),style:{...lookStyle(p,w,look,'stack',.085*minDim*ls).style,align:'left'}}),{wrap:'each',placement:keepPl(placement)??'overlay'});
      st.auto=true;st.card=card;st.req={tolerance:.02,corner:true,canPromote:false};out.push(st);continue;
    }
    // 'line' layout: two registers. Hooks keep their authored size/placement in the hero face; verses become
    // a small lowercase subtitle register in the accent colour, low in frame and in front.
    if(hook){const u=buildUnit(ctx,p,key,lineId,'hook',words,w=>lookStyle(p,w,look,'hook'));u.card=card;out.push(u);}
    else{const keep=!!look.verse?.keepPosition&&words.every(w=>w.position&&w.autoPlace===false);const cap=(look.verse?.max??.055)*minDim;
      const u=buildUnit(ctx,p,`${key}:verse`,lineId,'verse',words,w=>lookStyle(p,w,look,'verse',(sc===1?Math.min(styleOf(p,w).fontSize,cap):Math.min(styleOf(p,w).fontSize*sc,cap*sc))*lm),{placement:keep||pm?undefined:'overlay'});
      if(!keep){u.auto=true;u.req={tolerance:.02,hint:{x:.5,y:.84},canPromote:false};}u.card=card;out.push(u);}
  }
  // Neon signs and spray paint belong to the scene: every screen unit (not subtitles / HUD) sits behind the subject.
  if((baseLook.finish==='neon'||baseLook.wall==='spray')&&!pm)for(const u of out)if(!u.sub&&u.role!=='hud'&&(u.placement==='overlay'||u.placement==='behind')){u.placement='behind';u.req={...(u.req||{}),canPromote:false};}
  // Card gap: wrapped carded lines split into one card per row, Look.cardGap × size apart edge to edge (a row's card is
  // size + 2 × pad × .75, drawCard's screen padY).
  for(const u of out){const l=u.card&&u.rows.length>1?lineLookOf(p,u.lineId):undefined;const g=l?.cardGap??0;
    if(g>0){u.rowGap=(g+Math.max(0,.48*(l?.cardPad??1)-(ROW-1)))*u.size;u.height+=(u.rows.length-1)*u.rowGap;}}
  return out;
}
/** Auto-placement is on for behind lines unless turned off (position, if any, becomes the preferred spot), and for overlay lines without a position. */
export function isAutoPlaced(w:Word){
  if(w.placement!=='behind'&&w.placement!=='overlay')return false;
  if(w.autoPlace!=null)return w.autoPlace;
  return w.placement==='behind'||!w.position;
}

type DrawOpts = {shadow:number;plain?:boolean;shadowColor?:string;hard?:boolean;karaoke?:string;scroll?:number;
  /** MIDI note blocks (Word.note) colours; sparkle: 0..1 twinkles around the words from their onset. */
  /** Note block style; null = blocks hidden (Look.noteBlocks false). */
  note?:{fill:string;stroke:string;glow?:number}|null;sparkle?:number;
  /** Look entrance-motion amount (pop travel/scale, HUD jitter); undefined/1 = as authored. */
  motion?:number;
  /** Pop-in flicker 0..1: for half a second after its onset a word drops out on seeded frames (neon catching). */
  flicker?:number;
  /** Per-line colours (LineMeta.fill/karaoke/dim), keyed by lineId. */
  meta?:Record<string,LineMeta>;
  /** Voice field: the singer's loudness/pitch/vibrato move each word (look.fields.voice > 0). */
  voice?:{field:SongField;amount:number;
    /** Song clip shift (media.audioClip offset − in): the field is in song time, words in project time. */
    shift?:number};
  /** Look entrance/exit (Look.enter); replaces the pop preset. undefined = authored presets. */
  enter?:Look['enter'];
  /** Clean glyph edges (every look but the frozen hidden ones): all halos, then all outlines, then all fills, so a
   *  letter's outline/halo never cuts into its neighbour; halo blur follows the type's scale; the voice changes weight
   *  only on variable faces (a static face would jump to synthetic bold). */
  clean?:boolean;
  /** Fibres in local glyph coordinates: opaque cut paper, rather than holes punched through painted text. */
  paper?:boolean;
  /** Prototype role model: HUD-role words take the look's entrance (no HUD jitter / type-on of their own). */
  roles?:boolean};
const clamp01=(u:number)=>Math.min(1,Math.max(0,u));
const easeOut=(u:number)=>1-(1-clamp01(u))**3;
const easeInOut=(u:number)=>{u=clamp01(u);return u*u*(3-2*u);};
/** #rgb / #rrggbb / #rrggbbaa → rgba() with alpha a (× the colour's own alpha; other CSS colours are returned unchanged). */
function withAlpha(c:string,a:number){const m=/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(c);if(!m)return c;const h=m[1].length===3?[...m[1]].map(x=>x+x).join(''):m[1];
  if(h.length===8)a*=parseInt(h.slice(6),16)/255;const n=parseInt(h.slice(0,6),16);return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`;}
/** Look exits run in the last EXIT seconds of a line; only lines that last ≥ 1 s get one. 0 → 1. */
const EXIT=.24;
function exitK(line:Line,t:number){
  const d=line.aout;if(d===undefined)return line.end-line.start>=1?easeInOut((t-(line.end-EXIT))/EXIT):0;
  if(d<=0)return 0;const dd=Math.min(d,(line.end-line.start)*.5);return easeInOut((t-(line.end-dd))/dd);
}
/** Entrance progress over d s (the line's In when set, else `base`); In 0 = cut in. */
const inLen=(line:Line,base:number)=>line.ain??base;
const prog=(local:number,d:number)=>d>0?local/d:local>=0?1:-1;
/** 'wipe' entrance: each word wipes in over WIPE s from its onset; the card grows with it (left → right per row). */
const WIPE=.26;
type Wipe={rows:{edge:number;y0:number;y1:number}[];left:number;right:number;out:number;done:boolean};
/** Wipe geometry in unit coordinates: per row the revealed right edge, the card's row band (padY above/below the
 *  first/last row), and the exit's left edge. done = fully shown (draw the plain card). */
function wipeState(line:Line,t:number,padY:number,k=1):Wipe{
  const pad=line.size*.32*k,al=line.metrics[0].style.align,x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
  const L=x0-pad,R=x0+line.total+pad,n=line.rows.length;let done=true;
  const rows=line.rows.map((row,r)=>{const y=(r-(n-1)/2)*pitch(line);let x=-(al==='center'?row.width/2:al==='right'?row.width:0);let prev=L,edge=L;
    row.metrics.forEach((m,i)=>{const next=i===row.metrics.length-1?R:x+m.width+m.gap*.5;const u=prog(t-m.w.start,inLen(line,WIPE));
      if(u<1)done=false;if(u>0)edge=Math.max(edge,prev+(next-prev)*easeOut(u));prev=next;x+=m.width+m.gap;});
    return {edge,y0:r===0?-line.height/2-padY:y-pitch(line)/2,y1:r===n-1?line.height/2+padY:y+pitch(line)/2};});
  const out=L+(R-L)*exitK(line,t);
  return {rows,left:L,right:R,out,done:done&&out<=L};
}
/** The look entrance replaces pop: only lines with pop words wipe (authored 'none' etc. keep their hard cut). */
const popLine=(line:Line)=>line.role!=='hud'&&line.words.some(w=>w.preset==='pop');
/** A unit's flat card (palette.card), padY = vertical pad as a fraction of the horizontal pad, k = Look.cardPad.
 *  'wipe' grows it with the words and wipes it out at the end of the line. */
function drawCard(o:CanvasRenderingContext2D,line:Line,t:number,color:string,padY:number,enter?:Look['enter'],k=1){
  const pad=line.size*.32*k;const al=line.metrics[0].style.align;const x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
  o.fillStyle=color;
  const w=enter==='wipe'&&popLine(line)?wipeState(line,t,pad*padY,k):undefined;
  if(line.rowGap){
    // One card per row, hugging the row; the wipe clips each to its revealed span.
    const n=line.rows.length;const a=w&&!w.done?Math.max(w.left,w.out):-Infinity;o.beginPath();
    line.rows.forEach((row,r)=>{const y=(r-(n-1)/2)*pitch(line);const x=-(al==='center'?row.width/2:al==='right'?row.width:0);
      const L=Math.max(x-pad,a),R=w&&!w.done?Math.min(x+row.width+pad,w.rows[r].edge):x+row.width+pad;if(R>L)o.rect(L,y-line.size/2-pad*padY,R-L,line.size+2*pad*padY);});
    o.fill();return;}
  if(!w||w.done){o.fillRect(x0-pad,-line.height/2-pad*padY,line.total+2*pad,line.height+pad*padY*2);return;}
  const a=Math.max(w.left,w.out);o.beginPath();for(const r of w.rows)if(r.edge>a)o.rect(a,r.y0,r.edge-a,r.y1-r.y0);o.fill();
}
/** 'type' entrance: characters per second. */
const TYPE_CPS=28;
/** Draw one unit's words centred on the current origin (x by alignment, y=0). */
function drawWords(ctx:CanvasRenderingContext2D,line:Line,t:number,frame:number,opts:DrawOpts){
  const align=line.metrics[0].style.align;
  const en=line.sub||line.role==='hud'&&opts.enter!=='type'?undefined:opts.enter;const wp=en==='wipe'&&popLine(line)?wipeState(line,t,0):undefined;
  // Note lanes are centred on the line's mean pitch, so the authored position stays the line's centre.
  const ms=line.words.map(w=>midiOf(w.note)).filter((m):m is number=>m!==undefined);const ref=ms.length?ms.reduce((a,b)=>a+b,0)/ms.length:undefined;
  const vsh=opts.voice?.shift||0;const vref=opts.voice?opts.voice.field.refPitch(line.start-vsh,line.end-vsh):null;
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*pitch(line);let x=-(align==='center'?row.width/2:align==='right'?row.width:0)+(opts.scroll||0);
  for(const {w,text:full,style,spacing,width,gap,size} of row.metrics){
    const active=t>=w.start&&t<w.end;const local=t-w.start;
    let alpha=1,scale=1,dx=0,dy=0,text=full;
    const mk=opts.motion??1;
    // Look entrance (replaces pop; 'type' also takes HUD words): lift = paper shadow lift, spray = reveal 0..1, typing = cursor.
    const look=!!en&&(w.preset==='pop'||(en==='type'||opts.roles)&&w.preset==='hud');let lift=1,spray=1,typing=false;
    if(opts.flicker&&!en&&local>=0&&local<.5&&hash01(`${w.id}:fl:${frame}`)<opts.flicker*(1-local/.5)*.9)alpha=.12;
    if(w.preset==='pop'&&!en){if(local<0)alpha=0;else{const progress=line.ain===undefined?spring(local):line.ain>0?spring(local*.45/line.ain):1;scale=mk===1?.72+.28*progress:1-.28*mk*(1-progress);dy=(1-progress)*size*.5*mk;}}
    if(look){
      if(local<0)alpha=0;
      else if(en==='paste'){const e=easeOut(prog(local,inLen(line,.22)));scale=1+.03*(1-e);lift=1+1.5*(1-e);}
      else if(en==='spray')spray=clamp01(prog(local,inLen(line,Math.max(.25,Math.min(.5,(w.end-w.start)*.6)))));
      else if(en==='fade')alpha=easeInOut(prog(local,inLen(line,.3)));
      else if(en==='type'){const cs0=[...full].length;const n=line.ain===undefined?Math.floor(local*TYPE_CPS)+1:line.ain>0?Math.floor(local/line.ain*cs0)+1:cs0;const cs=[...full];text=cs.slice(0,n).join('');
        // Explicit durations end the cursor with the reveal. In=0 is a cut, without
        // a cursor; keeping n fixed at cs0 previously left it visible forever.
        typing=line.ain===undefined?n<cs.length+4:line.ain>0&&local<line.ain;}
      else if(en==='flicker'){const f=opts.flicker??.6;const u=prog(local,inLen(line,.45));if(u<1&&hash01(`${w.id}:fl:${frame}`)<f*(1-u)*.9)alpha=.08;}
      // Exits: neon powers off (a last dropout, then the tube dies), fade fades.
      const k=exitK(line,t);
      if(k>0&&en==='flicker')alpha*=(1-k)**1.5*(hash01(`${w.id}:off:${frame}`)<.5*(opts.flicker??.6)?.25:1);
      if(k>0&&en==='fade')alpha*=1-k;
    }
    // An explicit Out on an entrance without its own exit (paste, spray, type, cut, presets): fade out.
    if(line.aout&&!(look&&(en==='flicker'||en==='fade'||en==='wipe')))alpha*=1-exitK(line,t);
    const lm=opts.meta?.[w.lineId];
    if(w.preset==='karaoke')alpha=active?1:t<w.start?(lm?.dim?1:.26):.62;
    if(w.preset==='typewriter'){const count=Math.floor(Math.max(0,local)/Math.max(.02,(w.end-w.start)/Math.max(1,full.length)));text=[...full].slice(0,count+Number(local>=0)).join('');}
    if(w.preset==='write'&&local<0)alpha=0;
    if(w.preset==='hud'&&!(look&&(en==='type'||opts.roles))){alpha=local<0?.18:1;const k=Math.round(local*24);if(k>=0&&k<4){dx=(hash01(`${w.id}:${frame}:x`)-.5)*size*.18*mk;dy=(hash01(`${w.id}:${frame}:y`)-.5)*size*.12*mk;}}
    const m=midiOf(w.note);const lane=m!==undefined&&ref!==undefined?Math.max(-1.2,Math.min(1.2,-(m-ref)*.16))*size:0;
    // Per-line Boxes (lineMeta.boxes) wins over the look's note blocks; a noteless word boxed by its line gets no label.
    const boxed=lm?.boxes??(!!w.note&&opts.note!==null);
    if(boxed&&local>=0)drawNoteBlock(ctx,w.note||'',x,y+lane,width,size,local,t<w.end,!!w.note&&w.noteVerified===true,opts.note||undefined);
    dy+=lane;
    // Voice: the word swells with the singer (variable weight + width), rides the melody, wobbles on vibrato.
    let vs=style,vw=width,sx=1,sy=1;
    if(opts.voice){const v=opts.voice.field.mods(t-vsh,w.start-vsh,w.end-vsh,vref,opts.voice.amount);
      if(v.weight&&(!opts.clean||VARIABLE.has(style.fontFamily))){vs={...style,fontWeight:Math.max(100,Math.min(900,Math.round(style.fontWeight+v.weight)))};ctx.save();ctx.font=fontOf(vs,size);vw=measure(ctx,text,spacing);ctx.restore();}
      sx=v.sx;sy=v.sy;dy+=v.dy*size;}
    if(alpha>0&&wp&&!wp.done){const a=Math.max(wp.left,wp.out),b=wp.rows[r].edge;if(b<=Math.max(a,x-size))alpha=0;}
    if(alpha>0){
      ctx.save();ctx.globalAlpha*=alpha;ctx.font=fontOf(vs,size);ctx.textBaseline='middle';ctx.textAlign='left';
      if(wp&&!wp.done){const a=Math.max(wp.left,wp.out);ctx.beginPath();ctx.rect(a,y-line.size*ROW,wp.rows[r].edge-a,line.size*ROW*2);ctx.clip();}
      ctx.translate(x+width/2+dx,y+dy);ctx.scale(scale*sx,scale*sy);
      const fill=active&&w.preset==='karaoke'?(lm?.karaoke??(opts.karaoke||'#d8ff62')):lm?.dim&&w.preset==='karaoke'&&t<w.start?lm.dim:style.fill;
      let paint:string|CanvasGradient|CanvasPattern=opts.paper?paperPaint(ctx,fill):fill;
      if(spray<1){const s=size*.45,e=-vw/2-s+spray*(vw+2*s);const g=ctx.createLinearGradient(e-s,0,e+s,0);g.addColorStop(0,fill);g.addColorStop(1,withAlpha(fill,0));paint=g;}
      if(w.preset==='write'){
        // Write-on: a left→right reveal whose edge is jittered per row band (hash01), like a marker stroke catching up.
        const k=Math.min(1,Math.max(0,local/Math.max(.15,(w.end-w.start)*.7)));const edge=-width/2-size*.1+k*(width+size*.4);
        ctx.beginPath();ctx.moveTo(-width/2-size,-size);const bands=8;
        for(let i=0;i<=bands;i++){const yy=-size*.75+i*(size*1.5/bands);ctx.lineTo(edge+(hash01(`${w.id}:${i}:${Math.floor(frame/2)}`)-.5)*size*.35*(k<1?1:0),yy);}
        ctx.lineTo(-width/2-size,size);ctx.closePath();ctx.clip();
      }
      drawGlyphs(ctx,text,-vw/2,0,spacing,vs,size,paint,w.preset==='pop'&&!en?local:undefined,opts.plain?0:opts.shadow,opts.shadowColor,opts.hard,mk,lift,opts.clean);
      // Wall lettering reveals its glyphs without terminal cursor blocks. Slower
      // entrances can leave several words typing at once; their glowing cursors
      // then cover the neighbouring letters and look like duplicate wall text.
      if(typing&&line.placement!=='surface'){ctx.fillStyle=fill;ctx.fillRect(-vw/2+measure(ctx,text,spacing)+size*.08,-size*.36,size*.42,size*.72);}
      ctx.restore();
      if(opts.sparkle&&local>=0)drawSparkles(ctx,w.id,x+dx,y+dy,width,size,local,t,opts.sparkle);
    }
    x+=width+gap;
  }});
}
/** Scientific pitch ("D4", "bb3", "F#5") → MIDI number. */
export function midiOf(note?:string|null){const m=/^([a-g])(b|#)?(-?\d)$/i.exec((note||'').trim());if(!m)return undefined;
  return 12*(Number(m[3])+1)+({c:0,d:2,e:4,f:5,g:7,a:9,b:11} as Record<string,number>)[m[1].toLowerCase()]+(m[2]==='#'?1:m[2]?-1:0);}
/** Piano-roll note block under a word: grows in from the onset (note being recorded), flashes on the attack,
 *  dims when the word ends; only verified pitch names appear above the block. */
function drawNoteBlock(ctx:CanvasRenderingContext2D,note:string,x:number,y:number,width:number,size:number,local:number,on:boolean,showLabel:boolean,c:NonNullable<DrawOpts['note']>={fill:'#8d93f2',stroke:'#5a5fd6'}){
  const padX=size*.24,h=size*1.08,bx=x-padX,bw=width+2*padX;const g=Math.min(1,local/.16),e=1-Math.pow(1-g,3);const flash=Math.max(0,1-local/.45);
  const r=Math.min(size*.14,bw*e/2);
  // A translucent box colour (#rrggbbaa) sets the whole box's opacity (fill, outline, label): 0 removes it.
  const {rgb:fill,alpha:boxAlpha}=colorParts(c.fill);if(boxAlpha<=0)return;
  ctx.save();ctx.globalAlpha*=Math.min(1,(on?.72:.5)+.25*flash)*boxAlpha;
  ctx.beginPath();ctx.roundRect(bx,y-h/2,Math.max(1,bw*e),h,r);
  const glow=clamp01(c.glow??1);
  ctx.shadowBlur=0;
  if(flash>0&&glow>0){ctx.shadowColor=`rgba(255,255,255,${.9*glow})`;ctx.shadowBlur=size*.6*flash*glow;}
  ctx.fillStyle=fill;ctx.fill();ctx.shadowBlur=0;ctx.lineWidth=Math.max(1,size*.035);ctx.strokeStyle=c.stroke;ctx.stroke();
  if(showLabel){ctx.globalAlpha=Math.min(1,ctx.globalAlpha*1.3);ctx.font=`400 ${(size*.3).toFixed(1)}px "Space Mono"`;ctx.textBaseline='bottom';ctx.textAlign='left';ctx.fillStyle=c.stroke;
    ctx.fillText(note,bx+size*.04,y-h/2-size*.04);}
  ctx.restore();
}
/** Four-point twinkles scattered over a word (seeded per word): a burst after the onset, then a slow shimmer. */
function drawSparkles(ctx:CanvasRenderingContext2D,id:string,x:number,y:number,width:number,size:number,local:number,t:number,amount:number){
  const n=Math.max(1,Math.round(1+amount*3));
  for(let k=0;k<n;k++){
    const hx=hash01(`${id}:sp${k}:x`),hy=hash01(`${id}:sp${k}:y`),hp=hash01(`${id}:sp${k}:p`);
    const life=local-hp*.35;if(life<0)continue;
    const burst=life<.9?Math.sin(Math.PI*life/.9):0;const shimmer=.25+.25*Math.sin(2*Math.PI*(t*.8+hp));
    const a=Math.max(burst,shimmer)*amount;if(a<.02)continue;
    const px=x+hx*width,py=y+(hy-.5)*size*1.2,s=size*(.1+.12*hash01(`${id}:sp${k}:s`))*(.6+.4*a);
    ctx.save();ctx.globalAlpha*=Math.min(1,a);ctx.translate(px,py);ctx.rotate(hp*.4-.2);ctx.fillStyle='#ffffff';ctx.shadowColor='rgba(255,255,255,.95)';ctx.shadowBlur=s*1.6;
    ctx.beginPath();ctx.moveTo(0,-s);ctx.quadraticCurveTo(0,0,s*.55,0);ctx.quadraticCurveTo(0,0,0,s);ctx.quadraticCurveTo(0,0,-s*.55,0);ctx.quadraticCurveTo(0,0,0,-s);ctx.fill();
    ctx.restore();
  }
}
/** Variable faces (a weight axis): the only ones the voice field may re-weight smoothly. */
const VARIABLE=new Set(FONTS.filter(f=>/Variable|\[wght\]/.test(f.file)&&f.weight.includes(' ')).map(f=>f.family));
const paperTiles=new Map<string,HTMLCanvasElement>();
function paperPaint(ctx:CanvasRenderingContext2D,color:string):CanvasPattern|string{
  let tile=paperTiles.get(color);
  if(!tile){tile=document.createElement('canvas');tile.width=tile.height=96;const g=tile.getContext('2d')!;
    g.fillStyle=color;g.fillRect(0,0,96,96);
    for(let i=0;i<1800;i++){const x=hash01(`paper:x:${i}`)*96,y=hash01(`paper:y:${i}`)*96;
      g.fillStyle=i%3?'rgba(0,0,0,.16)':'rgba(255,255,255,.28)';g.fillRect(x,y,.5+hash01(`paper:w:${i}`)*2,.6);}
    for(let i=0;i<70;i++){g.strokeStyle=i%2?'rgba(255,255,255,.22)':'rgba(0,0,0,.12)';g.lineWidth=.4;
      const x=hash01(`fiber:x:${i}`)*96,y=hash01(`fiber:y:${i}`)*96;g.beginPath();g.moveTo(x,y);g.lineTo(x+2+hash01(`fiber:l:${i}`)*7,y+hash01(`fiber:a:${i}`)*3);g.stroke();}
    if(paperTiles.size>=32)paperTiles.delete(paperTiles.keys().next().value!);paperTiles.set(color,tile);}
  return ctx.createPattern(tile,'repeat')||color;
}
function drawGlyphs(ctx:CanvasRenderingContext2D,text:string,x:number,y:number,spacing:number,s:TextStyle,size:number,fill:string|CanvasGradient|CanvasPattern,popLocal:number|undefined,shadow:number,shadowColor?:string,hard?:boolean,motion=1,lift=1,clean=false){
  const outline=!!(s.stroke&&s.strokeWidth);
  if(clean&&(outline||shadow>0&&!hard)){
    // Layered: every glyph's halo, then every outline, then every fill. Shadow blur/offset are in device pixels, so they
    // take the current scale (fit × pop × voice) and stay the same size relative to the letters.
    const m=ctx.getTransform(),k=Math.hypot(m.a,m.b)||1;
    const each=(draw:(char:string,cx:number)=>void)=>{let cx=x,index=0;
      for(const char of text){ctx.save();
        if(popLocal!==undefined&&popLocal>=0){const progress=spring(Math.max(0,popLocal-index*.018));ctx.translate(0,(1-progress)*size*.14*motion);}
        index++;draw(char,cx);ctx.restore();cx+=ctx.measureText(char).width+spacing;}};
    if(shadow>0&&hard)each((c,cx)=>{ctx.globalAlpha*=shadow;ctx.fillStyle=shadowColor||'#000';ctx.fillText(c,cx+size*.035*lift,y+size*.045*lift);});
    else if(shadow>0)each((c,cx)=>{ctx.shadowColor=shadowColor?shadowColor:`rgba(0,0,0,${.6*shadow})`;ctx.shadowBlur=size*.12*k;ctx.shadowOffsetY=size*.025*k;
      if(shadowColor)ctx.globalAlpha*=.6*shadow;ctx.strokeStyle=shadowColor||`rgba(10,12,8,${.55*shadow})`;ctx.lineWidth=Math.max(1/k,size*.04);ctx.lineJoin='round';ctx.strokeText(c,cx,y);});
    if(outline)each((c,cx)=>{ctx.strokeStyle=s.stroke!;ctx.lineWidth=s.strokeWidth!*size;ctx.lineJoin='round';ctx.strokeText(c,cx,y);});
    each((c,cx)=>{ctx.fillStyle=fill;ctx.fillText(c,cx,y);});
    return;
  }
  let index=0;
  for(const char of text){
    ctx.save();
    if(popLocal!==undefined&&popLocal>=0){const progress=spring(Math.max(0,popLocal-index*.018));ctx.translate(0,(1-progress)*size*.14*motion);}
    index++;
    if(shadow>0&&hard){
      // Cut-paper drop shadow: a hard offset copy in the look's shadow colour.
      ctx.save();ctx.globalAlpha*=shadow;ctx.fillStyle=shadowColor||'#000';ctx.fillText(char,x+size*.035*lift,y+size*.045*lift);ctx.restore();
    }else if(shadow>0){
      // Legibility edge for behind words over light clothing (proof C): a soft dark halo + thin dark outline.
      ctx.save();ctx.shadowColor=shadowColor?shadowColor:`rgba(0,0,0,${.6*shadow})`;ctx.shadowBlur=size*.12;ctx.shadowOffsetY=size*.025;
      if(shadowColor)ctx.globalAlpha*=.6*shadow;
      ctx.strokeStyle=shadowColor||`rgba(10,12,8,${.55*shadow})`;ctx.lineWidth=Math.max(1,size*.04);ctx.lineJoin='round';ctx.strokeText(char,x,y);ctx.restore();
    }
    if(s.stroke&&s.strokeWidth){ctx.strokeStyle=s.stroke;ctx.lineWidth=s.strokeWidth*size;ctx.lineJoin='round';ctx.strokeText(char,x,y);}
    ctx.fillStyle=fill;ctx.fillText(char,x,y);ctx.restore();x+=ctx.measureText(char).width+spacing;
  }
}
function bracket(ctx:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,arm:number){
  ctx.beginPath();
  for(const [cx,cy,sx,sy] of [[x,y,1,1],[x+w,y,-1,1],[x+w,y+h,-1,-1],[x,y+h,1,-1]]){ctx.moveTo(cx+sx*arm,cy);ctx.lineTo(cx,cy);ctx.lineTo(cx,cy+sy*arm);}
  ctx.stroke();
}

// ---------- deterministic textures ----------
const noiseCache=new Map<string,HTMLCanvasElement>();
/** Seeded value-noise erosion mask (alpha = how much paint is missing). Deterministic per seed + size. */
function erosionMask(seed:string,w:number,h:number,threshold=.56,gain=5){
  const key=`${seed}:${w}x${h}:${threshold}:${gain}`;const hit=noiseCache.get(key);if(hit)return hit;
  const c=document.createElement('canvas');c.width=w;c.height=h;const g=c.getContext('2d')!;const img=g.createImageData(w,h);
  const lattice=(s:number,ix:number,iy:number)=>hash01(`${seed}:${s}:${ix}:${iy}`);
  const vnoise=(s:number,x:number,y:number)=>{const ix=Math.floor(x),iy=Math.floor(y),fx=x-ix,fy=y-iy;const u=fx*fx*(3-2*fx),v=fy*fy*(3-2*fy);
    const a=lattice(s,ix,iy),b=lattice(s,ix+1,iy),cc=lattice(s,ix,iy+1),d=lattice(s,ix+1,iy+1);return a+(b-a)*u+(cc-a)*v+(a-b-cc+d)*u*v;};
  const scale=Math.max(w,h);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const n=.55*vnoise(1,x/scale*9,y/scale*9)+.3*vnoise(2,x/scale*31,y/scale*31)+.15*vnoise(3,x/scale*90,y/scale*90);
    const a=Math.min(1,Math.max(0,(n-threshold)*gain));img.data[(y*w+x)*4+3]=Math.round(a*255);
  }
  g.putImageData(img,0,0);if(noiseCache.size>24)noiseCache.clear();noiseCache.set(key,c);return c;
}
const grainCache=new Map<number,HTMLCanvasElement>();
/** 4 seeded 256² grain tiles (mid-grey ± noise, for an overlay blend). Per frame: tile + offset from hash(frame). */
function grainTile(i:number){
  const hit=grainCache.get(i);if(hit)return hit;const c=document.createElement('canvas');c.width=c.height=256;const g=c.getContext('2d')!;const img=g.createImageData(256,256);
  let h=(i+1)*2654435761>>>0;
  for(let k=0;k<256*256;k++){h^=h<<13;h>>>=0;h^=h>>>17;h^=h<<5;h>>>=0;const v=128+((h&255)-128)*.9;img.data[k*4]=img.data[k*4+1]=img.data[k*4+2]=v;img.data[k*4+3]=255;}
  g.putImageData(img,0,0);grainCache.set(i,c);return c;
}

/** Neon tubes (filled): a wide glow halo, the letters filled in the tube colour (with bloom), then a white-hot face.
 *  `fit` = the context's scale (shadow blur is in device pixels). Used by neon walls and the Neon look's screen text. */
function drawTubes(o:CanvasRenderingContext2D,line:Line,t:number,frame:number,fit:number,opts:DrawOpts,hollow=false){
    if(hollow){
      // Monoline glass tubes (the Neon look): the hairline face (weight 100) stroked fat with round joins is one continuous
      // bent tube per stroke. Tight coloured bloom, the saturated glass, brighter gas, a near-white hot core.
      const saved=line.metrics.map(m=>m.style);const fill=saved[0].fill;
      const pass=(lw:number,color:string,blur:number,alpha=1)=>{o.save();o.globalAlpha*=alpha;if(blur>0){o.shadowColor=fill;o.shadowBlur=blur;}
        line.metrics.forEach((m,i)=>m.style={...saved[i],fill:color,stroke:color,strokeWidth:lw});drawWords(o,line,t,frame,opts);o.restore();};
      pass(.075,fill,line.size*.3*fit,.6);pass(.058,fill,line.size*.07*fit);pass(.03,mixHex(fill,'#ffffff',.45),line.size*.03*fit);pass(.008,mixHex(fill,'#ffffff',.85),0);
      line.metrics.forEach((m,i)=>m.style=saved[i]);return;
    }
    // Tube: glow passes then a hot core; drawn as outlines so it reads as bent glass.
    const tube=(lw:number,color:string,blur:number)=>{o.save();o.shadowColor=line.metrics[0].style.fill;o.shadowBlur=blur;for(const m of line.metrics)m.style={...m.style,stroke:color,strokeWidth:lw};drawWords(o,line,t,frame,opts);o.restore();};
    // Filled tubes: a wide glow halo, the letters filled in the tube colour (with bloom), then a white-hot face.
    const saved=line.metrics.map(m=>m.style);const fill=saved[0].fill;
    line.metrics.forEach((m)=>m.style={...m.style,fill:'rgba(0,0,0,0)'});
    tube(.075,fill,line.size*.5*fit);
    line.metrics.forEach((m,i)=>m.style={...saved[i],stroke:null,strokeWidth:null});
    o.save();o.shadowColor=fill;o.shadowBlur=line.size*.22*fit;drawWords(o,line,t,frame,opts);o.restore();
    line.metrics.forEach((m,i)=>m.style={...saved[i],fill:'#fffef4',stroke:null,strokeWidth:null});
    o.save();o.globalAlpha=.42;drawWords(o,line,t,frame,opts);o.restore();
    line.metrics.forEach((m,i)=>m.style=saved[i]);
}
/** #rrggbb mix (k = share of b). */
function mixHex(a:string,b:string,k:number){const p=(c:string)=>{const m=/^#?([0-9a-f]{6})(?:[0-9a-f]{2})?$/i.exec(c);const n=m?parseInt(m[1],16):0xffffff;return [n>>16&255,n>>8&255,n&255];};
  const x=p(a),y=p(b);return `rgb(${x.map((v,i)=>Math.round(v+(y[i]-v)*k)).join(',')})`;}
/** Neon sign hardware in unit coordinates: no back-plate, cable or return tubes (they read as stray marks); only
 *  small tube supports under each row, as on a sign mounted straight on the wall. Under the tubes. */
function drawMount(o:CanvasRenderingContext2D,line:Line,_seed:string){
  const s=line.size,al=line.metrics[0].style.align;
  o.save();o.fillStyle='rgba(150,150,158,.45)';
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*pitch(line)+s*.36;const rx=-(al==='center'?row.width/2:al==='right'?row.width:0);
    for(const f of [.12,.5,.88]){o.beginPath();o.arc(rx+row.width*f,y,s*.014,0,Math.PI*2);o.fill();}});
  o.restore();
}
/** Feet of a word's strokes: runs of columns whose lowest painted pixel sits on the line's bottom contour (stems,
 *  bowl bottoms; never counters or gaps). Sampled from the real glyphs at P px, cached; x/y in units of the font size
 *  from the word's left edge / the row centre; w = run width (stroke weight). */
const footCache=new Map<string,{x:number;y:number;w:number}[]>();
function strokeFeet(font:(px:number)=>string,text:string,spacingEm:number){
  const P=64,key=`${font(P)}|${text}|${spacingEm}`;const hit=footCache.get(key);if(hit)return hit;
  const c=document.createElement('canvas');const g=c.getContext('2d',{willReadFrequently:true})!;g.font=font(P);
  let wd=0;for(const ch of text)wd+=g.measureText(ch).width+spacingEm*P;
  c.width=Math.max(1,Math.ceil(wd+P*.2));c.height=P*2;g.font=font(P);g.textBaseline='middle';g.fillStyle='#fff';
  let x=0;for(const ch of text){g.fillText(ch,x,P);x+=g.measureText(ch).width+spacingEm*P;}
  const d=g.getImageData(0,0,c.width,c.height).data;const low=new Int16Array(c.width).fill(-1);let bottom=-1;
  for(let cx=0;cx<c.width;cx++)for(let cy=c.height-1;cy>=0;cy--)if(d[(cy*c.width+cx)*4+3]>128){low[cx]=cy;bottom=Math.max(bottom,cy);break;}
  const feet:{x:number;y:number;w:number}[]=[];const tol=Math.max(2,P*.07);let a=-1;
  for(let cx=0;cx<=c.width;cx++){const on=cx<c.width&&low[cx]>=0&&low[cx]>=bottom-tol;
    if(on&&a<0)a=cx;else if(!on&&a>=0){let ys=0;for(let k=a;k<cx;k++)ys+=low[k];feet.push({x:(a+cx)/2/P,y:(ys/(cx-a)-P)/P,w:(cx-a)/P});a=-1;}}
  if(footCache.size>200)footCache.clear();footCache.set(key,feet);return feet;
}
/** Spray paint marks in unit coordinates (wall:'spray'): drips that leave the feet of the letter strokes (where
 *  paint pools) and run straight down — tapered, wider at the root, a small bulb at the tip — once the spray has
 *  passed that stroke (ease-out growth, mostly short), and a stencil bridge through stencil-face rows. */
function drawSprayMarks(o:CanvasRenderingContext2D,line:Line,t:number,drips:number,stencil:boolean){
  const al=line.metrics[0].style.align;
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*pitch(line);let x=-(al==='center'?row.width/2:al==='right'?row.width:0);
    const rx=x;
    for(const m of row.metrics){const local=t-m.w.start;
      if(local>=0&&drips>0){
        const feet=strokeFeet(px=>fontOf(m.style,px),m.text,m.spacing/m.size);
        // A few per word, weighted toward heavier strokes (seeded per word, no repeats).
        const n=Math.min(feet.length,Math.round(drips*(1+[...m.text].length*.55)));const used=new Set<number>();
        const dur=Math.max(.25,Math.min(.5,(m.w.end-m.w.start)*.6));
        o.save();o.fillStyle=m.style.fill;
        for(let k=0;k<n;k++){let tot=0;feet.forEach((f,i)=>{if(!used.has(i))tot+=f.w**1.5;});let pick=hash01(`${m.w.id}:drip:${k}`)*tot,fi=-1;
          for(let i=0;i<feet.length;i++){if(used.has(i))continue;pick-=feet[i].w**1.5;if(pick<=0){fi=i;break;}}if(fi<0)break;used.add(fi);
          const f=feet[fi],s=m.size,h=(a:string)=>hash01(`${m.w.id}:drip:${k}:${a}`);
          const px=x+(f.x+(h('x')-.5)*f.w*.5)*s,py=y+f.y*s;
          // After the spray reaches this stroke; fast then slowing; lengths mostly short, a few long.
          const start=dur*Math.min(1,f.x*s/Math.max(1,m.width))+.1+.35*h('d'),T=1.1+1.2*h('t');
          const grow=1-(1-clamp01((local-start)/T))**3;if(grow<=0)continue;
          const len=s*(.04+.95*h('l')**2.2)*grow,rw=Math.min(f.w*s*.42,s*.055)*(.55+.45*h('w')),tw=rw*.42,bulb=tw*(1+.35*grow);
          o.beginPath();o.moveTo(px-rw*1.5,py-s*.03);
          o.quadraticCurveTo(px-rw*.55,py,px-rw*.5,py+Math.min(len,rw*2));o.lineTo(px-tw,py+len);
          o.lineTo(px+tw,py+len);o.lineTo(px+rw*.5,py+Math.min(len,rw*2));o.quadraticCurveTo(px+rw*.55,py,px+rw*1.5,py-s*.03);o.closePath();o.fill();
          o.beginPath();o.arc(px,py+len,bulb,0,Math.PI*2);o.fill();}
        o.restore();}
      x+=m.width+m.gap;}
    if(stencil){o.save();o.globalCompositeOperation='destination-out';o.fillRect(rx-line.size,y-line.size*.035,row.width+2*line.size,line.size*.05);o.restore();}
  });
}
/** Uneven spray coverage in the text's own space (unit or plane coordinates), so worn patches move with the words.
 *  The mask is seeded per line and stretched over the unit's box (drips included). */
function sprayWear(o:CanvasRenderingContext2D,line:Line,seed:string){
  const al=line.metrics[0].style.align,x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
  const bx=x0-line.size*.5,by=-line.height/2-line.size*.5,bw=line.total+line.size,bh=line.height+line.size*2;
  o.save();o.globalCompositeOperation='destination-out';o.globalAlpha=.4;
  o.drawImage(erosionMask(`spray:${seed}`,160,Math.max(8,Math.round(160*bh/bw)),.5,3),bx,by,bw,bh);o.restore();
}
/** Spray finish on a screen-space paint buffer: overspray halo and (env = the graded footage)
 *  modulation by the wall's own luminance, so the paint takes the light falloff, grain and cracks underneath. */
function sprayify(b:HTMLCanvasElement,tmp:HTMLCanvasElement,px:number,env?:HTMLCanvasElement){
  const g=b.getContext('2d')!;g.setTransform(1,0,0,1,0,0);
  if(tmp.width!==b.width)tmp.width=b.width;if(tmp.height!==b.height)tmp.height=b.height;
  const tg=tmp.getContext('2d')!;tg.setTransform(1,0,0,1,0,0);tg.globalAlpha=1;tg.globalCompositeOperation='source-over';tg.clearRect(0,0,tmp.width,tmp.height);
  tg.filter=`blur(${Math.max(.5,px*.025).toFixed(2)}px)`;tg.drawImage(b,0,0);tg.filter=`blur(${Math.max(1,px*.08).toFixed(2)}px)`;tg.globalAlpha=.35;tg.drawImage(b,0,0);tg.filter='none';tg.globalAlpha=1;
  g.globalCompositeOperation='destination-over';g.globalAlpha=.45;g.drawImage(tmp,0,0);g.globalAlpha=1;
  // Shade = 0.4 + 0.6 × the wall's (brightened) luminance: paint on a dark wall is dim but never vanishes.
  if(env){tg.clearRect(0,0,tmp.width,tmp.height);tg.fillStyle='rgb(102,102,102)';tg.fillRect(0,0,tmp.width,tmp.height);tg.globalAlpha=.6;tg.filter='grayscale(1) contrast(1.35) brightness(2.3)';tg.drawImage(env,0,0);tg.filter='none';tg.globalAlpha=1;
    tg.globalCompositeOperation='destination-in';tg.drawImage(b,0,0);tg.globalCompositeOperation='source-over';
    g.globalCompositeOperation='multiply';g.drawImage(tmp,0,0);}
  g.globalCompositeOperation='source-over';
}
/** Wall blend for warped wall text b (amount 0..1): multiply by the wall's brightened luminance (its light falloff),
 *  then soft-light the wall's luminance (texture, stains) through the text. */
function wallify(b:HTMLCanvasElement,tmp:HTMLCanvasElement,env:HTMLCanvasElement,amount:number){
  const g=b.getContext('2d')!;g.setTransform(1,0,0,1,0,0);
  if(tmp.width!==b.width)tmp.width=b.width;if(tmp.height!==b.height)tmp.height=b.height;
  const tg=tmp.getContext('2d')!;tg.setTransform(1,0,0,1,0,0);tg.globalCompositeOperation='source-over';tg.globalAlpha=1;
  const a=Math.min(1,amount),base=Math.round(255*(1-.75*a));
  tg.clearRect(0,0,tmp.width,tmp.height);tg.fillStyle=`rgb(${base},${base},${base})`;tg.fillRect(0,0,tmp.width,tmp.height);
  tg.globalAlpha=.75*a;tg.filter='grayscale(1) contrast(1.3) brightness(1.9)';tg.drawImage(env,0,0);tg.filter='none';tg.globalAlpha=1;
  tg.globalCompositeOperation='destination-in';tg.drawImage(b,0,0);tg.globalCompositeOperation='source-over';
  g.globalCompositeOperation='multiply';g.drawImage(tmp,0,0);
  // Detail: the wall's luminance (wall white ≈ mid-grey), soft-lit through the ink so its texture and stains show.
  tg.clearRect(0,0,tmp.width,tmp.height);tg.filter='grayscale(1) contrast(1.8) brightness(.62)';tg.drawImage(env,0,0);tg.filter='none';
  tg.globalCompositeOperation='destination-in';tg.drawImage(b,0,0);tg.globalCompositeOperation='source-over';
  g.globalCompositeOperation='soft-light';g.globalAlpha=a;g.drawImage(tmp,0,0);g.globalAlpha=1;
  g.globalCompositeOperation='source-over';
}
/** Torn photocopy sheet in plane pixels: jagged polygon (seeded), off-white paper, faint copier streaks + edge shade. */
function drawPosterSheet(o:CanvasRenderingContext2D,seed:string,W:number,H:number){
  const m=Math.min(W,H)*.04;const pts:Point[]=[];const n=26;
  const edge=(i:number,a:Point,b:Point,side:number)=>{for(let k=0;k<n;k++){const f=k/n;const j=(hash01(`${seed}:t${side}:${k}`)-.5)*m*(.6+1.4*hash01(`${seed}:d${side}:${k>>2}`));
    const nx=b[1]-a[1],ny=a[0]-b[0];const l=Math.hypot(nx,ny)||1;pts.push([a[0]+(b[0]-a[0])*f+nx/l*j,a[1]+(b[1]-a[1])*f+ny/l*j]);}void i;};
  const c:Point[]=[[m,m*1.2],[W-m,m],[W-m*1.2,H-m],[m*.8,H-m*1.1]];for(let i=0;i<4;i++)edge(i,c[i],c[(i+1)%4],i);
  o.save();o.beginPath();pts.forEach(([x,y],i)=>i?o.lineTo(x,y):o.moveTo(x,y));o.closePath();
  o.fillStyle='#dcd8ce';o.fill();o.clip();
  for(let k=0;k<4;k++){const y=hash01(`${seed}:s${k}`)*H,h=(.01+hash01(`${seed}:h${k}`)*.05)*H;o.fillStyle=`rgba(20,20,20,${(.05+hash01(`${seed}:a${k}`)*.08).toFixed(3)})`;o.fillRect(0,y,W,h);}
  const g=o.createLinearGradient(0,0,W,H);g.addColorStop(0,'rgba(0,0,0,.18)');g.addColorStop(.5,'rgba(0,0,0,0)');g.addColorStop(1,'rgba(0,0,0,.22)');o.fillStyle=g;o.fillRect(0,0,W,H);
  o.restore();
}

// ---------- surface text ----------
/** Pull a quad's left/right edges toward their mean length (k=1: no perspective squash left; 0: unchanged). */
function softenPerspective(q:Point[],k:number):Point[]{
  const [tl,tr,br,bl]=q;const len=(a:Point,b:Point)=>Math.hypot(b[0]-a[0],b[1]-a[1]);
  const hl=len(tl,bl),hr=len(tr,br),m=(hl+hr)/2;
  const scale=(a:Point,b:Point,h:number):[Point,Point]=>{const c:Point=[(a[0]+b[0])/2,(a[1]+b[1])/2];const s=(h+(m-h)*k)/Math.max(1e-6,h);return [[c[0]+(a[0]-c[0])*s,c[1]+(a[1]-c[1])*s],[c[0]+(b[0]-c[0])*s,c[1]+(b[1]-c[1])*s]];};
  const [ntl,nbl]=scale(tl,bl,hl),[ntr,nbr]=scale(tr,br,hr);return [ntl,ntr,nbr,nbl];
}
/** Source pixel size: surfaces are drawn in source-normalized coords (a reframe keeps the source's short side). */
function sourceSize(p:Project,c?:CropFrame):[number,number]{return c?[p.width/c.w,p.height/c.h]:[p.width,p.height];}
/** Plane sub-rectangle [u0,v0,u1,v1] of a surface (unit square = whole quad). */
export type PlaneRect=[number,number,number,number];
type PlaneFit={rect:PlaneRect;start?:number;end?:number}|'hidden'|undefined;
function subQuad(q:Point[],r:PlaneRect):Point[]{const H=squareToQuad(q);return [applyH(H,r[0],r[1]),applyH(H,r[2],r[1]),applyH(H,r[2],r[3]),applyH(H,r[0],r[3])];}
/** Scene effects for surface text: env = this frame's graded footage (spray modulation), buf = renderer scratch
 *  buffers, lightOnly = the neon light pass (tubes only, no hardware). */
type SurfaceFx={env?:HTMLCanvasElement;buf:(i:number)=>HTMLCanvasElement;lightOnly?:boolean};
function drawSurfaceLine(ctx:CanvasRenderingContext2D,p:Project,line:Line,surface:Surface,quadPx:Point[],t:number,frame:number,blend:boolean,look?:Look,scrollK?:number,sub?:PlaneRect,crop?:CropFrame,fx?:SurfaceFx){
  if(sub)quadPx=subQuad(quadPx,sub);
  // Authored neon on steep walls (tunnels): pull the near/far edges halfway to their mean height so the
  // tube lettering reads instead of being squashed by perspective.
  if(surface.material==='neon')quadPx=softenPerspective(quadPx,.5);
  if(!quadIsConvex(quadPx))return;
  // Plane rectangle aspect comes from the key-frame drawing (stable across frames, so text never re-wraps);
  // under a crop it is the visible sub-rectangle of that plane (same for every frame of the line).
  const [sw,sh]=sourceSize(p,crop);const key=surface.corners.map(([x,y])=>[x*sw,y*sh] as Point);
  let [kw,kh]=quadSize(sub?subQuad(key,sub):key);
  const marquee=scrollK!==undefined;
  // Look.wallScale: the plane grows about its centre (text may pass the drawn quad); width fill is capped so long
  // lines stay near the wall's width.
  const ws=marquee?1:look?.wallScale??1,ex=ws>1?Math.min(ws,1.12):1;
  if(ws!==1){quadPx=subQuad(quadPx,[-(ex-1)/2,-(ws-1)/2,1+(ex-1)/2,1+(ws-1)/2]);kw*=ex;kh*=ws;}
  const W=Math.max(64,Math.min(1600,Math.round(Math.max(kw,kh*kw/Math.max(1,kh))*1.6))),H=Math.max(16,Math.round(W*kh/Math.max(1,kw)));
  const off=document.createElement('canvas');off.width=W;off.height=H;const o=off.getContext('2d')!;
  const fit=(marquee?H*.62/Math.max(1,line.height*1.1):ws!==1?Math.min(W/ex*Math.min(.97,.88*ws)/Math.max(1,line.total),H*.72/Math.max(1,line.height*1.1))
    :Math.min(W*.88/Math.max(1,line.total),H*.72/Math.max(1,line.height*1.1)))
    *(marquee?1:p.lineMeta?.[line.words[0].lineId]?.scale??1);   // studio wall-resize handle
  // Under a look the wall text takes the look's colour; material still shapes the finish. A carded look keeps its
  // cards clean on painted walls (flat, no wear).
  const material=look?.id==='paper-cut'?'paper':look?.wall==='spray'&&fx?'spray':look?.finish==='neon'?'neon':look?.wall==='poster'?(surface.material==='neon'?'neon':surface.material==='flat'?'flat':'poster')
    :look?(look.optics.glow&&look.optics.glow>.5?'neon':look.texture==='paper'?'paint':line.card&&look.palette.card&&(surface.material||'flat')==='paint'?'flat':surface.material||'flat'):surface.material||'paint';
  const scroll=marquee?((W/fit+line.total)/2-scrollK!*(W/fit+line.total)):0;
  // Studio nudge: lineMeta.u/v move the text in the wall's plane (fractions of the plane; absent = centred).
  const nm=marquee?undefined:p.lineMeta?.[line.words[0].lineId];
  o.save();o.translate(W*(.5+(nm?.u??0)),H*(.5+(nm?.v??0)));o.scale(fit,fit);
  const en=look?.enter;
  if(line.card&&look?.palette.card){if(marquee){const pad=line.size*.32*(look.cardPad??1);const al=line.metrics[0].style.align;const x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
    o.fillStyle=look.palette.card;o.fillRect(x0-pad+((W/fit+line.total)/2-scrollK!*(W/fit+line.total)),-line.height/2-pad*.6,line.total+2*pad,line.height+pad*1.2);}
    else drawCard(o,line,t,look.palette.card,.6,en,look.cardPad);}
  if(material==='neon'){if(look?.finish==='neon'&&!fx?.lightOnly)drawMount(o,line,surface.id);drawTubes(o,line,t,frame,fit,{shadow:0,plain:true,scroll,flicker:look?.flicker,enter:en},look?.finish==='neon');}
  else if(material==='spray'){drawWords(o,line,t,frame,{shadow:0,plain:true,scroll,enter:en,clean:!!look&&!lookIsFrozen(look)});drawSprayMarks(o,line,t,look?.drips??.5,true);sprayWear(o,line,`${surface.id}:${line.key}`);}
  else if(material==='poster'){
    // Wheat-pasted photocopy: torn off-white sheet filling the plane, toner-black type, copier streaks.
    o.save();o.setTransform(1,0,0,1,0,0);drawPosterSheet(o,surface.id,W,H);o.restore();
    const saved=line.metrics.map(m=>m.style);line.metrics.forEach(m=>m.style={...m.style,fill:'#0c0c0c',stroke:null,strokeWidth:null});
    drawWords(o,line,t,frame,{shadow:0,plain:true,scroll,enter:en,clean:!!look&&!lookIsFrozen(look)});line.metrics.forEach((m,i)=>m.style=saved[i]);
  }else drawWords(o,line,t,frame,{shadow:material==='paper'?.85:0,shadowColor:look?.palette.shadow,hard:material==='paper',paper:material==='paper',plain:material!=='paper',scroll,enter:en,clean:!!look&&!lookIsFrozen(look)});
  o.restore();
  if(material==='poster'){o.globalCompositeOperation='destination-out';o.drawImage(erosionMask(`${surface.id}:poster`,Math.ceil(W/3),Math.ceil(H/3),.68,4),0,0,W,H);o.globalCompositeOperation='source-over';
    // "Every sign repeats": the same sheet pasted again along the wall (plane offsets left/right of the authored quad).
    // Each copy is pasted a little later (one every .28 s after the line starts), skewed and offset like hand pasting.
    const H0=squareToQuad(quadPx);
    [1,-1,-2].forEach((dx,k)=>{if(t<line.start+.28*(k+1))return;
      const j=(c:number,a:string)=>(hash01(`${surface.id}:${dx}:${c}:${a}`)-.5);const sy=j(9,'y')*.1;
      const q=[[0,0],[1,0],[1,1],[0,1]].map(([u,v],c)=>applyH(H0,dx+.035+u*.93+j(c,'u')*.03,.05+sy+v*.9+j(c,'v')*.04) as Point);
      if(!quadIsConvex(q))return;ctx.save();ctx.globalAlpha=.9;drawWarped(ctx,off,q);ctx.restore();});
    {const j=(c:number,a:string)=>(hash01(`${surface.id}:main:${c}:${a}`)-.5);quadPx=[[0,0],[1,0],[1,1],[0,1]].map(([u,v],c)=>applyH(H0,u+j(c,'u')*.02,v+j(c,'v')*.03) as Point);}}
  if(material==='paint'){o.globalCompositeOperation='destination-out';o.imageSmoothingEnabled=true;o.drawImage(erosionMask(surface.id,Math.ceil(W/3),Math.ceil(H/3)),0,0,W,H);o.globalCompositeOperation='source-over';}
  // P1 fake extrusion: N copies stepped along the quad's down-right diagonal, darkened, under the face.
  const depth=look?.optics.extrude||0;
  if(depth>0){
    const dark=document.createElement('canvas');dark.width=W;dark.height=H;const d=dark.getContext('2d')!;d.drawImage(off,0,0);d.globalCompositeOperation='source-atop';
    const diag=[quadPx[2][0]-quadPx[0][0],quadPx[2][1]-quadPx[0][1]];const len=Math.hypot(diag[0],diag[1])||1;const [hgt]=[quadSize(quadPx)[1]];
    const step=[diag[0]/len*hgt*.006*depth,diag[1]/len*hgt*.006*depth];
    for(let k=12;k>=1;k--){d.globalCompositeOperation='source-over';d.clearRect(0,0,W,H);d.drawImage(off,0,0);d.globalCompositeOperation='source-atop';d.fillStyle=`rgba(0,0,0,${.45+.4*k/12})`;d.fillRect(0,0,W,H);
      drawWarped(ctx,dark,quadPx.map(([x,y])=>[x+step[0]*k,y+step[1]*k] as Point));}
  }
  // Look.wallBlend: warp into screen space and take the wall's light and texture there (cards/ink read as on the wall).
  const wb=look?.wallBlend??0;
  if(wb>0&&fx?.env&&material!=='spray'&&material!=='neon'){
    const S=fx.buf(26);drawWarped(S.getContext('2d')!,off,quadPx);wallify(S,fx.buf(27),fx.env,wb);ctx.drawImage(S,0,0);return;
  }
  if(material==='spray'&&fx){
    // Spray paint: warp into screen space, then overspray + wall modulation there (perspective-correct, takes the wall's light).
    const S=fx.buf(26);drawWarped(S.getContext('2d')!,off,quadPx);
    sprayify(S,fx.buf(27),line.size*fit/H*quadSize(quadPx)[1],fx.env);
    ctx.save();ctx.globalAlpha=.94;ctx.drawImage(S,0,0);ctx.restore();return;
  }
  ctx.save();
  if(blend&&material==='paint'&&!look){ctx.globalAlpha=.9;ctx.globalCompositeOperation='hard-light';}
  if(blend&&material==='neon'&&!look)ctx.globalCompositeOperation='screen';
  drawWarped(ctx,off,quadPx);
  if(blend&&material==='neon'&&!look){ctx.globalCompositeOperation='source-over';ctx.globalAlpha=.55;drawWarped(ctx,off,quadPx);}
  ctx.restore();
}

type BeatGrid={beats:number[];downbeats?:number[]};
/** Flash strength at t: decays from the most recent beat (downbeats full, other beats × flash.beat). */
function flashAt(b:BeatGrid,t:number,f:NonNullable<Grade['flash']>){
  let last=-1;for(const x of b.beats)if(x<=t+1e-6)last=x;else break;if(last<0)return 0;
  const dt=t-last;if(dt>f.decay*1.5)return 0;const down=b.downbeats?b.downbeats.some(d=>Math.abs(d-last)<.03):true;
  return f.amount*(down?1:f.beat??.35)*Math.exp(-3*dt/Math.max(.01,f.decay));
}
/** Halation: highlights (thresholded by contrast), blurred and tinted warm, screened back over the footage. */
function halationPass(g:CanvasRenderingContext2D,b:HTMLCanvasElement,tmp:HTMLCanvasElement,amount:number){
  if(tmp.width!==b.width)tmp.width=b.width;if(tmp.height!==b.height)tmp.height=b.height;
  const t=tmp.getContext('2d')!;t.setTransform(1,0,0,1,0,0);t.globalAlpha=1;t.globalCompositeOperation='source-over';t.fillStyle='#000';t.fillRect(0,0,tmp.width,tmp.height);
  t.filter=`grayscale(1) brightness(.55) contrast(4) blur(${(b.height*.012).toFixed(2)}px)`;t.drawImage(b,0,0);t.filter='none';
  t.globalCompositeOperation='multiply';t.fillStyle='#ff6a3d';t.fillRect(0,0,tmp.width,tmp.height);t.globalCompositeOperation='source-over';
  g.save();g.globalCompositeOperation='screen';g.globalAlpha=Math.min(1,amount);g.drawImage(tmp,0,0);g.restore();
}
/** grade.mono: photocopy tone curve on luminance (+ exposure flash); pixels near keep.hue keep their colour. */
function monoPass(g:CanvasRenderingContext2D,w:number,h:number,m:NonNullable<Grade['mono']>,flash:number){
  const img=g.getImageData(0,0,w,h);const d=img.data;const lut=new Uint8ClampedArray(256);const crush=m.crush||0,piv=.38;
  for(let i=0;i<256;i++){let x=i/255;x=Math.min(1,x+flash*(.18+.82*x));x=Math.max(0,(x-crush)/(1-crush));
    let y=Math.min(1,Math.max(0,piv+(x-piv)*m.contrast));y=.5*y+.5*y*y*(3-2*y);lut[i]=Math.round(y*255);}
  const k=m.keep;
  for(let i=0;i<d.length;i+=4){const r=d[i],gg=d[i+1],bb=d[i+2];const L=lut[(77*r+150*gg+29*bb)>>8];let wgt=0;
    if(k){const mx=Math.max(r,gg,bb),mn=Math.min(r,gg,bb);const sat=mx?(mx-mn)/mx:0;
      if(sat>=k.minSat&&mx>40){const c=mx-mn;let hue=mx===r?((gg-bb)/c)%6:mx===gg?(bb-r)/c+2:(r-gg)/c+4;hue*=60;if(hue<0)hue+=360;
        let dh=Math.abs(hue-k.hue)%360;if(dh>180)dh=360-dh;wgt=Math.max(0,1-dh/k.width)*Math.min(1,(sat-k.minSat)/.15);}}
    if(wgt>0){d[i]=L+(lut[r]-L)*wgt;d[i+1]=L+(lut[gg]-L)*wgt;d[i+2]=L+(lut[bb]-L)*wgt;}else{d[i]=d[i+1]=d[i+2]=L;}
  }
  g.putImageData(img,0,0);
}
/** P0b cost cap: motion-blur sub-samples per frame (the brief's N). */
const LED=new WeakMap<Project,Project>();
/** Project view with word times shifted earlier by timing.leadMs (lines with lineMeta.pinTiming keep theirs). Memoized per project object. */
export function withLead(p:Project):Project{
  const ms=p.timing?.leadMs||0;if(!ms)return p;const hit=LED.get(p);if(hit)return hit;const d=ms/1000;
  const out={...p,timing:{...p.timing,leadMs:0},words:p.words.map(w=>p.lineMeta?.[w.lineId]?.pinTiming?w:{...w,start:Math.max(0,w.start-d),end:Math.max(0,w.end-d)})};
  LED.set(p,out);return out;
}
export const MOTION_BLUR_SAMPLES=6;
/** 5×7 LED dot-matrix glyphs (rows top→bottom, '1' = lit), trimmed to their lit columns; unknown characters → '?'. */
const LED_GLYPHS:Record<string,string>={
  A:'01110 10001 10001 11111 10001 10001 10001',B:'11110 10001 10001 11110 10001 10001 11110',C:'01110 10001 10000 10000 10000 10001 01110',
  D:'11100 10010 10001 10001 10001 10010 11100',E:'11111 10000 10000 11110 10000 10000 11111',F:'11111 10000 10000 11110 10000 10000 10000',
  G:'01110 10001 10000 10111 10001 10001 01111',H:'10001 10001 10001 11111 10001 10001 10001',I:'111 010 010 010 010 010 111',
  J:'00111 00010 00010 00010 00010 10010 01100',K:'10001 10010 10100 11000 10100 10010 10001',L:'10000 10000 10000 10000 10000 10000 11111',
  M:'10001 11011 10101 10101 10001 10001 10001',N:'10001 10001 11001 10101 10011 10001 10001',O:'01110 10001 10001 10001 10001 10001 01110',
  P:'11110 10001 10001 11110 10000 10000 10000',Q:'01110 10001 10001 10001 10101 10010 01101',R:'11110 10001 10001 11110 10100 10010 10001',
  S:'01111 10000 10000 01110 00001 00001 11110',T:'11111 00100 00100 00100 00100 00100 00100',U:'10001 10001 10001 10001 10001 10001 01110',
  V:'10001 10001 10001 10001 10001 01010 00100',W:'10001 10001 10001 10101 10101 10101 01010',X:'10001 10001 01010 00100 01010 10001 10001',
  Y:'10001 10001 10001 01010 00100 00100 00100',Z:'11111 00001 00010 00100 01000 10000 11111',
  '0':'01110 10001 10011 10101 11001 10001 01110','1':'010 110 010 010 010 010 111','2':'01110 10001 00001 00010 00100 01000 11111',
  '3':'11111 00010 00100 00010 00001 10001 01110','4':'00010 00110 01010 10010 11111 00010 00010','5':'11111 10000 11110 00001 00001 10001 01110',
  '6':'00110 01000 10000 11110 10001 10001 01110','7':'11111 00001 00010 00100 01000 01000 01000','8':'01110 10001 10001 01110 10001 10001 01110',
  '9':'01110 10001 10001 01111 00001 00010 01100','!':'1 1 1 1 1 0 1','?':'01110 10001 00001 00010 00100 00000 00100',
  '.':'0 0 0 0 0 0 1',',':'00 00 00 00 00 01 10',"'":'1 1 0 0 0 0 0','-':'0000 0000 0000 1111 0000 0000 0000',
  ':':'0 0 1 0 1 0 0','·':'0 0 0 1 0 0 0','&':'01100 10010 10100 01000 10101 10010 01101','/':'00001 00010 00010 00100 01000 01000 10000',
};
const LED_SPACE=3;
function ledGlyph(ch:string){return LED_GLYPHS[ch]??LED_GLYPHS[ch.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase()]??(ch.trim()?LED_GLYPHS['?']:'');}
/** Width of a string in LED columns (one dark column between glyphs). */
function ledWidth(text:string){let w=0,n=0;for(const ch of text){const g=ledGlyph(ch);w+=g?g.split(' ')[0].length:LED_SPACE;n++;}return w+Math.max(0,n-1);}
/** LED ticker crawl speed, em per second (em = the display's text height). */
const TICKER_SPEED=8;
/** Ticker gaps, em: between words of a line, between lines of a phrase. */
const TICKER_GAP_WORD=.9,TICKER_GAP_LINE=1.2;

/** Per-call render options; anything unset falls back to the instance fields. */
/** proxy: half-size copies (drag/scrub/thumbs); full: full-size short-GOP copies (paused studio frames, same pixels as the
 *  originals within encode noise); stale: checked after the media seeks, before anything is painted; true = drop this
 *  frame (the canvas keeps the previous one), so a newer request never waits behind a slow paint.
 *  Preview-only: cacheMedia reuses the graded footage/cutout; cacheLayouts retains bounded per-look placement plans;
 *  previewScale scales pixel-sized details when the caller supplies a reduced-size project. */
export type RenderOpts={heavyOptics?:boolean;proxy?:boolean;full?:boolean;cacheMedia?:boolean;cacheLayouts?:boolean;previewScale?:number;stale?:()=>boolean};
export class StageRenderer {
  project:Project;server:string;bg?:HTMLVideoElement;matte?:HTMLVideoElement;bgProxy?:HTMLVideoElement;matteProxy?:HTMLVideoElement;bgSeek?:HTMLVideoElement;matteSeek?:HTMLVideoElement;tracks?:Tracks;shots=new Map<string,HTMLVideoElement>();
  occupancy?:Occupancy;crop?:CropData;surfaceTracks=new Map<string,SurfaceTrack|null>();
  /** Set false to render positions exactly as authored (before/after comparisons). */
  autoPlace=true;
  /** Set false to skip the P0b optics (motion blur, chroma) — e.g. for fast scrubbing. Export keeps them. */
  heavyOptics=true;
  /** The project is an n× copy of its authored size (#/render &scale=n): pixel-sized effects (grain) scale with it. */
  renderScale=1;
  /** Studio only: also load the half-size short-GOP preview proxies (media/proxy/<video>.mp4, <matte>/fg_proxy.webm) when the
   *  server has made them; render({proxy:true}) then seeks those (~17 ms) instead of the originals (~100 ms). Never set on
   *  the #/render route: export, TypesetRender and capture always read the originals. */
  draftMedia=false;
  /** Exports only (#/render?decode=seq): footage and matte advance by playing forward (advance()) instead of seeking. */
  sequential=false;
  private stale?:()=>boolean;
  /** Preview-only, bounded to the current footage and subject frame. Never cache text or text-dependent relighting. */
  private cacheMedia=false;
  /** Scale pixel-sized HUD details / grain with a reduced preview project; export uses 1. */
  private previewScale=1;
  private mediaFrames:({source:HTMLVideoElement;key:string;canvas:HTMLCanvasElement}|undefined)[]=[];
  private cacheLayouts=false;
  private layoutPlans=new Map<string,{map:Map<string,LinePlacement>;boxes:Placed[]}>();
  private layoutSource?:OccupancySource;
  private plan?:{sig:string;map:Map<string,LinePlacement>;source:OccupancySource};private fixedBoxes:Placed[]=[];private occSource?:{key:object;crop?:CropData;fps:number;portrait:boolean;src:OccupancySource};
  private sourceTracks?:Tracks;private matteSig='';
  headTracks=new Map<string,Tracks>();
  /** Current visible footage's head, in composition coordinates. Source data survives trims, splits and moves. */
  head(t:number,id='person0',p=this.project,spot?:HeadSpot):{point:TrackPoint;state:HeadState}{
    const source=headSourceAt(p,t);if(!source)return {point:VIRTUAL_HEAD,state:'none'};
    const raw=this.headTracks.get(source.path);let pt=sampleHead(raw,source.time,id);
    if(!pt&&!raw){
      // Older projects may still use a subject matte's track, but only on the shot it belongs to.
      const s=p.analysis.matteSource;
      if(s&&source.layer?.id===s.layerId){const at=matteTime(p,t);if(at!=null)pt=sampleHead(this.sourceTracks,at,id);}
      else if(!s&&!source.layer&&p.media.video?.path===source.path)pt=sampleHead(this.sourceTracks,source.time,id);
    }
    if(!pt)return {point:VIRTUAL_HEAD,state:'none'};
    pt=headSpotPoint(pt,spot);
    if(source.layer)pt=headPoint(p,source,t,pt);
    else{const [cx,cy]=this.point(Math.round(t*p.fps),pt.cx,pt.cy);pt={...pt,cx,cy};}
    return {point:pt,state:'tracked'};
  }
  headSpot(t:number,point:Point,id='person0',p=this.project):HeadSpot|undefined{
    const basis=[{u:0,v:0},{u:1,v:0},{u:0,v:1}].map(spot=>this.head(t,id,p,spot));
    if(basis.some(h=>h.state==='none'))return;
    const [a,b,c]=basis.map(h=>[h.point.cx,h.point.cy] as Point);return relativeHeadSpot(point,a,b,c);
  }
  /** Shared by the rendered label and its draggable stage guide. */
  anchorOrigin(line:Line,fit:number,origin:{x:number;y:number},frame:number,trackId='person0'){
    const p=this.project,first=line.words[0],top=(line.height/2+line.size*(first.preset==='hud'?.85:.2))*fit/p.height,bot=(line.height/2+line.size*.2)*fit/p.height;
    const al=line.metrics[0].style.align,lx=-(al==='center'?line.total/2:al==='right'?line.total:0),pad=line.size*.3;
    const tagW=first.preset==='hud'?(`${trackId} · F0000 · LIVE`.length*.6+.6)*Math.max(13*this.previewScale/fit,line.size*.36):0;
    const exL=(lx-pad)*fit/p.width,exR=Math.max(lx+line.total+pad,lx-pad+tagW)*fit/p.width;
    const [smx,smy]=this.safeMargins(.03),off=(line.hudOff||0)*fit;
    origin={x:Math.min(1-exR-smx,Math.max(smx-exL,origin.x)),y:Math.min(1-bot-off-smy,Math.max(top+smy,origin.y))+off};
    for(const o of this.fixedBoxes){if(frame<o.f0||frame>o.f1)continue;const [x0,y0,x1,y1]=o.box,cl=.025;
      if(origin.x+exR>x0&&origin.x+exL<x1&&origin.y+bot>y0-cl&&origin.y-top<y1+cl&&y1+top+cl<1-bot-smy)origin={x:origin.x,y:y1+top+cl};}
    return origin;
  }
  private syncMatte(){const sig=matteSignature(this.project);if(sig===this.matteSig)return;this.matteSig=sig;
    this.tracks=matteTracks(this.project,this.sourceTracks);this.occSource=undefined;}
  private unitCache?:{sig:string;units:Line[]};private buffers:HTMLCanvasElement[]=[];
  constructor(project:Project,server=''){this.project=project;this.server=server;}
  /** Studio only: why the matte did not load (the stage still draws, Behind uncut). */
  matteError?:string;
  async load(layer:Layer='composite'){
    const p=this.project;
    await loadFonts();
    if(p.analysis.tracks)this.tracks=await fetch(assetUrl(p,p.analysis.tracks,this.server)).then(r=>{if(!r.ok)throw new Error('Cannot load tracking data');return r.json();});
    this.sourceTracks=this.tracks;this.syncMatte();
    await Promise.all(Object.entries(p.analysis.headTracks||{}).map(async([source,path])=>{const tr=await json<Tracks>(assetUrl(p,path,this.server));if(tr)this.headTracks.set(source,tr);}));
    // Occupancy: server file when present; else a local fixture (until the server writes it); else tracks fallback.
    this.occupancy=p.analysis.occupancy?await json<Occupancy>(assetUrl(p,p.analysis.occupancy,this.server)):undefined;
    if(!this.occupancy&&p.id!=='sample')this.occupancy=await json<Occupancy>(`/fixtures/${encodeURIComponent(p.frame?.source?.projectId||p.id)}/occupancy.json`);
    if(p.frame?.crop&&!this.crop){this.crop=await json<CropData>(assetUrl(p,p.frame.crop,this.server));
      if(this.crop&&p.timing?.sceneOffset)this.crop={...this.crop,frames:this.crop.frames.map(f=>({...f,f:f.f+Math.round(p.timing!.sceneOffset!*this.crop!.fps)}))};}
    await this.loadFields();
    await this.loadSurfaceTracks();
    // Text-only renders (alpha overlay exports) load the footage too when a glyph fill reads its light.
    if(layer!=='composite'&&!this.hasFill())return;
    if(p.media.video)this.bg=await video(assetUrl(p,p.media.video.path,this.server));
    // Studio (draftMedia): a matte that will not load leaves Behind uncut (the studio flags it) instead of failing the stage.
    if(p.analysis.matte)this.matte=await video(assetUrl(p,`${p.analysis.matte.replace(/\/$/,'')}/fg.webm`,this.server)).catch(e=>{if(!this.draftMedia)throw e;this.matteError=String(e);return undefined;});
    if(this.draftMedia){const none=()=>undefined;const md=p.analysis.matte?.replace(/\/$/,'');[this.bgProxy,this.matteProxy,this.bgSeek,this.matteSeek]=await Promise.all([
      p.media.video?video(assetUrl(p,proxyPath(p.media.video.path),this.server)).catch(none):undefined,
      p.analysis.matte?video(assetUrl(p,`${p.analysis.matte.replace(/\/$/,'')}/fg_proxy.webm`,this.server)).catch(none):undefined,
      p.media.video?video(assetUrl(p,seekPath(p.media.video.path),this.server)).catch(none):undefined,
      md?video(assetUrl(p,`${md}/fg_seek.webm`,this.server)).catch(none):undefined]);}
    await Promise.all(p.shots.filter(s=>s.status==='done'&&s.video).map(async s=>this.shots.set(s.id,await video(assetUrl(p,s.video!,this.server)))));
  }
  /** Field data (motion, voice), loaded when the analysis exists. */
  flow?:FlowField;voice?:SongField;audio?:SongField;
  /** The field look.fields.source asks for (bass = analysis.audio, vocal = analysis.voice), else whichever exists. */
  songField(look:Look){return look.fields?.source==='vocal'?this.voice??this.audio:this.audio??this.voice;}
  async loadFields(){
    const p=this.project;
    if(p.analysis.flow&&!this.flow){const d=await json<FlowDoc>(assetUrl(p,p.analysis.flow,this.server));if(d)this.flow=new FlowField(d);}
    if(p.analysis.voice&&!this.voice){const d=await json<VoiceDoc>(assetUrl(p,p.analysis.voice,this.server));if(d)this.voice=songField(d);}
    if(p.analysis.audio&&!this.audio){const d=await json<AudioDoc>(assetUrl(p,p.analysis.audio,this.server));if(d)this.audio=songField(d);}
  }
  async loadSurfaceTracks(){
    const p=this.project;
    await Promise.all((p.surfaces||[]).filter(s=>s.track&&!this.surfaceTracks.has(`${s.id}:${s.track}`)).map(async s=>{
      const raw=await json<SurfaceTrack>(assetUrl(p,s.track!,this.server)),off=p.timing?.sceneOffset||0;
      this.surfaceTracks.set(`${s.id}:${s.track}`,raw&&off?{...raw,frames:raw.frames.map(f=>({...f,f:f.f+Math.round(off*raw.fps)}))}:raw||null);
    }));
  }
  dispose(){for(const v of [this.bg,this.matte,this.bgProxy,this.matteProxy,this.bgSeek,this.matteSeek,...this.shots.values()])if(v){v.pause();v.removeAttribute('src');v.load();}
    for(const m of this.layerMedia.values())void m.then(e=>{if(e instanceof HTMLVideoElement){e.pause();e.removeAttribute('src');e.load();}}).catch(()=>{});this.layerMedia.clear();
    for(const entry of this.mediaFrames)if(entry)entry.canvas.width=entry.canvas.height=0;this.mediaFrames=[];this.layoutPlans.clear();}
  occ(){
    this.syncMatte();
    const key=this.occupancy||this.tracks||this;const p=this.project;
    const portrait=p.height>p.width;
    if(!this.occSource||this.occSource.key!==key||this.occSource.crop!==this.crop||this.occSource.fps!==p.fps||this.occSource.portrait!==portrait){
      const l=matteLayer(p),bound=!!p.analysis.matteSource;
      const off=p.timing?.sceneOffset||0;
      const mapping=bound&&l?{frame:(f:number)=>{const t=matteTime(p,f/p.fps);return t==null?undefined:t*p.fps;},point:(f:number,x:number,y:number)=>mattePoint(p,l,f/p.fps,x,y,true)}:
        off?{frame:(f:number)=>f<off*p.fps?undefined:f-off*p.fps,point:(f:number,x:number,y:number):Point=>{const c=cropAt(this.crop,f);return c?[c.x+x*c.w,c.y+y*c.h]:[x,y];}}:undefined;
      this.occSource={key,crop:this.crop,fps:p.fps,portrait,src:new OccupancySource(bound&&!l?undefined:this.occupancy,bound||off?this.sourceTracks:this.tracks,p.fps,bound?undefined:this.crop,portrait,mapping)};
      if(bound&&!l)this.occSource.src=new OccupancySource(undefined,undefined,p.fps);
    }
    return this.occSource.src;
  }
  private look(){return lookOf(this.project);}
  private hasFill(){return !!fillOf(this.look())||Object.values(this.project.lineMeta||{}).some(m=>m.appearance?.fill&&m.appearance.fill!=='off');}
  private grade(){return gradeOf(this.project);}
  /** Beat grid for grade.flash (loaded on first use; null = none). flashNow: this frame's flash, 0..1. */
  private beats?:BeatGrid|null;private flashNow=0;
  /** Drawable units for the current project state (cached on everything that affects layout). */
  /** Word timing as drawn: the project with timing.leadMs applied (text leads the voice; media seeks are unaffected).
   *  units/layout/renderWords all read this, so the studio overlay and the render agree. this.project is never swapped. */
  timed():Project{return withLead(this.project);}
  units(ctx:CanvasRenderingContext2D):Line[]{
    const p=this.timed();const look=this.look();
    const sig=JSON.stringify([p.width,p.height,p.style,p.words,p.look,p.lineMeta,!!p.analysis.matte]);
    if(this.unitCache?.sig===sig)return this.unitCache.units;
    const units=look?lookUnits(ctx,p,look,!!p.analysis.matte):lines(ctx,p);
    for(const u of units){if(u.sub)continue;const look=lineLookOf(p,u.lineId);const m=p.lineMeta?.[u.lineId];const ai=m?.animIn??look?.animIn,ao=m?.animOut??look?.animOut;
      if(ai!=null)u.ain=Math.max(0,ai);if(ao!=null)u.aout=Math.max(0,ao);}
    this.unitCache={sig,units};return units;
  }
  /** Map a tracked source-space point into output space for this frame. */
  private planeFit=new Map<string,PlaneFit>();private planeFitCrop?:CropData;
  /**
   * Under a crop (reframe), where and when surface text goes so it is never drawn cut by the frame edge.
   * Candidates are (u,v) rectangles of the plane (24×12 vertex grid, 3% output margin). Each is shown only during
   * its longest run of frames in which it is fully in frame; rectangles are ranked by type size × run length ×
   * (1 − mean subject coverage)³, among those giving ≥50% of the largest type. undefined = whole quad stays in
   * frame (unchanged); 'hidden' = nothing usable. Cached per line; deterministic.
   */
  private visiblePlane(line:Line,s:Surface,tr:SurfaceTrack|undefined,marquee:boolean):PlaneFit{
    if(this.planeFitCrop!==this.crop){this.planeFit.clear();this.planeFitCrop=this.crop;}
    const ck=`${line.key}|${s.id}|${s.track}|${s.corners.flat().join(',')}|${marquee}`;
    if(this.planeFit.has(ck))return this.planeFit.get(ck);
    const p=this.project;const NU=24,NV=12,M=.03,W1=NU+2;
    const f0=Math.floor(line.start*p.fps),f1=Math.max(f0,Math.ceil(line.end*p.fps)-1);
    // Per frame: prefix sums of off-frame vertices and of subject-covered vertices (null = no pose that frame).
    const off:(Int32Array|null)[]=[],cov:(Int32Array|null)[]=[];
    for(let f=f0;f<=f1;f++){
      const corners=surfaceCornersAt(s,tr,f);if(!corners){off.push(null);cov.push(null);continue;}
      const H=squareToQuad(corners.map(([x,y])=>this.point(f,x,y)));const a=new Int32Array(W1*(NV+2)),b=new Int32Array(W1*(NV+2));
      const g=this.occ().at(f);
      for(let j=0;j<=NV;j++)for(let i=0;i<=NU;i++){const [x,y]=applyH(H,i/NU,j/NV);const k=(j+1)*W1+i+1,inF=x>=M&&x<=1-M&&y>=M&&y<=1-M;
        const c=inF&&g?g.data[Math.min(g.rows-1,Math.floor(y*g.rows))*g.cols+Math.min(g.cols-1,Math.floor(x*g.cols))]>.35:false;
        a[k]=(inF?0:1)+a[k-W1]+a[k-1]-a[k-W1-1];b[k]=(c?1:0)+b[k-W1]+b[k-1]-b[k-W1-1];}
      off.push(a);cov.push(b);
    }
    const sum=(t:Int32Array,i0:number,j0:number,i1:number,j1:number)=>t[(j1+1)*W1+i1+1]-t[j0*W1+i1+1]-t[(j1+1)*W1+i0]+t[j0*W1+i0];
    let res:PlaneFit;
    if(off.every(t=>!t))res=undefined;
    else if(off.every(t=>!t||sum(t,0,0,NU,NV)===0))res=undefined;
    else{
      const [sw,sh]=sourceSize(p,cropAt(this.crop,f0));const [kw,kh]=quadSize(s.corners.map(([x,y])=>[x*sw,y*sh] as Point));
      const minRun=Math.min(12,off.length);
      const cands:{r:PlaneRect;score:number;a:number;b:number;cov:number}[]=[];let best=0;
      for(let i0=0;i0<NU;i0++)for(let i1=i0+1;i1<=NU;i1++)for(let j0=0;j0<NV;j0++)for(let j1=j0+1;j1<=NV;j1++){
        if((i1-i0)*(j1-j0)<.04*NU*NV)continue;
        let run=0,ra=0,bestRun=0,ba=0;
        for(let k=0;k<off.length;k++){const t=off[k];if(t&&!sum(t,i0,j0,i1,j1)){if(!run)ra=k;run++;if(run>bestRun){bestRun=run;ba=ra;}}else run=0;}
        if(bestRun<minRun)continue;
        const nv=(i1-i0+1)*(j1-j0+1);let c=0;for(let k=ba;k<ba+bestRun;k++)c+=sum(cov[k]!,i0,j0,i1,j1)/nv;
        const du=(i1-i0)/NU,dv=(j1-j0)/NV;
        const score=marquee?dv*kh:Math.min(du*kw*.88/Math.max(1,line.total),dv*kh*.72/Math.max(1,line.height*1.1));
        cands.push({r:[i0/NU,j0/NV,i1/NU,j1/NV],score,a:f0+ba,b:f0+ba+bestRun-1,cov:c/bestRun});if(score>best)best=score;
      }
      const value=(c:typeof cands[number])=>c.score*(c.b-c.a+1)*(1-c.cov)**3;
      const pick=cands.filter(c=>c.score>=.5*best).sort((x,y)=>value(y)-value(x)||x.r[0]-y.r[0]||x.r[1]-y.r[1])[0];
      res=pick?{rect:pick.r,start:pick.a>f0?pick.a:undefined,end:pick.b<f1?pick.b:undefined}:'hidden';
    }
    this.planeFit.set(ck,res);return res;
  }
  private point(frame:number,x:number,y:number):Point{return toOut(cropAt(this.crop,Math.round(frame)),x,y);}
  /** Positions for every auto-placed unit, computed once per word/style/look/occupancy state. */
  /** Safe margins that survive the current look's lens warp (base fraction from each edge after warping). */
  private safeMargins(base:number):[number,number]{const p=this.project;return warpSafeMargins(p.width,p.height,(this.look()?.optics.lensWarp||0)*.35,base);}
  layout(ctx:CanvasRenderingContext2D):Map<string,LinePlacement>{
    const p=this.timed(),source=this.occ();
    const sig=JSON.stringify([p.width,p.height,p.fps,p.style,p.words,p.look,p.lineMeta,this.autoPlace,source.kind,!!this.crop]);
    if(this.plan?.sig===sig&&this.plan.source===source)return this.plan.map;
    if(this.cacheLayouts){
      if(this.layoutSource!==source){this.layoutPlans.clear();this.layoutSource=source;}
      const hit=this.layoutPlans.get(sig);
      if(hit){this.layoutPlans.delete(sig);this.layoutPlans.set(sig,hit);this.plan={sig,map:hit.map,source};this.fixedBoxes=hit.boxes;return hit.map;}
    }
    const reqs:LineRequest[]=[];const rank=(l:Line)=>l.role==='hero'?0:l.role==='sat'?2:1;
    const all=this.units(ctx).filter(l=>this.autoPlace&&(l.auto||l.role==='line'&&isAutoPlaced(l.words[0])||l.role==='hook'&&isAutoPlaced(l.words[0])))
      .sort((a,b)=>a.start-b.start||rank(a)-rank(b)||(a.key<b.key?-1:1));
    for(const l of all){
      const fit=l.bleed?1:Math.min(1,p.width*.88/Math.max(1,l.total));
      const hint=l.words[0].position||undefined;
      reqs.push({key:l.key,w:l.total*fit/p.width+.02,h:l.height*fit*1.12/p.height,canPromote:l.placement==='behind',f0:Math.round(l.start*p.fps),f1:Math.max(Math.round(l.start*p.fps),Math.round(l.end*p.fps)-1),
        hint:hint?{x:hint.x,y:hint.y}:undefined,tolerance:l.placement==='behind'?Math.min(.25,Math.max(.02,.02+1.1*(l.size/p.height-.12))):.02,...(l.req||{})});
    }
    // Fixed-position overlay/behind text is an obstacle for auto-placed lines (count-in vs HUD meta line).
    const autoKeys=new Set(all.map(l=>l.key));const obstacles:Placed[]=[];
    for(const l of this.units(ctx)){const pos=l.words[0].position;
      if(autoKeys.has(l.key)||!pos||(l.placement!=='overlay'&&l.placement!=='behind'))continue;
      const fit=l.bleed?1:Math.min(1,p.width*.88/Math.max(1,l.total));const w=l.total*fit/p.width,h=l.height*fit/p.height;const al=l.metrics[0].style.align;
      const x0=al==='left'?pos.x:al==='right'?pos.x-w:pos.x-w/2;
      obstacles.push({box:[x0,pos.y-h/2,x0+w,pos.y+h/2],f0:Math.round(l.start*p.fps),f1:Math.max(Math.round(l.start*p.fps),Math.round(l.end*p.fps)-1)});}
    const map=autoPlace(reqs,source,p.width/p.height,obstacles,this.safeMargins(.06));
    this.plan={sig,map,source};this.fixedBoxes=obstacles;
    if(this.cacheLayouts){this.layoutPlans.set(sig,{map,boxes:obstacles});if(this.layoutPlans.size>16)this.layoutPlans.delete(this.layoutPlans.keys().next().value!);}
    return map;
  }
  /** Draw text units of one depth layer at time t (fractional frame `ft` for motion-blur sub-samples). */
  private renderWords(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',blend:boolean,ft=frame){
    const p=this.timed();const plan=this.layout(ctx);const look=this.look();
    const crawl=look?.motion==='marquee';
    if(crawl&&this.subPass!==true&&this.freePass!==true)this.drawTicker(ctx,t,frame,subset,ft);
    // Glyph fill: pinned to the shot (not through the motion field), under the units, never in the crisp subtitle pass.
    if(look&&this.hasFill()&&this.env&&this.subPass!==true&&this.freePass!==true)this.drawFill(ctx,t,frame,subset,ft);
    for(const line of this.units(ctx)){
      if(this.passLines&&!this.passLines.has(line.lineId))continue;
      const look=lineLookOf(p,line.lineId);
      if(t<line.start||t>=line.end)continue;
      if(crawl&&!line.sub&&line.role!=='hud')continue;
      if(this.subPass!==undefined&&!!line.sub!==this.subPass)continue;
      // Motion field: only free-floating lines drift/ripple; walls and head-anchored labels are already locked to the shot.
      if(this.freePass!==undefined&&(line.placement!=='surface'&&line.placement!=='anchor'&&line.role!=='hud')!==this.freePass)continue;
      const placement=line.placement;const behind=placement==='surface'||placement==='behind'&&!plan.get(line.key)?.front;
      if(subset==='behind'&&!behind||subset==='front'&&behind)continue;
      const first=line.words[0];
      const marqueeK=look?.motion==='marquee'&&line.role!=='hud'?Math.min(1,Math.max(0,(t-line.start)/Math.max(.1,line.end-line.start))):undefined;
      if(placement==='surface'){
        const s=p.surfaces?.find(x=>x.id===first.surfaceId);if(!s)continue;
        const tr=s.track?this.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;
        const corners=surfaceCornersAt(s,tr,ft);if(!corners)continue;
        const quad=corners.map(([x,y])=>{const [ox,oy]=this.point(frame,x,y);return [ox*p.width,oy*p.height] as Point;});
        // Hidden once the quad leaves the (crop) frame entirely.
        if(quad.every(([x])=>x<0)||quad.every(([x])=>x>p.width)||quad.every(([,y])=>y<0)||quad.every(([,y])=>y>p.height))continue;
        const fitp=this.crop?this.visiblePlane(line,s,tr,marqueeK!==undefined):undefined;
        if(fitp==='hidden'||fitp?.end!==undefined&&frame>fitp.end||fitp?.start!==undefined&&frame<fitp.start)continue;const sub=fitp?.rect;
        drawSurfaceLine(ctx,p,line,s,quad,t,frame,blend,look,marqueeK,sub,cropAt(this.crop,frame),look?.wall==='spray'||look?.finish==='neon'||look?.wallBlend?{env:this.env,buf:i=>this.buffer(i),lightOnly:this.lightOnly}:undefined);continue;
      }
      let fit=line.bleed?1:Math.min(1,p.width*.88/Math.max(1,line.total));
      let origin=first.position||{x:.5,y:.72};let anchorPx:Point|undefined;
      const auto=plan.get(line.key);
      if(auto){
        fit*=auto.scale;const align=line.metrics[0].style.align;const half=line.total*fit/2/p.width;
        origin={x:auto.cx+(align==='left'?-half:align==='right'?half:0),y:auto.cy};
      }
      if(placement==='anchor'){
        const anchor=first.anchor||{trackId:'person0',dx:0,dy:-.1};
        // No person at this frame: hold / interpolate the head, or with no track at all a screen label (no leader).
        const head=this.head(ft/p.fps,anchor.trackId);const point=head.point;const [cx,cy]=[point.cx,point.cy];
        const target=this.head(ft/p.fps,anchor.trackId,this.project,hudPointer(this.project,line.lineId).point).point;
        anchorPx=head.state==='none'?undefined:[target.cx*p.width,target.cy*p.height];origin={x:cx+anchor.dx,y:cy+anchor.dy};
        origin=this.anchorOrigin(line,fit,origin,frame,anchor.trackId);
      }
      const pm=p.roleModel==='placement';const opts:DrawOpts=look?{paper:look.id==='paper-cut',roles:pm,shadow:look.texture==='paper'?1:look.halo!=null&&!line.sub?look.halo:(placement==='behind'||pm&&!line.sub)&&look.palette.shadow?.5:0,shadowColor:look.palette.shadow,hard:look.texture==='paper',karaoke:look.palette.accent,
          note:!noteBlocksOn(look)&&p.lineMeta?.[line.lineId]?.boxes!==true?null:{fill:look.palette.note||'#8d93f2',stroke:look.palette.shadow||'#5a5fd6',glow:look.noteGlow},sparkle:(line.role==='hook'||line.role==='hero')?look.optics.sparkle:undefined,motion:look.intensity,flicker:look.flicker,
          voice:this.songField(look)&&look.fields?.voice&&line.role!=='hud'&&!line.sub?{field:this.songField(look)!,amount:look.fields.voice,shift:p.media.audioClip?shiftOf(clipOf(p)):0}:undefined,meta:p.lineMeta||undefined,enter:look.enter,clean:!lookIsFrozen(look)&&look.finish!=='neon'}
        :{shadow:first.style?.shadow??(placement==='behind'?.5:0),meta:p.lineMeta||undefined};
      ctx.save();ctx.translate(origin.x*p.width,origin.y*p.height);ctx.scale(fit,fit);
      if(line.card&&look?.palette.card&&marqueeK===undefined)drawCard(ctx,line,t,look.palette.card,.75,line.sub?undefined:look.enter,look.cardPad);
      if(marqueeK!==undefined&&line.card&&look?.palette.card){
        // LED band: the card becomes a full-width strip the line scrolls through.
        const pad=line.size*.32*(look.cardPad??1);ctx.fillStyle=look.palette.card;ctx.fillRect(-origin.x*p.width/fit,-line.height/2-pad*.75,p.width/fit,line.height+pad*1.5);}
      if(marqueeK!==undefined){
        // LED ticker: the line scrolls right→left through a fixed band over its duration.
        const band=Math.max(line.total*.6,p.width*.7/fit);ctx.beginPath();ctx.rect(-band/2,-line.height,band,line.height*2);ctx.clip();
        opts.scroll=(band+line.total)/2-marqueeK*(band+line.total);
      }
      const hud=line.words.some(w=>w.preset==='hud');
      const hudColor=look?hudLine(look):undefined;
      if(hud&&!(pm&&line.card))this.drawHud(ctx,line,t,frame,fit,origin,anchorPx,first.anchor?.trackId||'person0',true,hudColor);
      this.drawUnit(ctx,line,t,frame,fit,opts,look);
      if(hud)this.drawHud(ctx,line,t,frame,fit,origin,anchorPx,first.anchor?.trackId||'person0',false,hudColor);
      ctx.restore();
    }
  }
  /** Per-unit draw site for screen text (context already at the unit's origin, scaled by fit). One place to hook
   *  per-unit/per-glyph effects. Neon look: tubes (subtitles and HUD stay crisp). */
  private drawUnit(ctx:CanvasRenderingContext2D,line:Line,t:number,frame:number,fit:number,opts:DrawOpts,look?:Look){
    if(look?.finish==='neon'&&!line.sub&&line.role!=='hud'){if(!this.lightOnly)drawMount(ctx,line,line.key);drawTubes(ctx,line,t,frame,fit,{...opts,shadow:0,plain:true},true);return;}
    if(look?.wall==='spray'&&!line.sub&&line.role!=='hud'){
      // Spray paint on the background: drawn in a screen buffer, then overspray, drips and the wall's own light.
      const b=this.buffer(28),g=b.getContext('2d')!;g.setTransform(ctx.getTransform());
      drawWords(g,line,t,frame,{...opts,shadow:0,plain:true});drawSprayMarks(g,line,t,look.drips??.5,line.role!=='sat'&&line.role!=='verse');sprayWear(g,line,line.key);
      const m=ctx.getTransform();sprayify(b,this.buffer(29),line.size*Math.hypot(m.a,m.b),this.env);
      ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha*=.94;ctx.drawImage(b,0,0);ctx.restore();return;
    }
    drawWords(ctx,line,t,frame,opts);
  }
  private glyph?:GlyphFill;
  /** v4.3 glyph fill (looks.ts lineIsFilled): the filled lines of this frame as letter grids lit by this.env (the graded
   *  footage), masked by the matte (subject / world) or warped onto their wall. See glyph.ts. */
  private drawFill(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',ft:number){
    const p=this.timed();const env=this.env;if(!env)return;
    const groups=new Map<string,Word[]>();
    for(const w of p.words){if(w.placement==='inworld'||!wordIsShown(p,w))continue;const key=`${w.lineId}:${w.placement}`;const g=groups.get(key);if(g)g.push(w);else groups.set(key,[w]);}
    const lines:FillLine[]=[];
    for(const [key,ws] of groups){if(this.passLines&&!this.passLines.has(ws[0].lineId)||!lineIsFilled(p,ws[0].lineId))continue;
      lines.push({key,words:ws,start:Math.min(...ws.map(w=>w.start)),end:Math.max(...ws.map(w=>w.end)),surfaceId:ws[0].placement==='surface'?ws[0].surfaceId:null});}
    if(!lines.length)return;
    const quadOf=(id:string)=>{const s=p.surfaces?.find(x=>x.id===id);if(!s)return undefined;
      const tr=s.track?this.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;const corners=surfaceCornersAt(s,tr,ft);if(!corners)return undefined;
      const quad=corners.map(([x,y])=>{const [ox,oy]=this.point(frame,x,y);return [ox*p.width,oy*p.height] as Point;});
      if(quad.every(([x])=>x<0)||quad.every(([x])=>x>p.width)||quad.every(([,y])=>y<0)||quad.every(([,y])=>y>p.height))return undefined;
      return quadIsConvex(quad)?quad:undefined;};
    const matte=this.matte;const m=matte?(g:CanvasRenderingContext2D,w:number,h:number)=>this.drawMediaTo(g,matte,frame,w,h):undefined;
    for(const line of lines){const look=lineLookOf(p,line.words[0].lineId)!;const fill=fillOf(look)!;
      (this.glyph||(this.glyph=new GlyphFill())).draw(ctx,{look,fill,W:p.width,H:p.height,t,frame,fps:p.fps,env,matte:m,lines:[line],quadOf,subset,draft:!this.heavyOptics});}
  }
  /** A media frame through the crop, scaled to w×h. */
  private drawMediaTo(g:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number,w:number,h:number){
    if(v===this.matte&&this.project.analysis.matteSource){g.save();g.scale(w/this.project.width,h/this.project.height);this.drawMedia(g,v,frame);g.restore();return;}
    const c=cropAt(this.crop,frame);
    if(c){const vw=v.videoWidth,vh=v.videoHeight;g.drawImage(v,c.x*vw,c.y*vh,c.w*vw,c.h*vh,0,0,w,h);}else g.drawImage(v,0,0,w,h);
  }
  /** Ticker stream: every shown (non-subtitle) word in time order with its entry time, so words enter the display on
   *  their timing and never overlap: enter_i = max(start_i, enter_{i-1} + (width_{i-1} + gap) / speed). Cached. */
  private tickerCache=new Map<string,{sig:string;items:{text:string;enter:number;w:number;start:number}[];font:string}>();
  private tickerStream(look:Look,lane:'surface'|'behind'|'front'){
    const p=this.timed();const sig=JSON.stringify([p.words,p.lineMeta,p.look]);const cached=this.tickerCache.get(lane);if(cached?.sig===sig)return cached;
    const font='led5x7';
    const ws=p.words.filter(w=>wordIsShown(p,w)&&!isSubtitleLine(p,w.lineId)&&(lane==='surface'?w.placement==='surface':lane==='behind'?w.placement==='behind':w.placement==='overlay')).sort((a,b)=>a.start-b.start);
    // Lines, not words: each line crawls as one string, its words packed at TICKER_GAP_WORD em.
    const byLine=new Map<string,Word[]>();for(const w of ws){const g=byLine.get(w.lineId);if(g)g.push(w);else byLine.set(w.lineId,[w]);}
    type TL={words:{text:string;w:number;off:number}[];start:number;last:number;width:number;key:string};const tls:TL[]=[];
    for(const lw of [...byLine.values()].sort((a,b)=>a[0].start-b[0].start)){let off=0;
      const words=lw.map(w=>{const text=applyCase(w.text,look.font.heroCase);const x={text,w:ledWidth(text)/7,off};off+=x.w+TICKER_GAP_WORD;return x;});// em (7 LED rows)
      const key=words.map(x=>x.text.toLowerCase()).join(' ');
      // The same line shown twice (wall title + HUD label of one sung phrase) enters once.
      if(tls.some(o=>o.key===key&&Math.abs(o.start-lw[0].start)<3))continue;
      tls.push({words,start:lw[0].start,last:lw[lw.length-1].start,width:off-TICKER_GAP_WORD,key});}
    // Phrases: lines sung back to back (< 1.5 s from the previous line's last word) crawl evenly, TICKER_GAP_LINE em
    // apart; the phrase starts as late as needed (≤ 0.9 s) so no line ever shows before its first word is sung.
    // A pause in the singing (or a line that cannot fit) starts a new phrase, which enters on its own onset (late if
    // the previous phrase is still entering; never dropped).
    const items:{text:string;enter:number;w:number;start:number}[]=[];let free=-Infinity;const S=TICKER_SPEED;
    for(let i=0;i<tls.length;){
      let e0=Math.max(tls[i].start,free+TICKER_GAP_LINE/S);const mem=[i],offs=[0];let off=tls[i].width/S,j=i+1;
      for(;j<tls.length;j++){if(tls[j].start-tls[j-1].last>1.5)break;const o=off+TICKER_GAP_LINE/S,e=Math.max(e0,tls[j].start-o);
        if(e-Math.max(tls[i].start,free+TICKER_GAP_LINE/S)>.9)break;e0=e;mem.push(j);offs.push(o);off=o+tls[j].width/S;}
      mem.forEach((k,m)=>{for(const x of tls[k].words)items.push({text:x.text,enter:e0+offs[m]+x.off/S,w:x.w,start:tls[k].start});});
      free=e0+off;i=j;}
    const value={sig,items,font};this.tickerCache.set(lane,value);return value;
  }
  /** LED dot-matrix ticker: the word stream crawls right→left through a display at TICKER_SPEED em/s. Mounted on the
   *  wall (the union of the surfaces in use, middle band, behind the subject) when there is one, else a screen band. */
  private drawTicker(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',ft:number){
    if(subset!=='front'){this.drawTickerLane(ctx,t,frame,'surface',ft);this.drawTickerLane(ctx,t,frame,'behind',ft);}
    if(subset!=='behind')this.drawTickerLane(ctx,t,frame,'front',ft);
  }
  private drawTickerLane(ctx:CanvasRenderingContext2D,t:number,frame:number,lane:'surface'|'behind'|'front',ft:number){
    const p=this.timed();const look=this.look()!;const {items}=this.tickerStream(look,lane);
    const live=items.some(it=>t>=it.enter-.05&&t<it.enter+(it.w+40)/TICKER_SPEED);if(!live)return;
    // Surfaces in use around now: those with a surface word on screen from 3 s before its onset to 0.5 s after its end.
    const ids=lane==='surface'?[...new Set(p.words.filter(w=>w.placement==='surface'&&w.surfaceId&&t>w.start-3&&t<w.end+.5).map(w=>w.surfaceId!))]:[];
    const quads:Point[][]=[];
    for(const id of ids){const s=p.surfaces?.find(x=>x.id===id);if(!s)continue;const tr=s.track?this.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;
      const c=surfaceCornersAt(s,tr,ft);if(c)quads.push(c.map(([x,y])=>{const [ox,oy]=this.point(frame,x,y);return [ox*p.width,oy*p.height] as Point;}));}
    const mounted=quads.length>0;if(lane==='surface'&&!mounted)return;
    let dst:Point[];let bw:number,bh:number;
    if(mounted){
      // Union = bounding rect in the first wall's plane (staggered rows would otherwise shear the band).
      const ref=quads[0];if(!quadIsConvex(ref))return;const Hi=invertH(squareToQuad(ref));
      const uv=quads.flat().map(([x,y])=>applyH(Hi,x,y));
      const U=subQuad(ref,[Math.min(...uv.map(q=>q[0])),Math.min(...uv.map(q=>q[1])),Math.max(...uv.map(q=>q[0])),Math.max(...uv.map(q=>q[1]))]);
      if(!quadIsConvex(U))return;const [uw,uh]=quadSize(U);const hh=Math.min(.34,uw*.16/Math.max(1,uh));dst=subQuad(U,[.03,.5-hh/2,.97,.5+hh/2]);
      bw=uw*.94;bh=uh*hh;}
    else{bh=p.height*.13;bw=p.width;dst=[[0,p.height*.74],[p.width,p.height*.74],[p.width,p.height*.74+bh],[0,p.height*.74+bh]];}
    // 9 LED rows: the 5×7 glyphs on rows 1–7 with a dark row above and below.
    const rows=9,pitch=Math.max(2,bh/rows),cols=Math.ceil(bw/pitch);
    // 1. lit cells: the stream crawls one whole LED column at a time (em = 7 rows).
    const lit=new Uint8Array(cols*rows);const em=7;
    for(const it of items){const x0=Math.round(cols-(t-it.enter)*TICKER_SPEED*em);if(x0>=cols||x0+it.w*em<0)continue;
      let cx=x0;for(const ch of it.text){const gl=ledGlyph(ch);if(!gl){cx+=LED_SPACE+1;continue;}const rs=gl.split(' '),gw=rs[0].length;
        for(let r=0;r<7;r++)for(let c=0;c<gw;c++)if(rs[r][c]==='1'){const X=cx+c;if(X>=0&&X<cols)lit[(r+1)*cols+X]=1;}
        cx+=gw+1;}}
    // 2. display in its own pixels: housing, faint unlit dots, round lit dots with a hot centre, a tight bloom.
    const cs=Math.min(16,Math.max(3,pitch)),W=Math.max(16,Math.round(cols*cs)),H=Math.max(4,Math.round(rows*cs));
    const d=this.tickerDisp||(this.tickerDisp=document.createElement('canvas'));d.width=W;d.height=H;const g=d.getContext('2d')!;
    const ledColor=look.palette.text,housing=look.palette.card||'#0b0703';
    g.fillStyle=housing;g.fillRect(0,0,W,H);
    const dots=(gx:CanvasRenderingContext2D,on:boolean,rad:number)=>{gx.beginPath();for(let r=0;r<rows;r++)for(let c=0;c<cols;c++)if(!!lit[r*cols+c]===on){
      const x=(c+.5)*W/cols,y=(r+.5)*H/rows;gx.moveTo(x+rad,y);gx.arc(x,y,rad,0,Math.PI*2);}gx.fill();};
    g.save();g.globalAlpha=.1;g.fillStyle=ledColor;dots(g,false,cs*.38);g.restore();
    const L=this.tickerMask||(this.tickerMask=document.createElement('canvas'));L.width=W;L.height=H;const lg=L.getContext('2d')!;
    lg.fillStyle=ledColor;dots(lg,true,cs*.44);lg.fillStyle=mixHex(ledColor,'#ffffff',.55);dots(lg,true,cs*.2);
    g.save();g.globalCompositeOperation='lighter';g.filter=`blur(${(cs*.55).toFixed(1)}px)`;g.globalAlpha=.55;g.drawImage(L,0,0);g.filter='none';g.globalAlpha=1;g.drawImage(L,0,0);g.restore();
    // bezel
    g.strokeStyle='rgba(255,255,255,.08)';g.lineWidth=Math.max(1,cs*.5);g.strokeRect(0,0,W,H);
    drawWarped(ctx,d,dst);
  }
  private tickerMask?:HTMLCanvasElement;private tickerDisp?:HTMLCanvasElement;
  /** this frame's graded footage (graffiti modulation, neon spill); undefined outside composite renders. */
  private env?:HTMLCanvasElement;
  /** Neon light pass in progress: draw tubes only (no hardware). */
  private lightOnly=false;
  /** Neon light of this frame (centroid, mean colour, power 0..1, lowest lit row), from the light pass. */
  private light?:{x:number;y:number;color:number[];power:number;bottom:number};private lightSmall?:HTMLCanvasElement;
  /** Neon signs light the scene: the tubes (behind layer, no hardware) blurred into a wide spill, multiplied by the
   *  footage's luminance (walls take light by their own albedo), plus a squashed wet-floor reflection; added to the frame. */
  private lightPass(ctx:CanvasRenderingContext2D,t:number,frame:number,amount:number){
    const p=this.project;const L=this.buffer(20);const lg=L.getContext('2d')!;
    this.lightOnly=true;try{this.renderWords(lg,t,frame,'behind',false);}finally{this.lightOnly=false;}
    const sw=64,sh=Math.max(1,Math.round(64*p.height/p.width));const sm=this.lightSmall||(this.lightSmall=document.createElement('canvas'));sm.width=sw;sm.height=sh;
    const sg=sm.getContext('2d',{willReadFrequently:true})!;sg.clearRect(0,0,sw,sh);sg.drawImage(L,0,0,sw,sh);const d=sg.getImageData(0,0,sw,sh).data;
    let W=0,X=0,Y=0,R=0,G=0,B=0,bottom=0;
    for(let i=0;i<sw*sh;i++){const a=d[i*4+3]/255;if(a<.03)continue;const w=a*(d[i*4]+d[i*4+1]+d[i*4+2])/765;W+=w;X+=w*(i%sw);Y+=w*Math.floor(i/sw);R+=w*d[i*4];G+=w*d[i*4+1];B+=w*d[i*4+2];bottom=Math.max(bottom,Math.floor(i/sw));}
    if(W<.3){this.light=undefined;return;}
    const light={x:(X/W+.5)/sw,y:(Y/W+.5)/sh,color:[R/W,G/W,B/W],power:Math.min(1,Math.sqrt(W/(sw*sh))*5),bottom:(bottom+1)/sh};this.light=light;
    const S=this.buffer(21),g=S.getContext('2d')!;g.fillStyle='#000';g.fillRect(0,0,S.width,S.height);g.globalCompositeOperation='lighter';
    g.filter=`blur(${(p.height*.045).toFixed(1)}px)`;g.drawImage(L,0,0);g.drawImage(L,0,0);
    g.filter=`blur(${(p.height*.16).toFixed(1)}px)`;g.drawImage(L,0,0);g.drawImage(L,0,0);g.drawImage(L,0,0);g.filter='none';
    // Wet floor: the sign mirrored below its lowest lit row, squashed and blurred, fading out downward.
    const floor=Math.max(light.bottom*p.height+p.height*.04,p.height*.62);
    if(floor<p.height*.97){const T=this.buffer(22),tg=T.getContext('2d')!;tg.setTransform(1,0,0,-.55,0,floor*1.55);tg.filter=`blur(${(p.height*.012).toFixed(1)}px)`;tg.drawImage(L,0,0);tg.filter='none';tg.setTransform(1,0,0,1,0,0);
      const gr=tg.createLinearGradient(0,floor,0,floor+p.height*.3);gr.addColorStop(0,'rgba(0,0,0,.55)');gr.addColorStop(1,'rgba(0,0,0,0)');
      tg.globalCompositeOperation='destination-in';tg.fillStyle=gr;tg.fillRect(0,0,T.width,T.height);tg.globalCompositeOperation='source-over';g.drawImage(T,0,0);}
    // Ambient: the whole scene picks up the sign's colour (scaled by its power), then everything is multiplied by the
    // footage's luminance so lit surfaces take the light and dark sky stays dark.
    g.fillStyle=`rgb(${light.color.map(c=>Math.round(c)).join(',')})`;g.globalAlpha=Math.min(.6,.45*Math.max(.55,light.power));g.fillRect(0,0,S.width,S.height);g.globalAlpha=1;
    g.globalCompositeOperation='multiply';g.filter='grayscale(1) brightness(1.7)';if(this.env)g.drawImage(this.env,0,0);g.filter='none';g.globalCompositeOperation='source-over';
    ctx.save();ctx.globalCompositeOperation='lighter';ctx.globalAlpha=Math.min(1,amount);ctx.drawImage(S,0,0);ctx.restore();
  }
  /** Neon relights the subject: a coloured rim on the matte edges that face the sign (matte minus itself shifted toward
   *  the light) and a soft colour cast, both scaled by the sign's power and its distance to the subject. */
  private relight(ctx:CanvasRenderingContext2D,frame:number,amount:number){
    const l=this.light;if(!l||!this.matte)return;const p=this.project;
    const M=this.buffer(23);const mg=M.getContext('2d')!;this.drawMedia(mg,this.matte,frame);
    const a=anchorAt(this.tracks,'person0',frame);const [sx,sy]=a?(p.analysis.matteSource?[a.cx,a.cy]:this.point(frame,a.cx,a.cy)):[.5,.5];
    let vx=(l.x-sx)*p.width,vy=(l.y-sy)*p.height;const n=Math.hypot(vx,vy)||1;const dist=n/Math.hypot(p.width,p.height);vx/=n;vy/=n;
    const f=Math.max(.2,Math.min(1,1.3-1.6*dist))*l.power*amount;if(f<.01)return;
    const col=`rgb(${l.color.map(c=>Math.round(Math.min(255,c*1.1+25))).join(',')})`;const dd=p.height*.016;
    const R=this.buffer(24),rg=R.getContext('2d')!;rg.drawImage(M,0,0);rg.globalCompositeOperation='destination-out';rg.drawImage(M,-vx*dd,-vy*dd);
    rg.globalCompositeOperation='source-in';rg.fillStyle=col;rg.fillRect(0,0,R.width,R.height);rg.globalCompositeOperation='source-over';
    const Wb=this.buffer(25),wg=Wb.getContext('2d')!;wg.filter=`blur(${(dd*.8).toFixed(1)}px)`;wg.drawImage(R,0,0);wg.drawImage(R,0,0);wg.filter='none';
    wg.globalCompositeOperation='destination-in';wg.drawImage(M,0,0);wg.globalCompositeOperation='source-over';
    ctx.save();ctx.globalCompositeOperation='lighter';ctx.globalAlpha=Math.min(1,f*1.2);ctx.drawImage(Wb,0,0);
    mg.globalCompositeOperation='source-in';mg.fillStyle=col;mg.fillRect(0,0,M.width,M.height);mg.globalCompositeOperation='source-over';
    ctx.globalCompositeOperation='soft-light';ctx.globalAlpha=Math.min(.4,f*.3);ctx.drawImage(M,0,0);ctx.restore();
  }
  private drawHud(ctx:CanvasRenderingContext2D,line:Line,t:number,frame:number,fit:number,origin:{x:number;y:number},anchorPx:Point|undefined,trackId:string,backdrop:boolean,color='#d8ff62'){
    const p=this.project;const size=line.size;const align=line.metrics[0].style.align;
    const x0=-(align==='center'?line.total/2:align==='right'?line.total:0);const pad=size*.28;
    // Beat jitter: a few frames of deterministic shake after each word onset.
    // ('type' entrance: steady, no shake.)
    const onset=this.look()?.enter!=='type'&&line.words.some(w=>{const k=Math.round((t-w.start)*p.fps);return k>=0&&k<3;});
    const jx=onset?(hash01(`${line.key}:${frame}`)-.5)*size*.12:0;
    const bx=x0-pad+jx,by=-line.height/2-size*.18,bw=line.total+2*pad,bh=line.height+size*.36;
    ctx.save();ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=Math.max(1.5*this.previewScale,p.height/480)/fit;ctx.globalAlpha=onset?1:.92;
    if(backdrop){ctx.fillStyle='rgba(8,10,6,.45)';ctx.fillRect(bx,by,bw,bh);ctx.restore();return;}
    bracket(ctx,bx,by,bw,bh,Math.min(bw,bh)*.32);
    const pointer=hudPointer(p,line.lineId);
    if(anchorPx){
      // Leader from the nearest box edge to the tracked point.
      const ax=(anchorPx[0]-origin.x*p.width)/fit,ay=(anchorPx[1]-origin.y*p.height)/fit;
      const ex=Math.min(bx+bw,Math.max(bx,ax)),ey=Math.min(by+bh,Math.max(by,ay));
      ctx.save();
      if(pointer.connector&&Math.hypot(ax-ex,ay-ey)>size*.3){ctx.strokeStyle=pointer.connectorColor;ctx.beginPath();ctx.moveTo(ex,ey);ctx.lineTo(ax,ay);ctx.stroke();}
      if(pointer.dot){ctx.strokeStyle=pointer.dotColor;ctx.fillStyle=pointer.dotColor;ctx.beginPath();ctx.arc(ax,ay,Math.max(3*this.previewScale,size*.09),0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.arc(ax,ay,Math.max(1.2*this.previewScale,size*.03),0,Math.PI*2);ctx.fill();}
      ctx.restore();
    }
    if(line.hudSlot){ctx.restore();return;}
    const tag=Math.max(13*this.previewScale/fit,size*.36);ctx.font=`700 ${tag}px "Space Mono"`;ctx.textBaseline='bottom';ctx.textAlign='left';
    const label=`${trackId.toUpperCase()} · F${String(frame).padStart(4,'0')} · ${anchorPx?'LIVE':'LOST'}`;
    const tw=ctx.measureText(label).width+tag*.6;
    ctx.fillRect(bx,by-tag*1.25,tw,tag*1.25);ctx.fillStyle='#0b0d09';ctx.fillText(label,bx+tag*.3,by-tag*.12);
    ctx.restore();
  }
  private buffer(i:number){
    const p=this.project;let b=this.buffers[i];if(!b){b=document.createElement('canvas');this.buffers[i]=b;}
    if(b.width!==p.width)b.width=p.width;if(b.height!==p.height)b.height=p.height;
    const g=b.getContext('2d')!;g.setTransform(1,0,0,1,0,0);g.globalAlpha=1;g.globalCompositeOperation='source-over';g.filter='none';g.clearRect(0,0,b.width,b.height);return b;
  }
  /** Screen-space direction of subject motion (for chroma fringing); x when static. */
  private velocityDir(frame:number):[number,number]{
    const a=anchorAt(this.tracks,'person0',frame-1),b=anchorAt(this.tracks,'person0',frame+1);const p=this.project;
    if(!a||!b)return [1,0];const dx=(b.cx-a.cx)*p.width,dy=(b.cy-a.cy)*p.height;const l=Math.hypot(dx,dy);return l>1?[dx/l,dy/l]:[1,0];
  }
  /**
   * Text pass with the look's optics, in the brief's order: motion blur → chroma → (lens warp) → glow.
   * Without a look this is a direct draw (v2 path, pixel-identical).
   */
  private textPass(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',blend:boolean){
    const look=this.look();const p=this.project;
    if(!look){this.renderWords(ctx,t,frame,subset,blend);return;}
    // Subtitle register: kept out of the optics chain (no blur/chroma/warp/glow) and drawn crisp on top.
    this.subPass=false;try{
      for(const group of this.appearancePasses()){
        // A project may contain many styled clips, but only live clips need an optics pass this frame.
        if(look.motion!=='marquee'&&!group.ranges.some(([a,b])=>t>=a-1/p.fps&&t<b+.3))continue;
        this.passLines=group.ids;
        this.opticsPass(ctx,t,frame,subset,blend,group.look,group.look.optics,p);
      }
    }finally{this.subPass=undefined;this.passLines=undefined;}
    if(subset!=='behind'){this.subPass=true;try{this.renderWords(ctx,t,frame,'front',blend);}finally{this.subPass=undefined;}}
  }
  private subPass?:boolean;private freePass?:boolean;
  private passLines?:Set<string>;
  private appearanceCache?:{sig:string;groups:{look:Look;ids:Set<string>;ranges:[number,number][]}[]};
  /** Only split the costly optics pass when clips actually use different effects. Fonts and colours share a pass. */
  private appearancePasses(){
    const p=this.timed();const sig=JSON.stringify([p.look,p.lineMeta,p.words.map(w=>[w.lineId,w.start,w.end])]);
    if(this.appearanceCache?.sig===sig)return this.appearanceCache.groups;
    const ranges=new Map<string,[number,number]>();for(const w of p.words){const r=ranges.get(w.lineId);if(r){r[0]=Math.min(r[0],w.start);r[1]=Math.max(r[1],w.end);}else ranges.set(w.lineId,[w.start,w.end]);}
    const groups:{look:Look;ids:Set<string>;ranges:[number,number][]}[]=[];let previous='';
    for(const [id,range] of ranges){const look=lineLookOf(p,id)!;
      const key=JSON.stringify([look.optics,look.raster,look.fields?.motion,look.texture]);
      if(key!==previous){groups.push({look,ids:new Set(),ranges:[]});previous=key;}
      groups[groups.length-1].ids.add(id);groups[groups.length-1].ranges.push(range);
    }
    this.appearanceCache={sig,groups};return groups;
  }
  private opticsPass(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',blend:boolean,look:Look,o:Look['optics'],p:Project){
    const buf=this.buffer(0);const g=buf.getContext('2d')!;
    const mb=this.heavyOptics?o.motionBlur||0:0;
    const fm=look.fields?.motion||0,moving=fm>0&&!!this.flow;
    const draw=(gx:CanvasRenderingContext2D)=>{
      if(mb>0){
        // N sub-samples across a shutter of 0.5 frame × motionBlur, averaged exactly with additive 1/N weights.
        const N=MOTION_BLUR_SAMPLES;const tmp=this.buffer(1);const tg=tmp.getContext('2d')!;const shutter=.5*mb;
        for(let k=0;k<N;k++){const df=(k/(N-1)-.5)*shutter;tg.setTransform(1,0,0,1,0,0);tg.clearRect(0,0,buf.width,buf.height);
          this.renderWords(tg,t+df/p.fps,frame,subset,false,frame+df);gx.globalAlpha=1/N;gx.globalCompositeOperation='lighter';gx.drawImage(tmp,0,0);}
        gx.globalAlpha=1;gx.globalCompositeOperation='source-over';
      }else this.renderWords(gx,t,frame,subset,false);
    };
    if(moving){this.freePass=true;try{draw(g);}finally{this.freePass=undefined;}}else draw(g);
    let src:HTMLCanvasElement=buf;
    if(look.texture==='paper'&&look.id!=='paper-cut'){g.globalCompositeOperation='destination-out';g.globalAlpha=.55;g.drawImage(erosionMask(`paper:${p.id}`,Math.ceil(buf.width/2),Math.ceil(buf.height/2),.6,3),0,0,buf.width,buf.height);g.globalAlpha=1;g.globalCompositeOperation='source-over';}
    if(moving){
      // Motion field: free lines drift with the camera (inertia) and are pushed like liquid by what moves through them;
      // pinned lines (walls, anchors, HUD) are drawn on top unmoved.
      const out=this.buffer(9),og=out.getContext('2d')!;drawMotion(og,src,this.flow!,{amount:fm,width:p.width,height:p.height,frame:Math.round(frame-(p.timing?.sceneOffset||0)*p.fps),
        crop:cropAt(this.crop,Math.round(frame)),mesh:this.heavyOptics?20:10,trail:this.heavyOptics?4:1});
      this.freePass=false;try{draw(og);}finally{this.freePass=undefined;}src=out;
    }
    if(o.blur){const b=this.buffer(2);const bg=b.getContext('2d')!;bg.filter=`blur(${(o.blur*.006*p.height).toFixed(2)}px)`;bg.drawImage(src,0,0);bg.filter='none';src=b;}
    const ch=this.heavyOptics?o.chroma||0:0;
    if(ch>0){
      // Split R/G/B by multiply-masking copies, recombine additively with R and B pushed apart along the motion.
      const d=ch*.004*p.width;const [vx,vy]=this.velocityDir(frame);const out=this.buffer(3);const og=out.getContext('2d')!;const tmp=this.buffer(4);const tg=tmp.getContext('2d')!;
      for(const [color,s] of [['#ff0000',-1],['#00ff00',0],['#0000ff',1]] as [string,number][]){
        tg.globalCompositeOperation='source-over';tg.clearRect(0,0,tmp.width,tmp.height);tg.drawImage(src,0,0);
        tg.globalCompositeOperation='multiply';tg.fillStyle=color;tg.fillRect(0,0,tmp.width,tmp.height);
        tg.globalCompositeOperation='destination-in';tg.drawImage(src,0,0);
        og.globalCompositeOperation='lighter';og.drawImage(tmp,vx*d*s,vy*d*s);
      }
      og.globalCompositeOperation='source-over';src=out;
    }
    const k=(o.lensWarp||0)*.35;
    if(k>0){
      // P1 lens-matched text: barrel r' = r(1 + k r²) about the frame centre, text layer only (mesh warp).
      const out=this.buffer(5);const og=out.getContext('2d')!;const cx=p.width/2,cy=p.height/2,R=Math.hypot(cx,cy);
      drawMapped(og,src,(u,v)=>{const x=u*p.width-cx,y=v*p.height-cy;const r=Math.hypot(x,y)/R;const s=1+k*r*r;return [cx+x*s,cy+y*s];},20);src=out;
    }
    // v4.4 raster: the type so far becomes a fixed grid of dots (the glow below then wraps the dots).
    const ras=rasterOf(look);
    if(ras){const out=this.buffer(10);this.rasterPass(out.getContext('2d')!,src,ras,p);src=out;}
    const glow=o.glow||0;
    if(glow>0){
      const r=glow*.03*p.height;ctx.save();ctx.globalCompositeOperation=blend?'screen':'lighter';
      ctx.filter=`blur(${r.toFixed(2)}px)`;ctx.globalAlpha=Math.min(1,.55+.5*glow);ctx.drawImage(src,0,0);
      ctx.filter=`blur(${(r/3).toFixed(2)}px)`;ctx.globalAlpha=.7*glow;ctx.drawImage(src,0,0);ctx.restore();
    }
    ctx.drawImage(src,0,0);
  }
  /** v4.4 raster: src (the text layer so far) → a fixed screen grid of dots, cell = dot px from the frame's top-left.
   *  Each cell takes the average colour of the type under it and lights on its coverage, after a half-cell dilation so
   *  hairlines of a script face stay connected: LEDs with a soft threshold (.1 → .4, a drifting edge fades over a few
   *  frames instead of popping), pixels hard at .25 (1-bit). Stateless, so preview and export agree. */
  private rasterSmall=document.createElement('canvas');private rasterHalf=document.createElement('canvas');
  private rasterPass(g:CanvasRenderingContext2D,src:HTMLCanvasElement,ras:NonNullable<Look['raster']>,p:Project){
    // The dot grid is laid out at the authored size and scaled (n× renders keep the 1× pattern, just sharper).
    const rs=this.renderScale;const dot=Math.max(2,Math.round((ras.dot??RASTER_DEFAULTS.dot)*Math.min(p.width,p.height)/rs))*rs;const gap=Math.min(.9,Math.max(0,ras.gap??RASTER_DEFAULTS.gap));
    const cols=Math.ceil(p.width/dot),rows=Math.ceil(p.height/dot);
    const s=this.rasterSmall;if(s.width!==cols||s.height!==rows){s.width=cols;s.height=rows;}
    // Dilate by about a third of a cell first (the layer stacked at four offsets, at half resolution: cells are 6 px
    // or more), so a hairline lights its cell like a pixel font rasteriser would, instead of averaging away to nothing.
    const D=this.rasterHalf;const hw=Math.ceil(p.width/2),hh=Math.ceil(p.height/2);if(D.width!==hw||D.height!==hh){D.width=hw;D.height=hh;}
    const dg=D.getContext('2d')!;dg.clearRect(0,0,hw,hh);const o=dot*.15;for(const [ox,oy] of [[0,0],[o,0],[-o,0],[0,o],[0,-o]])dg.drawImage(src,ox,oy,hw,hh);
    const sg=s.getContext('2d',{willReadFrequently:true})!;sg.clearRect(0,0,cols,rows);sg.imageSmoothingEnabled=true;sg.imageSmoothingQuality='high';sg.drawImage(D,0,0,cols,rows);
    const d=sg.getImageData(0,0,cols,rows).data;const round=ras.shape==='round';
    // Pixels are 1-bit: whole-pixel squares, on or off at full opacity (no grey half-lit cells); LEDs keep the soft ramp.
    const size=round?dot*(1-gap):Math.max(1,Math.round(dot*(1-gap))),off=round?(dot-size)/2:Math.floor((dot-size)/2),r=size/2;
    let last='';
    for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){const i=(y*cols+x)*4;const a=d[i+3]/255;if(a<(round?.1:.25))continue;
      const fs=`rgb(${d[i]},${d[i+1]},${d[i+2]})`;if(fs!==last){g.fillStyle=fs;last=fs;}g.globalAlpha=round?Math.min(1,(a-.1)/.3):1;
      if(round){g.beginPath();g.arc(x*dot+dot/2,y*dot+dot/2,r,0,Math.PI*2);g.fill();}else g.fillRect(x*dot+off,y*dot+off,size,size);}
    g.globalAlpha=1;
  }
  /** Draw a video frame (through the crop) with the project's grade (gradeOf): 'color' tint keeping luminance,
   *  halation, photocopy mono (+ beat flash). The grade is independent of the look. */
  private paintVideo(ctx:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number,graded:boolean,place?:(g:CanvasRenderingContext2D)=>void){
    const p=this.project;const c=cropAt(this.crop,frame);const gr=graded?this.grade():undefined;const tint=gr?.tint;
    if(v===this.matte&&p.analysis.matteSource){const l=matteLayer(p);if(!l||matteTime(p,frame/p.fps)==null)return;
      place=g=>this.drawMedia(g,v,frame);}
    const draw=place||((g:CanvasRenderingContext2D)=>{if(c){const vw=v.videoWidth,vh=v.videoHeight;g.drawImage(v,c.x*vw,c.y*vh,c.w*vw,c.h*vh,0,0,p.width,p.height);}else g.drawImage(v,0,0,p.width,p.height);});
    const mono=gr?.mono;const hal=gr?.halation||0;
    if((!tint||!tint.amount)&&!mono&&!hal){draw(ctx);return;}
    const b=this.buffer(6);const g=b.getContext('2d')!;draw(g);
    if(tint&&tint.amount){
      g.globalCompositeOperation='color';g.globalAlpha=Math.min(1,tint.amount*1.6);g.fillStyle=tint.color;g.fillRect(0,0,b.width,b.height);
      g.globalAlpha=tint.amount*.5;g.globalCompositeOperation='multiply';g.fillRect(0,0,b.width,b.height);
      g.globalAlpha=1;g.globalCompositeOperation='destination-in';draw(g);g.globalCompositeOperation='source-over';
    }
    if(hal>0){halationPass(g,b,this.buffer(7),hal);g.globalCompositeOperation='destination-in';draw(g);g.globalCompositeOperation='source-over';}
    if(mono){
      if(gr!.monoMix>=1)monoPass(g,b.width,b.height,mono,this.flashNow);
      else{const m=this.buffer(8);const mg=m.getContext('2d')!;mg.drawImage(b,0,0);monoPass(mg,m.width,m.height,mono,this.flashNow);g.globalAlpha=gr!.monoMix;g.drawImage(m,0,0);g.globalAlpha=1;}
    }
    ctx.drawImage(b,0,0);
  }
  /** Reuse the independently graded background / alpha cutout while only the type changes. The source identity
   * separates original, proxy, seek-copy and generated-shot decoders; time, size, crop and grade cover all pixels
   * produced by paintVideo. Grain and neon relighting remain in the final composite, after the editable text. */
  private paintMedia(ctx:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number,slot:0|1){
    if(v===this.matte&&this.project.analysis.matteSource){const l=matteLayer(this.project);if(!l)return;ctx.save();ctx.globalAlpha*=layerStateAt(l,frame/this.project.fps).opacity;this.paintVideo(ctx,v,frame,l.graded!==false);ctx.restore();return;}
    if(!this.cacheMedia){this.paintVideo(ctx,v,frame,true);return;}
    const p=this.project;
    const key=JSON.stringify([frame,v.currentSrc,v.currentTime,v.videoWidth,v.videoHeight,p.width,p.height,cropAt(this.crop,frame),this.grade(),this.flashNow]);
    let entry=this.mediaFrames[slot];
    if(!entry||entry.source!==v||entry.key!==key){
      const c=entry?.canvas||document.createElement('canvas');
      if(c.width!==p.width)c.width=p.width;if(c.height!==p.height)c.height=p.height;
      const g=c.getContext('2d')!;g.clearRect(0,0,c.width,c.height);this.paintVideo(g,v,frame,true);
      entry={source:v,key,canvas:c};this.mediaFrames[slot]=entry;
    }
    ctx.drawImage(entry.canvas,0,0);
  }
  /** A media frame through the crop, ungraded. */
  private drawMedia(g:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number){
    const p=this.project;const c=cropAt(this.crop,frame);
    if(v===this.matte&&p.analysis.matteSource){const l=matteLayer(p);if(l&&matteTime(p,frame/p.fps)!=null)placeLayer(g,v,v.videoWidth,v.videoHeight,p.width,p.height,layerStateAt(l,frame/p.fps).transform);return;}
    if(c){const vw=v.videoWidth,vh=v.videoHeight;g.drawImage(v,c.x*vw,c.y*vh,c.w*vw,c.h*vh,0,0,p.width,p.height);}else g.drawImage(v,0,0,p.width,p.height);
  }
  /** Layer stack (Project.layers, bottom→top; layers.ts). Absent layers never come here: the fixed path above is the
   *  implied stack. Seeks every visible source first; false = the frame went stale (nothing painted). */
  private layerMedia=new Map<string,Promise<HTMLVideoElement|HTMLImageElement>>();private layerProxy=false;
  private layerEl(path:string,kind:'video'|'image',proxy:boolean):Promise<HTMLVideoElement|HTMLImageElement>{
    const key=`${proxy?'p':'o'}:${path}`;let m=this.layerMedia.get(key);
    if(!m){const p=this.project;m=kind==='image'?image(assetUrl(p,path,this.server)):proxy?video(assetUrl(p,proxyPath(path),this.server)).catch(()=>this.layerEl(path,kind,false)):video(assetUrl(p,path,this.server));
      this.layerMedia.set(key,m);m.catch(()=>this.layerMedia.delete(key));}
    return m;
  }
  private async composeStack(canvas:HTMLCanvasElement,ctx:CanvasRenderingContext2D,t:number,frame:number,fit:()=>void){
    const p=this.project;const stack=p.layers!.filter(l=>!l.hidden);const mid=.5/p.fps;
    const bgTime=t-(p.timing?.sceneOffset||0),bgActive=bgTime>=0&&(!p.media.video||bgTime<p.media.video.duration);
    const shot=p.shots.find(s=>s.status==='done'&&s.video&&s.start<=t&&s.end>t);const clip=shot?this.shots.get(shot.id):bgActive?this.bg:undefined;
    const matte=(shot&&!p.analysis.matteSource)||(!bgActive&&!p.analysis.matteSource)||matteTime(p,t)==null?undefined:this.matte;
    const go=(v:HTMLVideoElement,at:number,seq:boolean)=>seq?advance(v,at,p.fps):seek(v,at);
    const live:{l:MediaLayer;el:HTMLVideoElement|HTMLImageElement;at:number}[]=[];
    await Promise.all(stack.map(async l=>{if(l.kind!=='media')return;const a=assetOf(p,l.assetId);const at=layerSourceTime(l,t);if(!a||at===undefined)return;
      const el=await this.layerEl(a.path,a.kind,a.kind==='video'&&this.layerProxy).catch(()=>undefined);if(el)live.push({l,el,at});}));
    const usesPlate=stack.some(l=>l.kind==='plate')||this.hasFill(),usesMatte=stack.some(l=>l.kind==='subject'||(l.kind==='media'&&!!l.mask))||this.hasFill();
    await Promise.all([clip&&usesPlate?go(clip,(shot?t-shot.start:bgTime)+mid,this.sequential&&!shot):undefined,matte&&usesMatte?go(matte,matteTime(p,t)!+mid,this.sequential):undefined,
      ...live.map(({el,at})=>el instanceof HTMLVideoElement?go(el,at+mid,this.sequential):undefined)]);
    if(this.stale?.())return false;fit();
    ctx.clearRect(0,0,p.width,p.height);
    const look=this.look();const neonLight=look?.finish==='neon'?look.light??.8:0;
    const scene=look?.wall==='spray'||look?.finish==='neon'||this.hasFill()||!!look?.wallBlend||Object.values(p.lineMeta||{}).some(m=>m.appearance?.blend);
    for(const l of stack){
      if(l.kind==='plate'){if(clip)this.paintMedia(ctx,clip,frame,0);else{ctx.fillStyle='#242923';ctx.fillRect(0,0,p.width,p.height);}}
      else if(l.kind==='subject'){if(matte){this.paintMedia(ctx,matte,frame,1);if(neonLight>0)this.relight(ctx,frame,neonLight);}}
      else if(l.kind==='text'){
        if(l.which==='behind'){
          // Scene looks read what is under the behind text (same point as the fixed path: after the background).
          if(scene){const e=this.buffer(30);e.getContext('2d')!.drawImage(canvas,0,0);this.env=e;}
          if(neonLight>0)this.lightPass(ctx,t,frame,neonLight);else this.light=undefined;
        }
        this.textPass(ctx,t,frame,l.which,true);
      }else{
        const m=live.find(x=>x.l===l);if(!m)continue;const el=m.el;
        const w=el instanceof HTMLVideoElement?el.videoWidth:el.naturalWidth,h=el instanceof HTMLVideoElement?el.videoHeight:el.naturalHeight;if(!w||!h)continue;
        const st=layerStateAt(l,t);if(st.opacity<=0)continue;const b=this.buffer(32);const g=b.getContext('2d')!;
        this.paintVideo(g,el as HTMLVideoElement,frame,l.graded!==false,gx=>placeLayer(gx,el,w,h,p.width,p.height,st.transform));
        if(l.mask){if(matte){g.globalCompositeOperation=l.mask==='subject'?'destination-in':'destination-out';this.drawMedia(g,matte,frame);g.globalCompositeOperation='source-over';}else if(l.mask==='subject')continue;}
        ctx.save();ctx.globalAlpha=st.opacity;ctx.globalCompositeOperation=BLEND_OP[l.blend||'normal']||'source-over';ctx.drawImage(b,0,0);ctx.restore();
      }
    }
    if(!stack.some(l=>l.kind==='text'&&l.which==='behind'))this.light=undefined;
    return true;
  }
  /** One frame. opts apply to this call only (draft previews while scrubbing/dragging): heavyOptics overrides the instance
   *  switch; proxy seeks the preview proxies when loaded. Defaults = instance state, so export, TypesetRender and capture
   *  are unchanged. Calls on one instance are serialized by the callers (studio loop, thumb loop). */
  async render(canvas:HTMLCanvasElement,frame:number,layer:Layer='composite',opts?:RenderOpts){
    const prev=this.heavyOptics,bg=this.bg,matte=this.matte;if(opts?.heavyOptics!==undefined)this.heavyOptics=opts.heavyOptics;
    if(opts?.proxy){if(this.bgProxy)this.bg=this.bgProxy;if(this.matteProxy)this.matte=this.matteProxy;}
    else if(opts?.full){if(this.bgSeek)this.bg=this.bgSeek;if(this.matteSeek)this.matte=this.matteSeek;}
    this.layerProxy=this.draftMedia&&!!opts?.proxy;
    this.stale=opts?.stale;this.cacheMedia=this.draftMedia&&opts?.cacheMedia===true;
    this.cacheLayouts=this.draftMedia&&opts?.cacheLayouts===true;
    this.previewScale=this.draftMedia?Math.max(.01,Math.min(1,opts?.previewScale??1)):1;
    try{await this.renderFrame(canvas,frame,layer);}finally{this.heavyOptics=prev;this.bg=bg;this.matte=matte;this.stale=undefined;this.cacheMedia=false;this.cacheLayouts=false;this.previewScale=1;}
  }
  private async renderFrame(canvas:HTMLCanvasElement,frame:number,layer:Layer){
    this.syncMatte();
    const p=this.project;const last=Math.max(0,Math.round(p.duration*p.fps)-1);frame=Math.max(0,Math.min(last,frame));const t=frame/p.fps;
    await this.loadSurfaceTracks();
    const ctx=canvas.getContext('2d')!;
    const fl=this.grade()?.flash;
    if(fl&&this.beats===undefined&&p.id!=='sample')this.beats=(await json<BeatGrid>(assetUrl(p,(p.analysis as {beats?:string|null}).beats||'analysis/beats.json',this.server)))||null;
    this.flashNow=fl&&this.beats&&audibleAt(p,t)?flashAt(this.beats,toSong(p,t),fl):0;
    const fit=()=>{if(canvas.width!==p.width)canvas.width=p.width;if(canvas.height!==p.height)canvas.height=p.height;};
    if(layer==='composite'){
      if(p.layers?.length){if(!await this.composeStack(canvas,ctx,t,frame,fit))return;}else{
      const bgTime=t-(p.timing?.sceneOffset||0),bgActive=bgTime>=0&&(!p.media.video||bgTime<p.media.video.duration);
      const shot=p.shots.find(s=>s.status==='done'&&s.video&&s.start<=t&&s.end>t);const clip=shot?this.shots.get(shot.id):bgActive?this.bg:undefined;
      // Seek every media source before touching the visible canvas; never expose a half-painted frame.
      // Mid-frame times: frame f's pts is f/fps rounded to the container timebase, so seeking to exactly f/fps can
      // land a hair before it and show frame f-1. Half a frame in is unambiguous for both the footage and the matte.
      const mid=.5/p.fps;
      const go=(v:HTMLVideoElement,at:number,seq:boolean)=>seq?advance(v,at,p.fps):seek(v,at);
      await Promise.all([clip?go(clip,(shot?t-shot.start:bgTime)+mid,this.sequential&&!shot):Promise.resolve(),this.matte&&!shot&&matteTime(p,t)!=null?go(this.matte,matteTime(p,t)!+mid,this.sequential):Promise.resolve()]);
      if(this.stale?.())return;fit();
      ctx.clearRect(0,0,p.width,p.height);
      if(clip)this.paintMedia(ctx,clip,frame,0);else{ctx.fillStyle='#242923';ctx.fillRect(0,0,p.width,p.height);}
      // Scene looks (graffiti, neon) read the graded footage: paint takes the wall's light, signs light the wall.
      const look=this.look();const scene=look?.wall==='spray'||look?.finish==='neon'||this.hasFill()||!!look?.wallBlend||Object.values(p.lineMeta||{}).some(m=>m.appearance?.blend);
      if(scene){const e=this.buffer(30);e.getContext('2d')!.drawImage(canvas,0,0);this.env=e;}
      const neonLight=look?.finish==='neon'?look.light??.8:0;
      if(neonLight>0)this.lightPass(ctx,t,frame,neonLight);else this.light=undefined;
      this.textPass(ctx,t,frame,'behind',true);
      if(this.matte&&!shot&&matteTime(p,t)!=null&&(bgActive||p.analysis.matteSource)){this.paintMedia(ctx,this.matte,frame,1);if(neonLight>0)this.relight(ctx,frame,neonLight);}
      this.textPass(ctx,t,frame,'front',true);
      }
      this.env=undefined;
      const grain=this.grade()?.grain||0;
      if(grain>0){
        // Composite-only film grain: a seeded tile, offset per frame, overlay-blended.
        const tile=grainTile(frame%4);const pat=ctx.createPattern(tile,'repeat')!;const ox=Math.floor(hash01(`g${frame}x`)*256),oy=Math.floor(hash01(`g${frame}y`)*256);
        const s=this.previewScale*this.renderScale;ctx.save();ctx.globalCompositeOperation='overlay';ctx.globalAlpha=Math.min(1,grain*.6);ctx.translate(-ox*s,-oy*s);ctx.scale(s,s);ctx.fillStyle=pat;ctx.fillRect(ox,oy,p.width/s,p.height/s);ctx.restore();
      }
    }else{
      this.env=undefined;
      if(this.hasFill()){
        // Glyph fill reads the footage: seek it (and the matte) for text-only renders too, then grade it into env.
        const mid=.5/p.fps;const go=(v:HTMLVideoElement,at:number)=>this.sequential?advance(v,at,p.fps):seek(v,at);
        const bgTime=t-(p.timing?.sceneOffset||0);
        await Promise.all([this.bg&&bgTime>=0?go(this.bg,bgTime+mid):Promise.resolve(),this.matte&&matteTime(p,t)!=null?go(this.matte,matteTime(p,t)!+mid):Promise.resolve()]);
        if(this.stale?.())return;
        const e=this.buffer(30);if(this.bg&&bgTime>=0)this.paintMedia(e.getContext('2d')!,this.bg,frame,0);else e.getContext('2d')!.clearRect(0,0,e.width,e.height);this.env=e;
      }
      fit();ctx.clearRect(0,0,p.width,p.height);this.textPass(ctx,t,frame,layer==='text-behind'?'behind':layer==='text-front'?'front':'all',false);this.env=undefined;}
  }
}
