import type {ReactNode} from 'react';
import type {Project,LookParamKey} from '../types';
import {lineLookOf,lookOf,lookParam,lookParamApplies,lineIsHook,lineIsFilled,isSubtitleLine,setLineParam,setLineMeta,clearLineAppearance} from '../looks';
import {ParamControl} from './LookParams';
import {shared} from './groups';
import {lookControlGroups,lookControlParam,lookName} from './lookControls';
import './clip-appearance.css';

type Props={project:Project;lineIds:string[];edit:(f:(p:Project)=>Project)=>void;children?:ReactNode};

/** The same parameter definitions as Look settings; only explicit overrides are persisted. */
export function ClipAppearance({project:p,lineIds,edit,children}:Props){
  const base=lookOf(p);if(!base||!lineIds.length)return null;
  const words=p.words.filter(w=>lineIds.includes(w.lineId)&&w.placement!=='inworld');if(!words.length)return null;
  if(base.motion==='marquee')return <p className="clip-hint">Type and colour use Marquee settings.</p>;
  const looks=lineIds.map(id=>lineLookOf(p,id)!);
  const allFilled=lineIds.every(id=>lineIsFilled(p,id));
  const anySet=lineIds.some(id=>{const m=p.lineMeta?.[id];return m&&(Object.keys(m.appearance||{}).length||m.fill||m.karaoke||m.dim||m.boxes!=null);});
  const clipProject={...p,words,lineMeta:{...p.lineMeta,...Object.fromEntries(lineIds.map(id=>[id,{...p.lineMeta?.[id],hook:lineIsHook(p,id)}]))}};
  const applies=(key:LookParamKey)=>{
    if(allFilled&&!['case','card','fill','cell','backing','dots','dot','gap','glow','soft'].includes(key))return false;
    if(key==='note'||key==='noteGlow')return lineIds.some(id=>p.lineMeta?.[id]?.boxes===true)||looks.some(l=>lookParamApplies(clipProject,l,key));
    if(key==='fill')return words.some(w=>w.placement!=='anchor'&&!isSubtitleLine(p,w.lineId));
    if(lineIds.every(id=>isSubtitleLine(p,id)))return key==='case';
    return looks.some(l=>lookParamApplies(clipProject,l,key));
  };
  const control=(key:LookParamKey)=>{
    let param=lookControlParam(base,key);
    if(key==='font')param={...param,label:'Font'};
    if(key==='fill')param={...param,label:'Glyph mask',hint:'Choose where this clip fills the footage with letters. Person and Background use the subject matte.'};
    if(key==='dot'){const m=Math.min(p.width,p.height);param={...param,min:2/m,max:Math.max(3,Math.round(.02*m))/m,step:1/m};}
    const values=looks.map((l,i)=>key==='font'&&!p.lineMeta?.[lineIds[i]]?.appearance?.font
      ?isSubtitleLine(p,lineIds[i])?(words.find(w=>w.lineId===lineIds[i])?.style?.fontFamily??'Space Mono')
        :l.layout==='hud'||l.layout==='stack'||lineIsFilled(p,lineIds[i])||lineIsHook(p,lineIds[i])||words.some(w=>w.lineId===lineIds[i]&&w.placement==='surface')?l.font.hero:l.font.body
      :lookParam(l,key));
    const value=shared(values),overrides=lineIds.map(id=>p.lineMeta?.[id]?.appearance?.[key]);
    const explicit=overrides.some(v=>v!==undefined),mixed=value==='mixed';
    return <div key={key} className={`clip-param ${explicit?'overridden':''}`}>
      <ParamControl param={param} value={mixed?values[0]:value??values[0]} show={key==='dot'?v=>`${Math.max(2,Math.round(v*Math.min(p.width,p.height)))} px`:undefined}
        onChange={v=>edit(q=>setLineParam(q,lineIds,key,v))}/>
      {(mixed||explicit)&&<div className="clip-source">{mixed&&<span>Mixed{explicit?' · ':''}</span>}{explicit&&<button onClick={()=>edit(q=>setLineParam(q,lineIds,key,null))} aria-label={`Reset ${param.label} to look`} title="Use the look’s value">Reset</button>}</div>}
    </div>;
  };
  const boxValues=lineIds.map(id=>p.lineMeta?.[id]?.boxes??null);const boxes=shared(boxValues);
  const glyphOn=looks.some(l=>l.fill)&&words.some(w=>w.placement!=='anchor'&&!isSubtitleLine(p,w.lineId));
  const primaryGlyph=base.id==='glyph'&&applies('fill');
  const notes=lookControlGroups(base,'look').some(g=>g.keys.includes('boxes'));
  return <div className="clip-appearance">
    <div className="clip-heading"><span>{lineIds.length>1?'Selected clips':'Clip appearance'}</span>{anySet&&<button onClick={()=>edit(q=>clearLineAppearance(q,lineIds))}>Use look</button>}</div>
    {control('font')}{children}
    {primaryGlyph&&control('fill')}{primaryGlyph&&allFilled&&control('cell')}
    {glyphOn&&!p.analysis.matte&&<p className="clip-hint">Run Subject matte to use Person or Background masking. Until then the grid covers the frame.</p>}
    <details className="fold clip-more"><summary>{lookName(base)} settings</summary>
      {notes&&!allFilled&&!lineIds.every(id=>isSubtitleLine(p,id))&&<div className="clip-param"><label className="lp-select"><span>Note boxes</span>
        <select aria-label="Clip note boxes" value={boxes==='mixed'?'mixed':boxes===null?'look':boxes?'on':'off'} onChange={e=>{const v=e.target.value;edit(q=>lineIds.reduce((a,id)=>setLineMeta(a,id,{boxes:v==='look'?null:v==='on'}),q));}}>
          {boxes==='mixed'&&<option value="mixed" disabled>Mixed</option>}<option value="look">From look</option><option value="on">Every word</option><option value="off">Off</option>
        </select></label></div>}
      {lookControlGroups(base,'clip').map(g=>({...g,keys:g.keys.filter(k=>applies(k)&&!(k==='fill'&&primaryGlyph)&&!(k==='cell'&&primaryGlyph&&allFilled))})).filter(g=>g.keys.length).map(g=><div key={g.id} className="clip-group"><h4>{g.name}</h4>{g.keys.map(control)}</div>)}
    </details>
  </div>;
}
