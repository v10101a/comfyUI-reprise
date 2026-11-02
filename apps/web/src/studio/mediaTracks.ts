import type {MediaLayer,SceneLayer,Project} from '../types';

export type MediaTrack={row:number;clips:MediaLayer[]};
const overlaps=(a:MediaLayer,b:MediaLayer)=>a.start<b.start+b.out-b.in-1e-6&&b.start<a.start+a.out-a.in-1e-6;

/** Share rows across cuts; overlapping clips retain the composition's top-to-bottom order.
 * Longest overlap chains give the fewest rows compatible with that order. Held rows keep a
 * pointer-captured clip mounted in the same row until a drag/trim ends. No project edits. */
export function packMediaTracks(layers:SceneLayer[]|null|undefined,held?:Map<string,number>):MediaTrack[]{
  const media=[...(layers||[])].reverse().filter((l):l is MediaLayer=>l.kind==='media');
  const placed:{layer:MediaLayer;row:number}[]=[];
  for(const layer of media){
    let row=held?.get(layer.id)??0;
    if(!held?.has(layer.id))for(const higher of placed)if(overlaps(layer,higher.layer))row=Math.max(row,higher.row+1);
    placed.push({layer,row});
  }
  const rows:MediaTrack[]=[];
  for(const {layer,row} of placed){while(rows.length<=row)rows.push({row:rows.length,clips:[]});rows[row].clips.push(layer);}
  for(const row of rows)row.clips.sort((a,b)=>a.start-b.start||a.id.localeCompare(b.id));
  return rows;
}

/** Move only this clip in the authored display stack. Rows are a view, never a stored track assignment. */
export function reorderMedia(p:Project,id:string,targets:string[],where:'above'|'below'):Project{
  const layers=p.layers||[],moving=layers.find(l=>l.id===id&&l.kind==='media');if(!moving)return p;
  const rest=layers.filter(l=>l.id!==id),indices=rest.flatMap((l,i)=>l.kind==='media'&&targets.includes(l.id)?[i]:[]);
  if(!indices.length)return p;
  const at=where==='above'?Math.max(...indices)+1:Math.min(...indices);
  const next=[...rest.slice(0,at),moving,...rest.slice(at)];
  return next.every((l,i)=>l===layers[i])?p:{...p,layers:next};
}

export function stepMediaOrder(p:Project,id:string,direction:'above'|'below'):Project{
  const media=(p.layers||[]).filter(l=>l.kind==='media'),i=media.findIndex(l=>l.id===id);
  const other=media[i+(direction==='above'?1:-1)];return i<0||!other?p:reorderMedia(p,id,[other.id],direction);
}
