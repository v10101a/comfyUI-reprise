import type {Project,MediaLayer,Asset,LayerGeneration} from '../types';
import {assetOf,dragLayer,editMedia,layerLength,mediaLayer,insertLayer} from '../layers';
import {setClip,type Clip} from '../audioClip';

export const ASSET_MIME='application/x-typeset-asset';
export const visualFile=(file:File)=>/^(video|image)\//.test(file.type)||/\.(mp4|mov|webm|mkv|m4v|png|jpe?g|webp|gif|bmp|tiff?)$/i.test(file.name);
export type MediaDrop={assetId?:string;files?:File[];generation?:LayerGeneration};

/** Project duration is a frame boundary; shortening keeps all authored media and text. */
export function setDuration(p:Project,seconds:number):Project{
  if(!Number.isFinite(seconds)||seconds<=0)return p;
  const duration=Math.max(1,Math.round(seconds*p.fps))/p.fps;
  return Math.abs(duration-p.duration)<1e-8?p:{...p,duration};
}

/** Include a moved/extended media layer in playback and export, without shrinking the edit. */
export function fitLayerEnd(p:Project,l:MediaLayer):Project{
  const end=Math.ceil((l.start+layerLength(l))*p.fps-1e-6)/p.fps;
  return end>p.duration?{...p,duration:end}:p;
}

/** Occupied timeline clips, not unused source files in the bin, determine the edit's bounds. */
export function songTimelineRange(p:Project,c:Clip,includeHead=true){
  const epsilon=1e-6/p.fps;
  const ranges=[[c.offset,c.offset+c.out-c.in,.001],
    ...p.words.map(w=>[w.start,w.end,epsilon]),...p.shots.map(s=>[s.start,s.end,epsilon]),
    ...(p.layers||[]).flatMap(l=>l.kind==='media'?[[l.start,l.start+layerLength(l),epsilon]]:[])];
  if(p.media.video)ranges.push([p.timing?.sceneOffset||0,(p.timing?.sceneOffset||0)+p.media.video.duration,epsilon]);
  const valid=ranges.filter(([a,b])=>Number.isFinite(a)&&Number.isFinite(b)&&b>a);
  if(!valid.length)return {start:0,end:p.duration,duration:p.duration};
  // Audio trim timestamps persist to milliseconds; tolerate that quantization at a frame boundary.
  const start=includeHead?Math.min(...valid.map(([a,,e])=>Math.floor((a+e)*p.fps)))/p.fps:0;
  const end=Math.max(...valid.map(([,b,e])=>Math.ceil((b-e)*p.fps)))/p.fps;
  return {start,end,duration:Math.max(1/p.fps,end-start)};
}

/** Refit to occupied clips; adding/removing leading time moves the whole edit together. */
export function fitSongRange(p:Project,c:Clip,songDur:number,includeHead=true):{project:Project;shift:number}{
  const range=songTimelineRange(p,c,includeHead),shift=-range.start;
  let q=setClip(p,{...c,offset:c.offset+shift},songDur);
  q={...q,duration:range.duration};
  if(!shift)return {project:q,shift:0};
  q={...q,words:p.words.map(w=>({...w,start:w.start+shift,end:w.end+shift})),
    layers:p.layers?.map(l=>l.kind==='media'?{...l,start:l.start+shift}:l),
    shots:p.shots.map(s=>({...s,start:s.start+shift,end:s.end+shift})),
    surfaces:p.surfaces?.map(s=>({...s,keyFrame:s.keyFrame+Math.round(shift*p.fps),keys:s.keys?.map(k=>({...k,f:k.f+Math.round(shift*p.fps)}))})),
    lineMeta:p.lineMeta?Object.fromEntries(Object.entries(p.lineMeta).map(([id,m])=>[id,m.generation?.start==null?m:{...m,generation:{...m.generation,start:m.generation.start+shift}}])):p.lineMeta,
    timing:{...p.timing,sceneOffset:(p.timing?.sceneOffset||0)+shift}};
  return {project:q,shift};
}

export function setMediaLength(p:Project,id:string,seconds:number):Project{
  if(!Number.isFinite(seconds)||seconds<=0)return p;
  const l=p.layers?.find((l):l is MediaLayer=>l.id===id&&l.kind==='media');if(!l)return p;
  const length=Math.max(1,Math.round(seconds*p.fps))/p.fps;
  const next=dragLayer(l,assetOf(p,l.assetId),'tail',length-layerLength(l),p.fps);
  return fitLayerEnd(editMedia(p,id,()=>next),next);
}

/** Timeline drops keep full video duration; several files form consecutive clips. */
export function placeTimelineAssets(p:Project,assets:Asset[],time:number):{project:Project;layerId:string}{
  let q=p,start=Math.max(0,Math.round(time*p.fps)/p.fps),layerId='';
  if(!Number.isFinite(start)||!assets.length)return {project:p,layerId};
  const known=new Set((p.assets||[]).map(a=>a.id));
  q={...p,assets:[...(p.assets||[]),...assets.filter(a=>{if(known.has(a.id))return false;known.add(a.id);return true;})]};
  for(const a of assets){
    const l={...mediaLayer(a,q,start),in:0,out:a.kind==='video'&&a.duration?a.duration:5};
    // A generated take is reusable footage; carry its recipe, never the reference clip's trims/effects.
    const origin=q.layers?.find((x):x is MediaLayer=>x.kind==='media'&&x.id===a.source?.layerId);
    if(origin){l.generation=origin.generation?structuredClone(origin.generation):undefined;
      l.takes=[...new Set([a.id,origin.assetId,...(origin.takes||[]),...(q.assets||[]).filter(x=>x.source?.layerId===origin.id).map(x=>x.id)])];}
    q=fitLayerEnd(insertLayer(q,l,'under-text'),l);layerId=l.id;
    start=Math.ceil((l.start+layerLength(l))*p.fps-1e-6)/p.fps;
  }
  return {project:q,layerId};
}
