import type {Project,Word} from '../src/types';
import {ClipAppearance} from '../src/studio/ClipAppearance';
import {ColorRow} from '../src/studio/GroupInspector';
import {SizeSlider,ScrubNum,PRESETS,presetName,FAMILIES} from '../src/studio/LineInspector';
import {lineSizeMode,lookOf,setLineMeta} from '../src/looks';
import {setTextRole} from '../src/studio/groups';
import {HudControls} from '../src/studio/HudControls';
import {Icon} from '../src/studio/icons';

type Props={project:Project;word:Word;onSelect:(id:string)=>void;edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void;onDelete:()=>void};
export function StudyTextInspector({project:p,word,edit,checkpoint,onSelect,onDelete}:Props){
  const ws=p.words.filter(w=>w.lineId===word.lineId),first=ws[0],id=word.lineId,mode=lineSizeMode(p,id);
  const meta=p.lineMeta?.[id],size=(first.style?.fontSize??p.style.fontSize)*100;
  const change=(f:(w:Word)=>Word)=>edit(q=>({...q,words:q.words.map(w=>w.lineId===id?f(w):w)}));
  return <section className="panel-sec study-text-inspector" aria-label="Text controls">
    <div className="sec-head"><span>Text</span><button className="icon-button sec-more" aria-label="Delete text clip" title="Delete text clip" onClick={onDelete}><Icon name="trash" size={14}/></button></div>
    <div className="line-words">{ws.map(w=><button key={w.id} className={w.id===word.id?'selected':''} onClick={()=>onSelect(w.id)}>{w.text}</button>)}</div>
    <label className="fld"><input className="word-input" aria-label="Word text" value={word.text} onFocus={checkpoint} onChange={e=>{const text=e.target.value;edit(q=>({...q,words:q.words.map(w=>w.id===word.id?{...w,text}:w)}));}}/></label>
    <div className="fld"><div className="seg" role="group" aria-label="Text placement">{(['overlay','behind','anchor'] as const).map((role,i)=><button key={role} className={first.placement===role?'active':''} aria-pressed={first.placement===role} onClick={()=>{checkpoint();edit(q=>setTextRole(q,[id],role));}}>{['Front','Behind','HUD'][i]}</button>)}</div></div>
    {mode!=='none'&&<SizeSlider value={mode==='scale'?meta?.scale??1:size} min={mode==='scale'?.2:1} max={mode==='scale'?4:40} step={.01} fmt={v=>mode==='scale'?`×${v.toFixed(2)}`:`${v.toFixed(1)}%`} onStart={checkpoint} onChange={v=>mode==='scale'?edit(q=>setLineMeta(q,id,{scale:v})):change(w=>({...w,style:{...w.style,fontSize:(w.style?.fontSize??p.style.fontSize)*v/size}}))}/>}
    <div className="study-text-appearance" onPointerDownCapture={e=>{if((e.target as Element).closest('input,select,button'))checkpoint();}} onKeyDownCapture={e=>{if(!['Tab','Shift','Meta','Control'].includes(e.key))checkpoint();}}>
      {lookOf(p)?<ClipAppearance project={p} lineIds={[id]} edit={edit}><ColorRow project={p} lineIds={[id]} edit={edit}/></ClipAppearance>:<><label className="fld">Font<select aria-label="Font" value={word.style?.fontFamily??p.style.fontFamily} onChange={e=>{const fontFamily=e.target.value;change(w=>({...w,style:{...w.style,fontFamily}}));}}>{FAMILIES.map(f=><option key={f}>{f}</option>)}</select></label><ColorRow project={p} lineIds={[id]} edit={edit}/></>}
    </div>
    <HudControls project={p} lineIds={[id]} edit={edit} checkpoint={checkpoint}/>
    <details className="fold"><summary>Position &amp; motion</summary>
      <div className="fld"><div className="seg" role="group" aria-label="Text alignment">{(['left','center','right'] as const).map(align=><button key={align} aria-label={`Align ${align}`} className={(first.style?.align||p.style.align)===align?'active':''} onClick={()=>{checkpoint();change(w=>({...w,autoPlace:false,style:{...w.style,align},position:{x:align==='left'?.08:align==='right'?.92:.5,y:w.position?.y??.72}}));}}>{align[0].toUpperCase()+align.slice(1)}</button>)}</div></div>
      <div className="row2">{(['x','y'] as const).map(axis=><ScrubNum key={axis} label={axis.toUpperCase()} value={(first.position?.[axis]??(axis==='x'?.5:.72))*100} onStart={checkpoint} onChange={v=>change(w=>({...w,autoPlace:false,position:{x:w.position?.x??.5,y:w.position?.y??.72,[axis]:Math.max(0,Math.min(1,v/100))}}))}/>)}</div>
      {!lookOf(p)&&<div className="fld"><label>Motion</label><div className="seg presets">{PRESETS.map(pr=><button key={pr} className={first.preset===pr?'active':''} onClick={()=>{checkpoint();change(w=>({...w,preset:pr}));}}>{presetName(pr)}</button>)}</div></div>}
    </details>
  </section>;
}
