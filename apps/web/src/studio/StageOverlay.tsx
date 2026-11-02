// Stage guides drawn over the composition: subject occupancy heatmap, each visible line's box (drag to move, corner
// handles to resize), the preferred spot of an auto-placed line, the HUD anchor point, existing wall quads.
// Everything is in project pixels (SVG viewBox). Wall lines get their box in the wall's plane (perspective quad).
import {useEffect,useMemo,useRef} from 'react';
import type {Project,Point,Word} from '../types';
import {StageRenderer,lines,surfaceCornersAt,withLead,type HeadState} from '../renderer';
import {cropAt,toOut,quadIsConvex,squareToQuad,applyH,quadSize,type Homography} from '../geometry';
import {wordIsShown,lookOf} from '../looks';
import {hudPointer} from '../hud';

/** walls: always show wall quads (otherwise only while a wall or a wall line is selected). */
export type Guides = {occupancy:boolean;regions:boolean;anchor:boolean;walls?:boolean};
/** Wall text in its plane: h maps the unit square to the (look-scaled) wall quad in project px; uv is the text rect
 *  [u0,v0,u1,v1]; aw/ah are the plane's pixel proportions (so scaling stays uniform in the plane). */
export type PlaneBox = {h:Homography;uv:[number,number,number,number];aw:number;ah:number};
export type LineBox = {lineId:string;key:string;placement:Word['placement'];x:number;y:number;w:number;h:number;
  role?:string;auto:boolean;coverage?:number;front?:boolean;hint?:{x:number;y:number};anchorPt?:Point;quiet:boolean;text:string;
  /** Wall lines: the text's quad on the wall (TL,TR,BR,BL, project px) and its plane mapping. */
  quad?:Point[];plane?:PlaneBox;
  /** HUD lines: tracked head, held/interpolated (no person at this frame), or none (no person track: a screen label). */
  head?:HeadState};
/** Resize gesture, reported to the studio. k = uniform scale since the drag started; fixed = the point that stays put
 *  (project px; the opposite corner, or the centre with ⌥). Wall lines always scale about the text's centre in the plane. */
export type Resize = {lineId:string;placement:Word['placement'];phase:'start'|'move'|'end';k:number;fixed:Point;box:LineBox};

let scratch:CanvasRenderingContext2D|undefined;
const ctx2d=()=>scratch||(scratch=document.createElement('canvas').getContext('2d')!);

function invertH(m:Homography):Homography{
  const [a,b,c,d,e,f,g,h,i]=m;const A=e*i-f*h,B=-(d*i-f*g),C=d*h-e*g;const det=a*A+b*B+c*C||1e-12;
  return [A/det,-(b*i-c*h)/det,(b*f-c*e)/det,B/det,(a*i-c*g)/det,-(a*f-c*d)/det,C/det,-(a*h-b*g)/det,(a*e-b*d)/det];
}
/** Mirror of the renderer's softenPerspective (authored neon walls). */
function soften(q:Point[],k:number):Point[]{
  const [tl,tr,br,bl]=q;const len=(a:Point,b:Point)=>Math.hypot(b[0]-a[0],b[1]-a[1]);const hl=len(tl,bl),hr=len(tr,br),m=(hl+hr)/2;
  const sc=(a:Point,b:Point,h:number):[Point,Point]=>{const c:Point=[(a[0]+b[0])/2,(a[1]+b[1])/2];const s=(h+(m-h)*k)/Math.max(1e-6,h);return [[c[0]+(a[0]-c[0])*s,c[1]+(a[1]-c[1])*s],[c[0]+(b[0]-c[0])*s,c[1]+(b[1]-c[1])*s]];};
  const [ntl,nbl]=sc(tl,bl,hl),[ntr,nbr]=sc(tr,br,hr);return [ntl,ntr,nbr,nbl];
}
const subQuad=(q:Point[],r:[number,number,number,number]):Point[]=>{const H=squareToQuad(q);return [applyH(H,r[0],r[1]),applyH(H,r[2],r[1]),applyH(H,r[2],r[3]),applyH(H,r[0],r[3])];};

/** Mirror of the renderer's line origin math (overlay/behind/anchor) and wall plane fit. Approximate under look layouts
 *  that re-lay lines, and for walls under a reframe crop (the renderer's visible sub-plane is not mirrored). */
export function lineBoxes(r:StageRenderer|undefined,p:Project,frame:number):LineBox[]{
  if(!r)return [];
  try{
    r.project=p;const ctx=ctx2d();const t=frame/p.fps;const W=p.width,H=p.height;const plan=r.layout(ctx);const out:LineBox[]=[];const look=lookOf(p);
    // R's renderer exposes the drawable units (a line splits into hero + satellites under a look); older builds only lines().
    type U=ReturnType<typeof lines>[number]&{lineId?:string;role?:string;bleed?:boolean};
    const units=(typeof (r as unknown as {units?:unknown}).units==='function'?(r as unknown as {units:(c:CanvasRenderingContext2D)=>U[]}).units(ctx):lines(ctx,withLead(p))) as U[];
    for(const l of units){
      if(t<l.start||t>=l.end||l.placement==='inworld')continue;
      const first=l.words[0];const lineId=l.lineId||first.lineId;
      let quiet=false;try{quiet=!l.words.some(w=>wordIsShown(p,w));}catch{/* look API missing */}
      const text=l.words.map(w=>w.text).join(' ');
      if(l.placement==='surface'){
        const s=p.surfaces?.find(x=>x.id===first.surfaceId);if(!s)continue;
        let tr;try{tr=s.track?r.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;}catch{tr=undefined;}
        const corners=surfaceCornersAt(s,tr,frame);if(!corners)continue;const c=cropAt(r.crop,frame);
        let q=corners.map(([x,y])=>{const [ox,oy]=toOut(c,x,y);return [ox*W,oy*H] as Point;});
        if(s.material==='neon')q=soften(q,.5);if(!quadIsConvex(q))continue;
        const sw=c?W/c.w:W,sh=c?H/c.h:H;let [kw,kh]=quadSize(s.corners.map(([x,y])=>[x*sw,y*sh] as Point));
        const marquee=look?.motion==='marquee';const ws=marquee?1:look?.wallScale??1,ex=ws>1?Math.min(ws,1.12):1;
        if(ws!==1){q=subQuad(q,[-(ex-1)/2,-(ws-1)/2,1+(ex-1)/2,1+(ws-1)/2]);kw*=ex;kh*=ws;}
        const Wc=Math.max(64,Math.min(1600,Math.round(kw*1.6))),Hc=Math.max(16,Math.round(Wc*kh/Math.max(1,kw)));
        let fit=marquee?Hc*.62/Math.max(1,l.height*1.1):ws!==1?Math.min(Wc/ex*Math.min(.97,.88*ws)/Math.max(1,l.total),Hc*.72/Math.max(1,l.height*1.1))
          :Math.min(Wc*.88/Math.max(1,l.total),Hc*.72/Math.max(1,l.height*1.1));
        fit*=p.lineMeta?.[lineId]?.scale??1;
        const hu=l.total*fit/2/Wc,hv=l.height*fit/2/Hc;const lm=marquee?undefined:p.lineMeta?.[lineId];const cu=.5+(lm?.u??0),cv=.5+(lm?.v??0);
        const uv:[number,number,number,number]=[cu-hu,cv-hv,cu+hu,cv+hv];
        const hm=squareToQuad(q);const quad=[applyH(hm,uv[0],uv[1]),applyH(hm,uv[2],uv[1]),applyH(hm,uv[2],uv[3]),applyH(hm,uv[0],uv[3])];
        const xs=quad.map(v=>v[0]),ys=quad.map(v=>v[1]);const x=Math.min(...xs),y=Math.min(...ys);
        out.push({lineId,role:l.role,key:l.key,placement:'surface',x,y,w:Math.max(...xs)-x,h:Math.max(...ys)-y,auto:false,quiet,text,quad,plane:{h:hm,uv,aw:Wc,ah:Hc}});
        continue;
      }
      let fit=l.bleed?1:Math.min(1,W*.88/Math.max(1,l.total));let origin=first.position||{x:.5,y:.72};
      const auto=plan.get(l.key);const align=l.metrics[0]?.style.align||'center';let anchorPt:Point|undefined;let head:HeadState|undefined;
      if(auto){fit*=auto.scale;const half=l.total*fit/2/W;origin={x:auto.cx+(align==='left'?-half:align==='right'?half:0),y:auto.cy};}
      if(l.placement==='anchor'){
        const a=first.anchor||{trackId:'person0',dx:0,dy:-.1};const hd=r.head(t,a.trackId);head=hd.state;const pt=hd.point;
        const target=r.head(t,a.trackId,p,hudPointer(p,lineId).point).point;
        const [cx,cy]=[pt.cx,pt.cy];anchorPt=hd.state==='none'?undefined:[target.cx*W,target.cy*H];origin={x:cx+a.dx,y:cy+a.dy};
        origin=r.anchorOrigin(l,fit,origin,frame,a.trackId);
      }
      const w=l.total*fit,h=l.height*fit;const x=origin.x*W-(align==='center'?w/2:align==='right'?w:0),y=origin.y*H-h/2;
      out.push({lineId,role:l.role,key:l.key,placement:l.placement,x,y,w,h,auto:!!auto,coverage:auto?.coverage,front:auto?.front,
        hint:auto&&first.position?{x:first.position.x*W,y:first.position.y*H}:undefined,anchorPt,quiet,text,head});
    }
    return out;
  }catch{return [];}
}

/** Corners of a box (TL,TR,BR,BL) in project px. */
const cornersOf=(b:LineBox):Point[]=>b.quad||[[b.x,b.y],[b.x+b.w,b.y],[b.x+b.w,b.y+b.h],[b.x,b.y+b.h]];
const CURSORS=['nwse-resize','nesw-resize','nwse-resize','nesw-resize'];

export function StageGuides({renderer,project:p,frame,guides,selectedLine,onSelectLine,onDragLine,onResizeLine,onDragAnchor,box,selectedWall,onSelectWall,onWallEdit}:{
  renderer?:StageRenderer;project:Project;frame:number;guides:Guides;selectedLine?:string;
  onSelectLine:(lineId:string)=>void;onDragLine:(lineId:string,placement:Word['placement'],dx:number,dy:number,phase:'start'|'move'|'end')=>void;
  onResizeLine?:(r:Resize)=>void;
  onDragAnchor?:(lineId:string,point:Point,phase:'start'|'move'|'end'|'cancel')=>void;
  /** Walls: the selected wall (handles + body drag), click to select, drag to re-place (quad in project px at this frame). */
  selectedWall?:string;onSelectWall?:(id:string)=>void;onWallEdit?:(id:string,quad:Point[],phase:'start'|'move'|'end')=>void;
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
  // Wall quads only while a wall (or a wall line) is selected, or with the Walls guide on.
  const lineWall=p.words.find(w=>w.lineId===selectedLine&&w.placement==='surface')?.surfaceId||undefined;const activeWall=selectedWall||lineWall;
  const surfaces=useMemo(()=>{if(!renderer||!(guides.walls||activeWall))return [];const out:{id:string;label:string;quad:Point[];sel:boolean}[]=[];
    const sel=activeWall;
    for(const s of p.surfaces||[]){let tr;try{tr=s.track?renderer.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;}catch{tr=undefined;}
      const c=surfaceCornersAt(s,tr,frame);if(!c)continue;const q=c.map(([x,y])=>{const [ox,oy]=toOut(cropAt(renderer.crop,frame),x,y);return [ox*W,oy*H] as Point;});
      if(quadIsConvex(q))out.push({id:s.id,label:s.label||s.id,quad:q,sel:s.id===sel});}
    return out.sort((a,b)=>+a.sel-+b.sel);},[renderer,p,frame,guides.walls,activeWall]);// eslint-disable-line react-hooks/exhaustive-deps
  // Wall drag: a corner (i ≥ 0) or the whole quad (i = −1), from the quad drawn at this frame.
  const wd=useRef<{id:string;i:number;q0:Point[];p0:Point;moved:boolean}|null>(null);
  const wallDown=(e:React.PointerEvent,id:string,q:Point[],i:number)=>{e.stopPropagation();e.preventDefault();onSelectWall?.(id);if(!onWallEdit||id!==activeWall&&i<0)return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);wd.current={id,i,q0:q,p0:toPx(e) as Point,moved:false};};
  const wallMove=(e:React.PointerEvent)=>{const d=wd.current;if(!d)return;const P=toPx(e);const dx=P[0]-d.p0[0],dy=P[1]-d.p0[1];
    if(!d.moved){if(Math.hypot(dx,dy)<s*3)return;d.moved=true;onWallEdit?.(d.id,d.q0,'start');}
    const q=d.i<0?d.q0.map(([x,y])=>[x+dx,y+dy] as Point):d.q0.map((v,k)=>k===d.i?[P[0],P[1]] as Point:v);if(quadIsConvex(q))onWallEdit?.(d.id,q,'move');};
  const wallUp=(e:React.PointerEvent)=>{const d=wd.current;wd.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);if(d?.moved)onWallEdit?.(d.id,d.q0,'end');};

  const drag=useRef<{lineId:string;placement:Word['placement'];x0:number;y0:number}|null>(null);
  const anchorDrag=useRef<{id:string;start:Point;target:Point;moved:boolean}|null>(null);
  // Resize: k = base + (projection − ref) × gain; ⇧ re-bases with a quarter gain so fine control never jumps.
  const rs=useRef<{b:LineBox;fixed:Point;c0:Point;plane?:PlaneBox;inv?:Homography;base:number;ref:number;fine:boolean;k:number}|null>(null);
  const svg=useRef<SVGSVGElement>(null);
  const toPx=(e:React.PointerEvent)=>{const r=svg.current!.getBoundingClientRect();return [(e.clientX-r.left)/r.width*W,(e.clientY-r.top)/r.height*H];};
  const s=W/Math.max(1,box.width);// one screen pixel in project px
  const anchorDown=(e:React.PointerEvent,b:LineBox)=>{if(e.button!==0||!b.anchorPt||!onDragAnchor)return;
    e.preventDefault();e.stopPropagation();onSelectLine(b.lineId);(e.currentTarget as Element).setPointerCapture(e.pointerId);
    anchorDrag.current={id:b.lineId,start:toPx(e) as Point,target:b.anchorPt,moved:false};onDragAnchor(b.lineId,[b.anchorPt[0]/W,b.anchorPt[1]/H],'start');};
  const anchorMove=(e:React.PointerEvent)=>{const d=anchorDrag.current;if(!d)return;e.preventDefault();e.stopPropagation();const [x,y]=toPx(e);
    if(!d.moved&&Math.hypot(x-d.start[0],y-d.start[1])<s*2)return;d.moved=true;
    onDragAnchor?.(d.id,[(d.target[0]+x-d.start[0])/W,(d.target[1]+y-d.start[1])/H],'move');};
  const anchorUp=(e:React.PointerEvent)=>{const d=anchorDrag.current;if(!d)return;e.preventDefault();e.stopPropagation();anchorDrag.current=null;
    if((e.currentTarget as Element).hasPointerCapture(e.pointerId))(e.currentTarget as Element).releasePointerCapture(e.pointerId);
    onDragAnchor?.(d.id,[d.target[0]/W,d.target[1]/H],e.type==='pointercancel'?'cancel':'end');};
  const project=(st:NonNullable<typeof rs.current>,P:Point)=>{
    if(st.plane&&st.inv){const [u,v]=applyH(st.inv,P[0],P[1]);const {aw,ah,uv}=st.plane;const f=[(uv[0]+uv[2])/2*aw,(uv[1]+uv[3])/2*ah],c=[st.c0[0]*aw,st.c0[1]*ah],q=[u*aw,v*ah];
      const dx=c[0]-f[0],dy=c[1]-f[1];return ((q[0]-f[0])*dx+(q[1]-f[1])*dy)/Math.max(1e-6,dx*dx+dy*dy);}
    const dx=st.c0[0]-st.fixed[0],dy=st.c0[1]-st.fixed[1];return ((P[0]-st.fixed[0])*dx+(P[1]-st.fixed[1])*dy)/Math.max(1e-6,dx*dx+dy*dy);
  };
  const startResize=(e:React.PointerEvent,b:LineBox,i:number)=>{e.stopPropagation();e.preventDefault();
    const c=cornersOf(b);const centre:Point=[c.reduce((n,v)=>n+v[0],0)/4,c.reduce((n,v)=>n+v[1],0)/4];
    const plane=b.plane;const uvC:Point=plane?[[plane.uv[0],plane.uv[1]],[plane.uv[2],plane.uv[1]],[plane.uv[2],plane.uv[3]],[plane.uv[0],plane.uv[3]]][i] as Point:c[i];
    const fixed=plane||e.altKey?centre:c[(i+2)%4];
    rs.current={b,fixed,c0:uvC,plane,inv:plane?invertH(plane.h):undefined,base:1,ref:1,fine:e.shiftKey,k:1};
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    onResizeLine?.({lineId:b.lineId,placement:b.placement,phase:'start',k:1,fixed,box:b});};
  const moveResize=(e:React.PointerEvent)=>{const st=rs.current;if(!st)return;const P=toPx(e) as Point;const proj=project(st,P);
    if(e.shiftKey!==st.fine){st.base=st.k;st.ref=proj;st.fine=e.shiftKey;}
    st.k=Math.max(.1,Math.min(10,st.base+(proj-st.ref)*(st.fine?.25:1)));
    onResizeLine?.({lineId:st.b.lineId,placement:st.b.placement,phase:'move',k:st.k,fixed:st.fixed,box:st.b});};
  const endResize=(e:React.PointerEvent)=>{const st=rs.current;rs.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    if(st)onResizeLine?.({lineId:st.b.lineId,placement:st.b.placement,phase:'end',k:st.k,fixed:st.fixed,box:st.b});};

  return <>
    {guides.occupancy&&<canvas ref={heat} className="guide-heat" aria-hidden="true"/>}
    <svg ref={svg} className="stage-guides" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{['--px' as string]:s}}>
      {surfaces.map(q=><g key={q.id} className={`g-wall ${q.sel?'sel':''}`}>
        <polygon points={q.quad.map(p=>p.join(',')).join(' ')} style={{strokeWidth:s*1.2}} onPointerDown={e=>wallDown(e,q.id,q.quad,-1)} onPointerMove={wallMove} onPointerUp={wallUp} onPointerCancel={wallUp}><title>{q.label}{q.sel?' · drag to move · ⌫ deletes':''}</title></polygon>
        {q.sel&&onWallEdit&&q.quad.map(([x,y],i)=><circle key={i} className="g-wall-handle" cx={x} cy={y} r={s*6} style={{strokeWidth:s*1.5}} onPointerDown={e=>wallDown(e,q.id,q.quad,i)} onPointerMove={wallMove} onPointerUp={wallUp} onPointerCancel={wallUp}/>)}
      </g>)}
      {(guides.regions||guides.anchor||selectedLine)&&boxes.map(b=>{const sel=b.lineId===selectedLine;const c=cornersOf(b);const movable=b.placement!=='surface';
        const down=(e:React.PointerEvent)=>{e.stopPropagation();onSelectLine(b.lineId);if(!movable)return;const [x,y]=toPx(e);drag.current={lineId:b.lineId,placement:b.placement,x0:x,y0:y};(e.currentTarget as Element).setPointerCapture(e.pointerId);onDragLine(b.lineId,b.placement,0,0,'start');};
        const mv=(e:React.PointerEvent)=>{const d=drag.current;if(!d)return;const [x,y]=toPx(e);onDragLine(d.lineId,d.placement,(x-d.x0)/W,(y-d.y0)/H,'move');};
        const up=(e:React.PointerEvent)=>{const d=drag.current;drag.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);if(d){const [x,y]=toPx(e);onDragLine(d.lineId,d.placement,(x-d.x0)/W,(y-d.y0)/H,'end');}};
        const hs=s*(sel?9:7);
        return <g key={b.key} className={`g-line ${sel?'sel':''} ${b.quiet?'quiet':''} p-${b.placement} ${movable?'':'fixed'} ${guides.regions?'':'nobox'}`}>
        {b.hint&&sel&&<><line className="g-leader" x1={b.hint.x} y1={b.hint.y} x2={b.x+b.w/2} y2={b.y+b.h/2} style={{strokeWidth:s}}/><circle className="g-hint" cx={b.hint.x} cy={b.hint.y} r={s*4} style={{strokeWidth:s*1.2}}/></>}
        <polygon className="g-box" points={c.map(v=>v.join(',')).join(' ')} onPointerDown={down} onPointerMove={mv} onPointerUp={up}/>
        {sel&&onResizeLine&&c.map(([x,y],i)=><rect key={i} className="g-handle" x={x-hs/2} y={y-hs/2} width={hs} height={hs} rx={s*1.5} style={{cursor:CURSORS[i],strokeWidth:s*1.2}}
          onPointerDown={e=>startResize(e,b,i)} onPointerMove={moveResize} onPointerUp={endResize} onPointerCancel={endResize}/>)}
        <title>{b.role&&!['line','hud'].includes(b.role)?`${b.role==='sat'?'SATELLITE':b.role.toUpperCase()} · `:''}{b.placement==='anchor'?'HUD':b.placement==='surface'?'WALL':b.placement.toUpperCase()}{b.auto?` · AUTO${b.coverage!=null?` · ${Math.round(b.coverage*100)}% covered`:''}`:''}{b.front?' · PROMOTED TO FRONT':''}{b.quiet?' · QUIET':''}</title>
        {b.head&&b.head!=='tracked'&&<g className={`g-nohead ${b.head}`} transform={`translate(${b.x+b.w+s*4},${b.y-s*4}) scale(${s*.6})`}><circle cx="0" cy="0" r="10"/><path d="M-4 -3a4 4 0 1 0 8 0a4 4 0 1 0-8 0M-6 7c1-3 3-4.5 6-4.5s5 1.5 6 4.5M-8 8 8-8"/>
          <title>{b.head==='none'?'No head detected here · use Track head to analyze this footage':'No person here: HUD holds the head position'}</title></g>}
        {b.anchorPt&&(guides.anchor||sel)&&<g className={`g-anchor ${sel?'editable':''} ${b.head==='held'?'held':''}`}>
          <line x1={b.anchorPt[0]-s*10} y1={b.anchorPt[1]} x2={b.anchorPt[0]+s*10} y2={b.anchorPt[1]} style={{strokeWidth:s}}/><line x1={b.anchorPt[0]} y1={b.anchorPt[1]-s*10} x2={b.anchorPt[0]} y2={b.anchorPt[1]+s*10} style={{strokeWidth:s}}/><circle cx={b.anchorPt[0]} cy={b.anchorPt[1]} r={s*6} style={{strokeWidth:s}}/>
          {sel&&onDragAnchor&&<circle className="g-anchor-hit" role="button" tabIndex={0} aria-label="Move HUD tracking point" cx={b.anchorPt[0]} cy={b.anchorPt[1]} r={s*13}
            onPointerDown={e=>anchorDown(e,b)} onPointerMove={anchorMove} onPointerUp={anchorUp} onPointerCancel={anchorUp}
            onKeyDown={e=>{const dirs:Record<string,Point>={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};const d=dirs[e.key];if(!d||!b.anchorPt)return;e.stopPropagation();e.preventDefault();const n=s*(e.shiftKey?10:1);
              const point:Point=[(b.anchorPt[0]+d[0]*n)/W,(b.anchorPt[1]+d[1]*n)/H];onDragAnchor(b.lineId,point,'start');onDragAnchor(b.lineId,point,'move');onDragAnchor(b.lineId,point,'end');}}/>}
          <title>{sel?'Drag to attach to a different spot on the head · arrow keys nudge · editor guide only':'Head attachment · select its text clip to move'}</title></g>}
      </g>;})}
    </svg>
  </>;
}
