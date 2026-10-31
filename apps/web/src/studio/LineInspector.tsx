// Line-level inspector: role, hero word, placement, motion, type and visibility for the whole line.
// Word-level details (text, in/out, per-word overrides) sit behind a disclosure.
import type {Project,Word,Placement,Preset,SurfaceMaterial,TextStyle} from '../types';
import {isAutoPlaced} from '../renderer';
import {FONTS,setLineMeta,setWordHero} from '../looks';
import {ROLE_LABEL,type LineInfo,type Role} from './Timeline';

const PRESET_GLYPH:Record<string,string>={pop:'T↑',karaoke:'T̲',typewriter:'T_',write:'✎',hud:'[T]',none:'T'};
const presets=Object.keys(PRESET_GLYPH) as Preset[];
const materials:SurfaceMaterial[]=['paint','neon','flat'];
const ROLES:{role:Role;placement:Placement;hint:string}[]=[
  {role:'caption',placement:'overlay',hint:'above the scene, always readable. finds clear space by itself.'},
  {role:'behind',placement:'behind',hint:'behind the subject cutout (needs the matte).'},
  {role:'hud',placement:'anchor',hint:'a tracked label on the head, with a hud frame and leader.'},
  {role:'wall',placement:'surface',hint:'in perspective on a wall. the subject passes in front.'},
  {role:'inworld',placement:'inworld',hint:'generated into the shot by a comfyui ltx workflow.'},
];
const families=[...new Set(FONTS.map(f=>f.family))];
const t2=(n:number)=>n.toFixed(2);

export function LineInspector(props:{
  project:Project;line?:LineInfo;word?:Word;selected:string;setSelected:(id:string)=>void;
  edit:(u:(p:Project)=>Project)=>void;busy:boolean;
  startSurface:(id?:string)=>void;trackSurface:(id:string)=>void;generate:()=>void;prompt:string;setPrompt:(s:string)=>void;
  wordOpen:boolean;setWordOpen:(b:boolean)=>void;
}){
  const {project:p,line,word:cur,edit}=props;
  if(!line||!cur)return <section className="panel-sec insp-empty"><p>No line selected</p></section>;
  const ids=new Set(line.words.map(w=>w.id));
  const editLine=(f:(w:Word)=>Word)=>edit(q=>({...q,words:q.words.map(w=>ids.has(w.id)?f(w):w)}));
  const editWord=(patch:Partial<Word>)=>edit(q=>({...q,words:q.words.map(w=>w.id===cur.id?{...w,...patch}:w)}));
  const lineStyle=(patch:Partial<TextStyle>)=>editLine(w=>({...w,style:{...w.style,...patch}}));
  const first=line.words[0];const style={...p.style,...(cur.style||{})} as TextStyle;
  const placement=first.placement;
  const setRole=(r:typeof ROLES[number])=>{
    if(r.placement==='surface'){const sid=first.surfaceId||p.surfaces?.[0]?.id;if(sid)editLine(w=>({...w,placement:'surface',surfaceId:sid}));else props.startSurface();return;}
    if(r.role==='hud'){editLine(w=>({...w,placement:'anchor',preset:'hud',anchor:w.anchor||{trackId:'person0',dx:0,dy:-.1}}));return;}
    editLine(w=>({...w,placement:r.placement,...(w.preset==='hud'?{preset:'pop' as Preset}:{})}));
  };
  const meta=p.lineMeta?.[line.id]||{};
  const surface=p.surfaces?.find(x=>x.id===first.surfaceId);
  return <section className="panel-sec insp">
    <header className="sec-head"><span title={`${t2(line.start)}–${t2(line.end)} s`}>Line {String(line.index+1).padStart(2,'0')}</span>
      <span className="insp-flags">
        <button className={`flag ${line.hook?'on':''}`} onClick={()=>edit(q=>setLineMeta(q,line.id,{hook:!line.hook}))} title="hooks get the loud treatment in looks; quiet looks keep only hooks">Hook</button>
        <button className={`flag ${line.hidden?'on':''}`} onClick={()=>edit(q=>setLineMeta(q,line.id,{hidden:!meta.hidden?true:null}))} title={line.hidden?'show (H)':'hide (H)'} aria-label={line.hidden?'show line':'hide line'}>{line.hidden?'○':'●'}</button>
      </span>
    </header>
    <div className="line-words" aria-label="Words in line">
      {line.words.map(w=><span key={w.id} className="lw"><button className={`${props.selected===w.id?'selected':''} ${line.heroId===w.id?'hero':''}`} onClick={()=>props.setSelected(w.id)}>{w.text}</button>
        <button className={`star ${line.heroId===w.id?'on':''}`} title={line.heroId===w.id?'Hero word':'Make hero word'} aria-label={`Make ${w.text} the hero word`} onClick={()=>edit(q=>setWordHero(q,w.id,line.heroId!==w.id||!w.hero))}>✦</button></span>)}
    </div>
    <div className="fld"><label>Role</label>
      <div className="seg roles">{ROLES.map(r=><button key={r.role} className={line.role===r.role||(r.role==='hud'&&line.role==='anchor')?'active':''} onClick={()=>setRole(r)} title={r.hint}><i className={`role-dot role-${r.role}`}/>{ROLE_LABEL[r.role]}</button>)}</div>
    </div>
    {(placement==='behind'||placement==='overlay')&&<div className="fld auto-place">
      <label className="check" title="find a clear spot away from the subject; drag on the stage to nudge"><input type="checkbox" checked={isAutoPlaced(first)} onChange={e=>editLine(w=>({...w,autoPlace:e.target.checked}))}/> Auto place</label>
      <div className="row3">
        <label className="num">X<input type="number" min="0" max="100" value={Math.round((first.position?.x??.5)*100)} onChange={e=>{const x=Math.max(0,Math.min(1,Number(e.target.value)/100));editLine(w=>({...w,position:{x,y:first.position?.y??.72}}));}}/></label>
        <label className="num">Y<input type="number" min="0" max="100" value={Math.round((first.position?.y??.72)*100)} onChange={e=>{const y=Math.max(0,Math.min(1,Number(e.target.value)/100));editLine(w=>({...w,position:{x:first.position?.x??.5,y}}));}}/></label>
        <div className="seg mini">{(['left','center','right'] as const).map(a=><button key={a} className={style.align===a?'active':''} onClick={()=>lineStyle({align:a})} aria-label={`Align ${a}`}>{a==='left'?'⇤':a==='center'?'↔':'⇥'}</button>)}</div>
      </div>
      {placement==='behind'&&<label className="range">Shadow <b>{Math.round((first.style?.shadow??.5)*100)}%</b><input type="range" min="0" max="1" step=".05" value={first.style?.shadow??.5} onChange={e=>lineStyle({shadow:Number(e.target.value)})}/></label>}
    </div>}
    {placement==='anchor'&&<div className="fld"><label title={first.anchor?.trackId||'person0'}>Anchor</label><div className="row2">{(['dx','dy'] as const).map(axis=><label className="num" key={axis}>{axis}<input type="number" step=".01" min="-1" max="1" value={first.anchor?.[axis]||0} onChange={e=>{const v=Number(e.target.value);editLine(w=>({...w,anchor:{trackId:w.anchor?.trackId||'person0',dx:w.anchor?.dx||0,dy:w.anchor?.dy||0,[axis]:v}}));}}/></label>)}</div></div>}
    {placement==='surface'&&<div className="fld surface-panel"><label>Wall</label>
      <select value={first.surfaceId||''} onChange={e=>editLine(w=>({...w,surfaceId:e.target.value}))}>{(p.surfaces||[]).map(s=><option key={s.id} value={s.id}>{s.label||s.id} · {s.status||'drawn'}</option>)}</select>
      {surface?<><div className="seg">{materials.map(m=><button key={m} className={(surface.material||'paint')===m?'active':''} onClick={()=>edit(q=>({...q,surfaces:(q.surfaces||[]).map(x=>x.id===surface.id?{...x,material:m}:x)}))}>{m}</button>)}</div>
        <div className="row2"><button onClick={()=>props.startSurface(surface.id)}>Redraw</button><button disabled={props.busy} onClick={()=>props.trackSurface(surface.id)} title={surface.status==='tracked'?'tracked':surface.status==='failed'?'tracking failed, using drawn corners':`static, drawn at frame ${surface.keyFrame}`}>Track</button></div></>:<button className="wide" onClick={()=>props.startSurface()}>Draw wall</button>}
    </div>}
    {placement==='inworld'&&<div className="fld generation-panel"><textarea rows={3} aria-label="shot prompt" value={props.prompt} onChange={e=>props.setPrompt(e.target.value)}/><button className="wide primary" disabled={props.busy} onClick={props.generate} title="comfyui · ltx">Generate</button></div>}
    <div className="fld"><label>Motion</label>
      <div className="seg presets">{presets.map(pr=><button key={pr} className={line.words.every(w=>w.preset===pr)?'active':''} onClick={()=>editLine(w=>({...w,preset:pr}))} title={PRESET_GLYPH[pr]}>{pr==='typewriter'?'Type':pr==='hud'?'HUD':pr[0].toUpperCase()+pr.slice(1)}</button>)}</div>
    </div>
    <div className="fld"><label title="overrides the look">Type</label>
      <div className="row3 type-row">
        <select aria-label="Font family" value={style.fontFamily} onChange={e=>{const f=e.target.value;lineStyle({fontFamily:f,fontWeight:['Inter','Space Mono','Big Shoulders Display','Archivo Narrow'].includes(f)?700:400});}}>{families.map(f=><option key={f}>{f}</option>)}</select>
        <label className="num">%<input type="number" step=".5" min="1" max="60" value={Number((style.fontSize*100).toFixed(1))} onChange={e=>lineStyle({fontSize:Math.min(.6,Math.max(.01,Number(e.target.value)/100))})}/></label>
        <label className="swatch"><input aria-label="Text fill color" type="color" value={style.fill} onChange={e=>lineStyle({fill:e.target.value})}/></label>
      </div>
    </div>
    <details className="word-details" open={props.wordOpen} onToggle={e=>props.setWordOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary><b>{cur.text}</b></summary>
      <label className="fld"><input className="word-input" aria-label="word text" value={cur.text} onChange={e=>editWord({text:e.target.value})}/></label>
      <div className="row2">
        <label className="num">in<input type="number" min={0} max={cur.end-.01} step="0.01" value={cur.start} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v))editWord({start:Math.max(0,Math.min(v,cur.end-.01))});}}/></label>
        <label className="num">out<input type="number" min={cur.start+.01} max={p.duration} step="0.01" value={cur.end} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v))editWord({end:Math.min(p.duration,Math.max(v,cur.start+.01))});}}/></label>
      </div>
      <div className="row2">
        <label className="swatch wide-sw" title="word colour"><input type="color" value={style.fill} onChange={e=>editWord({style:{...cur.style,fill:e.target.value}})}/></label>
        <label className="check"><input type="checkbox" checked={!!cur.hidden} onChange={e=>editWord({hidden:e.target.checked||null})}/> Hide</label>
      </div>
      <button className="delete-button" onClick={()=>{const rest=p.words.filter(w=>w.id!==cur.id);edit(q=>({...q,words:q.words.filter(w=>w.id!==cur.id)}));props.setSelected(rest.find(w=>w.lineId===cur.lineId)?.id||rest[0]?.id||'');}}>Remove word</button>
    </details>
  </section>;
}
