// Wall (surface) edits: re-place a wall's quad, delete a wall. Pure project → project, so every edit is one undo step.
import type {Project,Point,Placement} from '../types';

/** New corners (source-normalized) drawn at `keyFrame`: the old track no longer fits, so the wall is static until re-tracked. */
export function setSurfaceQuad(p:Project,id:string,corners:Point[],keyFrame:number):Project{
  return {...p,surfaces:(p.surfaces||[]).map(s=>s.id===id?{...s,corners:corners.map(([x,y])=>[+x.toFixed(5),+y.toFixed(5)] as Point),keyFrame,status:'drawn',track:null}:s)};
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
