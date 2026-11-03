import type {Asset,LayerGeneration,Project,WorkflowDraft} from '../types';
import {assetOf} from '../layers';
import {patchScene,sceneForId,type Scene} from './scenes';

const object=(v:unknown):Record<string,any>=>v&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,any>:{};

/** Recover editable inputs, never the staged Comfy input paths from a previous run. */
export function assetGeneration(asset:Asset|undefined):LayerGeneration|undefined{
  const src=asset?.source,wid=src?.workflowId;if(!wid)return;
  const saved=object(src.regeneration),from=object(src.from),raw=object(src.inputs);
  if(!Object.keys(saved).length&&!Object.keys(from).length&&!Object.keys(raw).length)return;
  const draft:WorkflowDraft=structuredClone(saved),sources={...draft.sources},windows={...draft.sourceWindows},files={...draft.mediaFiles};
  for(const [key,value] of Object.entries(from)){
    const ref=object(value);
    if(!sources[key]){
      if(typeof ref.assetId==='string')sources[key]=ref.assetId;
      else if(typeof ref.path==='string'){sources[key]='@prepared';files[key]={path:ref.path,name:'Original vocal',duration:Number(ref.end)||5};}
      else if(typeof ref.audio==='string')sources[key]='@song';
      else if(typeof ref.video==='string')sources[key]=typeof ref.time==='number'?'@frame':'@range';
    }
    const window=Object.fromEntries(['time','start','end'].filter(k=>Number.isFinite(ref[k])).map(k=>[k,ref[k]]));
    if(!windows[key]&&Object.keys(window).length)windows[key]=window;
  }
  draft.inputs={...Object.fromEntries(Object.entries(raw).filter(([key])=>!from[key]&&!sources[key])),...draft.inputs};
  draft.sources=sources;if(Object.keys(windows).length)draft.sourceWindows=windows;if(Object.keys(files).length)draft.mediaFiles=files;
  if(!draft.postprocess&&src.postprocess)draft.postprocess=structuredClone(src.postprocess) as WorkflowDraft['postprocess'];
  return {workflowId:wid,workflows:{[wid]:draft}};
}

export function takeGeneration(p:Project,scene:Scene|undefined,assetId:string):LayerGeneration|undefined{
  return scene?.takeGenerations?.[assetId]||assetGeneration(assetOf(p,assetId));
}

/** The original still and its own identity references are the useful neighbours of a shot. */
export function relatedReferences(p:Project,assetId:string):string[]{
  const found=new Set<string>(),visited=new Set<string>();
  const visit=(id:string,depth:number)=>{if(visited.has(id)||depth>3)return;visited.add(id);const asset=assetOf(p,id);if(!asset)return;
    const gen=assetGeneration(asset),draft=gen?.workflows?.[gen.workflowId||''];
    for(const ref of Object.values(draft?.sources||{})){if(ref.startsWith('@')||ref===assetId||!assetOf(p,ref))continue;found.add(ref);visit(ref,depth+1);}
  };visit(assetId,0);return [...found];
}

export function inheritedReference(p:Project,assetId:string,key:string):string|undefined{
  for(const id of [assetId,...relatedReferences(p,assetId)]){
    const gen=assetGeneration(assetOf(p,id)),source=gen?.workflows?.[gen.workflowId||'']?.sources?.[key];
    if(source&&!source.startsWith('@')&&assetOf(p,source))return source;
  }
}

export function setTakeGeneration(p:Project,sceneId:string,assetId:string,workflowId:string,patch:WorkflowDraft={}):Project{
  const scene=sceneForId(p,sceneId);if(!scene||!assetOf(p,assetId))return p;
  const base=takeGeneration(p,scene,assetId)||scene.generation||{};
  const generation={...base,workflowId,workflows:{...base.workflows,[workflowId]:{...base.workflows?.[workflowId],...patch}}};
  return patchScene(p,scene.id,{takeGenerations:{...scene.takeGenerations,[assetId]:generation}});
}
