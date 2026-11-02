import type {LayerGeneration,MediaLayer,Project,WorkflowDraft} from '../types';
import {assetOf,layersOf} from '../layers';
import {cardsOf,groupMembers,type BoardRole} from './board';

/** Scenes organise sources and recipes; clips remain the authored timeline. */
export type Scene={id:string;name:string;x:number;y:number;clips:string[];takes:string[];refs:string[];
  roles?:Record<string,BoardRole>;notes?:string;generation?:LayerGeneration};
const unique=(ids:(string|undefined)[])=>[...new Set(ids.filter((id):id is string=>!!id))];
export const sceneHeight=(s:Scene)=>Math.max(160,24+(s.refs.length?64:0)+Math.ceil(Math.min(s.takes.length,6)/2)*102+(s.takes.length>6?32:0));
export const sceneClips=(p:Project,s:Scene)=>layersOf(p).filter((l):l is MediaLayer=>l.kind==='media'&&s.clips.includes(l.id));

/** Read old boards without rewriting them. Persist the grouping only on an actual scene edit. */
export function scenesOf(p:Project):Scene[]{
  const layers=layersOf(p).filter((l):l is MediaLayer=>l.kind==='media'),cards=cardsOf(p);
  let scenes=p.board?.scenes;
  if(!scenes){
    scenes=cards.filter(c=>c.kind==='group').map((g,i)=>{
      const members=g.layerId?cards.filter(c=>c.layerId===g.layerId):groupMembers(cards,g),l=layers.find(l=>l.id===g.layerId);
      const isTake=(c:typeof members[number])=>c.kind==='asset'&&(c.role==='asset'||c.role==='motion'&&assetOf(p,c.assetId||'')?.kind==='video');
      const refs=unique(members.filter(c=>c.kind==='asset'&&!isTake(c)).map(c=>c.assetId));
      return {id:g.id,name:g.title.replace(/^\d+\s*\/\s*/,''),x:(i%2)*310,y:Math.floor(i/2)*420,
        clips:g.layerId?[g.layerId]:[],takes:unique([...members.filter(isTake).map(c=>c.assetId),l?.assetId,...l?.takes||[]]),refs,
        roles:Object.fromEntries(members.filter(c=>c.assetId).map(c=>[c.assetId!,c.role])),
        notes:members.filter(c=>c.kind==='note'&&c.text).map(c=>c.text).join('\n\n'),generation:l?.generation};
    });
    for(const l of layers){
      if(scenes.some(s=>s.clips.includes(l.id)))continue;
      const related=scenes.find(s=>s.takes.includes(l.assetId)||l.takes?.some(id=>s.takes.includes(id))||assetOf(p,l.assetId)?.source?.layerId&&s.clips.includes(String(assetOf(p,l.assetId)?.source?.layerId)));
      if(related){related.clips.push(l.id);continue;}
      const i=scenes.length;
      scenes.push({id:`scene-${l.id}`,name:l.name||assetOf(p,l.assetId)?.name||`Scene ${i+1}`,x:(i%2)*310,y:Math.floor(i/2)*420,
        clips:[l.id],takes:unique([l.assetId,...l.takes||[]]),refs:[],generation:l.generation});
    }
  }
  const expanded=scenes.map(s=>{
    // Split/duplicated clips inherit their scene when they have not been explicitly assigned elsewhere.
    const clips=unique([...s.clips,...layers.filter(l=>!scenes.some(x=>x.clips.includes(l.id))&&scenes.find(x=>assetOf(p,l.assetId)?.source?.sceneId===x.id||x.takes.includes(l.assetId)||layers.some(origin=>x.clips.includes(origin.id)&&origin.assetId===l.assetId))?.id===s.id).map(l=>l.id)]);
    const own=layers.filter(l=>clips.includes(l.id));
    const takes=unique([...s.takes,...own.flatMap(l=>[l.assetId,...l.takes||[]]),...(p.assets||[]).filter(a=>a.source?.sceneId===s.id||s.clips.includes(String(a.source?.layerId))).map(a=>a.id)]).filter(id=>!!assetOf(p,id));
    const refs=unique([...s.refs,...Object.values(s.generation?.workflows||{}).flatMap(d=>Object.values(d.sources||{})).filter(id=>!id.startsWith('@'))]).filter(id=>!!assetOf(p,id));
    return {...s,clips,takes,refs};
  });
  if(!p.board?.scenes){let y=0;for(let i=0;i<expanded.length;i+=2){const row=expanded.slice(i,i+2);row.forEach((s,j)=>{s.x=j*310;s.y=y;});y+=Math.max(...row.map(sceneHeight))+64;}}
  return expanded;
}
export function setScenes(p:Project,scenes:Scene[]):Project{return {...p,board:{...p.board,cards:cardsOf(p),scenes}};}
export function patchScene(p:Project,id:string,patch:Partial<Scene>):Project{
  return setScenes(p,scenesOf(p).map(s=>s.id===id?{...s,...patch,id:s.id}:s));
}
export function setSceneGeneration(p:Project,id:string,workflowId:string,patch:WorkflowDraft={}):Project{
  const s=scenesOf(p).find(s=>s.id===id);if(!s)return p;
  return patchScene(p,id,{generation:{...s.generation,workflowId,workflows:{...s.generation?.workflows,
    [workflowId]:{...s.generation?.workflows?.[workflowId],...patch}}}});
}
export function attachSceneClip(p:Project,sceneId:string,clipId:string,assetId:string):Project{
  const scenes=scenesOf(p),s=scenes.find(s=>s.id===sceneId);if(!s)return p;
  return setScenes(p,scenes.map(x=>x.id===s.id?{...x,clips:unique([...x.clips,clipId]),takes:unique([...x.takes,assetId])}:x));
}
export function newScene(p:Project):Scene{
  const scenes=scenesOf(p);let n=scenes.length+1;while(scenes.some(s=>s.name===`Scene ${n}`))n++;
  return {id:`scene-${crypto.randomUUID()}`,name:`Scene ${n}`,x:scenes.length?Math.max(...scenes.map(s=>s.x))+310:0,y:0,clips:[],takes:[],refs:[]};
}
