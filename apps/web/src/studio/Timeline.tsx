// Arrangement timeline: one track per group (captions, hooks, behind, wall, HUD, in-world); a group's lines share rows and
// spill to a new row only when their times overlap (groups.ts packTracks). Word clips, waveform, beat grid, snap, zoom, loop brace.
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {Project,Word,CropData} from '../types';
import {lineIsHook,heroWordId,wordIsShown} from '../looks';
import type {Beats} from './pipeline';
import {Filmstrip} from './Filmstrip';
import {GROUPS,packTracks,type GroupId} from './groups';
import {type Clip,setClip,mapBeats,moveClip,slipClip,shiftDelta,shiftWords} from '../audioClip';
import {Icon} from './icons';

export type LineInfo = {id:string;index:number;words:Word[];start:number;end:number;text:string;role:Role;hook:boolean;hidden:boolean;heroId?:string};
export type Role = 'behind'|'caption'|'hud'|'wall'|'inworld'|'anchor';
export const ROLE_LABEL:Record<Role,string> = {behind:'Behind',caption:'Caption',hud:'HUD',wall:'Wall',inworld:'In-world',anchor:'Anchor'};
export function roleOf(words:Word[]):Role{
  const w=words[0];if(!w)return 'caption';
  if(w.placement==='surface')return 'wall';if(w.placement==='inworld')return 'inworld';
  if(w.placement==='anchor')return words.some(x=>x.preset==='hud')?'hud':'anchor';
  return w.placement==='behind'?'behind':'caption';
}
export function lineInfos(p:Project):LineInfo[]{
  const groups=new Map<string,Word[]>();
  for(const w of p.words){const g=groups.get(w.lineId);if(g)g.push(w);else groups.set(w.lineId,[w]);}
  const out=[...groups.entries()].map(([id,ws])=>{const words=[...ws].sort((a,b)=>a.start-b.start);
    const safe=(f:()=>unknown,d:unknown)=>{try{return f();}catch{return d;}};
    return {id,index:0,words,start:Math.min(...words.map(w=>w.start)),end:Math.max(...words.map(w=>w.end)),text:words.map(w=>w.text).join(' '),role:roleOf(words),
      hook:Boolean(safe(()=>lineIsHook(p,id),false)),hidden:!!p.lineMeta?.[id]?.hidden||words.every(w=>w.hidden),heroId:safe(()=>heroWordId(p,id),undefined) as string|undefined};});
  out.sort((a,b)=>a.start-b.start||a.id.localeCompare(b.id));out.forEach((l,i)=>l.index=i);return out;
}
/** Visual end of a word clip: the next word's onset in the same line, so clips tile instead of stacking. */
function clipEnd(line:LineInfo,i:number){const w=line.words[i];const next=line.words[i+1];return next?Math.max(w.start+.001,Math.min(w.end,next.start)):w.end;}

const HEADER=48;
type Drag = {kind:'onset'|'line'|'end'|'scrub'|'loop'|'clipIn'|'clipOut'|'move'|'slip';lineId?:string;wordId?:string;x0:number;t0:number;orig?:Word[];moved?:boolean;
  clip0?:Clip;words0?:Map<string,[number,number]>};

export function Timeline(props:{
  project:Project;frame:number;playing:boolean;selectedWord:string;selectedLine?:string;
  waveform:Float32Array|null;beats?:Beats;loop:{a:number;b:number}|null;loopOn:boolean;snap:boolean;zoom:number;
  setZoom:(z:number)=>void;setSnap:(s:boolean)=>void;setLoop:(l:{a:number;b:number}|null)=>void;setLoopOn:(b:boolean)=>void;
  /** scope: a word chip picks the word, a line region the line (Delete removes that). */
  onSelect:(wordId:string,seek?:boolean,scope?:'word'|'line')=>void;
  /** Add a text clip at a time on a track (double-click empty track space / context menu); delete words or lines. */
  onAddAt?:(time:number,group:GroupId)=>void;onDelete?:(t:{lineIds:string[];wordIds:string[]})=>void;
  /** Inline text edit on a word chip (opened by a new clip or a double-click). */
  inlineEdit?:{wordId:string;fresh:boolean}|null;onEditText?:(wordId:string)=>void;onCommitText?:(wordId:string,text:string)=>void;onCancelText?:()=>void;
  /** Track dot: hide / show every line of a track on stage. */
  onSetHidden?:(lineIds:string[],hidden:boolean)=>void;
  /** What the stage can do for Behind (subject matte) and HUD (person track); flagged per line when missing. */
  subject?:{matte:'ok'|'none'|'missing'|'stale';person:boolean};
  /** A drag gesture starts: the next edit opens one undo step. */
  onCheckpoint?:()=>void;
  /** Drop an audio file on the waveform to replace the song; realign (set once replaced) re-runs words + beats. */
  onDropAudio?:(file:File)=>void;onRealign?:()=>void;onSeek:(frame:number)=>void;onEdit:(update:(p:Project)=>Project)=>void;onToggleHidden:(lineId:string)=>void;onAddWord:()=>void;
  /** Source video for the filmstrip (project media) and the reframe crop, if any. */
  videoSrc?:string;crop?:CropData;
  /** Song clip (resolved; null = no song) and the song's length. Beats are song time; the timeline maps them. */
  clip?:Clip|null;songDur?:number;linkWords?:boolean;setLinkWords?:(b:boolean)=>void;
  /** Multi-selection (Figma-style groups): selected line ids; group chip click / ⇧⌘-click on a lane head. */
  multi?:string[];onPickGroup?:(lineIds:string[],title:string,additive:boolean)=>void;onToggleLine?:(lineId:string)=>void;
  onCopy:()=>void;onPaste:()=>void;onSplit:()=>void;canCopy:boolean;canPaste:boolean;canSplit:boolean;
}){
  const {project:p,frame,zoom,loop}=props;const clip=props.clip||null;const songDur=props.songDur||p.duration;
  const beats=useMemo(()=>p.media.audioClip?mapBeats(props.beats,clip):props.beats,[props.beats,clip?.in,clip?.out,clip?.offset,!!p.media.audioClip]);// eslint-disable-line react-hooks/exhaustive-deps
  const [trimming,setTrimming]=useState(false);
  const scroller=useRef<HTMLDivElement>(null);const wave=useRef<HTMLCanvasElement>(null);
  const [dropping,setDropping]=useState(false);
  const [width,setWidth]=useState(900);const [height,setHeight]=useState(200);const [scrollX,setScrollX]=useState(0);
  const lines=useMemo(()=>lineInfos(p),[p]);
  const rowsRef=useRef(new Map<string,number>());
  // While a clip is being dragged its rows are held (no re-packing mid-gesture, so lanes never jump); re-pack on drop.
  const [holding,setHolding]=useState(false);
  const tracks=useMemo(()=>{const t=packTracks(lines,rowsRef.current,undefined,holding);rowsRef.current=new Map(t.flatMap(k=>k.lines.map(x=>[x.line.id,x.row] as [string,number])));return t;},[lines,holding]);
  const rowCount=tracks.reduce((n,t)=>n+t.rows,0);
  useLayoutEffect(()=>{const el=scroller.current;if(!el)return;const ro=new ResizeObserver(()=>{setWidth(el.clientWidth);setHeight(el.clientHeight);});ro.observe(el);setWidth(el.clientWidth);setHeight(el.clientHeight);return()=>ro.disconnect();},[]);
  const dur=Math.max(.001,p.duration);const bodyW=Math.max(200,(width-HEADER-2)*zoom);const pps=bodyW/dur;
  const X=(t:number)=>t*pps;const T=(x:number)=>Math.max(0,Math.min(dur,x/pps));
  const time=frame/p.fps;
  // Lanes share the free height (Ableton-like: few lines → tall clips), clamped to stay scannable.
  const audioH=rowCount>5?40:52;const filmH=props.videoSrc?46:0;const laneH=Math.round(Math.max(22,Math.min(46,(height-40-filmH-audioH-2)/Math.max(1,rowCount))));

  // Keep the playhead in view: pages along while playing; when stopped, only for jumps from outside the timeline
  // (keys, transport) and never while the user is dragging or has just scrolled/zoomed the timeline by hand.
  const handAt=useRef(0);const touch=()=>{handAt.current=performance.now();};
  const progScroll=useRef(-1);const setScroll=(el:HTMLElement,v:number)=>{v=Math.max(0,Math.round(v));progScroll.current=v;el.scrollLeft=v;};
  useEffect(()=>{if(props.playing)return;const el=scroller.current;if(!el||drag.current||performance.now()-handAt.current<1500)return;
    const x=X(time)+HEADER;const left=el.scrollLeft,right=left+el.clientWidth;
    if(x<left+HEADER||x>right-40)setScroll(el,x-HEADER-(el.clientWidth-HEADER)/3);},[frame]);// eslint-disable-line react-hooks/exhaustive-deps
  // Playing: the playhead runs on its own clock between rendered frames (playback can render slower than the footage),
  // and the view follows smoothly: once the playhead passes the middle it stays there and the timeline glides under it.
  const playheadEl=useRef<HTMLDivElement>(null);const clock=useRef({t:time,at:performance.now()});
  const live=useRef({pps,dur,time});live.current={pps,dur,time};
  useEffect(()=>{clock.current={t:time,at:performance.now()};},[frame]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{if(!props.playing)return;let raf=0;let te=-1,prev=performance.now();
    const tick=()=>{const el=scroller.current,ph=playheadEl.current;const L=live.current;const c=clock.current;const now=performance.now();
      // Own clock, monotonic; eases toward the studio's frame clock and only snaps on a real jump (loop, seek).
      const target=Math.min(L.dur,c.t+Math.min(.25,(now-c.at)/1000));
      if(te<0||Math.abs(target-te)>.3)te=target;else te+=(now-prev)/1000;prev=now;te=Math.min(L.dur,te);const x=te*L.pps;
      if(ph)ph.style.left=`${x}px`;
      if(el&&!drag.current&&performance.now()-handAt.current>1500){const vw=el.clientWidth-HEADER;const on=x-el.scrollLeft;
        if(on>vw*.5)setScroll(el,x-vw*.5);else if(on<0)setScroll(el,x-vw*.1);}
      raf=requestAnimationFrame(tick);};
    raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);},[props.playing]);
  // Zoom about a time that stays under the same screen x (the pointer, else the playhead, else the view centre).
  const zoomRef=useRef(zoom);zoomRef.current=zoom;const pendingScroll=useRef<number|null>(null);
  const zoomTo=(nz:number,clientX?:number)=>{const el=scroller.current;if(!el)return;nz=Math.max(1,Math.min(48,nz));const z0=zoomRef.current;if(Math.abs(nz-z0)<1e-4)return;touch();
    const r=el.getBoundingClientRect();const w0=Math.max(200,(el.clientWidth-HEADER-2)*z0),pps0=w0/dur;
    const sl=pendingScroll.current??el.scrollLeft;let sx:number;if(clientX!==undefined)sx=clientX-r.left-HEADER;else{const ph=time*pps0-sl;sx=ph>=0&&ph<=el.clientWidth-HEADER?ph:(el.clientWidth-HEADER)/2;}
    const t=Math.max(0,Math.min(dur,(sl+sx)/pps0));zoomRef.current=nz;props.setZoom(nz);
    // Several wheel events can land before the next paint: chain from the pending scroll, not the stale one.
    const npps=Math.max(200,(el.clientWidth-HEADER-2)*nz)/dur;const target=Math.max(0,t*npps-sx);pendingScroll.current=target;
  };
  // Applied once the wider body is laid out (setting it earlier would clamp to the old width).
  useLayoutEffect(()=>{const el=scroller.current;const v=pendingScroll.current;if(el&&v!=null){setScroll(el,v);pendingScroll.current=null;}},[zoom]);
  // Trackpad pinch (ctrl+wheel), ⌘/⌥+wheel: zoom at the pointer. Native listener: React's wheel handlers are passive,
  // so preventDefault there cannot stop the browser's own page zoom.
  useEffect(()=>{const el=scroller.current;if(!el)return;const on=(e:WheelEvent)=>{if(!(e.ctrlKey||e.metaKey||e.altKey)){touch();return;}e.preventDefault();
      const k=Math.exp(-(e.deltaMode===1?e.deltaY*16:e.deltaY)*(e.ctrlKey&&!e.metaKey?.01:.0025));zoomRef.current&&zoomToRef.current(zoomRef.current*k,e.clientX);};
    el.addEventListener('wheel',on,{passive:false});return()=>el.removeEventListener('wheel',on);},[]);
  const zoomToRef=useRef(zoomTo);zoomToRef.current=zoomTo;
  // = / − zoom about the playhead, \ fits (focus outside text fields).
  useEffect(()=>{const key=(e:KeyboardEvent)=>{const tg=e.target as HTMLElement;if(tg.matches?.('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey)return;
    if(e.key==='='||e.key==='+'){e.preventDefault();zoomToRef.current(zoomRef.current*1.5);}else if(e.key==='-'||e.key==='_'){e.preventDefault();zoomToRef.current(zoomRef.current/1.5);}
    else if(e.key==='\\'){e.preventDefault();zoomToRef.current(1);}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);

  // Waveform in project time: the song sits at shift = offset − in; inside the clip in full ink, trimmed parts dimmed.
  const sh=clip?clip.offset-clip.in:0;
  useEffect(()=>{const c=wave.current;if(!c)return;const w=Math.min(16000,Math.round(bodyW));const h=Math.max(20,audioH-8);const dpr=Math.min(2,window.devicePixelRatio||1);
    c.width=w*dpr;c.height=h*dpr;c.style.width=`${w}px`;c.style.height=`${h}px`;const g=c.getContext('2d')!;g.scale(dpr,dpr);g.clearRect(0,0,w,h);
    const data=props.waveform;if(!data||!data.length)return;const bins=data.length/2;const sd=Math.max(.001,songDur);const tpp=dur/w;
    for(let x=0;x<w;x++){const s0=x*tpp-sh,s1=(x+1)*tpp-sh;if(s1<=0||s0>=sd)continue;
      const i0=Math.max(0,Math.floor(s0/sd*bins)),i1=Math.min(bins,Math.max(i0+1,Math.floor(s1/sd*bins)));let lo=0,hi=0;for(let i=i0;i<i1;i++){lo=Math.min(lo,data[i*2]);hi=Math.max(hi,data[i*2+1]);}
      const sm=(s0+s1)/2;const inClip=!clip||sm>=clip.in&&sm<clip.out;if(!inClip&&!trimming)continue;g.fillStyle=inClip?'#2e2e2e':'#2e2e2e3a';
      const y0=h/2-hi*h*.46,y1=h/2-lo*h*.46;g.fillRect(x,y0,1,Math.max(1,y1-y0));}
  },[props.waveform,bodyW,sh,clip?.in,clip?.out,songDur,audioH,trimming,dur]);// eslint-disable-line react-hooks/exhaustive-deps
  // Snap candidates: beats, word onsets/ends, then frames.
  const snapPoints=useMemo(()=>{const pts:number[]=[];if(beats)pts.push(...beats.beats);for(const w of p.words){pts.push(w.start,w.end);}return pts;},[beats,p.words]);
  const snapT=(t:number,exclude:Set<string>|undefined,shift:boolean)=>{
    const fr=Math.round(t*p.fps)/p.fps;if(!props.snap||shift)return fr;
    let best=fr,bd=8/pps;const cands=exclude?[...(beats?.beats||[]),...p.words.filter(w=>!exclude.has(w.id)).flatMap(w=>[w.start,w.end])]:snapPoints;
    for(const c of cands){const d=Math.abs(c-t);if(d<bd){bd=d;best=c;}}return best;};

  // Quiet = stretches with no visible line on screen (≥ .5 s). Lets the director see the breathing room.
  const quiet=useMemo(()=>{const iv=lines.filter(l=>!l.hidden).flatMap(l=>l.words.filter(w=>{try{return wordIsShown(p,w);}catch{return true;}}).map(w=>[w.start,w.end] as [number,number])).sort((a,b)=>a[0]-b[0]);
    const out:[number,number][]=[];let cur=0;for(const [a,b] of iv){if(a-cur>=.5)out.push([cur,a]);cur=Math.max(cur,b);}if(dur-cur>=.5)out.push([cur,dur]);return out;},[lines,p,dur]);

  const ticks=useMemo(()=>{const steps=[1/p.fps,2/p.fps,.25,.5,1,2,5,10,15,30,60];const step=steps.find(s=>s*pps>=64)||60;const out:number[]=[];for(let t=0;t<=dur+1e-6;t+=step)out.push(+t.toFixed(4));return {step,out};},[pps,dur,p.fps]);
  const fmt=(t:number)=>ticks.step<1?`${Math.floor(t)}.${String(Math.round((t%1)*100)).padStart(2,'0')}`:`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;

  const drag=useRef<Drag|null>(null);
  // Right-click menu: on a word, a line, or empty track space.
  const [menu,setMenu]=useState<{x:number;y:number;time:number;group:GroupId;lineId?:string;wordId?:string}|null>(null);
  useEffect(()=>{if(!menu)return;const close=(e:Event)=>{if(e instanceof KeyboardEvent&&e.key!=='Escape')return;if(e.type==='pointerdown'&&(e.target as Element).closest?.('.tl-menu'))return;setMenu(null);};
    window.addEventListener('pointerdown',close,true);window.addEventListener('keydown',close,true);window.addEventListener('blur',close);
    return()=>{window.removeEventListener('pointerdown',close,true);window.removeEventListener('keydown',close,true);window.removeEventListener('blur',close);};},[menu]);
  const openMenu=(e:React.MouseEvent,group:GroupId,lineId?:string,wordId?:string)=>{e.preventDefault();e.stopPropagation();
    if(lineId)props.onSelect(wordId||(sel===lineId?props.selectedWord:p.words.find(w=>w.lineId===lineId)?.id||''),false,wordId?'word':'line');
    const r=(e.currentTarget as Element).closest('.tl')!.getBoundingClientRect();setMenu({x:e.clientX-r.left,y:e.clientY-r.top,time:T(bodyX(e as unknown as React.PointerEvent)),group,lineId,wordId});};
  const menuAct=(f:()=>void)=>()=>{setMenu(null);f();};
  const bodyX=(e:React.PointerEvent|PointerEvent)=>{const el=scroller.current!;const r=el.getBoundingClientRect();return e.clientX-r.left+el.scrollLeft-HEADER;};
  function begin(e:React.PointerEvent,d:Omit<Drag,'x0'|'t0'>){
    e.stopPropagation();(e.currentTarget as Element).setPointerCapture?.(e.pointerId);const x0=bodyX(e);
    drag.current={...d,x0,t0:T(x0),orig:d.lineId?p.words.filter(w=>w.lineId===d.lineId).map(w=>({...w})):undefined};
    if(clip&&(d.kind==='clipIn'||d.kind==='clipOut'||d.kind==='move'||d.kind==='slip')){if(d.kind==='clipIn'||d.kind==='clipOut')setTrimming(true);drag.current.clip0={...clip};drag.current.words0=new Map(p.words.map(w=>[w.id,[w.start,w.end]]));props.onCheckpoint?.();}
    if(d.lineId){props.onCheckpoint?.();setHolding(true);}touch();
    if(d.kind==='scrub')props.onSeek(Math.round(snapT(T(x0),undefined,true)*p.fps));
    if(d.kind==='loop')props.setLoop({a:snapT(T(x0),undefined,e.shiftKey),b:snapT(T(x0),undefined,e.shiftKey)});
  }
  // Song clip gestures, Premiere-style (one undo step each). Edges trim (never touch words; snap to beats / the playhead).
  // Body: move the clip in time. ⌥-drag the body: slip (the clip stays put, the song slides under it).
  // Move and slip shift linked words rigidly by the change in song position; snap puts a beat on the playhead.
  function clipMove(d:Drag,x:number,free:boolean){
    const c0=d.clip0!;const raw=props.beats?.beats||[];const now=frame/p.fps;
    const near=(v:number,cands:number[],tol:number)=>{if(!props.snap||free)return v;let best=v,bd=tol;for(const c of cands){const k=Math.abs(c-v);if(k<bd){bd=k;best=c;}}return best;};
    let next:Clip;
    if(d.kind==='clipIn'||d.kind==='clipOut'){const sh0=c0.offset-c0.in;const sn=near(T(x)-sh0,[...raw,now-sh0],8/pps);
      if(d.kind==='clipIn'){const i=Math.max(0,Math.min(c0.out-.1,sn));next={in:i,out:c0.out,offset:c0.offset+(i-c0.in)};}
      else next={in:c0.in,out:Math.max(c0.in+.1,Math.min(songDur,sn)),offset:c0.offset};
      props.onEdit(q=>setClip(q,next,songDur));return;}
    if(d.kind==='move'){const off=near(c0.offset+(x-d.x0)/pps,[0,...raw.filter(b=>b>=c0.in&&b<=c0.out).map(b=>now-b+c0.in)],8/pps);next=moveClip(c0,off,dur);}
    else{const ds=near(-(x-d.x0)/pps,raw.map(b=>c0.offset+b-now-c0.in),8/pps);next=slipClip(c0,ds,songDur);}
    const dt=props.linkWords!==false?shiftDelta(c0,next):0;const words0=d.words0!;
    props.onEdit(q=>{const r=setClip(q,next,songDur);return props.linkWords!==false?shiftWords(r,words0,dt):r;});
  }
  function move(e:React.PointerEvent){
    const d=drag.current;if(!d)return;e.stopPropagation();const x=bodyX(e);const t=T(x);if(Math.abs(x-d.x0)>2)d.moved=true;
    if(d.kind==='scrub'){props.onSeek(Math.round(t*p.fps));return;}
    if(d.clip0){if(!d.moved)return;clipMove(d,x,e.shiftKey);return;}
    if(d.kind==='loop'){const a=snapT(d.t0,undefined,e.shiftKey),b=snapT(t,undefined,e.shiftKey);props.setLoop({a:Math.min(a,b),b:Math.max(a,b)});props.setLoopOn(true);return;}
    if(!d.moved||!d.orig)return;const ids=new Set(d.orig.map(w=>w.id));const orig=new Map(d.orig.map(w=>[w.id,w]));
    if(d.kind==='onset'&&d.wordId){const o=orig.get(d.wordId)!;const sorted=[...d.orig].sort((a,b)=>a.start-b.start);const i=sorted.findIndex(w=>w.id===d.wordId);
      const lo=i>0?sorted[i-1].start+.02:0,hi=o.end-.02;const ns=Math.max(lo,Math.min(hi,snapT(o.start+(t-d.t0),new Set([d.wordId]),e.shiftKey)));
      props.onEdit(q=>({...q,words:q.words.map(w=>w.id===d.wordId?{...w,start:+ns.toFixed(3)}:w)}));}
    if(d.kind==='line'){const s0=Math.min(...d.orig.map(w=>w.start)),e0=Math.max(...d.orig.map(w=>w.end));
      let dt=t-d.t0;const snapped=snapT(s0+dt,ids,e.shiftKey);dt=snapped-s0;dt=Math.max(-s0,Math.min(dur-e0,dt));
      props.onEdit(q=>({...q,words:q.words.map(w=>ids.has(w.id)?{...w,start:+(orig.get(w.id)!.start+dt).toFixed(3),end:+(orig.get(w.id)!.end+dt).toFixed(3)}:w)}));}
    if(d.kind==='end'){const e0=Math.max(...d.orig.map(w=>w.end));const ne=Math.min(dur,snapT(e0+(t-d.t0),ids,e.shiftKey));
      props.onEdit(q=>({...q,words:q.words.map(w=>{if(!ids.has(w.id))return w;const o=orig.get(w.id)!;const end=Math.abs(o.end-e0)<1e-3||o.end>ne?Math.max(o.start+.02,ne):o.end;return {...w,end:+end.toFixed(3)};})}));}
  }
  function end(e:React.PointerEvent){const d=drag.current;if(d)e.stopPropagation();drag.current=null;if(d?.lineId)setHolding(false);(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    if(d?.clip0)setTrimming(false);
    if(d&&(d.kind==='move'||d.kind==='slip')&&!d.moved)props.onSeek(Math.round(T(d.x0)*p.fps));
    if(d&&d.kind==='loop'&&!d.moved){props.setLoopOn(false);}}

  const sel=props.selectedLine;
  return <section className="tl" aria-label="Arrangement timeline" style={{['--lane' as string]:`${laneH}px`,['--audio' as string]:`${audioH}px`}}>
    <div className="tl-bar">
      <button className="tool-btn" onClick={props.onAddWord} aria-label="Add text" title="Add text at the playhead (or double-click a track)"><Icon name="plus" size={15}/></button>
      <button className="tool-btn" onClick={props.onCopy} disabled={!props.canCopy} aria-label="Copy text clips" title="Copy selected text clips (⌘C)"><Icon name="copy" size={15}/></button>
      <button className="tool-btn" onClick={props.onPaste} disabled={!props.canPaste} aria-label="Paste text clips" title="Paste text clips at the playhead (⌘V)"><Icon name="paste" size={15}/></button>
      <button className="tool-btn" onClick={props.onSplit} disabled={!props.canSplit} aria-label="Split text clips" title="Split selected text clips at the playhead (⌘B)"><Icon name="split" size={15}/></button>
      <span className="tl-spacer"/>
      <button className={`tool-btn ${props.snap?'active':''}`} onClick={()=>props.setSnap(!props.snap)} aria-pressed={props.snap} aria-label="Snap" title="Snap to beats, word edges and frames (hold ⇧ to bypass)"><Icon name="magnet" size={15}/></button>
      <input className="zoom" type="range" min={0} max={1} step={.01} value={Math.log(zoom)/Math.log(48)} onChange={e=>zoomTo(Math.pow(48,Number(e.target.value)))} aria-label="Timeline zoom" title="Zoom: = / −, pinch or ⌥ scroll · \ fits"/>
      <button className="tool-btn" onClick={()=>zoomTo(1)} aria-label="Fit" title="Fit the whole song (\)"><Icon name="fit" size={15}/></button>
      <button className="tool-btn tl-keyhelp" aria-label="Shortcuts" title="space play · ←/→ frame · ⇧←/→ 1 s · home/end · L loop line · H hide line · esc back to look · = / − zoom · \ fit · pinch or ⌥ scroll zooms at the pointer · ←↑↓→ nudge the selected line (⇧ ×10) · drag a word to slip it · drag a line to move it · ⇧ drag skips snap · ⌘Z undo · drag a box corner on the stage to resize (⇧ fine, ⌥ from centre) · track dot hides / shows the track · click the track head to select it · double-click a track to add text · ⌫ deletes the selection · double-click a word to edit it · drag the song to move it, ⌥ drag to slip it, its edges to trim · 1–9 looks · G all looks · O subject · R boxes · W wall"><Icon name="keys" size={15}/></button>
    </div>
    <div className="tl-scroll" ref={scroller} onScroll={e=>{const v=e.currentTarget.scrollLeft;if(Math.abs(v-progScroll.current)>1)touch();setScrollX(v);}}>
      <div className="tl-inner" style={{width:HEADER+bodyW}}>
        <div className="tl-row tl-ruler-row">
          <div className="tl-head tl-corner"/>
          <div className="tl-ruler" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}>
            <div className="tl-loopstrip" onPointerDown={e=>begin(e,{kind:'loop'})} onPointerMove={move} onPointerUp={end} title="drag to loop">
              {loop&&<div className={`tl-loop ${props.loopOn?'on':''}`} style={{left:X(loop.a),width:Math.max(2,X(loop.b)-X(loop.a))}}/>}
            </div>
            <div className="tl-map">
              {beats?.sections?.map((sec,i)=><div key={`s${i}`} className={`tl-section sec-${(sec.label||'').toLowerCase()}`} style={{left:X(sec.start),width:Math.max(2,X(sec.end)-X(sec.start)-2)}}><span>{sec.label||`§${i+1}`}</span></div>)}
              {lines.filter(l=>l.hook&&!l.hidden).map(l=><i key={`h${l.id}`} className="tl-hookmark" style={{left:X(l.start),width:Math.max(2,X(l.end)-X(l.start))}} title={`hook · ${l.text}`}/>)}
            </div>
            {ticks.out.map(t=><span key={t} className="tl-tick" style={{left:X(t)}}>{fmt(t)}</span>)}
          </div>
        </div>
        {props.videoSrc&&<div className="tl-row tl-film" style={{['--film' as string]:`${filmH}px`}}>
          <div className="tl-head"/>
          <div className="tl-body" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}>
            <Filmstrip src={props.videoSrc} fps={p.fps} aspect={p.width/p.height} crop={props.crop} pps={pps} bodyW={bodyW} height={filmH-6} viewLeft={Math.max(0,scrollX)} viewWidth={Math.max(1,width-HEADER)}/>
          </div>
        </div>}
        {tracks.map(tk=>{const g=GROUPS.find(x=>x.id===tk.group)!;const ids=tk.lines.map(x=>x.line.id);const on=!!props.multi&&props.multi.length===ids.length&&ids.every(i=>props.multi!.includes(i));const off=tk.lines.every(x=>x.line.hidden);
          return <div key={tk.group} className={`tl-row tl-track grp-${tk.group} ${on?'sel':''} ${off?'off':''}`} style={{['--rows' as string]:tk.rows}}>
          <div className="tl-head" title={`Select all ${g.label} · ⇧ adds`} onClick={e=>props.onPickGroup?.(ids,g.label,e.shiftKey||e.metaKey)}>
            <button className={`tl-swatch ${off?'off':''}`} aria-pressed={!off} aria-label={`${off?'Show':'Hide'} ${g.label}`} title={`${off?'Show':'Hide'} ${g.label} on stage · ⌘ click selects`}
              onClick={e=>{e.stopPropagation();if(e.metaKey||e.ctrlKey){props.onPickGroup?.(ids,g.label,e.shiftKey);return;}props.onSetHidden?.(ids,!off);}}/></div>
          <div className="tl-body" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}
            onDoubleClick={e=>{if(e.target===e.currentTarget&&props.onAddAt&&tk.group!=='inworld')props.onAddAt(T(bodyX(e as unknown as React.PointerEvent)),tk.group);}}
            onContextMenu={e=>{if(e.target===e.currentTarget&&tk.group!=='inworld')openMenu(e,tk.group);}}>
          {tk.lines.map(({line:l,row})=>{const narrow=l.words.some((w,i)=>(X(clipEnd(l,i))-X(w.start))<Math.max(22,w.text.length*6.2));const picked=sel===l.id||!!props.multi?.includes(l.id);
            return <div key={l.id} className={`tl-line role-${l.role} ${picked?'sel':''} ${l.hidden?'hidden':''} ${l.hook?'hook':''} ${narrow?'compact':''}`} style={{top:row*laneH}}>
            <div className="tl-region" style={{left:X(l.start),width:Math.max(3,X(l.end)-X(l.start))}} title={`${String(l.index+1).padStart(2,'0')} · ${ROLE_LABEL[l.role]}${l.hook?' · hook':''} · ${l.text}`}
              onPointerDown={e=>{if(e.button===2)return;if(e.shiftKey||e.metaKey||e.ctrlKey){e.stopPropagation();props.onToggleLine?.(l.id);return;}props.onSelect(sel===l.id?props.selectedWord:l.words[0].id,false,'line');begin(e,{kind:'line',lineId:l.id});}} onPointerMove={move} onPointerUp={end}
              onContextMenu={e=>openMenu(e,tk.group,l.id)}>
              {narrow&&<span className="tl-region-label">{l.words.map(w=>w.text).join(' ')}</span>}
              {l.role==='behind'&&props.subject&&props.subject.matte!=='ok'&&<i className="tl-warn" onPointerDown={e=>e.stopPropagation()} title={MATTE_TITLE[props.subject.matte]}><Icon name="noMatte" size={11}/></i>}
              {(l.role==='hud'||l.role==='anchor')&&props.subject&&!props.subject.person&&<i className="tl-warn" onPointerDown={e=>e.stopPropagation()} title="No person track: HUD sits as a screen label · run Subject matte"><Icon name="noPerson" size={11}/></i>}
              <button className={`eye ${l.hidden?'off':''}`} aria-label={l.hidden?'Show line':'Hide line'} title={l.hidden?'show':'hide (H)'} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();props.onToggleHidden(l.id);}}>{l.hidden?'○':'●'}</button>
              <div className="tl-region-end" onPointerDown={e=>begin(e,{kind:'end',lineId:l.id})} onPointerMove={move} onPointerUp={end} />
            </div>
            {l.words.map((w,i)=>{const a=X(w.start),b=X(clipEnd(l,i));let shown=true;try{shown=wordIsShown(p,w);}catch{/* look API */}
              return <button key={w.id} className={`word-chip ${props.selectedWord===w.id?'selected':''} ${l.heroId===w.id?'hero':''} ${shown?'':'quiet'} ${w.placement}`} style={{left:a,width:Math.max(3,b-a-1)}}
                title={`${w.text} · ${w.start.toFixed(2)}–${w.end.toFixed(2)}s`}
                onPointerDown={e=>{if(e.button===2)return;props.onSelect(w.id,false,'word');begin(e,{kind:'onset',lineId:l.id,wordId:w.id});}} onPointerMove={move} onPointerUp={e=>{const d=drag.current;end(e);if(d&&!d.moved)props.onSeek(Math.round((w.start+.04)*p.fps));}}
                onDoubleClick={e=>{e.stopPropagation();props.onEditText?.(w.id);}} onContextMenu={e=>openMenu(e,tk.group,l.id,w.id)}>
                {l.heroId===w.id&&<i className="hero-dot"/>}<span>{w.text}</span></button>;})}
            {l.words.map((w,i)=>props.inlineEdit?.wordId===w.id&&<InlineText key={`e${w.id}`} word={w} left={X(w.start)} width={Math.max(96,X(clipEnd(l,i))-X(w.start))}
              onCommit={t=>props.onCommitText?.(w.id,t)} onCancel={()=>props.onCancelText?.()}/>)}
            </div>;})}
          </div>
        </div>;})}
        {!lines.length&&<div className="tl-row tl-empty"><div className="tl-head"/><div className="tl-body" style={{width:bodyW}}><span>No words yet</span></div></div>}
        <div className={`tl-row tl-audio ${dropping?'dropping':''} `} onDragOver={e=>{if(!props.onDropAudio||!e.dataTransfer.types.includes('Files'))return;e.preventDefault();e.dataTransfer.dropEffect='copy';setDropping(true);}}
          onDragLeave={()=>setDropping(false)} onDrop={e=>{setDropping(false);const f=[...e.dataTransfer.files].find(x=>x.type.startsWith('audio/')||/\.(wav|mp3|m4a|aac|flac|ogg)$/i.test(x.name));if(!f||!props.onDropAudio)return;e.preventDefault();props.onDropAudio(f);}}>
          <div className="tl-head tl-audiohead">
            {props.onRealign&&<button className="tl-realign" onClick={props.onRealign} aria-label="Re-align" title="Re-align words and beats to the new song">↻</button>}
            {clip&&props.setLinkWords&&<button className={`tl-link ${props.linkWords!==false?'on':''}`} onClick={()=>props.setLinkWords!(props.linkWords===false)} aria-pressed={props.linkWords!==false} aria-label="Words follow the song"
              title={props.linkWords!==false?'Words move with the song when you move or slip it · click to keep them':'Words stay put when you move or slip the song · click to move them too'}><Icon name={props.linkWords!==false?'link':'unlink'} size={13}/></button>}
          </div>
          <div className="tl-body" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}
            title={props.onDropAudio?'Drop a song here to replace it':undefined}>
            <canvas ref={wave} className="tl-wave"/>
            {clip&&<div className={`tl-clip ${clip.offset<-.001?'cut-l':''} ${clip.offset+clip.out-clip.in>dur+.001?'cut-r':''}`} style={{left:X(Math.max(0,clip.offset)),width:Math.max(6,X(Math.min(dur,clip.offset+clip.out-clip.in))-X(Math.max(0,clip.offset))),top:3}}
              title={`Song ${clip.in.toFixed(2)}–${clip.out.toFixed(2)} s at ${clip.offset.toFixed(2)} s · drag to move · ⌥ drag to slip the song under it · edges trim · double-click resets`}
              onPointerDown={e=>begin(e,{kind:e.altKey?'slip':'move'})} onPointerMove={move} onPointerUp={end} onPointerCancel={end}
              onDoubleClick={e=>{e.stopPropagation();props.onCheckpoint?.();props.onEdit(q=>setClip(q,null,songDur));}}>
              <i className="tl-clip-edge in" role="slider" aria-label="Song in" aria-valuenow={+clip.in.toFixed(2)} onPointerDown={e=>begin(e,{kind:'clipIn'})} onPointerMove={move} onPointerUp={end} onPointerCancel={end}/>
              <i className="tl-clip-edge out" role="slider" aria-label="Song out" aria-valuenow={+clip.out.toFixed(2)} onPointerDown={e=>begin(e,{kind:'clipOut'})} onPointerMove={move} onPointerUp={end} onPointerCancel={end}/>
            </div>}
          </div>
        </div>
        <div className="tl-overlay" style={{left:HEADER,width:bodyW}}>
          {quiet.map(([a,b],i)=><div key={`q${i}`} className="tl-quiet" title="quiet" style={{left:X(a),width:X(b)-X(a),top:38+filmH}}></div>)}
          {beats?.beats.map((b,i)=>{const down=beats.downbeats?beats.downbeats.some(d=>Math.abs(d-b)<.02):i%4===0;return <i key={i} className={`tl-beat ${down?'down':''}`} style={{left:X(b)}}/>;})}
          {loop&&props.loopOn&&<><i className="tl-loopedge" style={{left:X(loop.a)}}/><i className="tl-loopedge" style={{left:X(loop.b)}}/></>}
          <div className="playhead" ref={playheadEl} style={props.playing?undefined:{left:X(time)}}><span/></div>
        </div>
      </div>
    </div>
    {menu&&<div className="tl-menu" role="menu" style={{left:menu.x,top:menu.y}} onContextMenu={e=>e.preventDefault()}>
      {menu.wordId&&<button role="menuitem" onClick={menuAct(()=>props.onEditText?.(menu.wordId!))}>Edit text</button>}
      {menu.wordId&&<button role="menuitem" onClick={menuAct(()=>props.onDelete?.({lineIds:[],wordIds:[menu.wordId!]}))}>Delete word<kbd>⌫</kbd></button>}
      {menu.lineId&&<button role="menuitem" onClick={menuAct(()=>props.onDelete?.({lineIds:[menu.lineId!],wordIds:[]}))}>Delete line{!menu.wordId&&<kbd>⌫</kbd>}</button>}
      {!menu.lineId&&<button role="menuitem" onClick={menuAct(()=>props.onAddAt?.(menu.time,menu.group))}>Add text</button>}
    </div>}
  </section>;
}

const MATTE_TITLE={none:'No subject matte: Behind cannot cut out the person · run Subject matte',missing:'Subject matte did not load: Behind is not cut out · run Subject matte',
  stale:'Subject matte does not match the footage · run Subject matte again',ok:''};

/** Inline text field over a word chip: ↵ or blur commits (spaces make several words), esc cancels. */
function InlineText({word,left,width,onCommit,onCancel}:{word:Word;left:number;width:number;onCommit:(t:string)=>void;onCancel:()=>void}){
  const [v,setV]=useState(word.text);const done=useRef(false);
  const commit=()=>{if(done.current)return;done.current=true;onCommit(v);};
  return <input className="tl-inline" autoFocus aria-label="Text" value={v} style={{left,width}} onFocus={e=>e.currentTarget.select()}
    onChange={e=>setV(e.target.value)} onPointerDown={e=>e.stopPropagation()} onDoubleClick={e=>e.stopPropagation()}
    onKeyDown={e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();commit();}else if(e.key==='Escape'){e.preventDefault();done.current=true;onCancel();}}} onBlur={commit}/>;
}
