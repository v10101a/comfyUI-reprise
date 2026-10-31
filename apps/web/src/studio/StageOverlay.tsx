// Stage guides drawn over the composition: subject occupancy heatmap, each visible line's solved region (drag to move),
// the preferred spot, the HUD anchor point, existing wall quads. Everything is in project pixels (SVG viewBox).
import {useEffect,useMemo,useRef} from 'react';
import type {Project,Point,Word} from '../types';
import {StageRenderer,lines,anchorAt,surfaceCornersAt,withLead} from '../renderer';
import {cropAt,toOut,quadIsConvex} from '../geometry';
import {wordIsShown} from '../looks';

export type Guides = {occupancy:boolean;regions:boolean;anchor:boolean};
export type LineBox = {lineId:string;key:string;placement:Word['placement'];x:number;y:number;w:number;h:number;
  pad?:{x:number;y:number;w:number;h:number};role?:string;auto:boolean;coverage?:number;front?:boolean;hint?:{x:number;y:number};anchorPt?:Point;quiet:boolean;text:string};

let scratch:CanvasRenderingContext2D|undefined;
const ctx2d=()=>scratch||(scratch=document.createElement('canvas').getContext('2d')!);

/** Mirror of the renderer's line origin math (overlay/behind/anchor). Approximate under look layouts that re-lay lines. */
export function lineBoxes(r:StageRenderer|undefined,p:Project,frame:number):LineBox[]{
  if(!r)return [];
  try{
    r.project=p;const ctx=ctx2d();const t=frame/p.fps;const W=p.width,H=p.height;const plan=r.layout(ctx);const out:LineBox[]=[];
    // R's renderer exposes the drawable units (a line splits into hero + satellites under a look); older builds only lines().
    type U=ReturnType<typeof lines>[number]&{lineId?:string;role?:string;bleed?:boolean};
    const units=(typeof (r as unknown as {units?:unknown}).units==='function'?(r as unknown as {units:(c:CanvasRenderingContext2D)=>U[]}).units(ctx):lines(ctx,withLead(p))) as U[];
    for(const l of units){
      if(t<l.start||t>=l.end||l.placement==='surface'||l.placement==='inworld')continue;
      const first=l.words[0];let fit=l.bleed?1:Math.min(1,W*.88/Math.max(1,l.total));let origin=first.position||{x:.5,y:.72};
      const auto=plan.get(l.key);const align=l.metrics[0]?.style.align||'center';let anchorPt:Point|undefined;
      if(auto){fit*=auto.scale;const half=l.total*fit/2/W;origin={x:auto.cx+(align==='left'?-half:align==='right'?half:0),y:auto.cy};}
      if(l.placement==='anchor'){
        const a=first.anchor||{trackId:'person0',dx:0,dy:-.1};const pt=anchorAt(r.tracks,a.trackId,Math.round(t*(r.tracks?.fps||p.fps)));if(!pt)continue;
        const [cx,cy]=toOut(cropAt(r.crop,frame),pt.cx,pt.cy);anchorPt=[cx*W,cy*H];origin={x:cx+a.dx,y:cy+a.dy};
        const hw=l.total*fit/2/W+.012,top=(l.height/2+l.size*(first.preset==='hud'?.85:.2))*fit/H,bot=(l.height/2+l.size*.2)*fit/H;
        origin={x:Math.min(1-hw-.02,Math.max(hw+.02,origin.x)),y:Math.min(1-bot-.03,Math.max(top+.03,origin.y))};
      }
      const w=l.total*fit,h=l.height*fit;const x=origin.x*W-(align==='center'?w/2:align==='right'?w:0),y=origin.y*H-h/2;
      const pw=w+.02*W,ph=h*1.12;
      let quiet=false;try{quiet=!l.words.some(w=>wordIsShown(p,w));}catch{/* look API missing */}
      out.push({lineId:l.lineId||first.lineId,role:l.role,key:l.key,placement:l.placement,x,y,w,h,pad:auto?{x:x+w/2-pw/2,y:y+h/2-ph/2,w:pw,h:ph}:undefined,auto:!!auto,coverage:auto?.coverage,front:auto?.front,
        hint:auto&&first.position?{x:first.position.x*W,y:first.position.y*H}:undefined,anchorPt,quiet,text:l.words.map(w=>w.text).join(' ')});
    }
    return out;
  }catch{return [];}
}

export function StageGuides({renderer,project:p,frame,guides,selectedLine,onSelectLine,onDragLine,box}:{
  renderer?:StageRenderer;project:Project;frame:number;guides:Guides;selectedLine?:string;
  onSelectLine:(lineId:string)=>void;onDragLine:(lineId:string,placement:Word['placement'],dx:number,dy:number,phase:'start'|'move'|'end')=>void;
  box:{width:number;height:number};
}){
  const W=p.width,H=p.height;const heat=useRef<HTMLCanvasElement>(null);
  const boxes=useMemo(()=>lineBoxes(renderer,p,frame),[renderer,p,frame]);
  // Occupancy heatmap: one pixel per grid cell, scaled up with smoothing → a soft silhouette.
  useEffect(()=>{const c=heat.current;if(!c)return;const g=c.getContext('2d')!;
    let grid;try{grid=guides.occupancy?renderer?.occ().at(frame):undefined;}catch{grid=undefined;}
    if(!grid){g.clearRect(0,0,c.width,c.height);return;}
    if(c.width!==grid.cols)c.width=grid.cols;if(c.height!==grid.rows)c.height=grid.rows;
    const img=g.createImageData(grid.cols,grid.rows);
    for(let i=0;i<grid.data.length;i++){const v=grid.data[i];img.data[i*4]=255;img.data[i*4+1]=92;img.data[i*4+2]=60;img.data[i*4+3]=Math.round(Math.min(1,v*1.2)*150);}
    g.putImageData(img,0,0);
  },[renderer,frame,guides.occupancy,p]);
  const surfaces=useMemo(()=>{if(!renderer||!guides.regions)return [];const out:{id:string;label:string;quad:Point[];sel:boolean}[]=[];
    const sel=p.words.find(w=>w.lineId===selectedLine)?.surfaceId;
    for(const s of p.surfaces||[]){let tr;try{tr=s.track?renderer.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;}catch{tr=undefined;}
      const c=surfaceCornersAt(s,tr,frame);if(!c)continue;const q=c.map(([x,y])=>{const [ox,oy]=toOut(cropAt(renderer.crop,frame),x,y);return [ox*W,oy*H] as Point;});
      if(quadIsConvex(q))out.push({id:s.id,label:s.label||s.id,quad:q,sel:s.id===sel});}
    return out;},[renderer,p,frame,guides.regions,selectedLine]);// eslint-disable-line react-hooks/exhaustive-deps

  const drag=useRef<{lineId:string;placement:Word['placement'];x0:number;y0:number}|null>(null);
  const svg=useRef<SVGSVGElement>(null);
  const toPx=(e:React.PointerEvent)=>{const r=svg.current!.getBoundingClientRect();return [(e.clientX-r.left)/r.width*W,(e.clientY-r.top)/r.height*H];};
  const s=W/Math.max(1,box.width);// one screen pixel in project px
  return <>
    {guides.occupancy&&<canvas ref={heat} className="guide-heat" aria-hidden="true"/>}
    {guides.occupancy&&<span className="guide-caption">Subject · {p.analysis.occupancy?<><b>BiRefNet matte</b> via ComfyUI → occupancy grid</>:renderer?.occupancy?'fixture occupancy grid':renderer?.tracks?'fallback: track boxes':'no matte yet'}</span>}
    <svg ref={svg} className="stage-guides" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{['--px' as string]:s}}>
      {surfaces.map(q=><g key={q.id} className={`g-wall ${q.sel?'sel':''}`}><polygon points={q.quad.map(p=>p.join(',')).join(' ')} style={{strokeWidth:s*1.2}}/><text x={q.quad[0][0]+s*6} y={q.quad[0][1]+s*16} style={{fontSize:s*10}}>▱ {q.label.toUpperCase()}</text></g>)}
      {(guides.regions||guides.anchor)&&boxes.map(b=>{const sel=b.lineId===selectedLine;return <g key={b.key} className={`g-line ${sel?'sel':''} ${b.quiet?'quiet':''} p-${b.placement} ${guides.regions?'':'nobox'}`}>
        {b.pad&&<rect className="g-pad" x={b.pad.x} y={b.pad.y} width={b.pad.w} height={b.pad.h} style={{strokeWidth:s}}/>}
        {b.hint&&sel&&<><line className="g-leader" x1={b.hint.x} y1={b.hint.y} x2={b.x+b.w/2} y2={b.y+b.h/2} style={{strokeWidth:s}}/><circle className="g-hint" cx={b.hint.x} cy={b.hint.y} r={s*4} style={{strokeWidth:s*1.2}}/></>}
        <rect className="g-box" x={b.x} y={b.y} width={b.w} height={b.h} style={{strokeWidth:s*(sel?1.5:1)}}
          onPointerDown={e=>{e.stopPropagation();onSelectLine(b.lineId);const [x,y]=toPx(e);drag.current={lineId:b.lineId,placement:b.placement,x0:x,y0:y};(e.currentTarget as Element).setPointerCapture(e.pointerId);onDragLine(b.lineId,b.placement,0,0,'start');}}
          onPointerMove={e=>{const d=drag.current;if(!d)return;const [x,y]=toPx(e);onDragLine(d.lineId,d.placement,(x-d.x0)/W,(y-d.y0)/H,'move');}}
          onPointerUp={e=>{const d=drag.current;drag.current=null;(e.currentTarget as Element).releasePointerCapture(e.pointerId);if(d){const [x,y]=toPx(e);onDragLine(d.lineId,d.placement,(x-d.x0)/W,(y-d.y0)/H,'end');}}}/>
        {sel&&[[b.x,b.y],[b.x+b.w,b.y],[b.x,b.y+b.h],[b.x+b.w,b.y+b.h]].map(([x,y],i)=><rect key={i} className="g-knob" x={x-s*3} y={y-s*3} width={s*6} height={s*6}/>)}
        <text className="g-label" x={b.x} y={b.placement==='anchor'?b.y+b.h+s*13:b.y-s*5} style={{fontSize:s*9.5}}>{b.role&&!['line','hud'].includes(b.role)?`${b.role==='sat'?'SATELLITE':b.role.toUpperCase()} · `:''}{b.placement==='anchor'?'HUD':b.placement.toUpperCase()}{b.auto?` · AUTO${b.coverage!=null?` · ${Math.round(b.coverage*100)}% covered`:''}`:' · FIXED'}{b.front?' · PROMOTED TO FRONT':''}{b.quiet?' · QUIET':''}</text>
        {b.anchorPt&&guides.anchor&&<g className="g-anchor"><line x1={b.anchorPt[0]-s*10} y1={b.anchorPt[1]} x2={b.anchorPt[0]+s*10} y2={b.anchorPt[1]} style={{strokeWidth:s}}/><line x1={b.anchorPt[0]} y1={b.anchorPt[1]-s*10} x2={b.anchorPt[0]} y2={b.anchorPt[1]+s*10} style={{strokeWidth:s}}/><circle cx={b.anchorPt[0]} cy={b.anchorPt[1]} r={s*6} style={{strokeWidth:s}}/><text x={b.anchorPt[0]+s*9} y={b.anchorPt[1]+s*14} style={{fontSize:s*9}}>HEAD · {(p.words.find(w=>w.lineId===b.lineId)?.anchor?.trackId||'person0').toUpperCase()}</text></g>}
      </g>;})}
    </svg>
  </>;
}
