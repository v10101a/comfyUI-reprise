import type {Asset,Project,MediaLayer} from '../types';
import {request} from '../api';
import {explicitLayers,mediaLayer} from '../layers';
import {useTake} from './takes';

/** A user-imported Comfy workflow (server/app/workflows.py, data/workflows/<id>/workflow.json). */
export type WfRole='media'|'prompt'|'text'|'seed'|'number'|'bool';
export type WfCandidate={node:string;field:string;classType:string;title:string;role:WfRole;kind:string;value:unknown;media?:'image'|'video'|'audio';min?:number;max?:number;step?:number};
export type WfInput=Omit<WfCandidate,'classType'|'value'>&{default?:unknown};
export type WfOutput={node:string;classType?:string;title?:string;type:string};
export type Workflow={id:string;name:string;createdAt:string;source:'file'|'comfy';nodes:number;missing:string[];missingModels?:string[];target?:'local'|'remote';readinessError?:string|null;
  candidates:{inputs:WfCandidate[];outputs:WfOutput[]};inputs:Record<string,WfInput>;output:WfOutput|null};
/** Where the workflow's media input comes from: an asset, else the footage (a frame at `time`, or [start,end)). */
export type WfSource={assetId?:string;path?:string;time?:number;start?:number;end?:number};
export type WfRunBody={inputs:Record<string,unknown>;source?:WfSource;sources?:Record<string,WfSource>;variants?:number;layerId?:string;addLayer?:boolean;takeOf?:string};
export type WfResult={asset:Asset&{layer?:MediaLayer};assetId:string;workflowId:string;promptId:string};

export const listWorkflows=()=>request<Workflow[]>('/api/workflows');
export const importWorkflow=(graph:unknown,name:string)=>request<Workflow>('/api/workflows',{method:'POST',body:JSON.stringify({graph,name,source:'file'})});
export const updateWorkflow=(id:string,patch:Partial<Pick<Workflow,'name'|'inputs'|'output'>>)=>request<Workflow>(`/api/workflows/${id}`,{method:'PUT',body:JSON.stringify(patch)});
export const deleteWorkflow=(id:string)=>request(`/api/workflows/${id}/delete`,{method:'POST'});
export const setSession=(projectId:string)=>request('/api/session',{method:'PUT',body:JSON.stringify({projectId})}).catch(()=>undefined);

export const inputKey=(c:{node:string;field:string;role:WfRole},taken:Set<string>)=>{
  const base=['media','prompt','seed'].includes(c.role)?c.role:`${c.node}.${c.field}`;let k=base,n=2;while(taken.has(k))k=`${base}${n++}`;return k;};

/** Mirror what the server did to project.json so the next save keeps it (assets + the new layer or take). */
export function landResult(p:Project,r:WfResult,takeOf?:string):Project{
  const {layer,...asset}=r.asset;
  if(p.assets?.some(a=>a.id===asset.id))return p;
  let layers=p.layers;
  if(takeOf)layers=explicitLayers(p).map(l=>l.id===takeOf&&l.kind==='media'?{...l,assetId:asset.id,takes:[...new Set([...(((l as {takes?:string[]}).takes)||[l.assetId]),asset.id])]}:l);
  else if(layer){const ls=explicitLayers(p);const at=ls.findIndex(l=>l.kind==='text'&&l.which==='behind');ls.splice(at<0?ls.length:at,0,layer);layers=ls;}
  return {...p,assets:[...(p.assets||[]),asset],layers};
}
/** Put an existing asset in the stack (under the behind text) or into a layer as its active take. */
export function applyAsset(p:Project,a:Asset,takeOf?:string):Project{
  if(takeOf)return useTake(p,takeOf,a.id);
  const ls=explicitLayers(p);const at=ls.findIndex(l=>l.kind==='text'&&l.which==='behind');ls.splice(at<0?ls.length:at,0,mediaLayer(a,p));return {...p,layers:ls};
}
