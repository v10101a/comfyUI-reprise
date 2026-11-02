import type {Asset,WorkflowDraft,MediaLayer,Project} from '../types';
import {assetOf,editMedia,layersOf} from '../layers';

export type Audition = {layerId:string;assetId:string};
export const visualLayer=(p:Project,id:string)=>layersOf(p).find((l):l is MediaLayer=>l.id===id&&l.kind==='media');

export function setGeneration(p:Project,id:string,workflowId:string,patch:WorkflowDraft={}):Project{
  return editMedia(p,id,l=>({...l,generation:{...l.generation,workflowId,workflows:{...l.generation?.workflows,
    [workflowId]:{...l.generation?.workflows?.[workflowId],...patch}}}}));
}

/** Include all generated candidates, even those finished after the editor closed. Other layers stay separate. */
export function layerTakes(p:Project,id:string):Asset[]{
  const l=visualLayer(p,id);if(!l)return [];
  const ids=new Set([...(l.takes||[]),l.assetId]);
  return (p.assets||[]).filter(a=>ids.has(a.id)||a.source?.layerId===id);
}

/** Preview is a derived project; saving/exporting the authored project cannot accidentally accept a candidate. */
export function auditionProject(p:Project,a:Audition|null):Project{
  if(!a||!assetOf(p,a.assetId))return p;
  const l=visualLayer(p,a.layerId);if(!l||l.assetId===a.assetId)return p;
  return {...p,layers:layersOf(p).map(l=>l.id===a.layerId?{...l,assetId:a.assetId}:l)};
}

/** Keep the complete edit, including the original take. Short video takes hold their last frame in the renderer. */
export function useTake(p:Project,id:string,assetId:string):Project{
  if(!assetOf(p,assetId))return p;
  return editMedia(p,id,l=>({...l,assetId,takes:[...new Set([...(l.takes||[]),l.assetId,assetId])]}));
}

/** Polling may finish after navigation; never add one project's outputs to another project. */
export function mergeAssets(p:Project,pid:string,assets:Asset[]):Project{
  if(p.id!==pid)return p;
  const have=new Set((p.assets||[]).map(a=>a.id));const added=assets.filter(a=>!have.has(a.id));
  return added.length?{...p,assets:[...(p.assets||[]),...added]}:p;
}
