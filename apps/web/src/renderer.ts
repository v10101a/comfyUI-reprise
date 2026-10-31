import type {Project,Word,Tracks,Layer,TextStyle,Occupancy,CropData,CropFrame,SurfaceTrack,Surface,Point,Look,Grade} from './types';
import {assetUrl} from './api';
import {FlowField,drawMotion,type FlowDoc} from './flow';
import {VoiceField,type VoiceDoc} from './voice';
import {at as atBase} from './base';
import {OccupancySource,autoPlace,type LineRequest,type LinePlacement,type Placed} from './placement';
import {cropAt,toOut,drawWarped,drawMapped,quadIsConvex,quadSize,squareToQuad,applyH,warpSafeMargins} from './geometry';
import {FONTS,lookOf,gradeOf,wordIsShown,lineIsHook,heroWordId,applyCase,isSubtitleLine} from './looks';

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
/** Surface pose at a frame: tracked corners (hold ≤6 frames), else the static drawn corners. Fractional frames interpolate. */
export function surfaceCornersAt(s:Surface,track:SurfaceTrack|undefined,frame:number):Point[]|undefined{
  if(!track)return s.corners;
  const at=(f:number)=>{const fr=track.frames;let lo=0,hi=fr.length-1,found=-1;
    while(lo<=hi){const mid=(lo+hi)>>1;if(fr[mid].f<=f){found=mid;lo=mid+1;}else hi=mid-1;}
    if(found<0||f-fr[found].f>6)return undefined;return fr[found];};
  const f0=Math.floor(frame),a=at(f0);if(!a)return undefined;if(frame===f0)return a.corners;
  const b=at(f0+1);if(!b||b.f!==f0+1||a.f!==f0)return a.corners;const k=frame-f0;
  return a.corners.map(([x,y],i)=>[x+(b.corners[i][0]-x)*k,y+(b.corners[i][1]-y)*k] as Point);
}
/** Deterministic hash → [0,1). */
export function hash01(s:string){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}h^=h>>>13;h=Math.imul(h,0x5bd1e995);h^=h>>>15;return (h>>>0)/4294967296;}

let fontsRegistered=false;
export async function loadFonts(){
  if(!fontsRegistered){fontsRegistered=true;
    // Registered from code (not CSS) so the render route and any UI get the same faces.
    await Promise.all(FONTS.map(async f=>{try{const face=new FontFace(f.family,`url("${atBase(`/fonts/${encodeURIComponent(f.file)}`)}")`,{weight:f.weight,style:f.style||'normal'});await face.load();document.fonts.add(face);}catch{/* keep going: CSS may already provide it */}}));
  }
  await Promise.all(['700 24px Inter','800 24px Inter','900 24px Inter','500 24px Inter','400 24px "Space Mono"','700 24px "Space Mono"','400 24px Anton','400 24px "Bebas Neue"'].map(font=>document.fonts.load(font)));await document.fonts.ready;
}
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
type Line = {sub?:boolean;key:string;lineId:string;role:Role;words:Word[];placement:Word['placement'];start:number;end:number;metrics:Metric[];rows:Row[];total:number;size:number;height:number;
  bleed?:boolean;auto?:boolean;req?:Partial<LineRequest>;card?:boolean};
const ROW=1.04;

/** HUD labels are never smaller than this fraction of frame height (proof A: the tiny tag was unreadable). */
const HUD_MIN=.05;
function styleOf(p:Project,w:Word):TextStyle{
  const s={...p.style,...(w.style||{})} as TextStyle;
  for(const k of Object.keys(s) as (keyof TextStyle)[])if(s[k]===null)delete s[k];
  if(w.preset==='hud'&&s.fontSize<HUD_MIN)s.fontSize=HUD_MIN;
  return s;
}
/** Relative luminance of #rrggbb (0..1). */
function lum(hex:string){const m=/^#?([0-9a-f]{6})$/i.exec(hex);if(!m)return 1;const n=parseInt(m[1],16);return (.2126*(n>>16&255)+.7152*(n>>8&255)+.0722*(n&255))/255;}
/** HUD sits on a dark backdrop: use the look's colours only when they are light enough to read there. */
function hudInk(look:Look){return [look.palette.text,look.palette.accent,look.palette.card||'#ffffff'].find(c=>lum(c)>.35)||'#ffffff';}
function hudLine(look:Look){return [look.palette.accent,look.palette.card||'',look.palette.text].find(c=>c&&lum(c)>.25)||'#ffffff';}
const DEFAULT_WEIGHT:Record<string,number>={Inter:800,'Archivo Narrow':500,'Big Shoulders Display':900,'Space Mono':700};
/** Look styling: the look owns typeface, weight, colour, case and spacing; per-word size/alignment still apply. */
function lookStyle(p:Project,w:Word,look:Look,role:Role,size?:number):{style:TextStyle;text:string}{
  const s=styleOf(p,w);
  if(role==='hud')return {style:{...s,fill:hudInk(look)},text:w.text};
  const heroish=role==='hero'||role==='hook'||role==='surface'||role==='stack';
  const family=heroish?look.font.hero:look.font.body;
  const weight=(heroish?look.font.heroWeight:look.font.bodyWeight)??DEFAULT_WEIGHT[family]??400;
  const fill=heroish?(look.heroFill==='accent'?look.palette.accent:look.palette.text):look.layout==='line'?look.palette.accent:look.palette.text;
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
  return [...groupWords(p,w=>!w.hidden&&!p.lineMeta?.[w.lineId]?.hidden).entries()].map(([key,words])=>buildUnit(ctx,p,key,words[0].lineId,'line',words,w=>({style:styleOf(p,w),text:w.text})));
}
/** Units under a look: styling, quiet, and the layout split (hero/satellites, constellation, stack). */
function lookUnits(ctx:CanvasRenderingContext2D,p:Project,look:Look,hasMatte:boolean):Line[]{
  const out:Line[]=[];const minDim=Math.min(p.width,p.height)/p.height;// font sizes are fractions of height
  const sc=look.scale??1,card=!!look.card;
  const groups=[...groupWords(p,w=>wordIsShown(p,w)).entries()];
  // Hero layout shows one line at a time: a line yields when the next text line starts (no hero pile-ups).
  const starts=[...new Set(groups.filter(([,ws])=>(ws[0].placement==='behind'||ws[0].placement==='overlay')&&!isSubtitleLine(p,ws[0].lineId)).map(([,ws])=>Math.min(...ws.map(w=>w.start))))].sort((a,b)=>a-b);
  const yieldAt=(start:number)=>starts.find(s=>s>start+1e-6)??Infinity;
  for(const [key,raw] of groups){
    // Subtitle/karaoke register keeps its authored placement, size and alignment under every look:
    // mono (unless the word names a family) in the palette's text colour; the active karaoke word takes the accent.
    if(isSubtitleLine(p,raw[0].lineId)){
      const u=buildUnit(ctx,p,key,raw[0].lineId,'line',raw,w=>({style:{...styleOf(p,w),fontFamily:w.style?.fontFamily??'Space Mono',fontWeight:w.style?.fontWeight??700,fill:lum(look.palette.text)>.25?look.palette.text:hudLine(look),stroke:null,strokeWidth:null,shadow:null,letterSpacing:w.style?.letterSpacing??0},text:w.text}));u.sub=true;out.push(u);continue;
    }
    // Layouts that size words individually split multi-token words ("than the radio") into tokens sharing the timing.
    const split=look.layout!=='line'&&(raw[0].placement==='behind'||raw[0].placement==='overlay');
    const words=split?raw.flatMap(w=>{const toks=w.text.split(/\s+/).filter(Boolean);return toks.length<2?[w]:toks.map((tk,i)=>({...w,id:`${w.id}~${i}`,text:tk,hero:w.hero&&i===0?w.hero:null}));}):raw;
    const lineId=words[0].lineId;const placement=words[0].placement;
    if(placement==='anchor'){out.push(buildUnit(ctx,p,key,lineId,'hud',words,w=>lookStyle(p,w,look,w.preset==='hud'?'hud':'verse')));continue;}
    if(placement==='surface'){
      // Neon walls take the accent (a tube colour, not body ink); a carded look puts its card on the wall too.
      const neon=p.surfaces?.find(x=>x.id===words[0].surfaceId)?.material==='neon';
      const u=buildUnit(ctx,p,key,lineId,'surface',words,w=>{const r=lookStyle(p,w,look,'surface');return neon?{...r,style:{...r.style,fill:look.palette.accent}}:r;});
      u.card=card;out.push(u);continue;}
    const hook=lineIsHook(p,lineId);
    if(look.layout==='hero'){
      const heroId=heroWordId({...p,words:[...p.words.filter(w=>w.lineId!==lineId),...words]},lineId);const hero=words.find(w=>w.id===heroId)||words[0];
      const end=Math.min(Math.max(...words.map(w=>w.end)),yieldAt(Math.min(...words.map(w=>w.start))));
      // Hero: 0.30–0.60 of min(width,height); shrink until ≥60% of the word stays in frame (bleed allowed).
      let size=.45*minDim*sc;const probe=buildUnit(ctx,p,'probe',lineId,'hero',[hero],w=>lookStyle(p,w,look,'hero',size),{wrap:'never'});
      const maxW=p.width/.62;if(probe.total>maxW)size*=maxW/probe.total;
      const u=buildUnit(ctx,p,`${key}:hero`,lineId,'hero',[hero],w=>lookStyle(p,w,look,'hero',size),{wrap:'never',placement:hasMatte?'behind':'overlay'});
      u.end=end;u.bleed=true;u.auto=true;u.card=card;u.req={tolerance:.55,noShrink:true,canPromote:false,hint:{x:.5,y:p.height>p.width?.42:.5}};out.push(u);
      for(const w of words)if(w!==hero){
        const s=buildUnit(ctx,p,`${key}:sat:${w.id}`,lineId,'sat',[w],x=>lookStyle(p,x,look,'sat',.048*minDim*sc),{wrap:'never',placement:'overlay'});
        s.auto=true;s.card=card;s.start=u.start;s.end=u.end;s.req={tolerance:.01,strict:true,canPromote:false,avoidKey:u.key,avoidR:u.height/p.height*1.05};out.push(s);
      }
      continue;
    }
    if(look.layout==='constellation'){
      for(const w of words){const s=buildUnit(ctx,p,`${key}:c:${w.id}`,lineId,'sat',[w],x=>lookStyle(p,x,look,'sat',.05*minDim*sc),{wrap:'never',placement:'overlay'});
        s.auto=true;s.card=card;s.start=Math.min(...words.map(x=>x.start));s.end=Math.max(...words.map(x=>x.end));s.req={tolerance:.01,strict:true,canPromote:false};out.push(s);}
      continue;
    }
    if(look.layout==='stack'){
      const st=buildUnit(ctx,p,`${key}:stack`,lineId,'stack',words,w=>({...lookStyle(p,w,look,'stack',.085*minDim*sc),style:{...lookStyle(p,w,look,'stack',.085*minDim*sc).style,align:'left'}}),{wrap:'each',placement:'overlay'});
      st.auto=true;st.card=card;st.req={tolerance:.02,corner:true,canPromote:false};out.push(st);continue;
    }
    // 'line' layout: two registers. Hooks keep their authored size/placement in the hero face; verses become
    // a small lowercase subtitle register in the accent colour, low in frame and in front.
    if(hook){const u=buildUnit(ctx,p,key,lineId,'hook',words,w=>lookStyle(p,w,look,'hook'));u.card=card;out.push(u);}
    else{const keep=!!look.verse?.keepPosition&&words.every(w=>w.position&&w.autoPlace===false);const cap=(look.verse?.max??.055)*minDim;
      const u=buildUnit(ctx,p,`${key}:verse`,lineId,'verse',words,w=>lookStyle(p,w,look,'verse',sc===1?Math.min(styleOf(p,w).fontSize,cap):Math.min(styleOf(p,w).fontSize*sc,cap*sc)),{placement:keep?undefined:'overlay'});
      if(!keep){u.auto=true;u.req={tolerance:.02,hint:{x:.5,y:.84},canPromote:false};}u.card=card;out.push(u);}
  }
  // Neon signs and spray paint belong to the scene: every screen unit (not subtitles / HUD) sits behind the subject.
  if(look.finish==='neon'||look.wall==='spray')for(const u of out)if(!u.sub&&u.role!=='hud'&&(u.placement==='overlay'||u.placement==='behind')){u.placement='behind';u.req={...(u.req||{}),canPromote:false};}
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
  note?:{fill:string;stroke:string};sparkle?:number;
  /** Look entrance-motion amount (pop travel/scale, HUD jitter); undefined/1 = as authored. */
  motion?:number;
  /** Pop-in flicker 0..1: for half a second after its onset a word drops out on seeded frames (neon catching). */
  flicker?:number;
  /** Voice field: the singer's loudness/pitch/vibrato move each word (look.fields.voice > 0). */
  voice?:{field:VoiceField;amount:number}};
/** Draw one unit's words centred on the current origin (x by alignment, y=0). */
function drawWords(ctx:CanvasRenderingContext2D,line:Line,t:number,frame:number,opts:DrawOpts){
  const align=line.metrics[0].style.align;
  // Note lanes are centred on the line's mean pitch, so the authored position stays the line's centre.
  const ms=line.words.map(w=>midiOf(w.note)).filter((m):m is number=>m!==undefined);const ref=ms.length?ms.reduce((a,b)=>a+b,0)/ms.length:undefined;
  const vref=opts.voice?opts.voice.field.refPitch(line.start,line.end):null;
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*line.size*ROW;let x=-(align==='center'?row.width/2:align==='right'?row.width:0)+(opts.scroll||0);
  for(const {w,text:full,style,spacing,width,gap,size} of row.metrics){
    const active=t>=w.start&&t<w.end;const local=t-w.start;
    let alpha=1,scale=1,dx=0,dy=0,text=full;
    const mk=opts.motion??1;
    if(opts.flicker&&local>=0&&local<.5&&hash01(`${w.id}:fl:${frame}`)<opts.flicker*(1-local/.5)*.9)alpha=.12;
    if(w.preset==='pop'){if(local<0)alpha=0;else{const progress=spring(local);scale=mk===1?.72+.28*progress:1-.28*mk*(1-progress);dy=(1-progress)*size*.5*mk;}}
    if(w.preset==='karaoke')alpha=active?1:t<w.start?.26:.62;
    if(w.preset==='typewriter'){const count=Math.floor(Math.max(0,local)/Math.max(.02,(w.end-w.start)/Math.max(1,full.length)));text=[...full].slice(0,count+Number(local>=0)).join('');}
    if(w.preset==='write'&&local<0)alpha=0;
    if(w.preset==='hud'){alpha=local<0?.18:1;const k=Math.round(local*24);if(k>=0&&k<4){dx=(hash01(`${w.id}:${frame}:x`)-.5)*size*.18*mk;dy=(hash01(`${w.id}:${frame}:y`)-.5)*size*.12*mk;}}
    const m=midiOf(w.note);const lane=m!==undefined&&ref!==undefined?Math.max(-1.2,Math.min(1.2,-(m-ref)*.16))*size:0;
    if(w.note&&local>=0)drawNoteBlock(ctx,w.note,x,y+lane,width,size,local,t<w.end,opts.note);
    dy+=lane;
    // Voice: the word swells with the singer (variable weight + width), rides the melody, wobbles on vibrato.
    let vs=style,vw=width,sx=1,sy=1;
    if(opts.voice){const v=opts.voice.field.mods(t,w.start,w.end,vref,opts.voice.amount);
      if(v.weight){vs={...style,fontWeight:Math.max(100,Math.min(900,Math.round(style.fontWeight+v.weight)))};ctx.save();ctx.font=fontOf(vs,size);vw=measure(ctx,text,spacing);ctx.restore();}
      sx=v.sx;sy=v.sy;dy+=v.dy*size;}
    if(alpha>0){
      ctx.save();ctx.globalAlpha*=alpha;ctx.font=fontOf(vs,size);ctx.textBaseline='middle';ctx.textAlign='left';
      ctx.translate(x+width/2+dx,y+dy);ctx.scale(scale*sx,scale*sy);
      const fill=active&&w.preset==='karaoke'?(opts.karaoke||'#d8ff62'):style.fill;
      if(w.preset==='write'){
        // Write-on: a left→right reveal whose edge is jittered per row band (hash01), like a marker stroke catching up.
        const k=Math.min(1,Math.max(0,local/Math.max(.15,(w.end-w.start)*.7)));const edge=-width/2-size*.1+k*(width+size*.4);
        ctx.beginPath();ctx.moveTo(-width/2-size,-size);const bands=8;
        for(let i=0;i<=bands;i++){const yy=-size*.75+i*(size*1.5/bands);ctx.lineTo(edge+(hash01(`${w.id}:${i}:${Math.floor(frame/2)}`)-.5)*size*.35*(k<1?1:0),yy);}
        ctx.lineTo(-width/2-size,size);ctx.closePath();ctx.clip();
      }
      drawGlyphs(ctx,text,-vw/2,0,spacing,vs,size,fill,w.preset==='pop'?local:undefined,opts.plain?0:opts.shadow,opts.shadowColor,opts.hard,mk);
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
 *  dims when the word ends; the note name sits above its left edge like a DAW/TouchDesigner piano roll. */
function drawNoteBlock(ctx:CanvasRenderingContext2D,note:string,x:number,y:number,width:number,size:number,local:number,on:boolean,c={fill:'#8d93f2',stroke:'#5a5fd6'}){
  const padX=size*.24,h=size*1.08,bx=x-padX,bw=width+2*padX;const g=Math.min(1,local/.16),e=1-Math.pow(1-g,3);const flash=Math.max(0,1-local/.45);
  const r=Math.min(size*.14,bw*e/2);
  ctx.save();ctx.globalAlpha*=Math.min(1,(on?.72:.5)+.25*flash);
  ctx.beginPath();ctx.roundRect(bx,y-h/2,Math.max(1,bw*e),h,r);
  if(flash>0){ctx.shadowColor='rgba(255,255,255,.9)';ctx.shadowBlur=size*.6*flash;}
  ctx.fillStyle=c.fill;ctx.fill();ctx.shadowBlur=0;ctx.lineWidth=Math.max(1,size*.035);ctx.strokeStyle=c.stroke;ctx.stroke();
  ctx.globalAlpha=Math.min(1,ctx.globalAlpha*1.3);ctx.font=`400 ${(size*.3).toFixed(1)}px "Space Mono"`;ctx.textBaseline='bottom';ctx.textAlign='left';ctx.fillStyle=c.stroke;
  ctx.fillText(note,bx+size*.04,y-h/2-size*.04);
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
function drawGlyphs(ctx:CanvasRenderingContext2D,text:string,x:number,y:number,spacing:number,s:TextStyle,size:number,fill:string,popLocal:number|undefined,shadow:number,shadowColor?:string,hard?:boolean,motion=1){
  let index=0;
  for(const char of text){
    ctx.save();
    if(popLocal!==undefined&&popLocal>=0){const progress=spring(Math.max(0,popLocal-index*.018));ctx.translate(0,(1-progress)*size*.14*motion);}
    index++;
    if(shadow>0&&hard){
      // Cut-paper drop shadow: a hard offset copy in the look's shadow colour.
      ctx.save();ctx.globalAlpha*=shadow;ctx.fillStyle=shadowColor||'#000';ctx.fillText(char,x+size*.035,y+size*.045);ctx.restore();
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
function drawTubes(o:CanvasRenderingContext2D,line:Line,t:number,frame:number,fit:number,opts:DrawOpts){
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
/** Neon sign hardware in unit coordinates: a dark acrylic back-plate, four standoffs, a power cable dropping out of
 *  the sign and blacked-out return tubes between words. Drawn under the tubes. */
function drawMount(o:CanvasRenderingContext2D,line:Line,seed:string){
  const s=line.size,al=line.metrics[0].style.align,x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
  const pad=s*.28,bx=x0-pad,by=-line.height/2-pad*.6,bw=line.total+2*pad,bh=line.height+pad*1.2;
  o.save();o.fillStyle='rgba(14,14,18,.22)';o.beginPath();o.roundRect(bx,by,bw,bh,s*.06);o.fill();
  o.strokeStyle='rgba(255,255,255,.07)';o.lineWidth=Math.max(1,s*.01);o.stroke();
  o.fillStyle='rgba(205,205,212,.45)';const k=s*.11;
  for(const [cx,cy] of [[bx+k,by+k],[bx+bw-k,by+k],[bx+k,by+bh-k],[bx+bw-k,by+bh-k]]){o.beginPath();o.arc(cx,cy,s*.022,0,Math.PI*2);o.fill();}
  const cx=bx+bw*(.15+.7*hash01(`${seed}:cable`));o.strokeStyle='rgba(6,6,8,.85)';o.lineWidth=s*.016;o.lineCap='round';
  o.beginPath();o.moveTo(cx,by+bh);o.quadraticCurveTo(cx+s*.25,by+bh+s*.5,cx+s*.08,by+bh+s*1.1);o.stroke();
  o.strokeStyle='rgba(64,54,60,.85)';o.lineWidth=s*.034;
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*s*ROW+s*.3;let x=-(al==='center'?row.width/2:al==='right'?row.width:0);
    row.metrics.forEach((m,i)=>{x+=m.width;if(i<row.metrics.length-1){o.beginPath();o.moveTo(x-s*.06,y);o.lineTo(x+m.gap+s*.06,y);o.stroke();}x+=m.gap;});});
  o.restore();
}
/** Spray paint marks in unit coordinates (wall:'spray'): seeded drips under letters that run after the word's onset,
 *  and a stencil bridge (a thin horizontal cut) through stencil-face rows. */
function drawSprayMarks(o:CanvasRenderingContext2D,line:Line,t:number,drips:number,stencil:boolean){
  const al=line.metrics[0].style.align;
  line.rows.forEach((row,r)=>{const y=(r-(line.rows.length-1)/2)*line.size*ROW;let x=-(al==='center'?row.width/2:al==='right'?row.width:0);
    const rx=x;
    for(const m of row.metrics){const local=t-m.w.start;
      if(local>=0&&drips>0){o.save();o.font=fontOf(m.style,m.size);o.fillStyle=m.style.fill;o.strokeStyle=m.style.fill;o.lineCap='round';let cx=x;
        [...m.text].forEach((ch,i)=>{const cw=o.measureText(ch).width;const h=hash01(`${m.w.id}:drip:${i}`);
          if(ch.trim()&&h<drips*.55){const grow=Math.min(1,Math.max(0,(local-.12-.4*hash01(`${m.w.id}:dd:${i}`))/1.4));if(grow>0){
            const px=cx+cw*(.2+.6*hash01(`${m.w.id}:dx:${i}`)),y0=y+m.size*.3,len=m.size*(.25+1.1*hash01(`${m.w.id}:dl:${i}`))*(1-Math.pow(1-grow,2));
            const lw=m.size*(.018+.022*hash01(`${m.w.id}:dw:${i}`));o.lineWidth=lw;o.beginPath();o.moveTo(px,y0);o.lineTo(px,y0+len);o.stroke();
            o.beginPath();o.arc(px,y0+len,lw*.9,0,Math.PI*2);o.fill();}}
          cx+=cw+m.spacing;});o.restore();}
      x+=m.width+m.gap;}
    if(stencil){o.save();o.globalCompositeOperation='destination-out';o.fillRect(rx-line.size,y-line.size*.035,row.width+2*line.size,line.size*.05);o.restore();}
  });
}
/** Spray finish on a screen-space paint buffer: overspray halo, uneven coverage, and (env = the graded footage)
 *  modulation by the wall's own luminance, so the paint takes the light falloff, grain and cracks underneath. */
function sprayify(b:HTMLCanvasElement,tmp:HTMLCanvasElement,px:number,env?:HTMLCanvasElement){
  const g=b.getContext('2d')!;g.setTransform(1,0,0,1,0,0);
  if(tmp.width!==b.width)tmp.width=b.width;if(tmp.height!==b.height)tmp.height=b.height;
  const tg=tmp.getContext('2d')!;tg.setTransform(1,0,0,1,0,0);tg.globalAlpha=1;tg.globalCompositeOperation='source-over';tg.clearRect(0,0,tmp.width,tmp.height);
  tg.filter=`blur(${Math.max(.5,px*.025).toFixed(2)}px)`;tg.drawImage(b,0,0);tg.filter=`blur(${Math.max(1,px*.08).toFixed(2)}px)`;tg.globalAlpha=.35;tg.drawImage(b,0,0);tg.filter='none';tg.globalAlpha=1;
  g.globalCompositeOperation='destination-over';g.globalAlpha=.45;g.drawImage(tmp,0,0);g.globalAlpha=1;
  g.globalCompositeOperation='destination-out';g.globalAlpha=.38;g.drawImage(erosionMask('spray',Math.ceil(b.width/4),Math.ceil(b.height/4),.5,3),0,0,b.width,b.height);g.globalAlpha=1;
  // Shade = 0.4 + 0.6 × the wall's (brightened) luminance: paint on a dark wall is dim but never vanishes.
  if(env){tg.clearRect(0,0,tmp.width,tmp.height);tg.fillStyle='rgb(102,102,102)';tg.fillRect(0,0,tmp.width,tmp.height);tg.globalAlpha=.6;tg.filter='grayscale(1) contrast(1.35) brightness(2.3)';tg.drawImage(env,0,0);tg.filter='none';tg.globalAlpha=1;
    tg.globalCompositeOperation='destination-in';tg.drawImage(b,0,0);tg.globalCompositeOperation='source-over';
    g.globalCompositeOperation='multiply';g.drawImage(tmp,0,0);}
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
  const [kw,kh]=quadSize(sub?subQuad(key,sub):key);
  const W=Math.max(64,Math.min(1600,Math.round(Math.max(kw,kh*kw/Math.max(1,kh))*1.6))),H=Math.max(16,Math.round(W*kh/Math.max(1,kw)));
  const off=document.createElement('canvas');off.width=W;off.height=H;const o=off.getContext('2d')!;
  const marquee=scrollK!==undefined;
  const fit=marquee?H*.62/Math.max(1,line.height*1.1):Math.min(W*.88/Math.max(1,line.total),H*.72/Math.max(1,line.height*1.1));
  // Under a look the wall text takes the look's colour; material still shapes the finish.
  const material=look?.wall==='spray'&&fx?'spray':look?.finish==='neon'?'neon':look?.wall==='poster'?(surface.material==='neon'?'neon':surface.material==='flat'?'flat':'poster')
    :look?(look.optics.glow&&look.optics.glow>.5?'neon':look.texture==='paper'?'paint':surface.material||'flat'):surface.material||'paint';
  const scroll=marquee?((W/fit+line.total)/2-scrollK!*(W/fit+line.total)):0;
  o.save();o.translate(W/2,H/2);o.scale(fit,fit);
  if(line.card&&look?.palette.card){const pad=line.size*.32;const al=line.metrics[0].style.align;const x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
    o.fillStyle=look.palette.card;o.fillRect(x0-pad+(marquee?((W/fit+line.total)/2-scrollK!*(W/fit+line.total)):0),-line.height/2-pad*.6,line.total+2*pad,line.height+pad*1.2);}
  if(material==='neon'){if(look?.finish==='neon'&&!fx?.lightOnly)drawMount(o,line,surface.id);drawTubes(o,line,t,frame,fit,{shadow:0,plain:true,scroll,flicker:look?.flicker});}
  else if(material==='spray'){drawWords(o,line,t,frame,{shadow:0,plain:true,scroll});drawSprayMarks(o,line,t,look?.drips??.5,true);}
  else if(material==='poster'){
    // Wheat-pasted photocopy: torn off-white sheet filling the plane, toner-black type, copier streaks.
    o.save();o.setTransform(1,0,0,1,0,0);drawPosterSheet(o,surface.id,W,H);o.restore();
    const saved=line.metrics.map(m=>m.style);line.metrics.forEach(m=>m.style={...m.style,fill:'#0c0c0c',stroke:null,strokeWidth:null});
    drawWords(o,line,t,frame,{shadow:0,plain:true,scroll});line.metrics.forEach((m,i)=>m.style=saved[i]);
  }else drawWords(o,line,t,frame,{shadow:0,plain:true,scroll});
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

export class StageRenderer {
  project:Project;server:string;bg?:HTMLVideoElement;matte?:HTMLVideoElement;tracks?:Tracks;shots=new Map<string,HTMLVideoElement>();
  occupancy?:Occupancy;crop?:CropData;surfaceTracks=new Map<string,SurfaceTrack|null>();
  /** Set false to render positions exactly as authored (before/after comparisons). */
  autoPlace=true;
  /** Set false to skip the P0b optics (motion blur, chroma) — e.g. for fast scrubbing. Export keeps them. */
  heavyOptics=true;
  private plan?:{sig:string;map:Map<string,LinePlacement>};private fixedBoxes:Placed[]=[];private occSource?:{key:object;crop?:CropData;src:OccupancySource};
  private unitCache?:{sig:string;units:Line[]};private buffers:HTMLCanvasElement[]=[];
  constructor(project:Project,server=''){this.project=project;this.server=server;}
  async load(layer:Layer='composite'){
    const p=this.project;
    await loadFonts();
    if(p.analysis.tracks)this.tracks=await fetch(assetUrl(p,p.analysis.tracks,this.server)).then(r=>{if(!r.ok)throw new Error('Cannot load tracking data');return r.json();});
    // Occupancy: server file when present; else a local fixture (until the server writes it); else tracks fallback.
    this.occupancy=p.analysis.occupancy?await json<Occupancy>(assetUrl(p,p.analysis.occupancy,this.server)):undefined;
    if(!this.occupancy&&p.id!=='sample')this.occupancy=await json<Occupancy>(`/fixtures/${encodeURIComponent(p.frame?.source?.projectId||p.id)}/occupancy.json`);
    if(p.frame?.crop&&!this.crop)this.crop=await json<CropData>(assetUrl(p,p.frame.crop,this.server));
    await this.loadFields();
    await this.loadSurfaceTracks();
    if(layer!=='composite')return;
    if(p.media.video)this.bg=await video(assetUrl(p,p.media.video.path,this.server));
    if(p.analysis.matte)this.matte=await video(assetUrl(p,`${p.analysis.matte.replace(/\/$/,'')}/fg.webm`,this.server));
    await Promise.all(p.shots.filter(s=>s.status==='done'&&s.video).map(async s=>this.shots.set(s.id,await video(assetUrl(p,s.video!,this.server)))));
  }
  /** Field data (motion, voice), loaded when the analysis exists. */
  flow?:FlowField;voice?:VoiceField;
  async loadFields(){
    const p=this.project;
    if(p.analysis.flow&&!this.flow){const d=await json<FlowDoc>(assetUrl(p,p.analysis.flow,this.server));if(d)this.flow=new FlowField(d);}
    if(p.analysis.voice&&!this.voice){const d=await json<VoiceDoc>(assetUrl(p,p.analysis.voice,this.server));if(d)this.voice=new VoiceField(d);}
  }
  async loadSurfaceTracks(){
    const p=this.project;
    await Promise.all((p.surfaces||[]).filter(s=>s.track&&!this.surfaceTracks.has(`${s.id}:${s.track}`)).map(async s=>{
      this.surfaceTracks.set(`${s.id}:${s.track}`,(await json<SurfaceTrack>(assetUrl(p,s.track!,this.server)))||null);
    }));
  }
  dispose(){for(const v of [this.bg,this.matte,...this.shots.values()])if(v){v.pause();v.removeAttribute('src');v.load();}}
  occ(){
    const key=this.occupancy||this.tracks||this;const p=this.project;
    if(!this.occSource||this.occSource.key!==key||this.occSource.crop!==this.crop)
      this.occSource={key,crop:this.crop,src:new OccupancySource(this.occupancy,this.tracks,p.fps,this.crop,p.height>p.width)};
    return this.occSource.src;
  }
  private look(){return lookOf(this.project);}
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
    const p=this.timed();
    const sig=JSON.stringify([p.width,p.height,p.fps,p.style,p.words,p.look,p.lineMeta,this.autoPlace,this.occ().kind,!!this.crop]);
    if(this.plan?.sig===sig)return this.plan.map;
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
    const map=autoPlace(reqs,this.occ(),p.width/p.height,obstacles,this.safeMargins(.06));
    this.plan={sig,map};this.fixedBoxes=obstacles;return map;
  }
  /** Draw text units of one depth layer at time t (fractional frame `ft` for motion-blur sub-samples). */
  private renderWords(ctx:CanvasRenderingContext2D,t:number,frame:number,subset:'all'|'behind'|'front',blend:boolean,ft=frame){
    const p=this.timed();const plan=this.layout(ctx);const look=this.look();
    for(const line of this.units(ctx)){
      if(t<line.start||t>=line.end)continue;
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
        drawSurfaceLine(ctx,p,line,s,quad,t,frame,blend,look,marqueeK,sub,cropAt(this.crop,frame),look?.wall==='spray'||look?.finish==='neon'?{env:this.env,buf:i=>this.buffer(i),lightOnly:this.lightOnly}:undefined);continue;
      }
      let fit=line.bleed?1:Math.min(1,p.width*.88/Math.max(1,line.total));
      let origin=first.position||{x:.5,y:.72};let anchorPx:Point|undefined;
      const auto=plan.get(line.key);
      if(auto){
        fit*=auto.scale;const align=line.metrics[0].style.align;const half=line.total*fit/2/p.width;
        origin={x:auto.cx+(align==='left'?-half:align==='right'?half:0),y:auto.cy};
      }
      if(placement==='anchor'){
        const anchor=first.anchor||{trackId:'person0',dx:0,dy:-.1};const point=anchorAtT(this.tracks,anchor.trackId,ft*(this.tracks?.fps||p.fps)/p.fps);
        if(!point||!anchorAt(this.tracks,anchor.trackId,Math.round(t*(this.tracks?.fps||p.fps))))continue;const [cx,cy]=this.point(frame,point.cx,point.cy);
        anchorPx=[cx*p.width,cy*p.height];origin={x:cx+anchor.dx,y:cy+anchor.dy};
        // Keep the label (and its HUD tag) on screen: proof D clipped it off the top.
        const hw=line.total*fit/2/p.width+.012,top=(line.height/2+line.size*(first.preset==='hud'?.85:.2))*fit/p.height,bot=(line.height/2+line.size*.2)*fit/p.height;
        // Horizontal extent from the origin: the label by its alignment, and the HUD tag (left-aligned on the box,
        // often wider than a short label: "PERSON0 · F0190 · 0.96").
        const al=line.metrics[0].style.align,lx=-(al==='center'?line.total/2:al==='right'?line.total:0),pad=line.size*.3;
        const tagW=first.preset==='hud'?(`${anchor.trackId} · F0000 · 0.00`.length*.6+.6)*Math.max(13/fit,line.size*.36):0;
        const exL=(lx-pad)*fit/p.width,exR=Math.max(lx+line.total+pad,lx-pad+tagW)*fit/p.width;void hw;
        const [smx,smy]=this.safeMargins(.03);origin={x:Math.min(1-exR-smx,Math.max(smx-exL,origin.x)),y:Math.min(1-bot-smy,Math.max(top+smy,origin.y))};
        // Fixed text on screen now (HUD meta line, subtitles, titles): an anchored label drops below it.
        for(const o of this.fixedBoxes){if(frame<o.f0||frame>o.f1)continue;const [x0,y0,x1,y1]=o.box;
          const cl=.025;if(origin.x+exR>x0&&origin.x+exL<x1&&origin.y+bot>y0-cl&&origin.y-top<y1+cl&&y1+top+cl<1-bot-smy)origin={x:origin.x,y:y1+top+cl};}
      }
      const opts:DrawOpts=look?{shadow:look.texture==='paper'?1:look.halo!=null&&!line.sub?look.halo:placement==='behind'&&look.palette.shadow?.5:0,shadowColor:look.palette.shadow,hard:look.texture==='paper',karaoke:look.palette.accent,
          note:look.palette.note&&look.palette.shadow?{fill:look.palette.note,stroke:look.palette.shadow}:undefined,sparkle:(line.role==='hook'||line.role==='hero')?look.optics.sparkle:undefined,motion:look.intensity,flicker:look.flicker,
          voice:this.voice&&look.fields?.voice&&line.role!=='hud'&&!line.sub?{field:this.voice,amount:look.fields.voice}:undefined}
        :{shadow:first.style?.shadow??(placement==='behind'?.5:0)};
      ctx.save();ctx.translate(origin.x*p.width,origin.y*p.height);ctx.scale(fit,fit);
      if(line.card&&look?.palette.card&&marqueeK===undefined){const pad=line.size*.32;const al=line.metrics[0].style.align;const x0=-(al==='center'?line.total/2:al==='right'?line.total:0);
        ctx.fillStyle=look.palette.card;ctx.fillRect(x0-pad,-line.height/2-pad*.75,line.total+2*pad,line.height+pad*1.5);}
      if(marqueeK!==undefined&&line.card&&look?.palette.card){
        // LED band: the card becomes a full-width strip the line scrolls through.
        const pad=line.size*.32;ctx.fillStyle=look.palette.card;ctx.fillRect(-origin.x*p.width/fit,-line.height/2-pad*.75,p.width/fit,line.height+pad*1.5);}
      if(marqueeK!==undefined){
        // LED ticker: the line scrolls right→left through a fixed band over its duration.
        const band=Math.max(line.total*.6,p.width*.7/fit);ctx.beginPath();ctx.rect(-band/2,-line.height,band,line.height*2);ctx.clip();
        opts.scroll=(band+line.total)/2-marqueeK*(band+line.total);
      }
      const hud=line.words.some(w=>w.preset==='hud');
      const hudColor=look?hudLine(look):undefined;
      if(hud)this.drawHud(ctx,line,t,frame,fit,origin,anchorPx,first.anchor?.trackId||'person0',true,hudColor);
      this.drawUnit(ctx,line,t,frame,fit,opts,look);
      if(hud)this.drawHud(ctx,line,t,frame,fit,origin,anchorPx,first.anchor?.trackId||'person0',false,hudColor);
      ctx.restore();
    }
  }
  /** Per-unit draw site for screen text (context already at the unit's origin, scaled by fit). One place to hook
   *  per-unit/per-glyph effects. Neon look: tubes (subtitles and HUD stay crisp). */
  private drawUnit(ctx:CanvasRenderingContext2D,line:Line,t:number,frame:number,fit:number,opts:DrawOpts,look?:Look){
    if(look?.finish==='neon'&&!line.sub&&line.role!=='hud'){if(!this.lightOnly)drawMount(ctx,line,line.key);drawTubes(ctx,line,t,frame,fit,{...opts,shadow:0,plain:true});return;}
    if(look?.wall==='spray'&&!line.sub&&line.role!=='hud'){
      // Spray paint on the background: drawn in a screen buffer, then overspray, drips and the wall's own light.
      const b=this.buffer(28),g=b.getContext('2d')!;g.setTransform(ctx.getTransform());
      drawWords(g,line,t,frame,{...opts,shadow:0,plain:true});drawSprayMarks(g,line,t,look.drips??.5,line.role!=='sat'&&line.role!=='verse');
      const m=ctx.getTransform();sprayify(b,this.buffer(29),line.size*Math.hypot(m.a,m.b),this.env);
      ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha*=.94;ctx.drawImage(b,0,0);ctx.restore();return;
    }
    drawWords(ctx,line,t,frame,opts);
  }
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
    const light={x:(X/W+.5)/sw,y:(Y/W+.5)/sh,color:[R/W,G/W,B/W],power:Math.min(1,W/(sw*sh)*16),bottom:(bottom+1)/sh};this.light=light;
    const S=this.buffer(21),g=S.getContext('2d')!;g.fillStyle='#000';g.fillRect(0,0,S.width,S.height);g.globalCompositeOperation='lighter';
    g.filter=`blur(${(p.height*.045).toFixed(1)}px)`;g.drawImage(L,0,0);g.drawImage(L,0,0);
    g.filter=`blur(${(p.height*.16).toFixed(1)}px)`;g.drawImage(L,0,0);g.drawImage(L,0,0);g.drawImage(L,0,0);g.filter='none';
    // Wet floor: the sign mirrored below its lowest lit row, squashed and blurred, fading out downward.
    const floor=Math.max(light.bottom*p.height+p.height*.04,p.height*.62);
    if(floor<p.height*.97){const T=this.buffer(22),tg=T.getContext('2d')!;tg.setTransform(1,0,0,-.55,0,floor*1.55);tg.filter=`blur(${(p.height*.012).toFixed(1)}px)`;tg.drawImage(L,0,0);tg.filter='none';tg.setTransform(1,0,0,1,0,0);
      const gr=tg.createLinearGradient(0,floor,0,floor+p.height*.3);gr.addColorStop(0,'rgba(0,0,0,.55)');gr.addColorStop(1,'rgba(0,0,0,0)');
      tg.globalCompositeOperation='destination-in';tg.fillStyle=gr;tg.fillRect(0,0,T.width,T.height);tg.globalCompositeOperation='source-over';g.drawImage(T,0,0);}
    g.globalCompositeOperation='multiply';g.filter='grayscale(1) brightness(1.7)';if(this.env)g.drawImage(this.env,0,0);g.filter='none';g.globalCompositeOperation='source-over';
    ctx.save();ctx.globalCompositeOperation='lighter';ctx.globalAlpha=Math.min(1,amount);ctx.drawImage(S,0,0);ctx.restore();
  }
  /** Neon relights the subject: a coloured rim on the matte edges that face the sign (matte minus itself shifted toward
   *  the light) and a soft colour cast, both scaled by the sign's power and its distance to the subject. */
  private relight(ctx:CanvasRenderingContext2D,frame:number,amount:number){
    const l=this.light;if(!l||!this.matte)return;const p=this.project;
    const M=this.buffer(23);const mg=M.getContext('2d')!;this.drawMedia(mg,this.matte,frame);
    const a=anchorAt(this.tracks,'person0',frame);const [sx,sy]=a?this.point(frame,a.cx,a.cy):[.5,.5];
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
    const onset=line.words.some(w=>{const k=Math.round((t-w.start)*p.fps);return k>=0&&k<3;});
    const jx=onset?(hash01(`${line.key}:${frame}`)-.5)*size*.12:0;
    const bx=x0-pad+jx,by=-line.height/2-size*.18,bw=line.total+2*pad,bh=line.height+size*.36;
    ctx.save();ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=Math.max(1.5,p.height/480)/fit;ctx.globalAlpha=onset?1:.92;
    if(backdrop){ctx.fillStyle='rgba(8,10,6,.45)';ctx.fillRect(bx,by,bw,bh);ctx.restore();return;}
    bracket(ctx,bx,by,bw,bh,Math.min(bw,bh)*.32);
    if(anchorPx){
      // Leader from the nearest box edge to the tracked point.
      const ax=(anchorPx[0]-origin.x*p.width)/fit,ay=(anchorPx[1]-origin.y*p.height)/fit;
      const ex=Math.min(bx+bw,Math.max(bx,ax)),ey=Math.min(by+bh,Math.max(by,ay));
      if(Math.hypot(ax-ex,ay-ey)>size*.3){ctx.beginPath();ctx.moveTo(ex,ey);ctx.lineTo(ax,ay);ctx.stroke();ctx.beginPath();ctx.arc(ax,ay,Math.max(3,size*.09),0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.arc(ax,ay,Math.max(1.2,size*.03),0,Math.PI*2);ctx.fill();}
    }
    const tag=Math.max(13/fit,size*.36);ctx.font=`700 ${tag}px "Space Mono"`;ctx.textBaseline='bottom';ctx.textAlign='left';
    const conf=(.86+hash01(`${trackId}:${Math.floor(frame/6)}`)*.13).toFixed(2);
    const label=`${trackId.toUpperCase()} · F${String(frame).padStart(4,'0')} · ${conf}`;
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
    const look=this.look();const o=look?.optics||{};const p=this.project;
    if(!look){this.renderWords(ctx,t,frame,subset,blend);return;}
    // Subtitle register: kept out of the optics chain (no blur/chroma/warp/glow) and drawn crisp on top.
    this.subPass=false;try{this.opticsPass(ctx,t,frame,subset,blend,look,o,p);}finally{this.subPass=undefined;}
    if(subset!=='behind'){this.subPass=true;try{this.renderWords(ctx,t,frame,'front',blend);}finally{this.subPass=undefined;}}
  }
  private subPass?:boolean;private freePass?:boolean;
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
    if(look.texture==='paper'){g.globalCompositeOperation='destination-out';g.globalAlpha=.55;g.drawImage(erosionMask(`paper:${p.id}`,Math.ceil(buf.width/2),Math.ceil(buf.height/2),.6,3),0,0,buf.width,buf.height);g.globalAlpha=1;g.globalCompositeOperation='source-over';}
    if(moving){
      // Motion field: free lines drift with the camera (inertia) and are pushed like liquid by what moves through them;
      // pinned lines (walls, anchors, HUD) are drawn on top unmoved.
      const out=this.buffer(9),og=out.getContext('2d')!;drawMotion(og,src,this.flow!,{amount:fm,width:p.width,height:p.height,frame:Math.round(frame),
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
    const glow=o.glow||0;
    if(glow>0){
      const r=glow*.03*p.height;ctx.save();ctx.globalCompositeOperation=blend?'screen':'lighter';
      ctx.filter=`blur(${r.toFixed(2)}px)`;ctx.globalAlpha=Math.min(1,.55+.5*glow);ctx.drawImage(src,0,0);
      ctx.filter=`blur(${(r/3).toFixed(2)}px)`;ctx.globalAlpha=.7*glow;ctx.drawImage(src,0,0);ctx.restore();
    }
    ctx.drawImage(src,0,0);
  }
  /** Draw a video frame (through the crop) with the project's grade (gradeOf): 'color' tint keeping luminance,
   *  halation, photocopy mono (+ beat flash). The grade is independent of the look. */
  private paintVideo(ctx:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number,graded:boolean){
    const p=this.project;const c=cropAt(this.crop,frame);const gr=graded?this.grade():undefined;const tint=gr?.tint;
    const draw=(g:CanvasRenderingContext2D)=>{if(c){const vw=v.videoWidth,vh=v.videoHeight;g.drawImage(v,c.x*vw,c.y*vh,c.w*vw,c.h*vh,0,0,p.width,p.height);}else g.drawImage(v,0,0,p.width,p.height);};
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
  /** A media frame through the crop, ungraded. */
  private drawMedia(g:CanvasRenderingContext2D,v:HTMLVideoElement,frame:number){
    const p=this.project;const c=cropAt(this.crop,frame);
    if(c){const vw=v.videoWidth,vh=v.videoHeight;g.drawImage(v,c.x*vw,c.y*vh,c.w*vw,c.h*vh,0,0,p.width,p.height);}else g.drawImage(v,0,0,p.width,p.height);
  }
  async render(canvas:HTMLCanvasElement,frame:number,layer:Layer='composite'){
    const p=this.project;const last=Math.max(0,Math.round(p.duration*p.fps)-1);frame=Math.max(0,Math.min(last,frame));const t=frame/p.fps;
    await this.loadSurfaceTracks();
    if(canvas.width!==p.width)canvas.width=p.width;if(canvas.height!==p.height)canvas.height=p.height;
    const ctx=canvas.getContext('2d')!;
    const fl=this.grade()?.flash;
    if(fl&&this.beats===undefined&&p.id!=='sample')this.beats=(await json<BeatGrid>(assetUrl(p,(p.analysis as {beats?:string|null}).beats||'analysis/beats.json',this.server)))||null;
    this.flashNow=fl&&this.beats?flashAt(this.beats,t,fl):0;
    if(layer==='composite'){
      const shot=p.shots.find(s=>s.status==='done'&&s.video&&s.start<=t&&s.end>t);const clip=shot?this.shots.get(shot.id):this.bg;
      // Seek every media source before touching the visible canvas; never expose a half-painted frame.
      // Mid-frame times: frame f's pts is f/fps rounded to the container timebase, so seeking to exactly f/fps can
      // land a hair before it and show frame f-1. Half a frame in is unambiguous for both the footage and the matte.
      const mid=.5/p.fps;
      await Promise.all([clip?seek(clip,(shot?t-shot.start:t)+mid):Promise.resolve(),this.matte&&!shot?seek(this.matte,t+mid):Promise.resolve()]);
      ctx.clearRect(0,0,p.width,p.height);
      if(clip)this.paintVideo(ctx,clip,frame,true);else{ctx.fillStyle='#242923';ctx.fillRect(0,0,p.width,p.height);}
      // Scene looks (graffiti, neon) read the graded footage: paint takes the wall's light, signs light the wall.
      const look=this.look();const scene=look?.wall==='spray'||look?.finish==='neon';
      if(scene){const e=this.buffer(30);e.getContext('2d')!.drawImage(canvas,0,0);this.env=e;}
      const neonLight=look?.finish==='neon'?look.light??.8:0;
      if(neonLight>0)this.lightPass(ctx,t,frame,neonLight);else this.light=undefined;
      this.textPass(ctx,t,frame,'behind',true);
      if(this.matte&&!shot){this.paintVideo(ctx,this.matte,frame,true);if(neonLight>0)this.relight(ctx,frame,neonLight);}
      this.textPass(ctx,t,frame,'front',true);
      this.env=undefined;
      const grain=this.grade()?.grain||0;
      if(grain>0){
        // Composite-only film grain: a seeded tile, offset per frame, overlay-blended.
        const tile=grainTile(frame%4);const pat=ctx.createPattern(tile,'repeat')!;const ox=Math.floor(hash01(`g${frame}x`)*256),oy=Math.floor(hash01(`g${frame}y`)*256);
        ctx.save();ctx.globalCompositeOperation='overlay';ctx.globalAlpha=Math.min(1,grain*.6);ctx.translate(-ox,-oy);ctx.fillStyle=pat;ctx.fillRect(ox,oy,p.width,p.height);ctx.restore();
      }
    }else{this.env=undefined;ctx.clearRect(0,0,p.width,p.height);this.textPass(ctx,t,frame,layer==='text-behind'?'behind':layer==='text-front'?'front':'all',false);}
  }
}
