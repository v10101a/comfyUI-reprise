// Media tab: the whole song, with the part the clip uses highlighted (the audible part stronger). Drag the highlight
// to slip: the clip stays put on the timeline and a different part of the song plays under it. One undo step per drag.
import {useEffect,useRef} from 'react';
import type {Project} from '../types';
import {clipOf,setClip,slipClip,shiftDelta,shiftWords,type Clip} from '../audioClip';

const mmss=(t:number)=>`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;

export function SongMap({project:p,peaks,songDur,linkWords,edit,checkpoint}:{project:Project;peaks:Float32Array|null;songDur:number;linkWords:boolean;
  edit:(u:(p:Project)=>Project)=>void;checkpoint:()=>void}){
  const box=useRef<HTMLDivElement>(null);const cv=useRef<HTMLCanvasElement>(null);
  const drag=useRef<{x0:number;w:number;c0:Clip;words0:Map<string,[number,number]>}|null>(null);
  const c=clipOf(p,songDur);const sh=c.offset-c.in;
  // Audible part of the song: inside the clip and under the video.
  const a0=Math.max(c.in,-sh),a1=Math.min(c.out,p.duration-sh);
  useEffect(()=>{const el=cv.current,b=box.current;if(!el||!b)return;const w=b.clientWidth,h=36;const dpr=Math.min(2,window.devicePixelRatio||1);
    el.width=w*dpr;el.height=h*dpr;el.style.width=`${w}px`;el.style.height=`${h}px`;const g=el.getContext('2d')!;g.scale(dpr,dpr);g.clearRect(0,0,w,h);
    if(!peaks?.length)return;const bins=peaks.length/2;
    for(let x=0;x<w;x++){const i0=Math.floor(x/w*bins),i1=Math.max(i0+1,Math.floor((x+1)/w*bins));let hi=0;for(let i=i0;i<i1;i++)hi=Math.max(hi,peaks[i*2+1],-peaks[i*2]);
      const s=(x+.5)/w*songDur;g.fillStyle=s>=a0&&s<a1?'#2e2e2e':'#2e2e2e4d';g.fillRect(x,h/2-hi*h*.46,1,Math.max(1,hi*h*.92));}
  },[peaks,songDur,a0,a1]);
  if(!songDur)return null;
  const pct=(t:number)=>`${Math.max(0,Math.min(100,t/songDur*100))}%`;
  return <div className="songmap" ref={box} title={`Plays ${mmss(Math.max(0,a0))}–${mmss(Math.max(0,a1))} of ${mmss(songDur)} · drag to pick the part of the song`}>
    <canvas ref={cv} aria-hidden="true"/>
    <div className="songmap-clip" style={{left:pct(c.in),width:`calc(${pct(c.out)} - ${pct(c.in)})`}}/>
    <div className="songmap-win" role="slider" aria-label="Song section" aria-valuemin={0} aria-valuemax={+songDur.toFixed(2)} aria-valuenow={+Math.max(0,a0).toFixed(2)} tabIndex={0}
      style={{left:pct(Math.max(0,a0)),width:`calc(${pct(Math.max(a0,a1))} - ${pct(Math.max(0,a0))})`}}
      onKeyDown={e=>{if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;e.preventDefault();const ds=(e.key==='ArrowRight'?1:-1)*(e.shiftKey?1:.1);const n=slipClip(c,ds,songDur);
        const w0=new Map(p.words.map(w=>[w.id,[w.start,w.end] as [number,number]]));edit(q=>{const r=setClip(q,n,songDur);return linkWords?shiftWords(r,w0,shiftDelta(c,n)):r;});}}
      onPointerDown={e=>{e.preventDefault();(e.currentTarget as Element).setPointerCapture(e.pointerId);checkpoint();
        drag.current={x0:e.clientX,w:box.current?.clientWidth||1,c0:{...c},words0:new Map(p.words.map(w=>[w.id,[w.start,w.end]]))};}}
      onPointerMove={e=>{const d=drag.current;if(!d)return;const n=slipClip(d.c0,(e.clientX-d.x0)/d.w*songDur,songDur);const dt=shiftDelta(d.c0,n);
        edit(q=>{const r=setClip(q,n,songDur);return linkWords?shiftWords(r,d.words0,dt):r;});}}
      onPointerUp={e=>{drag.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);}} onPointerCancel={()=>{drag.current=null;}}/>
  </div>;
}
