// Look-specific properties in the existing inspector. Footage grade stays independent of the text look.
import type {CSSProperties} from 'react';
import type {Project} from '../types';
import type {GradeId} from '../types';
import {GRADES,FONT_FAMILIES,lookOf,lookParam,lookParamApplies,setLookParam,setLookOverrides,clearLookOverrides,gradeRefOf,setGrade,setGradeAmount,colorParts,colorWith,type LookParam} from '../looks';
import {lookControlGroups,lookControlParam,lookName} from './lookControls';
const fmt=(v:number)=>v.toFixed(2).replace(/\.?0+$/,'')||'0';
/** Dot size is a fraction of min(w,h) that the renderer rounds to whole pixels: step one pixel and show pixels. */
const dotPx=(p:Project,param:LookParam)=>{const m=Math.min(p.width,p.height);const px=(v:number)=>Math.max(2,Math.round(v*m));
  return {param:{...param,min:2/m,max:Math.max(3,Math.round(.02*m))/m,step:1/m},show:(v:number)=>`${px(v)} px`};};

export function ParamControl({param,value,onChange,show=fmt}:{param:LookParam;value:string|number|boolean;onChange:(v:string|number|boolean)=>void;show?:(v:number)=>string}){
  const {label,kind,hint}=param;
  if(kind==='color')return <ColorControl label={label} hint={hint} value={String(value)} onChange={onChange}/>;
  if(kind==='font'||kind==='select'){const opts=kind==='font'?FONT_FAMILIES:param.options||[];
    return <label className="lp-select" title={hint}><span>{label}</span><select aria-label={label} value={String(value)} onChange={e=>onChange(e.target.value)}>{!opts.includes(String(value))&&<option value={String(value)} disabled>{param.optionLabels?.[String(value)]||String(value)}</option>}{opts.map(o=><option key={o} value={o}>{param.optionLabels?.[o]||o}</option>)}</select></label>;}
  if(kind==='toggle')return <label className="check lp-toggle" title={hint}><input type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/> {label}</label>;
  return <label className="lp-range" title={hint}><span>{label}</span><input type="range" aria-label={label} min={param.min} max={param.max} step={param.step} value={Number(value)} onChange={e=>onChange(Number(e.target.value))}/><b>{show(Number(value))}</b></label>;
}

/** Colour + opacity. The swatch shows the translucent result over a checker; the slider writes the alpha byte
 *  (#rrggbbaa, looks.ts colorWith), so a box or card can go glassy or vanish. */
export function ColorControl({label,hint,value,onChange}:{label:string;hint?:string;value:string;onChange:(v:string)=>void}){
  const {rgb,alpha}=colorParts(value);const a=Math.round(alpha*100)/100;
  return <div className="lp-color" title={hint||label}>
    <span className="lp-sw" style={{'--sw':value} as CSSProperties}><input type="color" aria-label={label} value={rgb} onChange={e=>onChange(colorWith(e.target.value,alpha))}/></span>
    <span className="lp-cl">{label}</span>
    <input type="range" className="lp-alpha" aria-label={`${label} opacity`} title={`Opacity ${Math.round(a*100)}%`} min={0} max={1} step={.01} value={a} onChange={e=>onChange(colorWith(rgb,Number(e.target.value)))}/>
  </div>;
}

export function LookParams({project,edit,showGrade=true}:{project:Project;edit:(f:(p:Project)=>Project)=>void;showGrade?:boolean}){
  const look=lookOf(project);const g=gradeRefOf(project);const gid=g?.id||'none';
  return <div className="look-params">
    {showGrade&&<div className="lp-grade">
      <label className="lp-select"><span>Footage grade</span><select aria-label="Grade" value={gid} onChange={e=>edit(p=>setGrade(p,e.target.value as GradeId))}>{GRADES.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      {gid!=='none'&&<label className="lp-range"><span>Amount</span><input type="range" aria-label="Grade amount" min={0} max={1} step={.05} value={g?.amount??1} onChange={e=>{const v=Number(e.target.value);edit(p=>setGradeAmount(p,v));}}/><b>{fmt(g?.amount??1)}</b></label>}
    </div>}
    {look&&<details className="lp-details">
      <summary title="Defaults for text clips using this look">{lookName(look)} settings{project.look?.overrides&&Object.keys(project.look.overrides).length?<button className="lp-reset" onClick={e=>{e.preventDefault();edit(clearLookOverrides);}} title="back to the preset">Reset</button>:null}</summary>
      {lookControlGroups(look,'look').map(gr=>({...gr,keys:gr.keys.filter(k=>lookParamApplies(project,look,k))})).filter(gr=>gr.keys.length).map(gr=><div key={gr.id} className={`lp-group lp-${gr.id}`}>
        {gr.id==='anim'&&<span className="lp-timing-label" title="Project defaults. A text clip with its own timing overrides these values.">Default timing</span>}
        {gr.keys.map(k=>k==='dot'?<ParamControl key={k} {...dotPx(project,lookControlParam(look,k))} value={lookParam(look,k)} onChange={v=>edit(p=>setLookParam(p,k,v))}/>
          :<ParamControl key={k} param={lookControlParam(look,k)} value={lookParam(look,k)} onChange={v=>edit(p=>setLookParam(p,k,v))}/>)}
        {gr.id==='fields'&&lookParamApplies(project,look,'voice')&&<div className="seg mini lp-source" role="radiogroup" aria-label="Audio source">{(['bass','vocal'] as const).map(src=>
          <button key={src} role="radio" aria-checked={(look.fields?.source??'bass')===src} className={(look.fields?.source??'bass')===src?'active':''}
            onClick={()=>edit(p=>{const l=lookOf(p);return l?setLookOverrides(p,{fields:{...l.fields,source:src}}):p;})}>{src==='bass'?'Bass':'Vocal'}</button>)}</div>}
      </div>)}
    </details>}
  </div>;
}
