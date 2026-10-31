// The perception pipeline, made visible: each ComfyUI workflow / server analysis with status, timing and the path that ran.
import {useEffect,useState} from 'react';
import type {Project} from '../types';
import {STEPS,stepStatus,type JobRecord,type StepDef,type StepId} from './pipeline';

type Health = {comfyui?:boolean;comfyuiVersion?:string;comfyuiUrl?:string;proxy?:boolean;generationTarget?:string};
const ENGINE:Record<string,string> = {comfy:'Comfy',cpu:'Server',remote:'Remote Comfy',browser:'Browser'};
const fmtS=(s?:number)=>s==null?'':s>=60?`${Math.floor(s/60)}m ${Math.round(s%60)}s`:s>=10?`${s.toFixed(0)} s`:`${s.toFixed(1)} s`;

export function PipelinePanel({project,jobs,occKind,hasBeats,beatsNote,comparing,busy,onRun,onOpenWorkflow}:{
  project:Project;jobs:Map<string,JobRecord>;occKind?:string;hasBeats:boolean;beatsNote?:string;comparing:boolean;busy:boolean;
  onRun:(id:StepId)=>void;onOpenWorkflow:(step:StepDef)=>void;
}){
  const [health,setHealth]=useState<Health|null>(null);
  useEffect(()=>{let live=true;const get=()=>fetch('/api/health').then(r=>r.ok?r.json():null).then(h=>{if(live)setHealth(h);}).catch(()=>{if(live)setHealth(null);});get();const t=setInterval(get,15000);return()=>{live=false;clearInterval(t);};},[]);
  const statuses=STEPS.map(s=>({def:s,st:stepStatus(s,project,jobs,{occKind,hasBeats,beatsNote,comparing})}));
  const comfyDone=statuses.filter(x=>x.def.engine==='comfy'&&x.st.state==='done').length;
  const comfySecs=statuses.filter(x=>x.def.engine==='comfy'&&x.st.state==='done').reduce((n,x)=>n+(x.st.seconds||0),0);
  const runnable:Partial<Record<StepId,string>>={words:'Transcribe',matte:'Isolate subject',occupancy:'Compute',beats:'Detect beats'};
  return <div className="pipeline">
    <div className={`comfy-head ${health?.comfyui?'up':'down'}`}>
      <div className="comfy-mark"><i/>ComfyUI</div>
      <div className="comfy-meta">{health?.comfyui?<>{health.comfyuiVersion?`v${health.comfyuiVersion} · `:''}{(health.comfyuiUrl||'').replace(/^https?:\/\//,'')} · {health.generationTarget==='remote'?'remote gen':'local'}</>:health?'not reachable':'server offline'}</div>
      <div className="comfy-sum"><b>{comfyDone}</b> Comfy workflows ran for this project{comfySecs?<> · <b>{fmtS(comfySecs)}</b> of model time</>:''}</div>
    </div>
    <ol className="steps">
      {statuses.map(({def,st},i)=><li key={def.id} className={`step st-${st.state} eng-${def.engine}`}>
        <div className="step-rail"><span className="step-led"/>{i<STEPS.length-1&&<span className="step-wire"/>}</div>
        <div className="step-body">
          <div className="step-top"><span className="step-title">{def.title}</span><span className={`eng eng-${def.engine}`}>{ENGINE[def.engine]}</span>{st.seconds!=null&&st.state!=='running'&&<span className="step-time">{fmtS(st.seconds)}</span>}</div>
          <div className="step-model">{def.model}</div>
          <div className="step-path"><span className={`path path-${st.state}`}>{st.state==='done'?'✓':st.state==='fallback'?'↺':st.state==='failed'?'✕':st.state==='running'?'●':'○'} {st.path}</span><span className="step-note">{st.engineNote}</span></div>
          {st.state==='running'&&<div className="step-progress"><i style={{width:`${Math.round((st.progress||0)*100)}%`}}/><span>{st.message}</span></div>}
          {st.state==='failed'&&st.message&&<div className="step-err">{st.message}</div>}
          {def.nodes.length>0&&<div className="step-nodes">{def.nodes.map((n,k)=><span key={k}>{n}</span>)}</div>}
          <div className="step-actions">
            {def.workflow&&<button className="link" onClick={()=>onOpenWorkflow(def)}>Workflow ↗</button>}
            {runnable[def.id]&&project.id!=='sample'&&<button className="mini" disabled={busy} onClick={()=>onRun(def.id)}>{st.state==='done'?'Re-run':runnable[def.id]}</button>}
          </div>
        </div>
      </li>)}
    </ol>
  </div>;
}

type Node = {id:string;cls:string;inputs:[string,string][];refs:string[];title?:string};
/** Read-only view of a ComfyUI API-format workflow: nodes in dependency order with their links and literal inputs. */
export function WorkflowSheet({step,onClose}:{step:StepDef;onClose:()=>void}){
  const [nodes,setNodes]=useState<Node[]|null>(null);const [err,setErr]=useState('');
  useEffect(()=>{if(!step.workflow)return;fetch(step.workflow.href).then(r=>{if(!r.ok)throw new Error(`${r.status}`);return r.json();}).then((g:Record<string,{class_type:string;inputs:Record<string,unknown>;_meta?:{title?:string}}>)=>{
    const list:Node[]=Object.entries(g).map(([id,n])=>({id,cls:n.class_type,title:n._meta?.title,refs:Object.values(n.inputs).filter((v):v is [string,number]=>Array.isArray(v)&&typeof v[0]==='string').map(v=>v[0]),
      inputs:Object.entries(n.inputs).map(([k,v])=>[k,Array.isArray(v)?`← #${v[0]}${v[1]?`.${v[1]}`:''}`:typeof v==='string'&&v.length>48?v.slice(0,46)+'…':JSON.stringify(v)] as [string,string])}));
    const depth=new Map<string,number>();const d=(id:string,seen=new Set<string>()):number=>{if(depth.has(id))return depth.get(id)!;if(seen.has(id))return 0;seen.add(id);const n=list.find(x=>x.id===id);const v=n&&n.refs.length?1+Math.max(...n.refs.map(r=>d(r,seen))):0;depth.set(id,v);return v;};
    list.forEach(n=>d(n.id));list.sort((a,b)=>depth.get(a.id)!-depth.get(b.id)!||Number(a.id)-Number(b.id));setNodes(list);}).catch(e=>setErr(String(e)));},[step]);
  return <div className="sheet-backdrop" onClick={onClose}><div className="wf-sheet" role="dialog" aria-label={`${step.title} workflow`} onClick={e=>e.stopPropagation()}>
    <header><div><span className="eng eng-comfy">ComfyUI workflow</span><b>{step.title}</b><code>{step.workflow?.repo}</code></div><div className="wf-actions"><a href={step.workflow?.href} target="_blank" rel="noreferrer">Open JSON ↗</a><button onClick={onClose}>Close</button></div></header>
    {err&&<p className="step-err">{err}</p>}
    <div className="wf-graph">{nodes?.map(n=><div key={n.id} className={`wf-node ${/Whisper|BiRefNet|LTXV|AudioBeat|TypesetTextPlate|MaskToTracks/.test(n.cls)?'key':''}`}>
      <div className="wf-cls"><span>#{n.id}</span>{n.cls}</div>
      {n.inputs.map(([k,v])=><div key={k} className={`wf-in ${v.startsWith('←')?'link':''}`}><span>{k}</span><em>{v}</em></div>)}
    </div>)}</div>
    <footer>API-format graph submitted by the Typeset server through the Comfy SDK. Node ids belong to the workflow sidecar ({step.workflow?.repo.replace('.api.json','.inputs.json')}).</footer>
  </div></div>;
}
