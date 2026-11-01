// Multi-line inspector (Figma-style group selection): shared properties for every selected line; differing values read "Mixed".
import {useEffect,useRef} from 'react';
import type {Project,Word,TextStyle} from '../types';
import {lookOf,setLineMeta} from '../looks';
import {lineColor,setLineColor,shared,type ColorKey} from './groups';
import {Crumb} from './Crumb';
import {Icon} from './icons';
import {PRESETS,presetName,FAMILIES,BOLD_FAMILIES,SizeSlider} from './LineInspector';

type Edit=(u:(p:Project)=>Project)=>void;

/** Text / active / upcoming colour for a set of lines. Unset = the look's colour (shown, not stored). */
export function ColorRow({project:p,lineIds,edit}:{project:Project;lineIds:string[];edit:Edit}){
  const look=lookOf(p);const ws=p.words.filter(w=>lineIds.includes(w.lineId));
  const karaoke=ws.some(w=>w.preset==='karaoke');
  const base=look?.palette.text??ws[0]?.style?.fill??p.style.fill;
  const fallback:Record<ColorKey,string>={fill:base,karaoke:look?.palette.accent??'#d8ff62',dim:base};
  const keys:{k:ColorKey;label:string;title:string}[]=[{k:'fill',label:'Text',title:'text colour'},
    ...(karaoke?[{k:'karaoke' as const,label:'Active',title:'sung word'},{k:'dim' as const,label:'Next',title:'words not sung yet'}]:[])];
  return <div className="color-row">{keys.map(({k,label,title})=>{
    const v=shared(lineIds.map(id=>lineColor(p,id,k)??null));const set=v!=null&&v!=='mixed';
    return <label key={k} className={`csw ${v==='mixed'?'mixed':''} ${set?'set':''}`} title={v==='mixed'?`${title} · mixed`:set?title:`${title} · from the look`}>
      <input type="color" value={set?v:fallback[k]} onChange={e=>{const c=e.target.value;edit(q=>setLineColor(q,lineIds,k,c));}}/>
      <span>{label}</span>
      {(set||v==='mixed')&&<button className="csw-x" aria-label={`reset ${label}`} title="back to the look" onClick={e=>{e.preventDefault();edit(q=>setLineColor(q,lineIds,k,null));}}>×</button>}
    </label>;})}</div>;
}

function Tri({checked,onChange,children,title}:{checked:boolean|'mixed';onChange:(v:boolean)=>void;children:React.ReactNode;title?:string}){
  const r=useRef<HTMLInputElement>(null);useEffect(()=>{if(r.current)r.current.indeterminate=checked==='mixed';},[checked]);
  return <label className="check" title={title}><input ref={r} type="checkbox" checked={checked===true} onChange={e=>onChange(e.target.checked)}/>{children}</label>;
}

export function GroupInspector({project:p,lineIds,title,edit,checkpoint,onClear}:{project:Project;lineIds:string[];title:string;edit:Edit;checkpoint:()=>void;onClear:()=>void}){
  const ids=new Set(lineIds);const ws=p.words.filter(w=>ids.has(w.lineId));
  const editWords=(f:(w:Word)=>Word)=>edit(q=>({...q,words:q.words.map(w=>ids.has(w.lineId)?f(w):w)}));
  const style=(patch:Partial<TextStyle>)=>editWords(w=>({...w,style:{...w.style,...patch}}));
  const st=(w:Word)=>({...p.style,...(w.style||{})}) as TextStyle;
  const family=shared(ws.map(w=>st(w).fontFamily));const size=shared(ws.map(w=>+(st(w).fontSize*100).toFixed(1)));
  const preset=shared(ws.map(w=>w.preset));const align=shared(ws.map(w=>st(w).align));
  const placeable=ws.filter(w=>w.placement==='overlay'||w.placement==='behind');
  const auto=shared(placeable.map(w=>w.autoPlace!==false));
  const hidden=shared(lineIds.map(id=>!!p.lineMeta?.[id]?.hidden));
  // Size: the first word's size; moving it scales every word proportionally (mixed sizes keep their ratios).
  const base=ws.length?st(ws[0]).fontSize*100:8;
  const setSize=(v:number)=>{const k=v/Math.max(.1,base);editWords(w=>({...w,style:{...(w.style||{}),fontSize:+Math.max(.008,Math.min(.6,st(w).fontSize*k)).toFixed(4)}}));};
  const roles=new Set(ws.map(w=>w.placement));const dot=roles.size===1?{overlay:'caption',behind:'behind',anchor:'hud',surface:'wall',inworld:'inworld'}[ws[0]?.placement||'overlay']:undefined;
  const M='Mixed';
  return <section className="panel-sec insp group-insp">
    <Crumb chip={{dot,text:`${title} · ${lineIds.length}`}} onBack={onClear}>
      <button className={`icon-sm ${hidden===true?'on':''}`} onClick={()=>edit(q=>lineIds.reduce((acc,id)=>setLineMeta(acc,id,{hidden:hidden===true?null:true}),q))}
        aria-pressed={hidden===true} aria-label={hidden===true?'Show all':'Hide all'} title={hidden===true?'Show all':hidden==='mixed'?'Some hidden · hide all':'Hide all'}><Icon name={hidden===true?'eyeOff':'eye'} size={14}/></button>
    </Crumb>
    <SizeSlider value={base} min={1} max={40} step={.1} fmt={v=>size==='mixed'?`${M}`:`${v.toFixed(1)}%`} onStart={checkpoint} onChange={setSize}/>
    <div className="fld"><ColorRow project={p} lineIds={lineIds} edit={edit}/></div>
    <details className="fold">
      <summary>More</summary>
      <div className="fld"><label>Motion{preset==='mixed'&&<em className="mixed-tag">{M}</em>}</label>
        <div className="seg presets">{PRESETS.map(pr=><button key={pr} className={preset===pr?'active':''} onClick={()=>editWords(w=>({...w,preset:pr}))}>{presetName(pr)}</button>)}</div>
      </div>
      <div className="fld"><label title="Overrides the look">Font</label>
        <select aria-label="Font family" value={family==='mixed'?'':family||''} onChange={e=>{const f=e.target.value;if(f)style({fontFamily:f,fontWeight:BOLD_FAMILIES.includes(f)?700:400});}}>
          {family==='mixed'&&<option value="">{M}</option>}{FAMILIES.map(f=><option key={f}>{f}</option>)}</select>
      </div>
      <div className="fld"><label>Position{align==='mixed'&&<em className="mixed-tag">{M}</em>}</label>
        <div className="row-pos">
          <div className="seg mini">{(['left','center','right'] as const).map(a=><button key={a} className={align===a?'active':''} onClick={()=>style({align:a})} aria-label={`Align ${a}`} title={`Align ${a}`}>{a==='left'?'⇤':a==='center'?'↔':'⇥'}</button>)}</div>
          {placeable.length>0&&<Tri checked={auto??false} onChange={v=>edit(q=>({...q,words:q.words.map(w=>ids.has(w.lineId)&&(w.placement==='overlay'||w.placement==='behind')?{...w,autoPlace:v}:w)}))} title="Find a clear spot away from the subject">Auto place</Tri>}
        </div>
      </div>
    </details>
  </section>;
}
