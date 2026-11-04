import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import type {Asset,WorkflowDraft,Job,LayerGeneration,MediaLayer,Project} from '../types';
import {request,assetUrl} from '../api';
import {assetOf,layersOf} from '../layers';
import {Icon} from './icons';
import {type Workflow,type WfInput,type WfSource,deleteWorkflow,importWorkflow,inputKey,listWorkflows,updateWorkflow} from './workflows';
import {type Audition,layerTakes,mergeAssets,setGeneration,useTake,visualLayer} from './takes';
import {ASSET_MIME} from './duration';
import {sceneForId,scenesOf,setSceneGeneration,patchScene,type Scene} from './scenes';
import {SceneThumb} from './SceneThumb';
import {assetGeneration,takeGeneration,relatedReferences,inheritedReference,setTakeGeneration} from './generationContext';
import {ReferencePicker,WorkflowPicker,type SourceChoice} from './GenerationPickers';
import {ReferenceAudio} from './ReferenceAudio';
import {at} from '../base';
import {GENERATION_PRESETS,openSetup,type GenerationPreset} from '../setup';
import './workflows.css';

const FOOT='@frame',RANGE='@range',LAYER='@layer',SONG='@song',PREPARED='@prepared';
type Props={scene?:Scene;selectedTake?:string;project:Project;edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void;time:number;range:{a:number;b:number}|null;
  selected:string;onSelect:(id:string)=>void;audition:Audition|null;onAudition:(a:Audition|null)=>void;onSeek:(t:number)=>void;
  sourcePreview:string;onPreview:(assetId:string)=>void;
  onPlace:(assetId:string,time:number,generation?:LayerGeneration)=>void;prepare:()=>Promise<void>};

/** Clips can supply a generation recipe; every result is reusable footage in the project bin. */
export function WorkflowsPanel({scene,selectedTake='',project,edit,checkpoint,time,range,selected,onSelect,audition,onAudition,onSeek,sourcePreview,onPreview,onPlace,prepare}:Props){
  const [list,setList]=useState<Workflow[]>([]),[loading,setLoading]=useState(true),[mapping,setMapping]=useState(false);
  const [loose,setLoose]=useState<LayerGeneration>({}),[jobs,setJobs]=useState<Job[]>([]),[preparing,setPreparing]=useState(false),[error,setError]=useState('');
  const [pick,setPick]=useState(''),[more,setMore]=useState(false);
  const [target,setTarget]=useState<'local'|'remote'>('local'),[presets,setPresets]=useState(false),[adding,setAdding]=useState('');
  const [available,setAvailable]=useState<boolean|null>(null);
  const refreshId=useRef(0),targetRef=useRef(target);targetRef.current=target;
  const [scope,setScope]=useState<'all'|'clip'>('all');
  const [referencePicker,setReferencePicker]=useState(''),[workflowPicker,setWorkflowPicker]=useState(false);
  const file=useRef<HTMLInputElement>(null),ref=useRef<HTMLInputElement>(null);
  const refTarget=useRef({key:'',wid:'',layerId:'',sceneId:'',recipeId:'',takeId:''}),mounted=useRef(true),starting=useRef(false);
  const knownAssets=useRef(new Set<string>());knownAssets.current=new Set((project.assets||[]).map(a=>a.id));
  const mediaLayers=layersOf(project).filter((l):l is MediaLayer=>l.kind==='media');
  const take=assetOf(project,selectedTake),fromTake=takeGeneration(project,scene,selectedTake),original=assetGeneration(take);
  const originalDraft=original?.workflows?.[original.workflowId||''];
  const related=relatedReferences(project,selectedTake);
  const layer=visualLayer(project,selected),generation=fromTake||scene?.generation||layer?.generation||(!layer?loose:{});
  const wid=generation.workflowId||list[0]?.id||'',wf=list.find(w=>w.id===wid);
  const draft=generation.workflows?.[wid]||{},vals=draft.inputs||{},sources=draft.sources||{};
  const mediaFiles={...originalDraft?.mediaFiles,...draft.mediaFiles};
  const hasSeed=!!wf&&Object.values(wf.inputs).some(i=>i.role==='seed'),variants=hasSeed?draft.variants||1:1;
  const activeJobs=jobs.filter(j=>j.status==='queued'||j.status==='running'),running=preparing||activeJobs.length>0;
  const results=useMemo(()=>scope==='clip'&&layer?layerTakes(project,layer.id):
    (project.assets||[]).filter(a=>a.source?.kind==='workflow'||a.source?.kind==='comfy'||a.id===layer?.assetId),[project.assets,layer,scope]);
  const picked=results.find(a=>a.id===pick),previewing=!!layer&&audition?.layerId===layer.id;
  const fail=(e:unknown)=>{if(mounted.current)setError(e instanceof Error?e.message:String(e));};
  const refresh=async(force=false)=>{const id=++refreshId.current;setLoading(true);try{const next=await listWorkflows(targetRef.current==='remote',force);if(mounted.current&&id===refreshId.current){setList(next);setAvailable(true);setError('');}}catch(e){if(mounted.current&&id===refreshId.current){setAvailable(false);if(project.id!=='sample')fail(e);}}finally{if(mounted.current&&id===refreshId.current)setLoading(false);}};
  const patch=(changes:WorkflowDraft={},workflowId=wid)=>{
    if(scene&&take)edit(p=>{
      // A loose still inherits the scene's prompt/vocal, but supplies its own image.
      const initialized=!fromTake&&wf?setTakeGeneration(p,scene.id,take.id,wid,{...draft,sources:Object.fromEntries(Object.entries(wf.inputs).filter(([,i])=>i.role==='media').map(([k,i])=>[k,sourceId(k,i)])),sourceWindows:Object.fromEntries(Object.entries(draft.sourceWindows||{}).filter(([k])=>wf.inputs[k]?.media==='audio'))}):p;
      return setTakeGeneration(initialized,scene.id,take.id,workflowId,changes);
    });
    else if(scene)edit(p=>setSceneGeneration(p,scene.id,workflowId,changes));
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
  useEffect(()=>{mounted.current=true;
    void request<Job[]>(`/api/jobs?projectId=${encodeURIComponent(project.id)}`).then(js=>{
      if(!mounted.current)return;const active=js.filter(j=>j.kind==='workflow'&&(j.status==='queued'||j.status==='running'));
      const arrived=js.filter(j=>j.kind==='workflow').flatMap(j=>(j.result as {assets?:Asset[]}|undefined)?.assets||[]);
      if(arrived.some(a=>!knownAssets.current.has(a.id)))edit(p=>mergeAssets(p,project.id,arrived));
      setJobs(active);for(const j of active)void watch(j).catch(fail);
    }).catch(()=>{});
    return()=>{mounted.current=false;};
  },[]);
  useEffect(()=>{void refresh();},[target]);
  useEffect(()=>{const focus=()=>void refresh();window.addEventListener('focus',focus);
    return()=>window.removeEventListener('focus',focus);},[]);
  useEffect(()=>{setPick('');setMapping(false);setMore(false);setReferencePicker('');setWorkflowPicker(false);onAudition(null);},[selected,selectedTake,scene?.id,wid]);
  // Finish the default recipe before the next keyboard edit (including immediate scene deletion).
  useLayoutEffect(()=>{if(scene&&wf&&!generation.workflowId)patch({},wf.id);
    else if(!scene&&layer&&wf&&!layer.generation?.workflowId)edit(p=>setGeneration(p,layer.id,wf.id));},[scene?.id,selectedTake,layer?.id,wf?.id]);

  async function importFile(f:File){
    setError('');try{const w=await importWorkflow(JSON.parse(await f.text()),f.name.replace(/\.(api\.)?json$/i,''));
      if(!mounted.current)return;patch({},w.id);setMapping(!w.output);await refresh();
    }catch(e){fail(e);}
  }
  async function addPreset(p:GenerationPreset){
    if(available===false){openSetup('local');return;}
    if(adding)return;setAdding(p.id);setError('');
    try{const graph=await request<unknown>(`/workflows/${p.file}`);const w=await importWorkflow(graph,p.name);
      if(mounted.current){patch({},w.id);setPresets(false);setMapping(!w.output);await refresh();}}
    catch(e){fail(e);}finally{if(mounted.current)setAdding('');}
  }
  const compatible=(id:string,inp:WfInput)=>{const a=assetOf(project,id);return !!a&&(inp.media==='audio'?!!a.hasAudio:inp.media!=='video'||a.kind==='video');};
  const sourceId=(k:string,inp:WfInput)=>{
    if(sources[k]&&(!take||fromTake||inp.media==='audio'))return sources[k];
    if(inp.media==='audio')return mediaFiles[k]?PREPARED:project.media.audio||project.media.video?SONG:'';
    const inherited=inheritedReference(project,selectedTake,k);if(inherited&&compatible(inherited,inp))return inherited;
    if(take&&inp.media==='video'&&take.kind==='video')return take.id;
    if(take&&inp.media!=='video')return (take.kind==='image'?take.id:related.find(id=>assetOf(project,id)?.kind==='image'))||take.id;
    return scene?scene.refs.find(id=>compatible(id,inp))||'':layer&&compatible(layer.assetId,inp)?LAYER:project.media.video?(inp.media==='video'?RANGE:FOOT):'';
  };
  function source(k:string,inp:WfInput):WfSource{
    const s=sourceId(k,inp),window=(!take||fromTake||inp.media==='audio')?(draft.sourceWindows?.[k]||(!sources[k]?originalDraft?.sourceWindows?.[k]:undefined)):undefined;
    if(s===PREPARED){const f=mediaFiles[k];return {path:f.path,start:0,end:f.duration,...window};}
    if(s===SONG)return {...(range?{start:range.a,end:range.b}:layer?{start:Math.max(0,layer.start),end:layer.start+layer.out-layer.in}:{start:time,end:time+3}),...window};
    if(inp.media==='audio'&&s!==LAYER){const a=assetOf(project,s);return {assetId:s,start:0,end:a?.duration||5,...window};}
    if(s===LAYER&&layer){const at=Math.max(layer.in,Math.min(layer.out-1/project.fps,layer.in+time-layer.start));
      return inp.media==='video'||inp.media==='audio'?{assetId:layer.assetId,start:layer.in,end:layer.out}:{assetId:layer.assetId,time:at};}
    if(s===FOOT)return {time,...window};if(s===RANGE)return {...(range?{start:range.a,end:range.b}:{start:time,end:time+3}),...window};
    return {assetId:s,...(inp.media==='video'?{start:0,end:assetOf(project,s)?.duration}: {time:0}),...window};
  }
  const missingReference=!!wf&&Object.entries(wf.inputs).some(([k,i])=>i.role==='media'&&(!sourceId(k,i)||
    (sourceId(k,i)===PREPARED&&!mediaFiles[k])||
    (i.media==='audio'&&!sourceId(k,i).startsWith('@')&&!assetOf(project,sourceId(k,i))?.hasAudio)||
    (i.media==='audio'&&sourceId(k,i)===LAYER&&!assetOf(project,layer?.assetId||'')?.hasAudio)||
    (!sourceId(k,i).startsWith('@')&&!assetOf(project,sourceId(k,i)))||
    (i.media==='video'&&sourceId(k,i)!==RANGE&&assetOf(project,sourceId(k,i)===LAYER?layer?.assetId||'':sourceId(k,i))?.kind!=='video')));
  const postprocess=wf&&Object.entries(wf.inputs).some(([k,i])=>i.media==='audio'&&sourceId(k,i)===PREPARED)?draft.postprocess||originalDraft?.postprocess:undefined;
  const modelInputs=wf?Object.entries(wf.inputs).filter(([,i])=>i.role==='model'):[];
  const missingModels=modelInputs.length?modelInputs.filter(([k,i])=>!i.choices?.includes(String(vals[k]??i.default??''))).map(([k,i])=>String(vals[k]??i.default??i.title)):wf?.missingModels||[];
  const blocked=project.id==='sample'?'Open or create a project to generate a take.':
    loading?'Checking the selected ComfyUI…':available===false?'Connect to Reprise to generate.':!wf?'Choose a workflow first.':wf.target&&wf.target!==target?'Refresh to connect to the selected ComfyUI.':!wf.output?'Choose an output in the workflow settings.':
    wf.readinessError|| (wf.missing.length?'This workflow needs nodes that are unavailable on the selected ComfyUI.':
    missingModels.length?'Choose installed models below, or download the missing files.':
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
        if(target.sceneId){const s=(target.takeId?scenesOf(q).find(s=>s.takes.includes(target.takeId)):undefined)||sceneForId(q,target.sceneId);if(!s)return q;
          const next=patchScene(q,s.id,{refs:[...new Set([...s.refs,a.id])]});
          if(target.takeId){const gen=takeGeneration(q,s,target.takeId)||s.generation;return setTakeGeneration(next,s.id,target.takeId,target.wid,{sources:{...gen?.workflows?.[target.wid]?.sources,[target.key]:a.id},sourceWindows:{...gen?.workflows?.[target.wid]?.sourceWindows,[target.key]:{}}});}
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
  const otherInputs=wf?Object.entries(wf.inputs).filter(([,i])=>i.role!=='media'&&i.role!=='model'):[];
  const chooseSource=(key:string,id:string)=>{patch({sources:{...sources,...Object.fromEntries(mediaInputs.map(([k,i])=>[k,sourceId(k,i)])),[key]:id},sourceWindows:{...draft.sourceWindows,[key]:{}},...(id===PREPARED?{mediaFiles:{...draft.mediaFiles,[key]:mediaFiles[key]}}:{})});setReferencePicker('');};
  const options=(key:string,inp:WfInput):SourceChoice[]=>[
    ...(inp.media==='audio'&&mediaFiles[key]?[{id:PREPARED,name:mediaFiles[key].name,detail:'Original prepared vocal'}]:[]),
    ...(inp.media==='audio'&&(project.media.audio||project.media.video)?[{id:SONG,name:'Song',detail:range?'Loop range':layer?'Selected clip range':'3 seconds from playhead'}]:[]),
    ...(layer&&compatible(layer.assetId,inp)?[{id:LAYER,name:'Timeline clip',detail:inp.media==='image'?'Frame at playhead':'Selected clip range'}]:[]),
    ...(project.media.video&&inp.media==='image'?[{id:FOOT,name:'Base video',detail:'Frame at playhead'}]:[]),
    ...(project.media.video&&inp.media==='video'?[{id:RANGE,name:'Base video',detail:range?'Loop range':'3 seconds from playhead'}]:[])];
  const nearby=[...new Set([selectedTake,...related,...scene?.refs||[],...scene?.takes||[],...Object.values(sources)])].filter(Boolean);
  const primaryInputs=otherInputs.filter(([k,i])=>i.role==='prompt'&&!/negative/i.test(`${k} ${i.title}`));
  const advancedInputs=otherInputs.filter(entry=>!primaryInputs.includes(entry));
  const inputControl=([k,inp]:[string,WfInput])=>{
    if(inp.role==='prompt')return <textarea key={k} className="wf-prompt" rows={4} value={String(vals[k]??inp.default??'')} aria-label={inp.title} title={inp.title} placeholder="Prompt…" onChange={e=>setVal(k,e.target.value)}/>;
    if(inp.role==='bool')return <label key={k} className="check" title={inp.title}><input type="checkbox" checked={!!(vals[k]??inp.default)} onChange={e=>setVal(k,e.target.checked)}/>{inp.field}</label>;
    const seed=inp.role==='seed';return <div className="wf-row" key={k} title={`${inp.title} · ${inp.field}`}><span className="lbl">{seed?'Seed':inp.field.replace(/_/g,' ')}</span><input type={inp.role==='text'?'text':'number'} aria-label={seed?`Seed: ${inp.title}`:inp.title} className="mono" min={inp.min} max={inp.max} step={inp.step} placeholder={seed?'random':undefined} value={String(vals[k]??(seed?'':inp.default??''))} onChange={e=>setVal(k,inp.role==='text'?e.target.value:e.target.value===''?undefined:Number(e.target.value))}/></div>;
  };
  return <div className="wf-panel" data-take-id={selectedTake}>
    <div className="wf-compute"><label>Run on <select aria-label="Run on" value={target} disabled={loading||running} onChange={e=>{if(e.target.value==='setup'){openSetup('cloud');return;}setTarget(e.target.value as 'local'|'remote');}}>
      <option value="local">My ComfyUI</option>{(wf?.targets||list[0]?.targets||[]).filter(t=>t.id==='remote').map(t=><option key={t.id} value={t.id}>{t.label}</option>)}<option value="setup">Set up Comfy Cloud…</option>
    </select></label><button className="ghost wf-setup" onClick={()=>openSetup('local')} title="Connect your existing ComfyUI"><Icon name="sliders" size={14}/>Setup</button></div>
    {!scene&&<div className="wf-context">
      <label htmlFor="take-layer">Reference clip <span>optional</span></label>
      <select id="take-layer" value={layer?.id||''} onChange={e=>{onAudition(null);onSelect(e.target.value);}} aria-label="Reference clip">
        <option value="">None · new footage</option>{mediaLayers.map(l=><option key={l.id} value={l.id}>{l.name||assetOf(project,l.assetId)?.name||'Clip'}</option>)}
      </select>
      <p>{layer?'Uses this clip’s references and settings. ':''}Every take is saved as footage. Drag any number onto the timeline to trim and combine.</p>
    </div>}
    <div className="wf-head">
      <button className="wf-workflow-choice" aria-label="Workflow" aria-haspopup="dialog" title={wf?.name} onClick={()=>setWorkflowPicker(true)}><span>{wf?.name||(loading?'Loading…':wid?'Workflow unavailable':'Choose a workflow')}</span><span aria-hidden="true">⌄</span></button>
      <button className="icon-sm" onClick={()=>available===false?openSetup('local'):file.current?.click()} title="Import ComfyUI API workflow (.json)" aria-label="Import workflow"><Icon name="upload" size={15}/></button>
      {wf&&<button className={`icon-sm ${mapping?'on':''}`} onClick={()=>setMapping(m=>!m)} title="Choose inputs and output" aria-label="Choose inputs and output" aria-pressed={mapping}><Icon name="keys" size={15}/></button>}
      <input ref={file} type="file" accept=".json,application/json" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void importFile(f);}}/>
      <input ref={ref} type="file" accept="image/*,video/*" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void addRef(f);}}/>
    </div>
    <button className="link wf-add" onClick={()=>setPresets(p=>!p)} aria-expanded={presets}><Icon name="plus" size={14}/>Add model workflow</button>
    {presets&&<div className="wf-presets">{GENERATION_PRESETS.map(p=><article key={p.id}><div className="wf-preset-title"><b title={`${p.description}\n${p.requirements}`}>{p.name}</b><button disabled={!!adding} aria-label={`Add ${p.name} workflow`} onClick={()=>void addPreset(p)}>{adding===p.id?'Adding…':'Add'}</button></div><small>{p.task}</small><div className="wf-preset-links"><a href={p.models} target="_blank" rel="noreferrer">Model files ↗</a><a href={at(`/workflows/${p.file}`)} download title="Download workflow JSON">Workflow JSON ↓</a></div></article>)}<p>Model files download separately.</p></div>}
    {workflowPicker&&<WorkflowPicker workflows={list} value={wid} related={[original?.workflowId||'',...Object.keys(scene?.generation?.workflows||{})]} onChoose={id=>{patch({},id);setMapping(false);setWorkflowPicker(false);}} onClose={()=>setWorkflowPicker(false)}/>}
    {referencePicker&&wf?.inputs[referencePicker]&&<ReferencePicker project={project} input={wf.inputs[referencePicker]} nearby={nearby} value={sourceId(referencePicker,wf.inputs[referencePicker])} choices={options(referencePicker,wf.inputs[referencePicker])} onChoose={id=>chooseSource(referencePicker,id)} onClose={()=>setReferencePicker('')}/>}
    {!loading&&!list.length&&<div className="wf-empty">{available===false?<><p>Try the edit here, then use your own ComfyUI and installed models to generate takes.</p><button onClick={()=>openSetup('local')}>Use my ComfyUI</button></>:<><p>Bring a workflow from ComfyUI. Choose its references and prompt here, then compare the results with your music.</p>
      <button onClick={()=>file.current?.click()}>Import workflow JSON</button><small>Use ComfyUI’s Export (API), or import from its Reprise sidebar.</small></>}</div>}
    {error&&<div className="wf-err" role="alert">{error}<button className="icon-sm" aria-label="Dismiss generation error" onClick={()=>setError('')}>×</button></div>}
    {wf?.missing.length?<div className="wf-err">Missing nodes: {wf.missing.join(', ')}</div>:null}
    {!!missingModels.length&&<details className="wf-unavailable"><summary>{missingModels.length} models unavailable on {target==='remote'?'remote':'local'} ComfyUI</summary>
      <p>{missingModels.join(', ')}</p><button onClick={()=>openSetup('models')}>Get missing models</button></details>}
    {modelInputs.length>0&&<details className="wf-models" open={missingModels.length>0||undefined}><summary title="Choose compatible files from the workflow’s model family"><span>Models <small>{modelInputs.length}</small></span><Icon name="keyNext" size={14}/></summary>
      {modelInputs.map(([k,i])=>{const value=String(vals[k]??i.default??''),installed=i.choices?.includes(value);return <label key={k} title={`${i.title} · ${i.field.replace(/_/g,' ')}`}>{i.title}<select aria-label={`Model: ${i.title} · ${i.field}`} value={value} disabled={loading||running} onChange={e=>setVal(k,e.target.value)}>
        {!installed&&<option value={value}>{value||'Choose a model'} · unavailable</option>}{i.choices?.map(v=><option key={v} value={v}>{v}</option>)}
      </select>{!i.choices?.length&&<small>No model files reported by this loader.</small>}</label>;})}
      <div className="wf-model-actions"><button className="ghost" disabled={loading} onClick={()=>void refresh(true)}><Icon name="redraw" size={13}/>{loading?'Checking…':'Refresh models'}</button><button className="link" onClick={()=>openSetup('models')}>Download help</button></div>
    </details>}
    {wf&&mapping&&<><Mapping key={wf.id} wf={wf} onSave={patch=>void updateWorkflow(wf.id,patch).then(()=>{setMapping(false);return refresh();}).catch(fail)}/>
      <button className="danger" onClick={()=>{if(confirm(`Remove ${wf.name}?`))void deleteWorkflow(wf.id).then(()=>refresh()).catch(fail);}}>Remove workflow</button></>}
    {wf&&!mapping&&<>
      {mediaInputs.length>0&&<div className="wf-references">{mediaInputs.map(([k,inp])=>{const value=sourceId(k,inp),a=assetOf(project,value===LAYER?layer?.assetId||'':value),special=options(k,inp).find(c=>c.id===value),label=inp.title.split(/[·(]/)[0].trim();
          const audioPath=inp.media==='audio'?(value===PREPARED?mediaFiles[k]?.path:a?.path||project.media.audio?.path||project.media.video?.path):undefined;
          return <div className={`wf-reference ${inp.media==='audio'?'wf-reference-audio':''}`} key={k} data-reference-key={k} data-reference-id={value}
            onDragOver={e=>{if(e.dataTransfer.types.includes(ASSET_MIME)){e.preventDefault();e.dataTransfer.dropEffect='copy';}}}
            onDrop={e=>{const id=e.dataTransfer.getData(ASSET_MIME);if(!id)return;e.preventDefault();e.stopPropagation();if(compatible(id,inp))chooseSource(k,id);else setError(`Choose ${inp.media==='audio'?'media with sound':inp.media==='video'?'a video':'an image or video'} for ${inp.title}.`);}}>
            {audioPath&&<ReferenceAudio key={`${selectedTake}:${k}:${value}`} src={assetUrl(project,audioPath)} name={a?.name||special?.name||label} start={source(k,inp).start||0} end={source(k,inp).end}/>}
            <button className="wf-reference-choice" aria-label={`Reference: ${inp.title}`} aria-haspopup="dialog" onClick={()=>setReferencePicker(k)} title={`${inp.title}: ${a?.name||special?.name||'Choose reference'}\nClick to change, or drop a take here`}>
              {inp.media!=='audio'&&<span className="wf-reference-image">{a?<SceneThumb project={project} asset={a} time={source(k,inp).time}/>:<Icon name="plus" size={22}/>}</span>}
              <span className="wf-reference-label">{label||'Reference'}<span aria-hidden="true">⌄</span></span>
            </button>
            {inp.media!=='audio'&&<button className="icon-sm" disabled={project.id==='sample'} onClick={()=>{refTarget.current={key:k,wid,layerId:layer?.id||'',sceneId:scene?.id||'',recipeId:scene?.recipeId||'',takeId:selectedTake};if(ref.current)ref.current.accept=inp.media==='video'?'video/*':'image/*,video/*';ref.current?.click();}} title="Upload reference" aria-label={`Upload reference: ${inp.title}`}><Icon name="plus" size={14}/></button>}
          </div>;})}</div>}
      {primaryInputs.map(inputControl)}
      {advancedInputs.length>0&&<details className="wf-settings"><summary aria-label="Generation settings" title="Generation settings"><Icon name="sliders" size={15}/><span aria-hidden="true">⌄</span></summary><div>{advancedInputs.map(inputControl)}</div></details>}
      <div className="wf-run">
        <div className="seg mini" role="radiogroup" aria-label="Variants" title="Number of takes to generate">{[1,2,4].map(n=>
          <button key={n} role="radio" aria-checked={variants===n} className={variants===n?'active':''} disabled={n>1&&!hasSeed} title={n>1&&!hasSeed?'Expose a seed input to generate different takes':undefined} onClick={()=>patch({variants:n})}>{n}×</button>)}</div>
        <button className="primary" onClick={()=>void run()} disabled={running||!!blocked} aria-label={preparing?'Preparing…':activeJobs.length?`Generating ${Math.round((activeJobs[0].progress||0)*100)}%`:`Generate ${variants===1?'take':`${variants} takes`}`} aria-describedby={blocked?'wf-run-status':undefined} title={blocked||`Generate on ${wf.target==='remote'?'remote GPU':'local ComfyUI'}`}>
          {preparing?'Preparing…':activeJobs.length?`Generating ${Math.round((activeJobs[0].progress||0)*100)}%`:'Generate'}</button>
      </div>
      {!!blocked&&<div id="wf-run-status" className="wf-note" role="status">{blocked}<button className="wf-more" onClick={()=>void refresh()}>Check again</button></div>}
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
