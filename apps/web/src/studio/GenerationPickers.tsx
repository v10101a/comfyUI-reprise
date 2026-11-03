import {useLayoutEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {createPortal} from 'react-dom';
import type {Project} from '../types';
import type {Workflow,WfInput} from './workflows';
import {SceneThumb} from './SceneThumb';
import {Icon} from './icons';

function Picker({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}){
  const ref=useRef<HTMLDialogElement>(null);
  useLayoutEffect(()=>{const el=ref.current;el?.showModal();return()=>el?.close();},[]);
  return createPortal(<dialog ref={ref} className="generation-picker" aria-label={title} onCancel={e=>{e.preventDefault();onClose();}}
    onKeyDown={e=>{e.stopPropagation();if(e.key==='Escape'){e.preventDefault();onClose();}if(e.key==='Tab'){
      const controls=Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button,input,select,textarea,[tabindex="0"]')).filter(el=>!el.hasAttribute('disabled')&&el.getClientRects().length);
      const first=controls[0],last=controls.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
    }}}
    onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}>
    <div className="generation-picker-head"><strong>{title}</strong><button className="icon-sm" aria-label="Close picker" title="Close (Esc)" onClick={onClose}><Icon name="close"/></button></div>{children}
  </dialog>,document.querySelector('.studio')||document.body);
}

export type SourceChoice={id:string;name:string;detail?:string};
export function ReferencePicker({project,input,nearby,value,choices,onChoose,onClose}:{project:Project;input:WfInput;nearby:string[];value:string;choices:SourceChoice[];onChoose:(id:string)=>void;onClose:()=>void}){
  const [query,setQuery]=useState(''),[all,setAll]=useState(false);
  const eligible=(project.assets||[]).filter(a=>input.media==='audio'?a.hasAudio:input.media!=='video'||a.kind==='video');
  const local=nearby.map(id=>eligible.find(a=>a.id===id)).filter((a):a is typeof eligible[number]=>!!a);
  const search=query.trim().toLowerCase();
  const shown=(all||search?eligible:local).filter(a=>!search||`${a.name||''} ${a.kind}`.toLowerCase().includes(search));
  return <Picker title={`Choose ${input.title}`} onClose={onClose}>
    <input autoFocus type="search" className="generation-search" aria-label="Search media" placeholder="Search by name…" value={query} onChange={e=>setQuery(e.target.value)}/>
    <div className="generation-picker-scope"><div className="seg"><button className={!all&&!search?'active':''} onClick={()=>{setAll(false);setQuery('');}}>This shot</button><button className={all||search?'active':''} onClick={()=>setAll(true)}>All media · {eligible.length}</button></div></div>
    <div className="generation-picker-scroll">
      {!search&&choices.length>0&&<div className="generation-specials">{choices.map(c=><button key={c.id} className={c.id===value?'chosen':''} aria-pressed={c.id===value} onClick={()=>onChoose(c.id)}><Icon name={input.media==='audio'?'sound':'media'} size={20}/><span>{c.name}<small>{c.detail}</small></span>{c.id===value&&<span>✓</span>}</button>)}</div>}
      <div className="generation-media-grid">{shown.map(a=><button key={a.id} title={`${a.name||'Untitled media'}${a.kind==='video'&&input.media==='image'?' · frame from video':''}`} aria-label={`Use ${a.name||'Untitled media'}`} aria-pressed={a.id===value} className={a.id===value?'chosen':''} onClick={()=>onChoose(a.id)}>
        <SceneThumb project={project} asset={a}/>{a.kind==='video'&&<small className="generation-media-duration"><Icon name="play" size={10}/>{a.duration?`${a.duration.toFixed(1)}s`:''}</small>}<span>{a.name||'Untitled media'}</span>
      </button>)}</div>
      {!shown.length&&<p className="generation-picker-empty">{search?'No matching media.':all?'No compatible media yet.':'No media attached to this shot yet.'}</p>}
    </div>
  </Picker>;
}

const summary=(w:Workflow)=>{
  const inputs=Object.values(w.inputs).filter(i=>i.role==='media').map(i=>i.media==='image'?'Still':i.media==='audio'?'Audio':'Video');
  return `${inputs.join(' + ')||'Prompt'} → ${w.output?.type==='video'?'video':'image'}`;
};
export function WorkflowPicker({workflows,value,related,onChoose,onClose}:{workflows:Workflow[];value:string;related:string[];onChoose:(id:string)=>void;onClose:()=>void}){
  const [query,setQuery]=useState('');const q=query.trim().toLowerCase();
  const shown=workflows.filter(w=>`${w.name} ${summary(w)}`.toLowerCase().includes(q));
  const groups=[{title:'Used in this shot',items:shown.filter(w=>related.includes(w.id)||w.id===value)},{title:'Other workflows',items:shown.filter(w=>!related.includes(w.id)&&w.id!==value)}];
  return <Picker title="Choose workflow" onClose={onClose}>
    <input autoFocus type="search" className="generation-search" aria-label="Search workflows" placeholder="Search by name or input type…" value={query} onChange={e=>setQuery(e.target.value)}/>
    <div className="generation-picker-scroll generation-workflow-list">{groups.filter(g=>g.items.length).map(g=><section key={g.title}><h3>{g.title}</h3>{g.items.map(w=>{
      const unavailable=!!(w.readinessError||w.missing.length||w.missingModels?.length),duplicate=workflows.filter(x=>x.name===w.name).length>1;
      return <button key={w.id} aria-label={`Use workflow ${w.name}${duplicate?` ${w.id}`:''}`} aria-pressed={w.id===value} className={w.id===value?'chosen':''} onClick={()=>onChoose(w.id)}>
        <Icon name={w.output?.type==='video'?'play':'media'} size={22}/><span><strong>{w.name}</strong><small>{summary(w)}{duplicate?` · ${w.nodes} nodes · ${w.id.slice(0,6)}`:''}</small></span>
        <em>{w.id===value?'✓':unavailable?'Unavailable':''}</em>
      </button>;
    })}</section>)}{!shown.length&&<p className="generation-picker-empty">No matching workflows.</p>}</div>
  </Picker>;
}
