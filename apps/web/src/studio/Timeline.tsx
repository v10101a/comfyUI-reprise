// Arrangement timeline: one lane per line (Ableton-style), word clips that never overlap, waveform, beat grid,
// snap, zoom, loop brace, quiet/hook visibility.
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {Project,Word,CropData} from '../types';
import {lineIsHook,heroWordId,wordIsShown} from '../looks';
import type {Beats} from './pipeline';
import {Filmstrip} from './Filmstrip';

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

const HEADER=180;
type Drag = {kind:'onset'|'line'|'end'|'scrub'|'loop';lineId?:string;wordId?:string;x0:number;t0:number;orig?:Word[];moved?:boolean};

export function Timeline(props:{
  project:Project;frame:number;playing:boolean;selectedWord:string;selectedLine?:string;
  waveform:Float32Array|null;beats?:Beats;loop:{a:number;b:number}|null;loopOn:boolean;snap:boolean;zoom:number;
  setZoom:(z:number)=>void;setSnap:(s:boolean)=>void;setLoop:(l:{a:number;b:number}|null)=>void;setLoopOn:(b:boolean)=>void;
  onSelect:(wordId:string,seek?:boolean)=>void;onSeek:(frame:number)=>void;onEdit:(update:(p:Project)=>Project)=>void;onToggleHidden:(lineId:string)=>void;onAddWord:()=>void;
  /** Source video for the filmstrip (project media) and the reframe crop, if any. */
  videoSrc?:string;crop?:CropData;
}){
  const {project:p,frame,beats,zoom,loop}=props;
  const scroller=useRef<HTMLDivElement>(null);const wave=useRef<HTMLCanvasElement>(null);
  const [width,setWidth]=useState(900);const [height,setHeight]=useState(200);const [scrollX,setScrollX]=useState(0);
  const lines=useMemo(()=>lineInfos(p),[p]);
  useLayoutEffect(()=>{const el=scroller.current;if(!el)return;const ro=new ResizeObserver(()=>{setWidth(el.clientWidth);setHeight(el.clientHeight);});ro.observe(el);setWidth(el.clientWidth);setHeight(el.clientHeight);return()=>ro.disconnect();},[]);
  const dur=Math.max(.001,p.duration);const bodyW=Math.max(200,(width-HEADER-2)*zoom);const pps=bodyW/dur;
  const X=(t:number)=>t*pps;const T=(x:number)=>Math.max(0,Math.min(dur,x/pps));
  const time=frame/p.fps;
  // Lanes share the free height (Ableton-like: few lines → tall clips), clamped to stay scannable.
  const audioH=lines.length>5?36:52;const filmH=props.videoSrc?46:0;const laneH=Math.round(Math.max(22,Math.min(46,(height-40-filmH-audioH-2)/Math.max(1,lines.length))));

  // Keep the playhead in view while playing / when it jumps outside.
  useEffect(()=>{const el=scroller.current;if(!el)return;const x=X(time)+HEADER;const left=el.scrollLeft,right=left+el.clientWidth;
    if(x<left+HEADER||x>right-40)el.scrollLeft=Math.max(0,x-HEADER-(props.playing?40:(el.clientWidth-HEADER)/3));},[frame,zoom,width]);// eslint-disable-line react-hooks/exhaustive-deps

  // Waveform: min/max peaks drawn at the body's pixel width.
  useEffect(()=>{const c=wave.current;if(!c)return;const w=Math.min(16000,Math.round(bodyW));const h=44;const dpr=Math.min(2,window.devicePixelRatio||1);
    c.width=w*dpr;c.height=h*dpr;c.style.width=`${w}px`;const g=c.getContext('2d')!;g.scale(dpr,dpr);g.clearRect(0,0,w,h);
    const data=props.waveform;if(!data||!data.length)return;const bins=data.length/2;
    g.fillStyle='#2e2e2e';/* ink; CSS sets opacity and inverts it at night */for(let x=0;x<w;x++){const i0=Math.floor(x/w*bins),i1=Math.max(i0+1,Math.floor((x+1)/w*bins));let lo=0,hi=0;for(let i=i0;i<i1;i++){lo=Math.min(lo,data[i*2]);hi=Math.max(hi,data[i*2+1]);}
      const y0=h/2-hi*h*.46,y1=h/2-lo*h*.46;g.fillRect(x,y0,1,Math.max(1,y1-y0));}
  },[props.waveform,bodyW]);

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
  const bodyX=(e:React.PointerEvent|PointerEvent)=>{const el=scroller.current!;const r=el.getBoundingClientRect();return e.clientX-r.left+el.scrollLeft-HEADER;};
  function begin(e:React.PointerEvent,d:Omit<Drag,'x0'|'t0'>){
    e.stopPropagation();(e.currentTarget as Element).setPointerCapture?.(e.pointerId);const x0=bodyX(e);
    drag.current={...d,x0,t0:T(x0),orig:d.lineId?p.words.filter(w=>w.lineId===d.lineId).map(w=>({...w})):undefined};
    if(d.kind==='scrub')props.onSeek(Math.round(snapT(T(x0),undefined,true)*p.fps));
    if(d.kind==='loop')props.setLoop({a:snapT(T(x0),undefined,e.shiftKey),b:snapT(T(x0),undefined,e.shiftKey)});
  }
  function move(e:React.PointerEvent){
    const d=drag.current;if(!d)return;e.stopPropagation();const x=bodyX(e);const t=T(x);if(Math.abs(x-d.x0)>2)d.moved=true;
    if(d.kind==='scrub'){props.onSeek(Math.round(t*p.fps));return;}
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
  function end(e:React.PointerEvent){const d=drag.current;if(d)e.stopPropagation();drag.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    if(d&&d.kind==='loop'&&!d.moved){props.setLoopOn(false);}}
  function wheel(e:React.WheelEvent){if(!(e.ctrlKey||e.metaKey))return;e.preventDefault();const el=scroller.current!;const x=bodyX(e as unknown as React.PointerEvent);const t=T(x);
    const nz=Math.max(1,Math.min(24,zoom*(e.deltaY<0?1.25:.8)));props.setZoom(nz);requestAnimationFrame(()=>{const npps=(width-HEADER-2)*nz/dur;el.scrollLeft=Math.max(0,t*npps-(e.clientX-el.getBoundingClientRect().left-HEADER));});}

  const sel=props.selectedLine;
  return <section className="tl" aria-label="Arrangement timeline" style={{['--lane' as string]:`${laneH}px`,['--audio' as string]:`${audioH}px`}}>
    <div className="tl-bar">
      <button className="ghost tl-keyhelp" aria-label="Shortcuts" title="space play · ←/→ frame · ⇧←/→ 1 s · home/end · L loop line · H hide line · ⌘/ctrl+scroll zoom · drag a word to slip it · drag a line to move it · ⇧ drag skips snap · 1–9 looks · G all looks · O subject · W wall">?</button>
      <div className="tl-tools">
        <button className={`tog ${props.snap?'on':''}`} onClick={()=>props.setSnap(!props.snap)} title="snap to beats, word edges and frames (⇧ to bypass)">Snap</button>
        <button className={`tog ${props.loopOn?'on':''}`} onClick={()=>{if(!props.loopOn&&!loop){const l=lines.find(x=>x.id===sel);props.setLoop(l?{a:l.start,b:l.end}:{a:0,b:dur});}props.setLoopOn(!props.loopOn);}} title="loop (L). drag the top of the ruler to set it">Loop</button>
        <span className="sep"/>
        <button className="ghost" aria-label="Zoom out" onClick={()=>props.setZoom(Math.max(1,zoom/1.5))}>−</button>
        <input className="zoom" type="range" min={0} max={1} step={.01} value={Math.log(zoom)/Math.log(24)} onChange={e=>props.setZoom(Math.pow(24,Number(e.target.value)))} aria-label="Timeline zoom"/>
        <button className="ghost" aria-label="Zoom in" onClick={()=>props.setZoom(Math.min(24,zoom*1.5))}>+</button>
        <button className="ghost" onClick={()=>props.setZoom(1)} title="fit the whole song">Fit</button>
        <span className="sep"/>
        <button className="ghost" onClick={props.onAddWord}>+ Word</button>
      </div>
    </div>
    <div className="tl-scroll" ref={scroller} onWheel={wheel} onScroll={e=>setScrollX(e.currentTarget.scrollLeft)}>
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
        {lines.map(l=>{const active=time>=l.start&&time<l.end;const narrow=l.words.some((w,i)=>(X(clipEnd(l,i))-X(w.start))<Math.max(22,w.text.length*6.2));return <div key={l.id} className={`tl-row tl-lane role-${l.role} ${sel===l.id?'sel':''} ${l.hidden?'hidden':''} ${l.hook?'hook':''} ${narrow?'compact':''}`}>
          <div className="tl-head" onClick={()=>props.onSelect(l.words[0].id,true)}>
            <span className="tl-name" title={`${String(l.index+1).padStart(2,'0')} · ${ROLE_LABEL[l.role]}${l.hook?' · hook':''} · ${l.text}`}>{l.text}</span>
            <button className={`eye ${l.hidden?'off':''}`} aria-label={l.hidden?'Show line':'Hide line'} title={l.hidden?'show':'hide (H)'} onClick={e=>{e.stopPropagation();props.onToggleHidden(l.id);}}>{l.hidden?'○':'●'}</button>
            {active&&<i className="tl-live"/>}
          </div>
          <div className="tl-body" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}>
            <div className="tl-region" style={{left:X(l.start),width:Math.max(3,X(l.end)-X(l.start))}} onPointerDown={e=>{props.onSelect(sel===l.id?props.selectedWord:l.words[0].id);begin(e,{kind:'line',lineId:l.id});}} onPointerMove={move} onPointerUp={end} >
              {narrow&&<span className="tl-region-label">{l.words.map(w=>w.text).join(' ')}</span>}
              <div className="tl-region-end" onPointerDown={e=>begin(e,{kind:'end',lineId:l.id})} onPointerMove={move} onPointerUp={end} />
            </div>
            {l.words.map((w,i)=>{const a=X(w.start),b=X(clipEnd(l,i));let shown=true;try{shown=wordIsShown(p,w);}catch{/* look API */}
              return <button key={w.id} className={`word-chip ${props.selectedWord===w.id?'selected':''} ${l.heroId===w.id?'hero':''} ${shown?'':'quiet'} ${w.placement}`} style={{left:a,width:Math.max(3,b-a-1)}}
                title={`${w.text} · ${w.start.toFixed(2)}–${w.end.toFixed(2)}s`}
                onPointerDown={e=>{props.onSelect(w.id);begin(e,{kind:'onset',lineId:l.id,wordId:w.id});}} onPointerMove={move} onPointerUp={e=>{const d=drag.current;end(e);if(d&&!d.moved)props.onSeek(Math.round((w.start+.04)*p.fps));}}>
                {l.heroId===w.id&&<i className="hero-dot"/>}<span>{w.text}</span></button>;})}
          </div>
        </div>;})}
        {!lines.length&&<div className="tl-row tl-empty"><div className="tl-head"/><div className="tl-body" style={{width:bodyW}}><span>No words yet</span></div></div>}
        <div className="tl-row tl-audio">
          <div className="tl-head" title={beats?`audio · ${beats.bpm?Math.round(beats.bpm)+' bpm · ':''}${beats.beats.length} beats`:'audio'}><span className="tl-idx">♪</span></div>
          <div className="tl-body" style={{width:bodyW}} onPointerDown={e=>begin(e,{kind:'scrub'})} onPointerMove={move} onPointerUp={end}>
            <canvas ref={wave} className="tl-wave"/>
          </div>
        </div>
        <div className="tl-overlay" style={{left:HEADER,width:bodyW}}>
          {quiet.map(([a,b],i)=><div key={`q${i}`} className="tl-quiet" title="quiet" style={{left:X(a),width:X(b)-X(a),top:38+filmH}}></div>)}
          {beats?.beats.map((b,i)=>{const down=beats.downbeats?beats.downbeats.some(d=>Math.abs(d-b)<.02):i%4===0;return <i key={i} className={`tl-beat ${down?'down':''}`} style={{left:X(b)}}/>;})}
          {loop&&props.loopOn&&<><i className="tl-loopedge" style={{left:X(loop.a)}}/><i className="tl-loopedge" style={{left:X(loop.b)}}/></>}
          <div className="playhead" style={{left:X(time)}}><span/></div>
        </div>
      </div>
    </div>

  </section>;
}
