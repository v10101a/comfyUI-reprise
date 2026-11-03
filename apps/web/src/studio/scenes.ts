import type {LayerGeneration,MediaLayer,Project,WorkflowDraft} from '../types';
import {assetOf,layersOf} from '../layers';
import {cardsOf,groupMembers,type BoardRole} from './board';

/** Scenes organise sources and recipes; clips remain the authored timeline. */
export type Scene={id:string;name:string;x:number;y:number;clips:string[];takes:string[];refs:string[];
  roles?:Record<string,BoardRole>;notes?:string;generation?:LayerGeneration;collapsed?:boolean;
  /** Retired IDs still receive in-flight generation results after a merge. */
  mergedIds?:string[];recipes?:SceneRecipe[];recipeId?:string;excludedTakes?:string[];
  /** Edited generation drafts belong to the selected take, independently of the scene recipe. */
  takeGenerations?:Record<string,LayerGeneration>};
export type SceneRecipe={id:string;name:string;generation:LayerGeneration};
const unique=(ids:(string|undefined)[])=>[...new Set(ids.filter((id):id is string=>!!id))];
export const sceneHeight=(s:Scene)=>s.collapsed?64:Math.max(160,24+(s.refs.length?64:0)+Math.ceil(Math.min(s.takes.length,6)/2)*102+(s.takes.length>6?32:0));
export const sceneClips=(p:Project,s:Scene)=>layersOf(p).filter((l):l is MediaLayer=>l.kind==='media'&&s.clips.includes(l.id));
export const ownsSceneId=(s:Scene,id:unknown)=>typeof id==='string'&&(s.id===id||!!s.mergedIds?.includes(id));
export const sceneForId=(p:Project,id:string)=>scenesOf(p).find(s=>ownsSceneId(s,id));

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
  const assigned=(id:string)=>scenes.find(s=>ownsSceneId(s,p.board?.takeAssignments?.[id]));
  const sourceScene=(id:string)=>scenes.find(s=>ownsSceneId(s,assetOf(p,id)?.source?.sceneId));
  const expanded=scenes.map(s=>{
    // Split/duplicated clips inherit their scene when they have not been explicitly assigned elsewhere.
    const clips=unique([...s.clips,...layers.filter(l=>!scenes.some(x=>x.clips.includes(l.id))&&(assigned(l.assetId)||sourceScene(l.assetId)||scenes.find(x=>x.takes.includes(l.assetId)||layers.some(origin=>x.clips.includes(origin.id)&&origin.assetId===l.assetId)))?.id===s.id).map(l=>l.id)]);
    const own=layers.filter(l=>clips.includes(l.id));
    const takes=unique([...s.takes,...own.flatMap(l=>[l.assetId,...l.takes||[]]),...(p.assets||[]).filter(a=>{
      const origin=sourceScene(a.id);return origin?origin.id===s.id:s.clips.includes(String(a.source?.layerId));
    }).map(a=>a.id)]).filter(id=>!!assetOf(p,id)&&!s.excludedTakes?.includes(id)&&(!assigned(id)||assigned(id)?.id===s.id));
    const refs=unique([...s.refs,...Object.values(s.generation?.workflows||{}).flatMap(d=>Object.values(d.sources||{})).filter(id=>!id.startsWith('@'))]).filter(id=>!!assetOf(p,id));
    return {...s,clips,takes,refs};
  });
  if(!p.board?.scenes){let y=0;for(let i=0;i<expanded.length;i+=2){const row=expanded.slice(i,i+2);row.forEach((s,j)=>{s.x=j*310;s.y=y;});y+=Math.max(...row.map(sceneHeight))+64;}}
  return expanded;
}
export function setScenes(p:Project,scenes:Scene[]):Project{return {...p,board:{...p.board,cards:cardsOf(p),scenes}};}
export function patchScene(p:Project,id:string,patch:Partial<Scene>):Project{
  const scenes=scenesOf(p),s=scenes.find(s=>ownsSceneId(s,id));if(!s)return p;
  const next={...s,...patch,id:s.id};
  if(patch.generation&&next.recipes)next.recipes=next.recipes.map(r=>r.id===next.recipeId?{...r,generation:patch.generation!}:r);
  return setScenes(p,scenes.map(x=>x.id===s.id?next:x));
}
export function setSceneGeneration(p:Project,id:string,workflowId:string,patch:WorkflowDraft={},recipeId?:string):Project{
  const s=sceneForId(p,id);if(!s)return p;
  const recipe=s.recipes?.find(r=>r.id===(recipeId||(id!==s.id?id:s.recipeId))),base=recipe?.generation||s.generation;
  const generation={...base,workflowId,workflows:{...base?.workflows,[workflowId]:{...base?.workflows?.[workflowId],...patch}}};
  return recipe&&recipe.id!==s.recipeId?patchScene(p,s.id,{recipes:s.recipes!.map(r=>r.id===recipe.id?{...r,generation}:r)}):patchScene(p,s.id,{generation});
}
export function attachSceneClip(p:Project,sceneId:string,clipId:string,assetId:string):Project{
  const scenes=scenesOf(p),s=scenes.find(s=>ownsSceneId(s,sceneId));if(!s)return p;
  return setScenes(p,scenes.map(x=>x.id===s.id?{...x,clips:unique([...x.clips,clipId]),takes:unique([...x.takes,assetId])}:{...x,clips:x.clips.filter(id=>id!==clipId)}));
}

/** One grouping operation; media, clips, timings and original generation provenance stay intact. */
export function combineScenes(p:Project,targetId:string,ids:string[],name:string):Project{
  const scenes=scenesOf(p),target=scenes.find(s=>s.id===targetId);if(!target)return p;
  const sources=scenes.filter(s=>s.id!==targetId&&ids.includes(s.id));if(!sources.length)return p;
  const all=[target,...sources],removed=new Set(sources.map(s=>s.id));
  const recipes=all.flatMap(s=>s.recipes?.length?s.recipes.map(r=>r.id===s.recipeId?{...r,generation:s.generation||r.generation}:r):[{id:s.id,name:s.name,generation:s.generation||{}}]);
  const merged:Scene={...target,name:name.trim()||target.name,collapsed:false,
    mergedIds:unique(all.flatMap(s=>[s.id,...s.mergedIds||[]])).filter(id=>id!==target.id),
    clips:unique(all.flatMap(s=>s.clips)),takes:unique(all.flatMap(s=>s.takes)),refs:unique(all.flatMap(s=>s.refs)),
    excludedTakes:unique(all.flatMap(s=>s.excludedTakes||[])).filter(id=>!all.some(s=>s.takes.includes(id))),
    roles:Object.assign({},...all.slice().reverse().map(s=>s.roles)),
    takeGenerations:Object.assign({},...all.slice().reverse().map(s=>s.takeGenerations)),
    notes:[target.notes,...sources.filter(s=>s.notes).map(s=>`${s.name}\n${s.notes}`)].filter(Boolean).join('\n\n'),
    recipes,recipeId:target.recipeId||target.id,generation:target.generation||{}};
  const q=setScenes(p,scenes.filter(s=>!removed.has(s.id)).map(s=>s.id===targetId?merged:s));
  if(p.board?.takeAssignments)q.board!.takeAssignments=Object.fromEntries(Object.entries(p.board.takeAssignments).map(([aid,sid])=>[aid,ownsSceneId(merged,sid)?targetId:sid]));
  return q;
}

export function selectSceneRecipe(p:Project,id:string,recipeId:string):Project{
  const s=sceneForId(p,id),recipe=s?.recipes?.find(r=>r.id===recipeId);if(!s||!recipe||s.recipeId===recipeId)return p;
  return patchScene(p,s.id,{recipeId,generation:structuredClone(recipe.generation)});
}

/** Move a take and its existing clip associations, never the clips themselves or a shared reference. */
export function moveSceneTake(p:Project,assetId:string,targetId:string):Project{
  const scenes=scenesOf(p),target=scenes.find(s=>s.id===targetId);if(!target||!assetOf(p,assetId))return p;
  const generation=scenes.find(s=>s.takes.includes(assetId)&&s.takeGenerations?.[assetId])?.takeGenerations?.[assetId];
  const clips=layersOf(p).filter((l):l is MediaLayer=>l.kind==='media'&&l.assetId===assetId).map(l=>l.id);
  const q=setScenes(p,scenes.map(s=>s.id===targetId?{...s,takes:unique([...s.takes,assetId]),clips:unique([...s.clips,...clips]),excludedTakes:s.excludedTakes?.filter(id=>id!==assetId),
      ...(generation?{takeGenerations:{...s.takeGenerations,[assetId]:generation}}:{})}:
    {...s,takes:s.takes.filter(id=>id!==assetId),clips:s.clips.filter(id=>!clips.includes(id)),
      ...(s.takeGenerations?.[assetId]?{takeGenerations:Object.fromEntries(Object.entries(s.takeGenerations).filter(([id])=>id!==assetId))}:{})}));
  q.board!.takeAssignments={...p.board?.takeAssignments,[assetId]:targetId};return q;
}

/** Remove the board item without deleting the source or any use of it in the film. */
export function removeSceneTake(p:Project,sceneId:string,assetId:string):Project{
  const s=sceneForId(p,sceneId);if(!s||!s.takes.includes(assetId))return p;
  return patchScene(p,s.id,{takes:s.takes.filter(id=>id!==assetId),excludedTakes:unique([...s.excludedTakes||[],assetId])});
}

export function placeSceneInList(p:Project,id:string,targetId:string,after:boolean):Project{
  const scenes=scenesOf(p),s=scenes.find(s=>s.id===id);if(!s||id===targetId||!scenes.some(s=>s.id===targetId))return p;
  const next=scenes.filter(s=>s.id!==id),at=next.findIndex(s=>s.id===targetId)+(after?1:0);next.splice(at,0,s);return setScenes(p,next);
}

export function newScene(p:Project):Scene{
  const scenes=scenesOf(p);let n=scenes.length+1;while(scenes.some(s=>s.name===`Scene ${n}`))n++;
  return {id:`scene-${crypto.randomUUID()}`,name:`Scene ${n}`,x:scenes.length?Math.max(...scenes.map(s=>s.x))+310:0,y:0,clips:[],takes:[],refs:[]};
}
