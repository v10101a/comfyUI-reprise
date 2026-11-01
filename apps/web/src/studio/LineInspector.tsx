// Line inspector: editable text, placement, size, alignment and colour stay visible.
import {useRef,useState,useEffect} from 'react';
import type {Project,Word,Placement,Preset,SurfaceMaterial,TextStyle} from '../types';
import {isAutoPlaced} from '../renderer';
import {FONTS,setLineMeta,setWordHero,lineSizeMode} from '../looks';
import {ROLE_LABEL,type LineInfo,type Role} from './Timeline';
import {ColorRow} from './GroupInspector';
import {Crumb} from './Crumb';
import {Icon} from './icons';
import {WallButtons} from './WallTool';
import {wallFallback} from './walls';

export const PRESETS:Preset[]=['pop','karaoke','typewriter','write','hud','none'];
export const presetName=(p:Preset)=>p==='typewriter'?'Type':p==='hud'?'HUD':p[0].toUpperCase()+p.slice(1);
const PRESET_HINT:Record<string,string>={pop:'springs in',karaoke:'lights up as it is sung',typewriter:'types letter by letter',write:'appears on its onset',hud:'jitters in like a readout',none:'no motion'};
const materials:SurfaceMaterial[]=['paint','neon','flat'];
const ROLES:{role:Role;placement:Placement;label:string;hint:string}[]=[
  {role:'caption',placement:'overlay',label:'Caption',hint:'On top, like subtitles'},
  {role:'behind',placement:'behind',label:'Behind',hint:'Behind the person'},
  {role:'hud',placement:'anchor',label:'HUD',hint:'Follows the head'},
  {role:'wall',placement:'surface',label:'Wall',hint:'Painted on a surface'},
  {role:'inworld',placement:'inworld',label:'In-world',hint:'Generated into the shot'},
];
/** In-world = local ComfyUI writes the word into a frame (Qwen edit), then MiniMax H3 animates it on the remote 4090.
 *  The LTX path cannot run here (the remote lacks its text encoder and has no room to add it). Asked once per session;
 *  resolves to '' when it can run, else the reason. */
let inworldCheck:Promise<string>|undefined;
function inworldBlocker(){
  return inworldCheck??=fetch('/api/health').then(r=>r.ok?r.json():null).then((h:{comfyui?:boolean;remote?:{comfyui?:boolean}}|null)=>
    !h?'Server offline':!h.remote?.comfyui?'Remote GPU not reachable':!h.comfyui?'Local ComfyUI not reachable':'').catch(()=>'Server offline');
}
const MATTE_WHY={none:'No subject matte: Behind cannot cut out the person',missing:'Subject matte did not load: Behind is not cut out',stale:'Subject matte does not match the footage'};
export const FAMILIES=[...new Set(FONTS.map(f=>f.family))];
export const BOLD_FAMILIES=['Inter','Space Mono','Big Shoulders Display','Archivo Narrow'];
const t2=(n:number)=>n.toFixed(2);
export const lineChipText=(text:string)=>{const ws=text.split(/\s+/);return ws.length>4?ws.slice(0,4).join(' ')+'…':text;};

/** Size: fontSize % of frame height for screen lines; the wall scale for wall lines. Mirrors the stage corner handles. */
export function SizeSlider({value,min,max,step,fmt,onChange,onStart,label='Size'}:{value:number;min:number;max:number;step:number;fmt:(v:number)=>string;onChange:(v:number)=>void;onStart?:()=>void;label?:string}){
  return <label className="size-row"><span className="lbl">{label}</span>
    <input type="range" aria-label={label} min={min} max={max} step={step} value={Math.max(min,Math.min(max,value))} onPointerDown={onStart} onChange={e=>onChange(Number(e.target.value))}/>
    <b className="mono">{fmt(value)}</b></label>;
}

/** Number field whose label scrubs: drag the label sideways (⇧ = 10× finer). One undo step per drag. */
export function ScrubNum({label,value,onChange,onStart,step=.1,title}:{label:string;value:number;onChange:(v:number)=>void;onStart?:()=>void;step?:number;title?:string}){
  const d=useRef<{x:number;v:number}|null>(null);
  return <label className="num scrub" title={title}>
    <span className="scrub-l" onClick={e=>e.preventDefault()} onPointerDown={e=>{e.preventDefault();(e.currentTarget as Element).setPointerCapture(e.pointerId);onStart?.();d.current={x:e.clientX,v:value};}}
      onPointerMove={e=>{const s=d.current;if(!s)return;onChange(+(s.v+(e.clientX-s.x)*step*(e.shiftKey?.1:1)).toFixed(2));}}
      onPointerUp={e=>{d.current=null;(e.currentTarget as Element).releasePointerCapture?.(e.pointerId);}}>{label}</span>
    <input type="number" step=".1" aria-label={label} value={+value.toFixed(1)} onChange={e=>{const v=Number(e.target.value);if(e.target.value!==''&&Number.isFinite(v))onChange(v);}}/>
  </label>;
}

export function LineInspector(props:{
  project:Project;line?:LineInfo;word?:Word;selected:string;setSelected:(id:string)=>void;
  edit:(u:(p:Project)=>Project)=>void;checkpoint:()=>void;busy:boolean;onBack:()=>void;
  startSurface:(id?:string)=>void;trackSurface:(id:string)=>void;generate:()=>void;prompt:string;setPrompt:(s:string)=>void;
  wordOpen:boolean;setWordOpen:(b:boolean)=>void;
  /** The line's drawn box at the current frame (project px), when it is on screen. */
  box?:{x:number;y:number;w:number;h:number};
  /** Subject matte (Behind) and person track (HUD) as the stage loaded them; run the matte step in place. */
  subject?:{matte:'ok'|'none'|'missing'|'stale';person:boolean};matteRunning?:boolean;runMatte?:()=>void;
  deleteWall?:(id:string)=>void;wallRunning?:boolean;
}){
  const {project:p,line,word:cur,edit}=props;
  const [genWhy,setGenWhy]=useState<string|null>(null);useEffect(()=>{let live=true;void inworldBlocker().then(w=>{if(live)setGenWhy(w);});return()=>{live=false;};},[]);
  const inworldWhy=p.id==='sample'?'Not in the sample':!p.media.video?'Needs footage':genWhy===null?'Checking…':genWhy;
  // In-world is chosen first, then generated: the line keeps its place until a shot lands (the server moves it in-world).
  const [pending,setPending]=useState(false);useEffect(()=>setPending(false),[line?.id]);
  if(!line||!cur)return null;
  const ids=new Set(line.words.map(w=>w.id));
  const editLine=(f:(w:Word)=>Word)=>edit(q=>({...q,words:q.words.map(w=>ids.has(w.id)?f(w):w)}));
  const editWord=(patch:Partial<Word>)=>edit(q=>({...q,words:q.words.map(w=>w.id===cur.id?{...w,...patch}:w)}));
  const lineStyle=(patch:Partial<TextStyle>)=>editLine(w=>({...w,style:{...w.style,...patch}}));
  const first=line.words[0];const style={...p.style,...(cur.style||{})} as TextStyle;
  const placement=first.placement;
  const setRole=(r:typeof ROLES[number])=>{
    if(r.role==='inworld'){if(!inworldWhy)setPending(true);return;}setPending(false);
    if(r.placement==='surface'){const sid=first.surfaceId||p.surfaces?.[0]?.id;if(sid)editLine(w=>({...w,placement:'surface',surfaceId:sid}));else props.startSurface();return;}
    if(r.role==='hud'){editLine(w=>({...w,placement:'anchor',preset:'hud',anchor:w.anchor||{trackId:'person0',dx:0,dy:-.1}}));return;}
    editLine(w=>({...w,placement:r.placement,...(w.preset==='hud'?{preset:'pop' as Preset}:{})}));
  };
  const meta=p.lineMeta?.[line.id]||{};
  const matteWhy=props.subject&&props.subject.matte!=='ok'?MATTE_WHY[props.subject.matte]:'';const noPerson=!!props.subject&&!props.subject.person;
  const surface=p.surfaces?.find(x=>x.id===first.surfaceId);
  const firstSize=(first.style?.fontSize??p.style.fontSize)*100;const sizeMode=lineSizeMode(p,line.id);
  // Proportional: every word keeps its size relative to the first (hero words stay bigger).
  const setSize=(v:number)=>{const k=v/Math.max(.1,firstSize);editLine(w=>({...w,style:{...(w.style||{}),fontSize:+Math.max(.008,Math.min(.6,(w.style?.fontSize??p.style.fontSize)*k)).toFixed(4)}}));};
  const screen=placement==='overlay'||placement==='behind';
  // Position = the centre of the drawn line box in frame fractions, whatever the alignment (the stored origin is the
  // aligned edge: left edge for left, centre, right edge for right). Off screen at this frame: the stored origin.
  const b=props.box;const W=p.width,H=p.height;const al=style.align||'center';
  const pos=b?{cx:(b.x+b.w/2)/W,cy:(b.y+b.h/2)/H,hw:b.w/2/W}:{cx:first.position?.x??.5,cy:first.position?.y??.72,hw:0};
  const originX=(cx:number,a:string)=>cx+(a==='left'?-pos.hw:a==='right'?pos.hw:0);
  const clamp01=(v:number)=>Math.max(0,Math.min(1,v));
  // Typing or scrubbing exact numbers places the line there (auto place off), like a stage drag that sticks.
  const setCentre=(cx:number,cy:number)=>{const x=+clamp01(originX(cx,al)).toFixed(4),y=+clamp01(cy).toFixed(4);editLine(w=>({...w,autoPlace:false,position:{x,y}}));};
  // Align the line within the frame, keeping its vertical position. Manual alignment wins over auto placement.
  const setAlign=(a:'left'|'center'|'right')=>{const x=a==='left'?.08:a==='right'?.92:.5;
    editLine(w=>({...w,autoPlace:false,style:{...w.style,align:a},position:{x,y:w.position?.y??pos.cy}}));};
  return <section className="panel-sec insp">
    <Crumb chip={{dot:line.role,text:lineChipText(line.text),title:`${String(line.index+1).padStart(2,'0')} · ${ROLE_LABEL[line.role]} · ${t2(line.start)}–${t2(line.end)} s · ${line.text}`}} onBack={props.onBack}>
      <button className={`icon-sm ${line.hidden?'on':''}`} onClick={()=>edit(q=>setLineMeta(q,line.id,{hidden:!meta.hidden?true:null}))} aria-pressed={line.hidden} aria-label={line.hidden?'Show line':'Hide line'} title={line.hidden?'Show line (H)':'Hide line (H)'}><Icon name={line.hidden?'eyeOff':'eye'} size={14}/></button>
    </Crumb>
    <div className="line-words" aria-label="Words in line">
      {line.words.map(w=><span key={w.id} className="lw"><button className={`${props.selected===w.id?'selected':''} ${line.heroId===w.id?'hero':''} ${w.hidden?'gone':''}`} onClick={()=>props.setSelected(w.id)} title={`${w.start.toFixed(2)}–${w.end.toFixed(2)} s`}>{w.text}</button>
        <button className={`star ${line.heroId===w.id?'on':''}`} title={line.heroId===w.id?'Hero word':'Make hero word'} aria-label={`Make ${w.text} the hero word`} onClick={()=>edit(q=>setWordHero(q,w.id,line.heroId!==w.id||!w.hero))}>✦</button></span>)}
    </div>
    <label className="fld"><input className="word-input" aria-label="Word text" value={cur.text} onChange={e=>editWord({text:e.target.value})}/></label>
    <div className="seg roles icons" role="radiogroup" aria-label="Role">{ROLES.map(r=>{const on=pending?r.role==='inworld':line.role===r.role||(r.role==='hud'&&line.role==='anchor');
      const off=r.role==='inworld'&&!!inworldWhy&&placement!=='inworld';
      const warn=r.role==='behind'&&matteWhy?matteWhy:r.role==='hud'&&noPerson?'No person track: HUD sits as a screen label':'';
      const hint=off?`In-world: ${inworldWhy}`:warn?`${r.hint} · ${warn}`:r.hint;
      return <button key={r.role} role="radio" aria-checked={on} aria-disabled={off} className={`${on?'active':''} ${off?'off':''}`} onClick={()=>{if(!off)setRole(r);}} title={hint} aria-label={`${r.label}: ${hint}`}><span className={`role-ic role-${r.role}`}><Icon name={r.role} size={16}/>{warn&&<i className="role-warn"/>}</span><span className="role-lb">{r.label}</span></button>;})}</div>
    {((placement==='behind'&&matteWhy)||(placement==='anchor'&&noPerson))&&<div className="fld need-row">
      <span className="need-ic" title={placement==='behind'?matteWhy:'No person track: HUD sits as a screen label. The subject matte also tracks the person.'}><Icon name={placement==='behind'?'noMatte':'noPerson'} size={16}/></span>
      <button className="wide" disabled={props.busy||props.matteRunning||p.id==='sample'} onClick={props.runMatte} title="Run Subject matte (ComfyUI · BiRefNet): cut-out + person track">{props.matteRunning?'Matte running…':'Run subject matte'}</button>
    </div>}
    <label className="toggle-row" title="Hook: hero styling, bigger and louder in every look (Hooks track)"><input type="checkbox" checked={line.hook} onChange={()=>edit(q=>setLineMeta(q,line.id,{hook:!line.hook}))}/><span className="tg"/>Hook</label>
    {placement==='surface'&&<div className="fld surface-panel">
      <div className="row-wall">
        <select aria-label="Wall" value={first.surfaceId||''} onChange={e=>editLine(w=>({...w,surfaceId:e.target.value}))}>{(p.surfaces||[]).map(s=><option key={s.id} value={s.id}>{s.label||s.id}</option>)}</select>
        {surface&&<WallButtons surface={surface} running={!!props.wallRunning} busy={props.busy} onTrack={()=>props.trackSurface(surface.id)} onRedraw={()=>props.startSurface(surface.id)}
          onDelete={()=>props.deleteWall?.(surface.id)} fallback={wallFallback(p)}/>}
        <button className="icon-sm" onClick={()=>props.startSurface()} aria-label="Draw new wall" title="Draw a new wall"><Icon name="wallNew" size={14}/></button>
      </div>
      {surface&&<div className="seg">{materials.map(m=><button key={m} className={(surface.material||'paint')===m?'active':''} onClick={()=>edit(q=>({...q,surfaces:(q.surfaces||[]).map(x=>x.id===surface.id?{...x,material:m}:x)}))}>{m[0].toUpperCase()+m.slice(1)}</button>)}</div>}
    </div>}
    {(placement==='inworld'||pending)&&<div className="fld generation-panel"><textarea rows={3} aria-label="Shot prompt" value={props.prompt} onChange={e=>props.setPrompt(e.target.value)}/><button className="wide primary" disabled={props.busy||!!inworldWhy} onClick={props.generate} title={inworldWhy||'Local Qwen edit writes the line into the frame, MiniMax H3 animates it on the remote GPU (several minutes)'}>Generate</button></div>}
    {/* lineSizeMode: walls and layout-sized lines take a ×scale (lineMeta.scale); in-world/ticker lines cannot resize. */}
    {sizeMode==='scale'
      ?<SizeSlider value={meta.scale??1} min={.2} max={4} step={.01} fmt={v=>`×${v.toFixed(2)}`} onStart={props.checkpoint} onChange={v=>edit(q=>setLineMeta(q,line.id,{scale:Math.abs(v-1)<.005?null:+v.toFixed(3)}))}/>
      :sizeMode==='font'&&<SizeSlider value={firstSize} min={1} max={40} step={.1} fmt={v=>`${v.toFixed(1)}%`} onStart={props.checkpoint} onChange={setSize}/>}
    <div className="fld"><ColorRow project={p} lineIds={[line.id]} edit={edit}/></div>
    {screen&&<div className="fld"><div className="seg" role="group" aria-label="Text alignment">{(['left','center','right'] as const).map(a=>
      <button key={a} className={style.align===a?'active':''} aria-pressed={style.align===a} onClick={()=>setAlign(a)} aria-label={`Align ${a}`} title={`Align ${a}`}>{a[0].toUpperCase()+a.slice(1)}</button>)}</div></div>}
    <details className="fold">
      <summary>Position &amp; motion</summary>
      <div className="fld"><label>Motion</label>
        <div className="seg presets">{PRESETS.map(pr=><button key={pr} className={line.words.every(w=>w.preset===pr)?'active':''} onClick={()=>editLine(w=>({...w,preset:pr}))} title={PRESET_HINT[pr]}>{presetName(pr)}</button>)}</div>
      </div>
      <div className="fld"><label title="Overrides the look">Font</label>
        <select aria-label="Font family" value={style.fontFamily} onChange={e=>{const f=e.target.value;lineStyle({fontFamily:f,fontWeight:BOLD_FAMILIES.includes(f)?700:400});}}>{FAMILIES.map(f=><option key={f}>{f}</option>)}</select>
      </div>
      {screen&&<div className="fld"><label title="Centre of the line box, % of the frame (X right, Y down)">Position</label>
        <label className="check" title="Find a clear spot away from the subject; drag on the stage to nudge"><input type="checkbox" checked={isAutoPlaced(first)} onChange={e=>editLine(w=>({...w,autoPlace:e.target.checked}))}/> Auto place</label>
        <div className="row2">
          <ScrubNum label="X" value={pos.cx*100} onStart={props.checkpoint} onChange={v=>setCentre(v/100,pos.cy)} title="Centre X, % of the frame width · drag the label"/>
          <ScrubNum label="Y" value={pos.cy*100} onStart={props.checkpoint} onChange={v=>setCentre(pos.cx,v/100)} title="Centre Y, % of the frame height (down) · drag the label"/>
        </div>
        {placement==='behind'&&<label className="range">Shadow <b>{Math.round((first.style?.shadow??.5)*100)}%</b><input type="range" min="0" max="1" step=".05" value={first.style?.shadow??.5} onPointerDown={props.checkpoint} onChange={e=>lineStyle({shadow:Number(e.target.value)})}/></label>}
      </div>}
      {placement==='anchor'&&<div className="fld"><label title={`Offset from ${first.anchor?.trackId||'person0'}'s head, % of the frame (X right, Y down)`}>Offset from head</label><div className="row2">{(['dx','dy'] as const).map(axis=>
        <ScrubNum key={axis} label={axis==='dx'?'X':'Y'} value={(first.anchor?.[axis]||0)*100} onStart={props.checkpoint} title={`${axis==='dx'?'Right':'Down'} of the head, % of the frame · drag the label`}
          onChange={v=>editLine(w=>({...w,anchor:{trackId:w.anchor?.trackId||'person0',dx:w.anchor?.dx||0,dy:w.anchor?.dy||0,[axis]:+(v/100).toFixed(4)}}))}/>)}</div></div>}
    </details>
    <details className="fold word-fold" open={props.wordOpen} onToggle={e=>props.setWordOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Word timing</summary>
      <div className="row2">
        <label className="num" title="Onset, s">in<input type="number" min={0} max={cur.end-.01} step="0.01" value={cur.start} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v))editWord({start:Math.max(0,Math.min(v,cur.end-.01))});}}/></label>
        <label className="num" title="End, s">out<input type="number" min={cur.start+.01} max={p.duration} step="0.01" value={cur.end} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v))editWord({end:Math.min(p.duration,Math.max(v,cur.start+.01))});}}/></label>
      </div>
      <div className="word-acts">
        <label className="swatch" title="Word colour"><input type="color" aria-label="Word colour" value={style.fill} onChange={e=>editWord({style:{...cur.style,fill:e.target.value}})}/></label>
        <button className={`icon-sm ${cur.hidden?'on':''}`} onClick={()=>editWord({hidden:cur.hidden?null:true})} aria-pressed={!!cur.hidden} aria-label={cur.hidden?'Show word':'Hide word'} title={cur.hidden?'Show word':'Hide word'}><Icon name={cur.hidden?'eyeOff':'eye'} size={14}/></button>
        <button className="icon-sm danger" onClick={()=>{const rest=p.words.filter(w=>w.id!==cur.id);edit(q=>({...q,words:q.words.filter(w=>w.id!==cur.id)}));props.setSelected(rest.find(w=>w.lineId===cur.lineId)?.id||'');}} aria-label="Remove word" title="Remove word"><Icon name="trash" size={14}/></button>
      </div>
    </details>
  </section>;
}
