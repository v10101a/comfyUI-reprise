import type {Project,HudPointer,HeadSpot,Point} from './types';
import {lineLookOf,setLineMeta} from './looks';

export function hudPointer(p:Project,lineId:string){
  const h=p.lineMeta?.[lineId]?.hud,color=lineLookOf(p,lineId)?.palette.accent??'#d8ff62';
  return {point:h?.point??undefined,dot:h?.dot!==false,connector:h?.connector!==false,dotColor:h?.dotColor??color,connectorColor:h?.connectorColor??color};
}
export function setHudPointer(p:Project,lineIds:string[],patch:{[K in keyof HudPointer]?:HudPointer[K]|null}):Project{
  return lineIds.reduce((q,id)=>{const h={...q.lineMeta?.[id]?.hud};
    for(const k of Object.keys(patch) as (keyof HudPointer)[]){if(patch[k]==null)delete h[k];else Object.assign(h,{[k]:patch[k]});}
    return setLineMeta(q,id,{hud:Object.keys(h).length?h:null});},p);
}
/** Invert the displayed head's two axes. Works with cover fit, crop, rotation, and animated clip transforms. */
export function relativeHeadSpot(point:Point,topLeft:Point,topRight:Point,bottomLeft:Point):HeadSpot|undefined{
  const ax=topRight[0]-topLeft[0],ay=topRight[1]-topLeft[1],bx=bottomLeft[0]-topLeft[0],by=bottomLeft[1]-topLeft[1];
  const dx=point[0]-topLeft[0],dy=point[1]-topLeft[1],det=ax*by-ay*bx;if(Math.abs(det)<1e-10)return;
  return {u:+((dx*by-dy*bx)/det).toFixed(5),v:+((ax*dy-ay*dx)/det).toFixed(5)};
}
