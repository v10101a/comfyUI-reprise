import type {Project,Asset,SceneLayer,MediaLayer,LayerBlend,LayerTransform,LayerKey} from './types';

/** The stack a project without `layers` renders (docs/SCHEMA.md §1 layers): plate, behind text, subject cutout, front text. */
export const DEFAULT_LAYERS:SceneLayer[]=[{id:'plate',kind:'plate'},{id:'text-behind',kind:'text',which:'behind'},{id:'subject',kind:'subject'},{id:'text-front',kind:'text',which:'front'}];
export function layersOf(p:Project):SceneLayer[]{return p.layers?.length?p.layers:DEFAULT_LAYERS;}
export function assetOf(p:Project,id:string):Asset|undefined{return p.assets?.find(a=>a.id===id);}
/** Seconds the layer occupies on the timeline (out − in). */
export function layerLength(l:MediaLayer){return Math.max(0,l.out-l.in);}
/** Source time at project time t, or undefined when the layer is not on screen. */
export function layerSourceTime(l:MediaLayer,t:number){const d=t-l.start;return d>=0&&d<l.out-l.in?l.in+d:undefined;}
export const BLEND_OP:Record<LayerBlend,GlobalCompositeOperation>={normal:'source-over',screen:'screen',multiply:'multiply',add:'lighter',overlay:'overlay'};
type Prop='x'|'y'|'scale'|'rotate'|'opacity';
const BASE:Record<Prop,number>={x:0,y:0,scale:1,rotate:0,opacity:1};
/** Static value of a property (transform / opacity), ignoring keys. */
export function staticProp(l:MediaLayer,k:Prop):number{return k==='opacity'?l.opacity??1:(l.transform?.[k]??BASE[k]);}
/** A property at layer-local time lt: smoothstep between the keys that set it, held outside them; no keys = static. */
export function propAt(l:MediaLayer,k:Prop,lt:number):number{
  const ks=(l.keys||[]).filter(x=>x[k]!=null).sort((a,b)=>a.t-b.t);if(!ks.length)return staticProp(l,k);
  if(lt<=ks[0].t)return ks[0][k]!;const last=ks[ks.length-1];if(lt>=last.t)return last[k]!;
  const i=ks.findIndex(x=>x.t>lt);const a=ks[i-1],b=ks[i];const u=(lt-a.t)/Math.max(1e-6,b.t-a.t);const s=u*u*(3-2*u);return a[k]!+(b[k]!-a[k]!)*s;
}
/** Transform and opacity at project time t. */
export function layerStateAt(l:MediaLayer,t:number):{transform:LayerTransform;opacity:number}{
  const lt=t-l.start;return {transform:{x:propAt(l,'x',lt),y:propAt(l,'y',lt),scale:propAt(l,'scale',lt),rotate:propAt(l,'rotate',lt)},opacity:Math.max(0,Math.min(1,propAt(l,'opacity',lt)))};
}
/** Set a property: on a key at lt when the layer is keyed for it (or `key` asks to add one), else the static value. */
export function setLayerProp(l:MediaLayer,k:Prop,v:number,lt:number,key=false):MediaLayer{
  const keyed=(l.keys||[]).some(x=>x[k]!=null);
  if(!keyed&&!key)return k==='opacity'?{...l,opacity:v}:{...l,transform:{...l.transform,[k]:v}};
  const t=+lt.toFixed(3);const keys=[...(l.keys||[])];const i=keys.findIndex(x=>Math.abs(x.t-t)<1e-3);
  if(i>=0)keys[i]={...keys[i],[k]:v};else keys.push({t,[k]:v} as LayerKey);keys.sort((a,b)=>a.t-b.t);return {...l,keys};
}
/** Key every animatable property at lt (◆ button) / remove the key there. */
export function keyAll(l:MediaLayer,lt:number):MediaLayer{const s=layerStateAt(l,l.start+lt);return (['x','y','scale','rotate','opacity'] as Prop[]).reduce((q,k)=>setLayerProp(q,k,k==='opacity'?s.opacity:s.transform[k as 'x']!,lt,true),l);}
export function unkey(l:MediaLayer,lt:number):MediaLayer{const keys=(l.keys||[]).filter(x=>Math.abs(x.t-lt)>=1e-3);return {...l,keys:keys.length?keys:null};}
export function keyNear(l:MediaLayer,lt:number,eps:number){return (l.keys||[]).find(x=>Math.abs(x.t-lt)<eps);}
/** Cover-fit the asset's w×h into W×H, then the transform (x/y fractions of the frame, scale ×, rotate °). */
export function placeLayer(g:CanvasRenderingContext2D,src:CanvasImageSource,w:number,h:number,W:number,H:number,tr:LayerTransform){
  const s=Math.max(W/w,H/h)*(tr.scale??1);
  g.save();g.translate(W/2+(tr.x||0)*W,H/2+(tr.y||0)*H);if(tr.rotate)g.rotate(tr.rotate*Math.PI/180);g.drawImage(src,-w*s/2,-h*s/2,w*s,h*s);g.restore();
}
export function image(src:string):Promise<HTMLImageElement>{return new Promise((resolve,reject)=>{const i=new Image();i.crossOrigin='anonymous';i.onload=()=>resolve(i);i.onerror=()=>reject(new Error(`Cannot load image: ${src}`));i.src=src;});}
/** The stack to edit: the explicit one, or the implied default made explicit (first edit). */
export function explicitLayers(p:Project):SceneLayer[]{return (p.layers?.length?p.layers:DEFAULT_LAYERS).map(l=>({...l}));}
export function mapLayer(p:Project,id:string,f:(l:SceneLayer)=>SceneLayer|null):Project{
  return {...p,layers:explicitLayers(p).flatMap(l=>{if(l.id!==id)return [l];const n=f(l);return n?[n]:[];})};
}
export function editMedia(p:Project,id:string,f:(l:MediaLayer)=>MediaLayer):Project{return mapLayer(p,id,l=>l.kind==='media'?f(l):l);}
/** Move layer `id` to stack index `to` (bottom = 0). */
export function moveLayer(p:Project,id:string,to:number):Project{
  const ls=explicitLayers(p);const i=ls.findIndex(l=>l.id===id);if(i<0)return p;const [l]=ls.splice(i,1);ls.splice(Math.max(0,Math.min(ls.length,to)),0,l);return {...p,layers:ls};
}
/** A media layer for an asset: whole asset (images hold to the end), from `start`. */
export function mediaLayer(a:Asset,p:Project,start=0):MediaLayer{
  const room=Math.max(1/p.fps,p.duration-start);const len=Math.min(a.kind==='video'&&a.duration?a.duration:room,room);
  return {id:`l_${Math.random().toString(36).slice(2,12)}`,kind:'media',assetId:a.id,name:a.name,start,in:0,out:+len.toFixed(3)};
}
/** Insert a layer just under the behind text (a new background), on top, or just above layer `above`. */
export function insertLayer(p:Project,l:SceneLayer,where:'under-text'|'top'|{above:string}):Project{
  const ls=explicitLayers(p).filter(x=>x.id!==l.id);let i=ls.length;
  if(where==='under-text'){const j=ls.findIndex(x=>x.kind==='text'&&x.which==='behind');if(j>=0)i=j;}
  else if(where!=='top'){const j=ls.findIndex(x=>x.id===where.above);if(j>=0)i=j+1;}
  ls.splice(i,0,l);return {...p,layers:ls};
}
/** Replace (a new take): same placement, timing, transform, keys and effects; the out point is clamped to the new source. */
export function replaceAsset(p:Project,id:string,a:Asset):Project{
  return editMedia(p,id,l=>{const len=l.out-l.in;const max=a.kind==='video'&&a.duration?a.duration:Infinity;const inn=Math.min(l.in,Math.max(0,max-len));
    return {...l,assetId:a.id,name:a.name??l.name,in:+inn.toFixed(3),out:+Math.min(max,inn+len).toFixed(3)};});
}
/** Timeline trims: move (start), trim head (start+in together), trim tail (out). Source bounds respected for video. */
export function dragLayer(l:MediaLayer,a:Asset|undefined,kind:'move'|'head'|'tail',d:number,fps:number):MediaLayer{
  const max=a?.kind==='video'&&a.duration?a.duration:Infinity;const min=1/fps;const r=(n:number)=>Math.round(n*fps)/fps;
  if(kind==='move')return {...l,start:r(Math.max(0,l.start+d))};
  if(kind==='head'){const dd=Math.max(-l.in,-l.start,Math.min(r(d),l.out-l.in-min));return {...l,start:r(l.start+dd),in:r(l.in+dd),keys:l.keys?.map(k=>({...k,t:k.t-dd}))??l.keys};}
  return {...l,out:Math.min(max,r(Math.max(l.in+min,Math.min(max,l.out+d))))};
}

/** Split a visual at the playhead into independently editable clips without retiming its source or animation. */
export function splitMediaLayer(p:Project,id:string,time:number,newId=()=>`l_${crypto.randomUUID()}`):{project:Project;layerId:string}|null{
  if(!Number.isFinite(time))return null;
  const l=layersOf(p).find((l):l is MediaLayer=>l.id===id&&l.kind==='media');if(!l)return null;
  const at=Math.round(time*p.fps)/p.fps,delta=at-l.start;
  if(delta<1/p.fps-1e-6||layerLength(l)-delta<1/p.fps-1e-6)return null;
  const cut=l.in+delta,right:MediaLayer={...structuredClone(l),id:newId(),start:at,in:cut,
    // Retain keys outside the clip: they define the same interpolation on either side of the cut.
    keys:l.keys?.map(k=>({...k,t:k.t-delta}))??l.keys,
    takes:[...new Set([l.assetId,...(l.takes||[]),...(p.assets||[]).filter(a=>a.source?.layerId===id).map(a=>a.id)])]};
  return {project:{...p,layers:explicitLayers(p).flatMap(x=>x.id===id?[{...l,out:cut},right]:[x])},layerId:right.id};
}
