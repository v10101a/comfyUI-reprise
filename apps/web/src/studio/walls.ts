// Wall (surface) edits: re-place a wall's quad, delete a wall. Pure project → project, so every edit is one undo step.
import type {Project,Point,Placement,Surface,SurfaceKey} from '../types';
import {squareToQuad,invertH,applyH} from '../geometry';

/** New corners (source-normalized) drawn at `keyFrame`: the old track no longer fits, so the wall is static until re-tracked. */
export function setSurfaceQuad(p:Project,id:string,corners:Point[],keyFrame:number):Project{
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id===id?{...s,corners:corners.map(([x,y])=>[+x.toFixed(5),+y.toFixed(5)] as Point),keyFrame,status:'drawn',track:null,inPlane:null}:s)};
}
/** Move a tracked wall: `corners` (source-normalized, drawn at a frame whose raw tracked quad is `tracked`) are stored in
 *  the track's plane, so the wall keeps following the track. */
export function setSurfaceInPlane(p:Project,id:string,corners:Point[],tracked:Point[]):Project{
  const Hi=invertH(squareToQuad(tracked));const inPlane=corners.map(([x,y])=>applyH(Hi,x,y)).map(([u,v])=>[+u.toFixed(5),+v.toFixed(5)] as Point);
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id===id?{...s,inPlane}:s)};
}
/** Before a re-track: a moved or keyframed wall's corners at `frame` become its key quad (the tracker starts from them). */
export function bakeSurface(p:Project,id:string,corners:Point[]|undefined,frame:number):Project{
  if(!corners)return p;
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id===id&&(s.inPlane||s.keys)?{...s,corners:round(corners),keyFrame:frame,inPlane:null,keys:null}:s)};
}
const round=(c:Point[])=>c.map(([x,y])=>[+x.toFixed(5),+y.toFixed(5)] as Point);

// ---------- keyframes ----------
export const keyAt=(s:Surface|undefined,frame:number)=>s?.keys?.find(k=>k.f===frame);
/** Set (or add) the key at `frame`. */
export function setSurfaceKey(p:Project,id:string,frame:number,corners:Point[]):Project{
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id!==id?s:{...s,keys:[...(s.keys||[]).filter(k=>k.f!==frame),{f:frame,corners:round(corners)}].sort((a,b)=>a.f-b.f)})};
}
/** Remove the key at `frame`; removing the last one leaves keyframe mode (the raw track again). */
export function deleteSurfaceKey(p:Project,id:string,frame:number):Project{
  return {...p,surfaces:(p.surfaces||[]).map(s=>{if(s.id!==id)return s;const keys=(s.keys||[]).filter(k=>k.f!==frame);return {...s,keys:keys.length?keys:null};})};
}
export function setSurfaceKeys(p:Project,id:string,keys:SurfaceKey[]):Project{
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id===id?{...s,keys}:s)};
}

/** Where a deleted wall's lines go: Behind the person when there is a matte, else on top (Caption). */
export const wallFallback=(p:Project):Placement=>p.analysis.matte?'behind':'overlay';

export function deleteSurface(p:Project,id:string):{project:Project;lines:number;to:Placement}{
  const to=wallFallback(p);const lines=new Set<string>();
  const words=p.words.map(w=>{if(w.placement!=='surface'||w.surfaceId!==id)return w;lines.add(w.lineId);return {...w,placement:to,surfaceId:null};});
  return {project:{...p,surfaces:(p.surfaces||[]).filter(s=>s.id!==id),words},lines:lines.size,to};
}

export type WallStatus = 'tracked'|'static'|'failed'|'tracking';
export const wallStatus=(s:{status?:string;track?:string|null}|undefined,running:boolean):WallStatus=>
  running||s?.status==='tracking'?'tracking':s?.status==='tracked'&&s.track?'tracked':s?.status==='failed'?'failed':'static';
export const WALL_STATUS_TITLE:Record<WallStatus,string>={tracked:'Tracked · re-track',static:'Not tracked: the wall stays where it was drawn · track',failed:'Tracking failed: using the drawn corners · retry',tracking:'Tracking…'};
