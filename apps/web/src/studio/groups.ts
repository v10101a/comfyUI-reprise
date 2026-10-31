// Figma-style groups: lines of the same kind (captions, hooks, behind, wall, HUD, in-world) selected and styled together.
import type {Project,LineMeta} from '../types';
import type {LineInfo} from './Timeline';

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
