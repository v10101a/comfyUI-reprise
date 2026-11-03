import {useEffect,useMemo,useRef,useState} from 'react';
import type {Asset,WorkflowDraft,Job,LayerGeneration,MediaLayer,Project} from '../types';
import {request} from '../api';
import {assetOf,layersOf} from '../layers';
import {Icon} from './icons';
import {type Workflow,type WfInput,type WfSource,deleteWorkflow,importWorkflow,inputKey,listWorkflows,updateWorkflow} from './workflows';
import {type Audition,layerTakes,mergeAssets,setGeneration,useTake,visualLayer} from './takes';
import {ASSET_MIME} from './duration';
import {sceneForId,setSceneGeneration,patchScene,type Scene} from './scenes';
import {SceneThumb} from './SceneThumb';
import './workflows.css';

const FOOT='@frame',RANGE='@range',LAYER='@layer',SONG='@song',PREPARED='@prepared';
type Props={scene?:Scene;project:Project;edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void;time:number;range:{a:number;b:number}|null;
  selected:string;onSelect:(id:string)=>void;audition:Audition|null;onAudition:(a:Audition|null)=>void;onSeek:(t:number)=>void;
  sourcePreview:string;onPreview:(assetId:string)=>void;
  onPlace:(assetId:string,time:number,generation?:LayerGeneration)=>void;prepare:()=>Promise<void>};

/** Clips can supply a generation recipe; every result is reusable footage in the project bin. */
export function WorkflowsPanel({scene,project,edit,checkpoint,time,range,selected,onSelect,audition,onAudition,onSeek,sourcePreview,onPreview,onPlace,prepare}:Props){
  const [list,setList]=useState<Workflow[]>([]),[loading,setLoading]=useState(true),[mapping,setMapping]=useState(false);
  const [loose,setLoose]=useState<LayerGeneration>({}),[jobs,setJobs]=useState<Job[]>([]),[preparing,setPreparing]=useState(false),[error,setError]=useState('');
  const [pick,setPick]=useState(''),[more,setMore]=useState(false);
  const [scope,setScope]=useState<'all'|'clip'>('all');
  const file=useRef<HTMLInputElement>(null),ref=useRef<HTMLInputElement>(null);
  const refTarget=useRef({key:'',wid:'',layerId:'',sceneId:'',recipeId:''}),mounted=useRef(true),starting=useRef(false);
  const knownAssets=useRef(new Set<string>());knownAssets.current=new Set((project.assets||[]).map(a=>a.id));
  const mediaLayers=layersOf(project).filter((l):l is MediaLayer=>l.kind==='media');
  const layer=visualLayer(project,selected),generation=scene?.generation||layer?.generation||(!layer?loose:{});
  const wid=generation.workflowId||list[0]?.id||'',wf=list.find(w=>w.id===wid);
  const draft=generation.workflows?.[wid]||{},vals=draft.inputs||{},sources=draft.sources||{};
  const hasSeed=!!wf&&Object.values(wf.inputs).some(i=>i.role==='seed'),variants=hasSeed?draft.variants||1:1;
  const activeJobs=jobs.filter(j=>j.status==='queued'||j.status==='running'),running=preparing||activeJobs.length>0;
  const results=useMemo(()=>scope==='clip'&&layer?layerTakes(project,layer.id):
    (project.assets||[]).filter(a=>a.source?.kind==='workflow'||a.source?.kind==='comfy'||a.id===layer?.assetId),[project.assets,layer,scope]);
  const picked=results.find(a=>a.id===pick),previewing=!!layer&&audition?.layerId===layer.id;
  const fail=(e:unknown)=>{if(mounted.current)setError(e instanceof Error?e.message:String(e));};
  const refresh=async()=>{try{const next=await listWorkflows();if(mounted.current)setList(next);}catch(e){fail(e);}finally{if(mounted.current)setLoading(false);}};
  const patch=(changes:WorkflowDraft={},workflowId=wid)=>{
    if(scene)edit(p=>setSceneGeneration(p,scene.id,workflowId,changes));
    else if(layer)edit(p=>setGeneration(p,layer.id,workflowId,changes));
    else setLoose(g=>({...g,workflowId,workflows:{...g.workflows,[workflowId]:{...g.workflows?.[workflowId],...changes}}}));
  };
  const setVal=(k:string,v:unknown)=>patch({inputs:{...vals,[k]:v}});
  // Resume polling after opening a project; outputs stay on the server even if this panel is closed.
  async function watch(start:Job,sceneId?:string){
    let j=start;
    while(mounted.current){
      setJobs(js=>[...js.filter(x=>x.id!==j.id),j]);
      const got=((j.result as {assets?:Asset[]}|undefined)?.assets||[]).map(a=>sceneId?{...a,source:{...a.source,kind:a.source?.kind||'workflow' as const,sceneId}}:a);
      if(got.some(a=>!knownAssets.current.has(a.id)))edit(p=>mergeAssets(p,project.id,got));
      if(j.status!=='queued'&&j.status!=='running'){if(j.status==='failed')fail(j.message||'Generation failed');return;}
      await new Promise(resolve=>setTimeout(resolve,900));if(!mounted.current)return;
      j=await request<Job>(`/api/jobs/${j.id}`);
    }
  }
  useEffect(()=>{mounted.current=true;void refresh();
    void request<Job[]>(`/api/jobs?projectId=${encodeURIComponent(project.id)}`).then(js=>{
      if(!mounted.current)return;const active=js.filter(j=>j.kind==='workflow'&&(j.status==='queued'||j.status==='running'));
      const arrived=js.filter(j=>j.kind==='workflow').flatMap(j=>(j.result as {assets?:Asset[]}|undefined)?.assets||[]);
      if(arrived.some(a=>!knownAssets.current.has(a.id)))edit(p=>mergeAssets(p,project.id,arrived));
      setJobs(active);for(const j of active)void watch(j).catch(fail);
    }).catch(()=>{});
    return()=>{mounted.current=false;};
  },[]);
  useEffect(()=>{const focus=()=>void refresh();window.addEventListener('focus',focus);
    return()=>window.removeEventListener('focus',focus);},[]);
  useEffect(()=>{setPick('');setMapping(false);setMore(false);onAudition(null);},[selected,scene?.id,wid]);
  useEffect(()=>{if(scene&&wf&&!scene.generation?.workflowId)edit(p=>setSceneGeneration(p,scene.id,wf.id));
    else if(!scene&&layer&&wf&&!layer.generation?.workflowId)edit(p=>setGeneration(p,layer.id,wf.id));},[scene?.id,layer?.id,wf?.id]);

  async function importFile(f:File){
    setError('');try{const w=await importWorkflow(JSON.parse(await f.text()),f.name.replace(/\.(api\.)?json$/i,''));
      if(!mounted.current)return;setList(ls=>[w,...ls]);patch({},w.id);setMapping(!w.output);
    }catch(e){fail(e);}
  }
  const sourceId=(k:string,inp:WfInput)=>sources[k]||
    (inp.media==='audio'?(draft.mediaFiles?.[k]?PREPARED:project.media.audio||project.media.video?SONG:''):
    (scene?scene.refs.find(id=>inp.media!=='video'||assetOf(project,id)?.kind==='video')||'':layer&&(inp.media!=='video'||assetOf(project,layer.assetId)?.kind==='video')?LAYER:project.media.video?(inp.media==='video'?RANGE:FOOT):''));
  function source(k:string,inp:WfInput):WfSource{
    const s=sourceId(k,inp);
    if(s===PREPARED){const f=draft.mediaFiles![k];return {path:f.path,start:0,end:f.duration};}
    if(s===SONG)return range?{start:range.a,end:range.b}:layer?{start:Math.max(0,layer.start),end:layer.start+layer.out-layer.in}:{start:time,end:time+3};
    if(inp.media==='audio'&&s!==LAYER){const a=assetOf(project,s);return {assetId:s,start:0,end:a?.duration||5};}
    if(s===LAYER&&layer){const at=Math.max(layer.in,Math.min(layer.out-1/project.fps,layer.in+time-layer.start));
      return inp.media==='video'||inp.media==='audio'?{assetId:layer.assetId,start:layer.in,end:layer.out}:{assetId:layer.assetId,time:at};}
    if(s===FOOT)return {time};if(s===RANGE)return range?{start:range.a,end:range.b}:{start:time,end:time+3};
    return {assetId:s,time:0};
  }
  const missingReference=!!wf&&Object.entries(wf.inputs).some(([k,i])=>i.role==='media'&&(!sourceId(k,i)||
    (sourceId(k,i)===PREPARED&&!draft.mediaFiles?.[k])||
    (i.media==='audio'&&!sourceId(k,i).startsWith('@')&&!assetOf(project,sourceId(k,i))?.hasAudio)||
    (i.media==='audio'&&sourceId(k,i)===LAYER&&!assetOf(project,layer?.assetId||'')?.hasAudio)||
    (!sourceId(k,i).startsWith('@')&&!assetOf(project,sourceId(k,i)))||
    (i.media==='video'&&sourceId(k,i)!==RANGE&&assetOf(project,sourceId(k,i)===LAYER?layer?.assetId||'':sourceId(k,i))?.kind!=='video')));
  const postprocess=wf&&Object.entries(wf.inputs).some(([k,i])=>i.media==='audio'&&sourceId(k,i)===PREPARED)?draft.postprocess:undefined;
  const blocked=project.id==='sample'?'Open or create a project to generate a take.':
    !wf?'Choose a workflow first.':!wf.output?'Choose an output in the workflow settings.':
    wf.readinessError|| (wf.missing.length?'This workflow needs nodes that are unavailable on the selected ComfyUI.':
    wf.missingModels?.length?'This workflow needs models that are unavailable on the selected ComfyUI.':
    missingReference?'Choose or upload a reference for each input.':'');
  async function run(){
    if(!wf||blocked||starting.current||running)return;starting.current=true;setPreparing(true);setError('');
    const inputs:Record<string,unknown>={},runSources:Record<string,WfSource>={};
    for(const [k,inp] of Object.entries(wf.inputs)){if(inp.role==='media')runSources[k]=source(k,inp);else if(k in vals)inputs[k]=vals[k];}
    try{
      await prepare();
      const start=await request<Job>(`/api/projects/${project.id}/workflows/${wf.id}/run`,{method:'POST',body:JSON.stringify({inputs,sources:runSources,variants,layerId:layer?.id,sceneId:scene?.id,remote:wf.target==='remote',postprocess})});
      if(mounted.current)void watch(start,scene?.id).catch(fail);
    }catch(e){fail(e);}finally{starting.current=false;if(mounted.current)setPreparing(false);}
  }
  async function addRef(f:File){
    const target={...refTarget.current},pid=project.id;setError('');
    const form=new FormData();form.append('file',f);
    try{const a=await request<Asset>(`/api/projects/${pid}/assets`,{method:'POST',body:form});if(!mounted.current)return;
      edit(p=>{if(p.id!==pid)return p;const q=mergeAssets(p,pid,[a]);
        if(target.sceneId){const s=sceneForId(q,target.sceneId);if(!s)return q;
          const next=patchScene(q,s.id,{refs:[...new Set([...s.refs,a.id])]});
          const recipeId=target.recipeId||target.sceneId,generation=s.recipes?.find(r=>r.id===recipeId)?.generation||s.generation;
          return setSceneGeneration(next,s.id,target.wid,{sources:{...generation?.workflows?.[target.wid]?.sources,[target.key]:a.id}},recipeId);}
        if(!target.layerId)return q;const prev=visualLayer(q,target.layerId)?.generation?.workflows?.[target.wid]?.sources;
        return setGeneration(q,target.layerId,target.wid,{sources:{...prev,[target.key]:a.id}});});
      if(!target.layerId&&!target.sceneId)setLoose(g=>{const prev=g.workflows?.[target.wid]||{};return {...g,workflows:{...g.workflows,
        [target.wid]:{...prev,sources:{...prev.sources,[target.key]:a.id}}}};});
    }catch(e){fail(e);}
  }
  function auditionTake(a:Asset){
    setPick(a.id);onPreview('');if(!layer)return;
    onAudition(a.id===layer.assetId?null:{layerId:layer.id,assetId:a.id});
    if(time<layer.start||time>=layer.start+layer.out-layer.in)onSeek(layer.start);
  }
  function accept(){
    if(!picked||!layer)return;checkpoint();edit(p=>useTake(p,layer.id,picked.id));
    onPreview('');onAudition(null);
  }
  const mediaInputs=wf?Object.entries(wf.inputs).filter(([,i])=>i.role==='media'):[];
  const otherInputs=wf?Object.entries(wf.inputs).filter(([,i])=>i.role!=='media'):[];
  return <div className="wf-panel">
    {!scene&&<div className="wf-context">
      <label htmlFor="take-layer">Reference clip <span>optional</span></label>
      <select id="take-layer" value={layer?.id||''} onChange={e=>{onAudition(null);onSelect(e.target.value);}} aria-label="Reference clip">
        <option value="">None · new footage</option>{mediaLayers.map(l=><option key={l.id} value={l.id}>{l.name||assetOf(project,l.assetId)?.name||'Clip'}</option>)}
      </select>
      <p>{layer?'Uses this clip’s references and settings. ':''}Every take is saved as footage. Drag any number onto the timeline to trim and combine.</p>
    </div>}
    <div className="wf-section-title"><b>Workflow</b><span>ComfyUI</span></div>
    <div className="wf-head">
      <select value={wid} onChange={e=>{patch({},e.target.value);setMapping(false);}} aria-label="Workflow" title={wf?`${wf.nodes} nodes`:undefined}>
        {!list.length&&<option value="">{loading?'Loading…':'Import a workflow'}</option>}
        {wid&&!wf&&!!list.length&&<option value={wid}>Workflow unavailable</option>}
        {list.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select>
      <button className="icon-sm" onClick={()=>file.current?.click()} title="Import ComfyUI API workflow (.json)" aria-label="Import workflow"><Icon name="upload" size={15}/></button>
      {wf&&<button className={`icon-sm ${mapping?'on':''}`} onClick={()=>setMapping(m=>!m)} title="Choose inputs and output" aria-label="Choose inputs and output" aria-pressed={mapping}><Icon name="keys" size={15}/></button>}
      <input ref={file} type="file" accept=".json,application/json" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void importFile(f);}}/>
      <input ref={ref} type="file" accept="image/*,video/*" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void addRef(f);}}/>
    </div>
    {!loading&&!list.length&&<div className="wf-empty"><p>Bring a workflow from ComfyUI. Choose its references and prompt here, then compare the results with your music.</p>
      <button onClick={()=>file.current?.click()}>Import workflow JSON</button><small>Use ComfyUI’s Export (API), or import from its Reprise sidebar.</small></div>}
    {error&&<div className="wf-err" role="alert">{error}<button className="icon-sm" aria-label="Dismiss generation error" onClick={()=>setError('')}>×</button></div>}
    {wf?.missing.length?<div className="wf-err">Missing nodes: {wf.missing.join(', ')}</div>:null}
    {!!wf?.missingModels?.length&&<details className="wf-unavailable"><summary>{wf.missingModels.length} models unavailable on {wf.target==='remote'?'remote':'local'} ComfyUI</summary>
      <p>{wf.missingModels.join(', ')}</p><button onClick={()=>void refresh()}>Check again</button></details>}
    {wf&&mapping&&<><Mapping key={wf.id} wf={wf} onSave={patch=>void updateWorkflow(wf.id,patch).then(w=>{setList(ls=>ls.map(x=>x.id===w.id?w:x));setMapping(false);}).catch(fail)}/>
      <button className="danger" onClick={()=>{if(confirm(`Remove ${wf.name}?`))void deleteWorkflow(wf.id).then(()=>refresh()).catch(fail);}}>Remove workflow</button></>}
    {wf&&!mapping&&<>
      {mediaInputs.length>0&&<><div className="wf-section-title"><b>References</b><span>{mediaInputs.length} input{mediaInputs.length===1?'':'s'}</span></div>
        <div className="wf-references">{mediaInputs.map(([k,inp])=>{const value=sourceId(k,inp),a=assetOf(project,value===LAYER?layer?.assetId||'':value);
          return <div className="wf-reference" key={k}>
            <div className="wf-reference-image">{a?<TakeThumb project={project} asset={a}/>:<Icon name="media" size={20}/>}</div>
            <div className="wf-reference-field"><label htmlFor={`ref-${k}`}>{inp.title}</label>
              <select id={`ref-${k}`} value={value} onChange={e=>patch({sources:{...sources,[k]:e.target.value}})} aria-label={`Reference: ${inp.title}`}>
                <option value="" disabled>Choose a reference</option>
                {inp.media==='audio'&&draft.mediaFiles?.[k]&&<option value={PREPARED}>{draft.mediaFiles[k].name}</option>}
                {inp.media==='audio'&&(project.media.audio||project.media.video)&&<option value={SONG}>Song · {layer?'selected shot window':'playhead window'}</option>}
                {layer&&(inp.media==='audio'?assetOf(project,layer.assetId)?.hasAudio:inp.media!=='video'||assetOf(project,layer.assetId)?.kind==='video')&&<option value={LAYER}>Current take{inp.media==='audio'?' · sound':inp.media==='video'?'':' · frame'}</option>}
                {project.media.video&&inp.media!=='video'&&inp.media!=='audio'&&<option value={FOOT}>Footage at playhead</option>}
                {project.media.video&&inp.media==='video'&&<option value={RANGE}>{range?'Loop range':'3 s from playhead'}</option>}
                {(project.assets||[]).filter(a=>inp.media==='audio'?a.hasAudio:inp.media!=='video'||a.kind==='video').map(a=><option key={a.id} value={a.id}>{a.name||a.path.split('/').pop()}</option>)}
              </select></div>
            {inp.media!=='audio'&&<button className="icon-sm" disabled={project.id==='sample'} onClick={()=>{refTarget.current={key:k,wid,layerId:layer?.id||'',sceneId:scene?.id||'',recipeId:scene?.recipeId||''};if(ref.current)ref.current.accept=inp.media==='video'?'video/*':'image/*,video/*';ref.current?.click();}} title="Upload reference" aria-label={`Upload reference: ${inp.title}`}><Icon name="plus" size={14}/></button>}
            {scene&&inp.media!=='audio'&&<div className="scene-source-choices" aria-label={`Scene references for ${inp.title}`}>
              {[...new Set([...scene.refs,...scene.takes])].filter(id=>inp.media!=='video'||assetOf(project,id)?.kind==='video').map(id=>{const a=assetOf(project,id);return a&&<button key={id} title={a.name||'Reference'} aria-label={`Use reference ${a.name||id}`} aria-pressed={value===id} className={value===id?'active':''} onClick={()=>patch({sources:{...sources,[k]:id}})}><TakeThumb project={project} asset={a}/></button>;})}
            </div>}
          </div>;})}</div></>}
      {postprocess&&<p className="wf-note">Imported vocal timing · returns at {postprocess.fps} fps, {postprocess.trimStart.toFixed(2)} s pre-roll removed. The prepared vocal stays fixed when you move this shot.</p>}
      {otherInputs.map(([k,inp])=>{
        if(inp.role==='prompt')return <label className="wf-prompt" key={k}><span>{inp.title}</span><textarea rows={4} value={String(vals[k]??inp.default??'')} aria-label={inp.title} placeholder="Describe the movement, mood, and details you want to explore…" onChange={e=>setVal(k,e.target.value)}/></label>;
        if(inp.role==='bool')return <label key={k} className="check" title={inp.title}><input type="checkbox" checked={!!(vals[k]??inp.default)} onChange={e=>setVal(k,e.target.checked)}/>{inp.field}</label>;
        const seed=inp.role==='seed';
        return <div className="wf-row" key={k} title={`${inp.title} · ${inp.field}`}><span className="lbl">{seed?'Seed':inp.field.replace(/_/g,' ')}</span>
          <input type={inp.role==='text'?'text':'number'} aria-label={seed?`Seed: ${inp.title}`:inp.title} className="mono" min={inp.min} max={inp.max} step={inp.step} placeholder={seed?'random':undefined}
            value={String(vals[k]??(seed?'':inp.default??''))} onChange={e=>setVal(k,inp.role==='text'?e.target.value:e.target.value===''?undefined:Number(e.target.value))}/></div>;
      })}
      <div className="wf-run">
        <div className="seg mini" role="radiogroup" aria-label="Variants" title="Number of takes to generate">{[1,2,4].map(n=>
          <button key={n} role="radio" aria-checked={variants===n} className={variants===n?'active':''} disabled={n>1&&!hasSeed} title={n>1&&!hasSeed?'Expose a seed input to generate different takes':undefined} onClick={()=>patch({variants:n})}>{n}×</button>)}</div>
        <button className="primary" onClick={()=>void run()} disabled={running||!!blocked} aria-describedby="wf-run-status" title={blocked||undefined}>
          {preparing?'Preparing…':activeJobs.length?`Generating ${Math.round((activeJobs[0].progress||0)*100)}%`:`Generate ${variants===1?'take':`${variants} takes`}`}</button>
      </div>
      <div id="wf-run-status" className="wf-note" role="status">{blocked||`Runs on ${wf.target==='remote'?'remote GPU':'local ComfyUI'}.`}
        {!!blocked&&<button className="wf-more" onClick={()=>void refresh()}>Check again</button>}</div>
      {activeJobs.length>0&&<p className="wf-note" role="status">{activeJobs[0].message||'Queued'} · You can keep editing.</p>}
    </>}
    {!scene&&<><div className="wf-section-title wf-takes-title"><b>Generated footage</b><span>{results.length}</span></div>
    <div className="seg mini" role="radiogroup" aria-label="Show takes">
      <button role="radio" aria-checked={scope==='all'||!layer} className={scope==='all'||!layer?'active':''} onClick={()=>{setScope('all');setMore(false);}}>All takes</button>
      <button role="radio" aria-checked={scope==='clip'&&!!layer} className={scope==='clip'&&layer?'active':''} disabled={!layer} onClick={()=>{setScope('clip');setMore(false);}}>This clip</button>
    </div>
    {results.length===0?<p className="wf-note">Your generated footage will appear here.</p>:<>
      <p className="wf-note">Click to preview the full take. Drag it onto the timeline to use it.</p>
      <div className="wf-grid" role="listbox" aria-label="Takes">{(more?results:[...results].reverse().slice(0,8)).map(a=>
        <button key={a.id} role="option" draggable onDragStart={e=>{e.dataTransfer.setData(ASSET_MIME,a.id);e.dataTransfer.effectAllowed='copy';onPreview('');onAudition(null);}}
          aria-selected={a.id===(pick||layer?.assetId)} className={`${a.id===(pick||layer?.assetId)?'on':''} ${a.id===layer?.assetId?'current':''}`}
          onClick={()=>{setPick(a.id);onPreview(a.id);}} aria-label={`Preview ${a.name||'take'}`} title={`${a.name||''}${a.source?.seed!=null?` · seed ${a.source.seed}`:''} · drag to timeline`}>
          <TakeThumb project={project} asset={a}/><span className="wf-take-caption"><span>{a.name||'Take'}</span><em>{a.id===layer?.assetId?'Current':a.source?.seed!=null?`#${a.source.seed}`:a.kind}</em></span>
        </button>)}</div>
      {results.length>8&&<button className="wf-more" onClick={()=>setMore(v=>!v)}>{more?'Show recent takes':`Show all ${results.length} takes`}</button>}
      {picked&&<div className="wf-take-actions">
        <button aria-pressed={sourcePreview===picked.id} onClick={()=>onPreview(picked.id)}>Preview full take</button>
        {layer&&picked.id!==layer.assetId&&<div className="seg" role="group" aria-label="Compare takes">
          <button className={!previewing&&!sourcePreview?'active':''} aria-pressed={!previewing&&!sourcePreview} onClick={()=>{onPreview('');onAudition(null);}}>Current</button>
          <button className={previewing?'active':''} aria-pressed={previewing} onClick={()=>auditionTake(picked)}>Candidate</button></div>}
        <button className="primary" onClick={()=>{onPreview('');onAudition(null);onPlace(picked.id,time,!layer&&picked.source?.workflowId===wid?loose:undefined);}}>Add to timeline</button>
        {layer&&<button onClick={accept} disabled={picked.id===layer.assetId}>Replace selected clip</button>}
        {layer&&picked.kind==='video'&&!!picked.duration&&picked.duration<layer.out&&<small>Replacing this clip holds the take’s last frame to fill its length. Add to timeline uses the full source as a new clip.</small>}
      </div>}
    </>}
    </>}
  </div>;
}

function TakeThumb({project,asset}:{project:Project;asset:Asset}){
  return <SceneThumb project={project} asset={asset}/>;
}

function Mapping({wf,onSave}:{wf:Workflow;onSave:(patch:Pick<Workflow,'inputs'|'output'>)=>void}){
  const on=(n:string,f:string)=>Object.values(wf.inputs).some(i=>i.node===n&&i.field===f);
  const [sel,setSel]=useState(()=>new Set(wf.candidates.inputs.filter(c=>on(c.node,c.field)).map(c=>`${c.node}.${c.field}`)));
  const [out,setOut]=useState(wf.output?.node||'');
  const byNode=wf.candidates.inputs.reduce<Record<string,typeof wf.candidates.inputs>>((m,c)=>{(m[c.node]||=[]).push(c);return m;},{});
  function save(){
    const inputs:Record<string,WfInput>={};const taken=new Set<string>();
    for(const c of wf.candidates.inputs){if(!sel.has(`${c.node}.${c.field}`))continue;
      const existing=Object.entries(wf.inputs).find(([,i])=>i.node===c.node&&i.field===c.field);
      const k=existing?.[0]&&!taken.has(existing[0])?existing[0]:inputKey(c,taken);taken.add(k);
      inputs[k]={node:c.node,field:c.field,kind:c.kind,role:c.role,title:c.title,default:existing?.[1].default??c.value};}
    const o=wf.candidates.outputs.find(x=>x.node===out);
    onSave({inputs,output:o?{node:o.node,type:o.type}:wf.output});
  }
  return <div className="wf-map">
    {Object.entries(byNode).map(([node,cs])=><fieldset key={node}><legend title={cs[0].classType}>{cs[0].title}</legend>
      {cs.map(c=><label key={c.field} className="check" title={`${c.role} · ${JSON.stringify(c.value)?.slice(0,60)}`}>
        <input type="checkbox" checked={sel.has(`${c.node}.${c.field}`)} onChange={e=>setSel(s=>{const n=new Set(s);const id=`${c.node}.${c.field}`;if(e.target.checked)n.add(id);else n.delete(id);return n;})}/>{c.field}</label>)}
    </fieldset>)}
    <fieldset><legend>Output</legend>{wf.candidates.outputs.map(o=><label key={o.node} className="check" title={o.classType}>
      <input type="radio" name={`out-${wf.id}`} checked={out===o.node} onChange={()=>setOut(o.node)}/>{o.title}</label>)}</fieldset>
    <button className="primary" onClick={save} disabled={!out}>Save</button>
  </div>;
}
