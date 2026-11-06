import type {Project,MediaLayer,Tracks,Point,MatteSource} from './types';
import {assetOf,layerSourceTime,layerStateAt,topMediaAt} from './layers';

/** Never reuse a matte from another take or from outside its extracted range. */
export function matteLayer(p:Project):MediaLayer|undefined{
  const s=p.analysis.matteSource;if(!s)return;
  const l=p.layers?.find((l):l is MediaLayer=>l.id===s.layerId&&l.kind==='media');
  return l&&l.assetId===s.assetId&&assetOf(p,l.assetId)?.path===s.path&&l.in>=s.in-.001&&l.out<=s.out+.001?l:undefined;
}
export function matteTime(p:Project,t:number):number|undefined{
  const s=p.analysis.matteSource;if(!s){const at=t-(p.timing?.sceneOffset||0);return at>=0?at:undefined;}
  const l=matteLayer(p);if(!l||l.hidden||layerStateAt(l,t).opacity<=0)return;
  const at=layerSourceTime(l,t);return at==null?undefined:s.kind==='image'?0:Math.max(0,at-s.in);
}
/** Same cover-fit + centre rotation as placeLayer, in normalized composition coordinates. */
export function mattePoint(p:Project,l:MediaLayer,t:number,x:number,y:number,inverse=false):Point{
  const s=p.analysis.matteSource!,tr=layerStateAt(l,t).transform;
  const scale=Math.max(p.width/s.width,p.height/s.height)*(tr.scale??1),a=(tr.rotate||0)*Math.PI/180,c=Math.cos(a),sin=Math.sin(a);
  const cx=p.width*(.5+(tr.x||0)),cy=p.height*(.5+(tr.y||0));
  if(inverse){const dx=x*p.width-cx,dy=y*p.height-cy;return [(.5+(dx*c+dy*sin)/(s.width*scale)),(.5+(-dx*sin+dy*c)/(s.height*scale))];}
  const dx=(x-.5)*s.width*scale,dy=(y-.5)*s.height*scale;return [(cx+dx*c-dy*sin)/p.width,(cy+dx*sin+dy*c)/p.height];
}
/** Only source geometry/timing invalidates the mapped analysis, never unrelated text or board edits. */
export function matteSignature(p:Project){const l=matteLayer(p);return JSON.stringify([p.analysis.matteSource,p.width,p.height,p.duration,p.fps,p.timing?.sceneOffset,l&&[l.assetId,l.start,l.in,l.out,l.hidden,l.transform,l.opacity,l.keys]]);}
export function matteTracks(p:Project,raw:Tracks|undefined):Tracks|undefined{
  if(!p.analysis.matteSource){const off=p.timing?.sceneOffset||0;return !off||!raw?raw:{...raw,frames:raw.frames+Math.round(off*raw.fps),tracks:raw.tracks.map(t=>({...t,frames:t.frames.map(f=>({...f,f:f.f+Math.round(off*raw.fps)}))}))};}
  const l=matteLayer(p);if(!l||l.hidden||!raw)return;
  const frames=Math.ceil(p.duration*p.fps);
  return {fps:p.fps,frames,tracks:raw.tracks.map(track=>{
    const points=new Map(track.frames.map(pt=>[pt.f,pt])),last=Math.max(0,raw.frames-1);
    const mapped:typeof track.frames=[];
    for(let f=Math.max(0,Math.ceil(l.start*p.fps));f<Math.min(frames,Math.ceil((l.start+l.out-l.in)*p.fps));f++){
      const t=f/p.fps,at=matteTime(p,t);if(at==null)continue;const sf=Math.min(last,Math.round(at*raw.fps));
      let pt=points.get(sf);for(let back=1;!pt&&back<=6;back++)pt=points.get(sf-back);if(!pt)continue;
      const [x,y,w,h]=pt.bbox,corners=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]].map(([x,y])=>mattePoint(p,l,t,x,y));
      const xs=corners.map(c=>c[0]),ys=corners.map(c=>c[1]),[cx,cy]=mattePoint(p,l,t,pt.cx,pt.cy);
      mapped.push({f,cx,cy,bbox:[Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)]});
    }
    return {...track,frames:mapped};})};
}

/** One cutout run: a per-clip entry (analysis.mattes) or the legacy single matte (id '' when it is the original footage). */
export type MatteEntry={id:string;matte:string;source:MatteSource|null;tracks?:string|null;occupancy?:string|null};
/** Every cutout the project holds; a per-clip entry wins over the legacy copy of the same clip. */
export function matteEntries(p:Project):MatteEntry[]{
  const a=p.analysis,out=new Map<string,MatteEntry>();
  if(a.matte){const id=a.matteSource?.layerId||'';out.set(id,{id,matte:a.matte,source:a.matteSource||null,tracks:a.tracks,occupancy:a.occupancy});}
  for(const [id,e] of Object.entries(a.mattes||{}))if(e?.matte&&e.matteSource)out.set(id,{id,matte:e.matte,source:e.matteSource,tracks:e.tracks,occupancy:e.occupancy});
  return [...out.values()];
}
export function matteFor(p:Project,layerId:string):MatteEntry|undefined{return matteEntries(p).find(e=>e.id===layerId);}
/** The project with one cutout in the legacy slots (what matteLayer / matteTime / mattePoint read); none = no cutout. */
export function withMatte(p:Project,e:MatteEntry|undefined):Project{
  const a=p.analysis;
  if(!e)return a.matte?{...p,analysis:{...a,matte:null,matteSource:null,tracks:null,occupancy:null}}:p;
  if(a.matte===e.matte&&(a.matteSource??null)===(e.source??null)&&(a.tracks??null)===(e.tracks??null)&&(a.occupancy??null)===(e.occupancy??null))return p;
  return {...p,analysis:{...a,matte:e.matte,matteSource:e.source,tracks:e.tracks??null,occupancy:e.occupancy??null}};
}
/** False when the entry's clip changed take or grew past the extracted range (never for the original footage). */
export function matteValid(p:Project,e:MatteEntry){return !e.source||!!matteLayer(withMatte(p,e));}
/** The cutout at t: the one belonging to the clip on top of the stack (a clip without one covers the rest, so none);
 *  the original footage's matte where no clip covers it. */
export function activeMatteAt(p:Project,t:number):MatteEntry|undefined{
  const entries=matteEntries(p);if(!entries.length)return;
  const legacy=entries.find(e=>!e.source);
  const top=p.layers?.length?[...p.layers].reverse().find((l):l is MediaLayer=>l.kind==='media'&&!l.hidden&&layerSourceTime(l,t)!==undefined&&layerStateAt(l,t).opacity>0):undefined;
  if(!top)return legacy;
  const e=entries.find(x=>x.id===top.id);return e&&matteTime(withMatte(p,e),t)!=null?e:undefined;
}
export {topMediaAt};
