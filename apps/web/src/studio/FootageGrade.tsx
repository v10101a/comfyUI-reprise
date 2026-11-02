import type {Project,GradeId} from '../types';
import {GRADES,gradeRefOf,setGrade,setGradeAmount} from '../looks';

export function FootageGrade({project,edit}:{project:Project;edit:(f:(p:Project)=>Project)=>void}){
  const grade=gradeRefOf(project),id=grade?.id||'none';
  return <section className="panel-sec" aria-label="Footage grading"><div className="sec-head"><span>Footage grade</span></div><label className="lp-select"><span>Project</span><select aria-label="Footage grade" value={id} onChange={e=>edit(p=>setGrade(p,e.target.value as GradeId))}>{GRADES.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
    {id!=='none'&&<label className="lp-range"><span>Amount</span><input type="range" aria-label="Footage grade amount" min={0} max={1} step={.05} value={grade?.amount??1} onChange={e=>edit(p=>setGradeAmount(p,Number(e.target.value)))}/><b>{Math.round((grade?.amount??1)*100)}%</b></label>}
  </section>;
}
