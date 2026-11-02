import type {Project} from '../types';
import {setGeneration,visualLayer} from './takes';
import type {Scene} from './scenes';

export const BOARD_ROLES=['reference','character','wardrobe','setting','lighting','motion','asset'] as const;
export type BoardRole=typeof BOARD_ROLES[number];
export type BoardCard={id:string;kind:'asset'|'note'|'group';x:number;y:number;w:number;h:number;title:string;role:BoardRole;assetId?:string;layerId?:string;text?:string;url?:string};
export type BoardView={x:number;y:number;zoom:number};
export type ReferenceBoardState={cards:BoardCard[];view?:BoardView;scenes?:Scene[];sceneView?:BoardView};
export const DEFAULT_VIEW:BoardView={x:40,y:40,zoom:1};
export const cardId=()=>`card_${crypto.randomUUID().slice(0,12)}`;
export const cardsOf=(p:Project)=>p.board?.cards||[];

export function addCards(p:Project,cards:BoardCard[]):Project{
  return {...p,board:{...p.board,cards:[...cardsOf(p),...cards]}};
}
export function updateCard(p:Project,id:string,patch:Partial<BoardCard>):Project{
  return {...p,board:{...p.board,cards:cardsOf(p).map(c=>c.id===id?{...c,...patch,id:c.id}:c)}};
}
/** Removing a reference from the board never removes its media, takes or workflow assignments. */
export function removeCard(p:Project,id:string):Project{
  return {...p,board:{...p.board,cards:cardsOf(p).filter(c=>c.id!==id)}};
}
export function groupMembers(cards:BoardCard[],group:BoardCard):BoardCard[]{
  return cards.filter(c=>c.id===group.id||(c.x>=group.x&&c.y>=group.y&&c.x+c.w<=group.x+group.w&&c.y+c.h<=group.y+group.h));
}
/** Gesture coordinates come from the initial snapshot, so moving a group never compounds its delta. */
export function moveCards(p:Project,before:BoardCard[],dx:number,dy:number):Project{
  const byId=new Map(before.map(c=>[c.id,c]));return {...p,board:{...p.board,cards:cardsOf(p).map(c=>{
    const old=byId.get(c.id);return old?{...c,x:Math.round(old.x+dx),y:Math.round(old.y+dy)}:c;})}};
}
export function boardPoint(client:{x:number;y:number},view:BoardView){return {x:(client.x-view.x)/view.zoom,y:(client.y-view.y)/view.zoom};}
export function zoomAt(view:BoardView,point:{x:number;y:number},factor:number):BoardView{
  const z=Math.max(.25,Math.min(2,view.zoom*factor));const world=boardPoint(point,view);
  return {x:point.x-world.x*z,y:point.y-world.y*z,zoom:z};
}
export function fitBoard(cards:BoardCard[],width:number,height:number):BoardView{
  if(!cards.length)return DEFAULT_VIEW;const left=Math.min(...cards.map(c=>c.x)),top=Math.min(...cards.map(c=>c.y));
  const w=Math.max(...cards.map(c=>c.x+c.w))-left,h=Math.max(...cards.map(c=>c.y+c.h))-top;
  const zoom=Math.max(.25,Math.min(1.2,(width-80)/Math.max(1,w),(height-80)/Math.max(1,h)));
  return {x:(width-w*zoom)/2-left*zoom,y:(height-h*zoom)/2-top*zoom,zoom};
}
export function assignReference(p:Project,layerId:string,workflowId:string,inputKey:string,assetId:string):Project{
  const layer=visualLayer(p,layerId);if(!layer||!p.assets?.some(a=>a.id===assetId))return p;
  const sources=layer.generation?.workflows?.[workflowId]?.sources||{};
  return setGeneration(p,layerId,workflowId,{sources:{...sources,[inputKey]:assetId}});
}
export function appendDirection(p:Project,layerId:string,workflowId:string,inputKey:string,text:string,fallback=''):Project{
  const l=visualLayer(p,layerId),note=text.trim();if(!l||!note)return p;
  const inputs=l.generation?.workflows?.[workflowId]?.inputs||{},old=String(inputs[inputKey]??fallback).trim();
  if(old.split('\n\n').includes(note))return p;
  return setGeneration(p,layerId,workflowId,{inputs:{...inputs,[inputKey]:[old,note].filter(Boolean).join('\n\n')}});
}
