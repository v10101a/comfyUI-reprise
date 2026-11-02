import {useEffect,useRef} from 'react';
import type {Project,HudPointer} from '../types';
import {hudPointer,setHudPointer} from '../hud';
import {lineLookOf,isSubtitleLine} from '../looks';
import {ColorControl} from './LookParams';
import {shared} from './groups';

export function HudControls({project:p,lineIds,edit,checkpoint}:{project:Project;lineIds:string[];edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void}){
  const ids=lineIds.filter(id=>p.words.some(w=>w.lineId===id&&(w.placement==='anchor'||w.preset==='hud'||w.placement!=='inworld'&&!isSubtitleLine(p,id)&&lineLookOf(p,id)?.layout==='hud')));
  if(!ids.length)return null;
  const values=ids.map(id=>hudPointer(p,id));
  const change=(patch:Parameters<typeof setHudPointer>[2])=>{checkpoint();edit(q=>setHudPointer(q,ids,patch));};
  return <div className="hud-controls" aria-label="HUD pointer settings">
    <div className="clip-heading"><span>HUD pointer</span><button disabled={!values.some(v=>v.point)} onClick={()=>change({point:null})}>Reset point</button></div>
    <p className="clip-hint">Select a clip, then drag its target on the video. It stays relative to the moving head.</p>
    {([{key:'dot',label:'Dot',color:'dotColor',colorLabel:'Dot color'},{key:'connector',label:'Connector line',color:'connectorColor',colorLabel:'Connector color'}] as const).map(({key,label,color,colorLabel})=>{
      const shown=shared(values.map(v=>v[key]))??true,c=shared(values.map(v=>v[color]));const explicit=ids.some(id=>p.lineMeta?.[id]?.hud?.[color]);
      return <div className="hud-pointer-part" key={key}>
        <PointerToggle label={label} value={shown} onChange={v=>change({[key]:v})}/>
        <ColorControl label={colorLabel} value={c==='mixed'?values[0][color]:c??values[0][color]} onChange={v=>edit(q=>setHudPointer(q,ids,{[color]:v} as Partial<HudPointer>))}/>
        {(c==='mixed'||explicit)&&<div className="clip-source">{c==='mixed'&&<span>Mixed · </span>}{explicit&&<button onClick={()=>change({[color]:null})} aria-label={`Reset ${colorLabel}`}>Use look color</button>}</div>}
      </div>;})}
  </div>;
}
function PointerToggle({label,value,onChange}:{label:string;value:boolean|'mixed';onChange:(v:boolean)=>void}){
  const ref=useRef<HTMLInputElement>(null);useEffect(()=>{if(ref.current)ref.current.indeterminate=value==='mixed';},[value]);
  return <label className="check"><input ref={ref} type="checkbox" aria-label={label} checked={value===true} onChange={e=>onChange(e.target.checked)}/>{label}{value==='mixed'&&<em className="mixed-tag">Mixed</em>}</label>;
}
