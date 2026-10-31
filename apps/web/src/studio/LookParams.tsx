// Look params + footage grade, under the look row. Params write project.look.overrides (looks.ts LOOK_PARAMS);
// the grade is project.grade (independent of the look). Groups are data: append a group to PARAM_GROUPS to add controls.
import type {Project} from '../types';
import type {GradeId} from '../types';
import {LOOK_PARAMS,GRADES,FONT_FAMILIES,lookOf,lookParam,setLookParam,clearLookOverrides,gradeRefOf,setGrade,setGradeAmount,type LookParamKey,type LookParam} from '../looks';

export type ParamGroup={id:string;keys:LookParamKey[]};
/** Rendered in order; each group is one row/grid. To add a group (e.g. Fields), add its keys to LOOK_PARAMS and a group here. */
export const PARAM_GROUPS:ParamGroup[]=[
  {id:'colour',keys:['ink','accent','card']},
  {id:'type',keys:['font','body','case','layout']},
  {id:'amount',keys:['scale','motion','glow','flicker','drips','light','outline','halo','soft']},
  {id:'flags',keys:['cards','tubes','scroll','hooks']},
  {id:'fields',keys:['flow','voice']},
];
const BY_KEY=Object.fromEntries(LOOK_PARAMS.map(p=>[p.key,p])) as Record<LookParamKey,LookParam>;
const fmt=(v:number)=>v.toFixed(2).replace(/\.?0+$/,'')||'0';

export function ParamControl({param,value,onChange}:{param:LookParam;value:string|number|boolean;onChange:(v:string|number|boolean)=>void}){
  const {label,kind}=param;
  if(kind==='color')return <label className="lp-color" title={label}><input type="color" aria-label={label} value={String(value)} onChange={e=>onChange(e.target.value)}/><span>{label}</span></label>;
  if(kind==='font'||kind==='select'){const opts=kind==='font'?FONT_FAMILIES:param.options||[];
    return <label className="lp-select"><span>{label}</span><select aria-label={label} value={String(value)} onChange={e=>onChange(e.target.value)}>{opts.map(o=><option key={o} value={o}>{o}</option>)}</select></label>;}
  if(kind==='toggle')return <label className="check lp-toggle"><input type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/> {label}</label>;
  return <label className="lp-range"><span>{label}</span><input type="range" aria-label={label} min={param.min} max={param.max} step={param.step} value={Number(value)} onChange={e=>onChange(Number(e.target.value))}/><b>{fmt(Number(value))}</b></label>;
}

export function LookParams({project,edit}:{project:Project;edit:(f:(p:Project)=>Project)=>void}){
  const look=lookOf(project);const g=gradeRefOf(project);const gid=g?.id||'none';
  return <div className="look-params">
    <div className="lp-grade">
      <label className="lp-select"><span>Grade</span><select aria-label="Grade" value={gid} onChange={e=>edit(p=>setGrade(p,e.target.value as GradeId))}>{GRADES.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      {gid!=='none'&&<label className="lp-range"><span>Amount</span><input type="range" aria-label="Grade amount" min={0} max={1} step={.05} value={g?.amount??1} onChange={e=>{const v=Number(e.target.value);edit(p=>setGradeAmount(p,v));}}/><b>{fmt(g?.amount??1)}</b></label>}
    </div>
    {look&&<details className="lp-details">
      <summary>Adjust{project.look?.overrides&&Object.keys(project.look.overrides).length?<button className="lp-reset" onClick={e=>{e.preventDefault();edit(clearLookOverrides);}} title="back to the preset">Reset</button>:null}</summary>
      {PARAM_GROUPS.map(gr=><div key={gr.id} className={`lp-group lp-${gr.id}`}>
        {gr.keys.filter(k=>BY_KEY[k]&&!(k==='card'&&!look.card)&&!(k==='drips'&&look.wall!=='spray')&&!(k==='light'&&look.finish!=='neon')).map(k=><ParamControl key={k} param={BY_KEY[k]} value={lookParam(look,k)} onChange={v=>edit(p=>setLookParam(p,k,v))}/>)}
      </div>)}
    </details>}
  </div>;
}
