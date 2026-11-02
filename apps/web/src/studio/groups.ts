// Figma-style groups: lines of the same kind (captions, hooks, behind, wall, HUD, in-world) selected and styled together.
import type {Project,LineMeta,Placement} from '../types';
import type {LineInfo} from './Timeline';
import {lineLookOf,setLineParam} from '../looks';

/** Explicit placement overrides a HUD layout too, so Caption/Behind do what their controls say. */
export function setTextRole(p:Project,lineIds:string[],placement:Placement):Project{
  const ids=new Set(lineIds);let q=p;
  if(placement!=='anchor')q=setLineParam(q,lineIds.filter(id=>lineLookOf(q,id)?.layout==='hud'),'layout','line');
  return {...q,words:q.words.map(w=>!ids.has(w.lineId)?w:{...w,placement,
    ...(placement==='anchor'?{preset:'hud' as const,anchor:w.anchor||{trackId:'person0',dx:0,dy:-.1}}:w.preset==='hud'?{preset:'pop' as const}:{}),
    ...(placement==='surface'?{surfaceId:w.surfaceId||q.surfaces?.[0]?.id}:{})})};
}

export type GroupId = 'captions'|'hooks'|'behind'|'wall'|'hud'|'inworld';
export const GROUPS:{id:GroupId;label:string}[] = [
  {id:'captions',label:'Captions'},{id:'hooks',label:'Hooks'},{id:'behind',label:'Behind'},
  {id:'wall',label:'Wall'},{id:'hud',label:'HUD'},{id:'inworld',label:'In-world'},
];
export function inGroup(l:LineInfo,g:GroupId){
  switch(g){
    case 'captions':return l.role==='caption'&&!l.hook;
    case 'hooks':return l.hook;
    case 'behind':return l.role==='behind';
    case 'wall':return l.role==='wall';
    case 'hud':return l.role==='hud'||l.role==='anchor';
    case 'inworld':return l.role==='inworld';
  }
}
export const groupLines=(lines:LineInfo[],g:GroupId)=>lines.filter(l=>inGroup(l,g)).map(l=>l.id);
/** The one group a line belongs to for timeline packing (a behind hook packs with the hooks). */
export const groupOf=(l:LineInfo):GroupId=>l.hook?'hooks':l.role==='behind'?'behind':l.role==='wall'?'wall':l.role==='hud'||l.role==='anchor'?'hud':l.role==='inworld'?'inworld':'captions';

export type Track = {group:GroupId;rows:number;lines:{line:LineInfo;row:number}[]};
/** Timeline tracks: one per group, lines packed greedily into rows, spilling to a new row only when times overlap.
 *  `prev` (lineId → row from the last pass) keeps rows stable while editing: a line stays on its row while it fits. */
export function packTracks(lines:LineInfo[],prev?:Map<string,number>,gap=.02,hold=false):Track[]{
  const out:Track[]=[];
  for(const g of GROUPS){
    const ls=lines.filter(l=>groupOf(l)===g.id).sort((a,b)=>a.start-b.start||a.id.localeCompare(b.id));if(!ls.length)continue;
    const rows:[number,number][][]=[];const fits=(r:number,l:LineInfo)=>!(rows[r]||[]).some(([a,b])=>l.start<b+gap&&a<l.end+gap);
    const put=(r:number,l:LineInfo)=>{while(rows.length<=r)rows.push([]);rows[r].push([l.start,l.end]);at.set(l.id,r);};
    const at=new Map<string,number>();
    // Keepers first (their previous row still fits), then the rest greedily in start order.
    // hold: mid-drag, every known line keeps its row even if it overlaps for a moment.
    for(const l of ls){const r=prev?.get(l.id);if(r!=null&&(hold||fits(r,l)))put(r,l);}
    for(const l of ls){if(at.has(l.id))continue;let r=0;while(!fits(r,l))r++;put(r,l);}
    // Drop rows emptied by edits, keeping order.
    const used=[...new Set(at.values())].sort((a,b)=>a-b);const remap=new Map(used.map((r,i)=>[r,i]));
    out.push({group:g.id,rows:used.length,lines:ls.map(l=>({line:l,row:remap.get(at.get(l.id)!)!}))});
  }
  return out;
}

/** Per-line colour overrides (renderer contract: lineMeta.fill / karaoke / dim win over the look; unset = look). */
export type ColorKey = 'fill'|'karaoke'|'dim';
type ColorMeta = LineMeta & Partial<Record<ColorKey,string|null>>;
export const lineColor=(p:Project,lineId:string,k:ColorKey)=>(p.lineMeta?.[lineId] as ColorMeta|undefined)?.[k]??undefined;
export function setLineColor(p:Project,lineIds:string[],k:ColorKey,v:string|null):Project{
  const all={...(p.lineMeta||{})} as Record<string,ColorMeta>;
  for(const id of lineIds){const cur={...(all[id]||{})} as Record<string,unknown>;if(v==null)delete cur[k];else cur[k]=v;
    if(Object.keys(cur).length)all[id]=cur as ColorMeta;else delete all[id];}
  return {...p,lineMeta:all as Record<string,LineMeta>};
}
/** One value for every item, 'mixed' when they differ. */
export function shared<T>(vals:T[]):T|'mixed'|undefined{
  if(!vals.length)return undefined;const a=JSON.stringify(vals[0]);return vals.every(v=>JSON.stringify(v)===a)?vals[0]:'mixed';
}
