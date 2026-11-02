// Wall mode: draw a wall by clicking four corners or dragging a rectangle, then adjust corners or drag the whole quad.
// Corners are OUTPUT-normalized (the studio maps them through the reframe crop when it places the wall).
import {useRef} from 'react';
import type {Point,Surface,Placement} from '../types';
import {squareToQuad,applyH,quadIsConvex} from '../geometry';
import {Icon} from './icons';
import {wallStatus,WALL_STATUS_TITLE} from './walls';

const inside=(q:Point[],[x,y]:Point)=>{let s=0;for(let i=0;i<q.length;i++){const [ax,ay]=q[i],[bx,by]=q[(i+1)%q.length];const c=Math.sign((bx-ax)*(y-ay)-(by-ay)*(x-ax));if(c){if(s&&c!==s)return false;s=c;}}return true;};
const NAMES=['top-left','top-right','bottom-right','bottom-left'];

export function WallTool({W,H,corners,setCorners}:{W:number;H:number;corners:Point[];setCorners:(f:(c:Point[])=>Point[])=>void}){
  const svg=useRef<SVGSVGElement>(null);
  const drag=useRef<{kind:'corner'|'body'|'rect';i?:number;p0:Point;c0:Point[];moved:boolean}|null>(null);
  const pts=corners.map(([x,y])=>[x*W,y*H] as Point);
  const grid:[Point,Point][]=[];
  if(pts.length===4&&quadIsConvex(pts)){const h=squareToQuad(pts);for(let i=1;i<8;i++)grid.push([applyH(h,i/8,0),applyH(h,i/8,1)]);for(let j=1;j<4;j++)grid.push([applyH(h,0,j/4),applyH(h,1,j/4)]);}
  const r=Math.max(W,H)*.011;
  const pt=(e:React.PointerEvent):Point|null=>{const el=svg.current;if(!el)return null;const b=el.getBoundingClientRect();return [Math.min(1.2,Math.max(-.2,(e.clientX-b.left)/b.width)),Math.min(1.2,Math.max(-.2,(e.clientY-b.top)/b.height))];};
  const down=(e:React.PointerEvent)=>{const q=pt(e);if(!q)return;const h=(e.target as Element).closest('.handle');
    svg.current?.setPointerCapture(e.pointerId);
    if(h){drag.current={kind:'corner',i:Number(h.getAttribute('data-i')),p0:q,c0:corners,moved:false};return;}
    if(corners.length===4){if(inside(pts,[q[0]*W,q[1]*H]))drag.current={kind:'body',p0:q,c0:corners,moved:false};return;}
    if(corners.length===0){drag.current={kind:'rect',p0:q,c0:[],moved:false};return;}
    setCorners(c=>c.length<4?[...c,q]:c);};
  const move=(e:React.PointerEvent)=>{const d=drag.current;if(!d)return;const q=pt(e);if(!q)return;
    const dx=q[0]-d.p0[0],dy=q[1]-d.p0[1];if(!d.moved&&Math.hypot(dx*W,dy*H)<Math.max(W,H)*.006)return;d.moved=true;
    if(d.kind==='corner')setCorners(c=>c.map((v,k)=>k===d.i?q:v));
    else if(d.kind==='body')setCorners(()=>d.c0.map(([x,y])=>[x+dx,y+dy] as Point));
    else{const x0=Math.min(d.p0[0],q[0]),x1=Math.max(d.p0[0],q[0]),y0=Math.min(d.p0[1],q[1]),y1=Math.max(d.p0[1],q[1]);setCorners(()=>[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]);}};
  const up=(e:React.PointerEvent)=>{const d=drag.current;drag.current=null;if(svg.current?.hasPointerCapture(e.pointerId))svg.current.releasePointerCapture(e.pointerId);
    if(d?.kind==='rect'&&!d.moved)setCorners(c=>c.length<4?[...c,d.p0]:c);};
  const body=pts.length===4;
  return <svg ref={svg} className={`surface-overlay ${body?'placed':''}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
    {body&&<polygon points={pts.map(p=>p.join(',')).join(' ')} className={quadIsConvex(pts)?'quad':'quad bad'} style={{strokeWidth:r*.22}}/>}
    {pts.length>1&&pts.length<4&&<polyline points={pts.map(p=>p.join(',')).join(' ')} className="quad open" style={{strokeWidth:r*.22}}/>}
    {grid.map(([a,b],i)=><line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="grid" style={{strokeWidth:r*.1}}/>)}
    {pts.map((p,i)=><g key={i} className="handle" data-i={i}><circle cx={p[0]} cy={p[1]} r={r} style={{strokeWidth:r*.22}}/><text x={p[0]+r*1.4} y={p[1]-r*1.2} style={{fontSize:r*1.5}}>{['TL','TR','BR','BL'][i]}</text></g>)}
  </svg>;
}

/** Wall-mode bar: progress, redraw, delete (an existing wall), cancel, place. */
export function WallBar({corners,editing,busy,onRedraw,onDelete,onCancel,onPlace}:{corners:Point[];editing:boolean;busy:boolean;
  onRedraw:()=>void;onDelete?:()=>void;onCancel:()=>void;onPlace:()=>void}){
  const n=corners.length;const ok=n===4&&quadIsConvex(corners);
  return <div className="surface-bar">
    <span className="sb-step" title="Click four corners, or drag a rectangle. Then drag corners or the whole wall.">{n<4?<><b>{NAMES[n]}</b> {n}/4</>:ok?'4/4':'corners cross'}</span>
    {n>0&&<button onClick={onRedraw} title="Clear and draw again">Redraw</button>}
    {editing&&onDelete&&<button className="danger" onClick={onDelete} title="Delete wall (⌫)">Delete</button>}
    <button onClick={onCancel} title="esc">Cancel</button>
    <button className="primary" disabled={busy||!ok} onClick={onPlace} title="Place and track (↵)">Place</button>
  </div>;
}

/** Keyframe controls for one wall: at = a key on this frame; prev/next = jump targets. */
export type WallKeyProps={at:boolean;keyed:boolean;onKey:()=>void;onPrev?:()=>void;onNext?:()=>void};
/** Track status + re-track, keyframes, redraw, delete for one wall (stage bar and line panel). */
export function WallButtons({surface,running,busy,onTrack,onRedraw,onDelete,fallback,keys}:{surface:Surface;running:boolean;busy:boolean;
  onTrack:()=>void;onRedraw:()=>void;onDelete:()=>void;fallback:Placement;keys?:WallKeyProps}){
  const st=wallStatus(surface,running);
  return <>
    {keys&&<>
      {keys.keyed&&<button className="icon-sm" disabled={!keys.onPrev} onClick={keys.onPrev} aria-label="Previous wall key" title="Previous key"><Icon name="keyPrev" size={14}/></button>}
      <button className={`icon-sm wall-key ${keys.at?'on':''}`} onClick={keys.onKey} aria-pressed={keys.at}
        aria-label={!keys.keyed?'Keyframe wall':keys.at?'Remove key':'Add key'}
        title={!keys.keyed?'Keyframe the wall: smooths its track; then drag it on any frame to set a key':keys.at?'Remove this key':'Add a key here (or just drag the wall)'}><Icon name="key" size={14}/></button>
      {keys.keyed&&<button className="icon-sm" disabled={!keys.onNext} onClick={keys.onNext} aria-label="Next wall key" title="Next key"><Icon name="keyNext" size={14}/></button>}
    </>}
    <button className={`icon-sm wall-track st-${st}`} disabled={busy||st==='tracking'} onClick={onTrack} aria-label={`Wall ${st}: track`} title={keys?.keyed?'Keyframed · re-track replaces the keys':WALL_STATUS_TITLE[st]}><Icon name="track" size={14}/><i className="wt-dot"/></button>
    <button className="icon-sm" onClick={onRedraw} aria-label="Edit wall" title="Edit corners or redraw (W)"><Icon name="redraw" size={14}/></button>
    <button className="icon-sm danger" onClick={onDelete} aria-label="Delete wall" title={`Delete wall · its lines move ${fallback==='behind'?'Behind':'on top (Caption)'} · undo ⌘Z`}><Icon name="trash" size={14}/></button>
  </>;
}
