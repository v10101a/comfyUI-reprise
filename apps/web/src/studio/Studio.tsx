// Typeset Studio v3: stage-first editor. Layout: top bar · [Pipeline/Media | Stage | Look + Line] · Arrangement · status.
import {useState,useEffect,useLayoutEffect,useRef,useCallback,useMemo} from 'react';
import type {Project,Word,Job,LookId,Surface,Point} from '../types';
import {request,getProject,assetUrl,pollJob} from '../api';
import {StageRenderer,loadFonts,type RenderOpts} from '../renderer';
import {reframeProject} from '../reframe';
import {prepareExport} from '../exportFrames';
import {cropAt,toOut,toSource} from '../geometry';
import {LOOKS,setLook,setLineMeta,lineSizeMode} from '../looks';
import {Timeline,lineInfos} from './Timeline';
import {copyText,pasteText,splitText,deleteText,addText,setWordText,type TextClipboard,type TextEdit} from './timelineEdits';
import {WallTool,WallBar,WallButtons} from './WallTool';
import {setSurfaceQuad,deleteSurface,wallFallback} from './walls';
import {groupOf,type GroupId} from './groups';
import {StageGuides,lineBoxes,type Guides,type Resize} from './StageOverlay';
import {LookPicker,useLookThumbs} from './LookPicker';
import {LineInspector} from './LineInspector';
import {GroupInspector} from './GroupInspector';
import {PipelinePanel,WorkflowSheet} from './PipelinePanel';
import {latestJobs,parseBeats,type Beats,type JobRecord,type StepDef,type StepId} from './pipeline';
import {ThemeToggle} from './ThemeToggle';
import {Icon} from './icons';
import {SongMap} from './SongMap';
import {PipelineRail} from './PipelinePanel';
import {clipOf,shiftOf,songRef} from '../audioClip';
import PIECES from '../showcase-pieces.json';
import './studio.css';

/** Projects whose demo-page clip re-renders after a save (showcase-pieces.json pieces with `encode`). */
const SHOWCASE=new Set((PIECES.pieces as {project?:string;encode?:object}[]).filter(x=>x.project&&x.encode).map(x=>x.project!));
const DEMO_DEBOUNCE=5000;
/** Stage quality per render request. Draft while a pointer is down on the timeline or stage (preview proxies + light
 *  optics: ~43 ms a frame on the hero instead of ~160), proxies only during playback, full quality once settled. */
const DRAFT:RenderOpts={proxy:true,heavyOptics:false};const PLAYBACK:RenderOpts={proxy:true};const SETTLED:RenderOpts={full:true};
type Req={frame:number;opts?:RenderOpts};

const timecode=(time:number)=>`${Math.floor(time/60).toString().padStart(2,'0')}:${Math.floor(time%60).toString().padStart(2,'0')}.${Math.floor((time%1)*100).toString().padStart(2,'0')}`;
type Fmt='mp4'|'mov'|'webm';
const FORMATS:{id:Fmt;label:string;note:string}[]=[{id:'mp4',label:'mp4',note:'composite · H.264 + audio'},{id:'mov',label:'mov',note:'text layer · ProRes 4444 alpha'},{id:'webm',label:'webm',note:'text layer · VP9 alpha'}];


export default function Studio({initialProjectId='sample'}:{initialProjectId?:string}){
  const [project,setProject]=useState<Project|null>(null);const [projects,setProjects]=useState<Project[]>([]);const [selected,setSelected]=useState('');const [frame,setFrame]=useState(24);const [playing,setPlaying]=useState(false);const [muted,setMuted]=useState(false);const [busy,setBusy]=useState(false);const [job,setJob]=useState<Job|null>(null);const [notice,setNotice]=useState('');const [error,setError]=useState('');const [dirty,setDirty]=useState(false);const [ready,setReady]=useState(false);
  const [waveform,setWaveform]=useState<Float32Array|null>(null);const [songDur,setSongDur]=useState(0);const [linkWords,setLinkWords]=useState(true);const [prompt,setPrompt]=useState('Sculptural letters made from polished chrome, gentle camera push in, studio lighting');const [leftTab,setLeftTab]=useState<'pipeline'|'media'>('pipeline');const [exports,setExports]=useState<string[]>([]);
  const [jobs,setJobs]=useState<JobRecord[]>([]);const [beats,setBeats]=useState<Beats|undefined>();const [guides,setGuides]=useState<Guides>({occupancy:false,regions:true,anchor:true,walls:false});
  const [multi,setMulti]=useState<{ids:string[];title:string}|null>(null);const [zoom,setZoom]=useState(1);const [snap,setSnap]=useState(true);const [loop,setLoop]=useState<{a:number;b:number}|null>(null);const [loopOn,setLoopOn]=useState(false);
  const [wordOpen,setWordOpen]=useState(false);const [looksOpen,setLooksOpen]=useState(false);const [outputOpen,setOutputOpen]=useState(false);const [wfStep,setWfStep]=useState<StepDef|null>(null);const [formats,setFormats]=useState<Fmt[]>(['mp4','mov','webm']);const [savedAt,setSavedAt]=useState<number|null>(null);
  const [clipboard,setClipboard]=useState<TextClipboard|null>(null);
  // Surface tool: corners in OUTPUT-normalized coords while drawing; `id` set when re-drawing an existing surface.
  const [surfaceTool,setSurfaceTool]=useState<{corners:Point[];id?:string}|null>(null);
  // Selected wall (stage quad click / wall mode): ⌫ deletes it. selScope: what ⌫ removes when a line is selected.
  const [selectedWall,setSelectedWall]=useState('');const [selScope,setSelScope]=useState<'word'|'line'>('line');
  const [inlineEdit,setInlineEdit]=useState<{wordId:string;fresh:boolean}|null>(null);
  // Side-by-side: original vs. client-side 9:16 reframe (or, in a reframed project, its source).
  const [compare,setCompare]=useState(false);const compareCanvas=useRef<HTMLCanvasElement>(null);const compareRenderer=useRef<StageRenderer>();const [compareReady,setCompareReady]=useState(false);const comparing=useRef(false);const compareRequested=useRef<Req>({frame:0});
  const canvas=useRef<HTMLCanvasElement>(null);const renderer=useRef<StageRenderer>();const rendering=useRef(false);const requested=useRef<Req>({frame:0});const uploadInput=useRef<HTMLInputElement>(null);const audio=useRef<HTMLAudioElement>(null);const stageWrap=useRef<HTMLDivElement>(null);const projectRef=useRef(project);projectRef.current=project;
  const [stageBox,setStageBox]=useState({w:800,h:450});
  const current=project?.words.find(w=>w.id===selected);const time=project?frame/project.fps:0;
  const lines=useMemo(()=>project?lineInfos(project):[],[project]);const currentLine=lines.find(l=>l.id===current?.lineId);
  const totalFrames=project?Math.max(1,Math.round(project.duration*project.fps)):1;
  // Undo: edits closer than 600 ms together are one step (typing); a drag calls checkpoint() first and is exactly one
  // step however long it lasts (the gesture closes on the next pointerup anywhere).
  const hist=useRef<{past:Project[];future:Project[];last:number;gesture?:boolean;pushed?:boolean}>({past:[],future:[],last:0});
  const edit=useCallback((update:(p:Project)=>Project)=>{const h=hist.current;const now=performance.now();const cur=projectRef.current;
    if(cur&&(h.gesture?!h.pushed:now-h.last>600)){h.past.push(cur);if(h.past.length>200)h.past.shift();h.pushed=true;}h.future=[];h.last=now;
    setProject(p=>p?update(p):p);setDirty(true);},[]);
  const checkpoint=useCallback(()=>{const h=hist.current;h.gesture=true;h.pushed=false;},[]);
  // Capture phase (timeline handlers stop propagation), closed after this event's own handlers have made their last edit.
  useEffect(()=>{const up=()=>setTimeout(()=>{const h=hist.current;if(h.gesture){h.gesture=false;h.last=0;}},0);window.addEventListener('pointerup',up,true);window.addEventListener('pointercancel',up,true);
    return()=>{window.removeEventListener('pointerup',up,true);window.removeEventListener('pointercancel',up,true);};},[]);
  const [held,setHeld]=useState(false);
  useEffect(()=>{const down=(e:PointerEvent)=>{if((e.target as Element|null)?.closest?.('.tl,.stage-wrap'))setHeld(true);};const up=()=>setHeld(false);const ups=['pointerup','pointercancel','blur'];
    window.addEventListener('pointerdown',down,true);for(const n of ups)window.addEventListener(n,up,true);
    return()=>{window.removeEventListener('pointerdown',down,true);for(const n of ups)window.removeEventListener(n,up,true);};},[]);
  const undo=(redo:boolean)=>{const h=hist.current;const cur=projectRef.current;const prev=(redo?h.future:h.past).pop();if(!prev||!cur)return;(redo?h.past:h.future).push(cur);h.last=0;setProject(prev);setDirty(true);};
  const undoRef=useRef(undo);undoRef.current=undo;
  const changeProject=useCallback((p:Project)=>{hist.current={past:[],future:[],last:0};setSongStale(false);setProject(p);setSelected('');setFrame(Math.min(Math.round(.8*p.fps),Math.max(0,Math.round(p.duration*p.fps)-1)));setPlaying(false);setDirty(false);setExports([]);setError('');setLoop(null);setLoopOn(false);setCompare(false);setSurfaceTool(null);setSelectedWall('');setInlineEdit(null);},[]);
  useEffect(()=>{let live=true;const initial=initialProjectId==='sample'?request<Project>('/sample/project.json'):getProject(initialProjectId);initial.then(p=>{if(live){const saved=initialProjectId==='sample'?localStorage.getItem('typeset.sample'):null;if(saved){try{p=JSON.parse(saved);}catch{/* fresh sample */}}changeProject(p);}}).catch(e=>{if(live)setError(String(e));});request<Project[]>('/api/projects').then(p=>{if(live)setProjects(p);}).catch(()=>{});return()=>{live=false;};},[changeProject,initialProjectId]);
  const mediaSignature=JSON.stringify([project?.id,project?.media.video,project?.analysis,project?.shots]);
  useEffect(()=>{if(!projectRef.current)return;let live=true;const r=new StageRenderer(projectRef.current);r.draftMedia=true;setReady(false);renderer.current?.dispose();renderer.current=r;
    r.load().then(()=>{if(live)setReady(true);}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;r.dispose();};
  },[mediaSignature]);
  // One request object per (frame, project, quality): the loop runs until the request it just drew is still the latest, so
  // the same frame with different text is a new result (the last edit of a drag used to be dropped when it landed mid-render).
  useEffect(()=>{const r=renderer.current;if(r&&project)r.project=project;if(!ready||!r||!canvas.current)return;{const q:Req={frame};q.opts={...(held?DRAFT:playing?PLAYBACK:SETTLED),stale:()=>requested.current!==q};requested.current=q;}
    const draw=async()=>{if(rendering.current)return;rendering.current=true;try{do{const q=requested.current;await r.render(canvas.current!,q.frame,'composite',q.opts);if(q===requested.current)break;}while(true);}catch(e){setError(String(e));}finally{rendering.current=false;}};void draw();
  },[frame,project,ready,held,playing]);
  useEffect(()=>{if(!compare||!ready||!projectRef.current||!renderer.current){compareRenderer.current?.dispose();compareRenderer.current=undefined;setCompareReady(false);return;}
    let live=true;const base=projectRef.current;const source=base.frame?.source?.projectId;
    const make=async()=>{let r:StageRenderer;
      if(source){r=new StageRenderer(await getProject(source));}
      else{await loadFonts();const {project:rp,crop}=reframeProject(base,'9:16',renderer.current?.tracks);r=new StageRenderer(rp);r.crop=crop;}
      r.draftMedia=true;await r.load();if(!live){r.dispose();return;}compareRenderer.current=r;setCompareReady(true);};
    make().catch(e=>{if(live)setError(String(e));});
    return()=>{live=false;compareRenderer.current?.dispose();compareRenderer.current=undefined;setCompareReady(false);};
  },[compare,ready,mediaSignature]);
  useEffect(()=>{const r=compareRenderer.current;const p=projectRef.current;if(!compareReady||!r||!p||!compareCanvas.current)return;
    if(!p.frame?.source)r.project=reframeProject(p,'9:16',renderer.current?.tracks,r.crop).project;
    {const q:Req={frame};q.opts={...(held?DRAFT:playing?PLAYBACK:SETTLED),stale:()=>compareRequested.current!==q};compareRequested.current=q;}
    const draw=async()=>{if(comparing.current)return;comparing.current=true;try{do{const q=compareRequested.current;await r.render(compareCanvas.current!,q.frame,'composite',q.opts);if(q===compareRequested.current)break;}while(true);}catch(e){setError(String(e));}finally{comparing.current=false;}};void draw();
  },[frame,project,compareReady,held,playing]);
  // Waveform: min/max peaks (2 floats per bin) so the arrangement can redraw at any zoom.
  useEffect(()=>{if(!project)return;const path=project.media.audio?.path||project.media.video?.path;if(!path){setWaveform(null);return;}let live=true;const context=new AudioContext();
    fetch(assetUrl(project,path)).then(r=>r.arrayBuffer()).then(b=>context.decodeAudioData(b)).then(buffer=>{const data=buffer.getChannelData(0);const bins=Math.min(6000,Math.max(400,Math.round(buffer.duration*200)));const size=Math.max(1,Math.floor(data.length/bins));const out=new Float32Array(bins*2);let max=.001;
      for(let i=0;i<bins;i++){let lo=0,hi=0;for(let j=i*size;j<Math.min(data.length,(i+1)*size);j+=4){const v=data[j];if(v<lo)lo=v;if(v>hi)hi=v;}out[i*2]=lo;out[i*2+1]=hi;max=Math.max(max,hi,-lo);}
      for(let i=0;i<out.length;i++)out[i]/=max;if(live){setWaveform(out);setSongDur(buffer.duration);}}).catch(()=>{if(live)setWaveform(null);}).finally(()=>{void context.close();});return()=>{live=false;};},[project?.id,project?.media.audio?.path,project?.media.video?.path]);// eslint-disable-line react-hooks/exhaustive-deps
  // beats.json (ComfyUI AudioBeatMarkers job). Optional: analysis.beats if the server sets it, else the conventional path.
  useEffect(()=>{if(!project||project.id==='sample'){setBeats(undefined);return;}let live=true;const path=(project.analysis as {beats?:string|null}).beats||'analysis/beats.json';
    fetch(assetUrl(project,path)).then(r=>r.ok?r.json():undefined).then(j=>{if(live)setBeats(parseBeats(j));}).catch(()=>{if(live)setBeats(undefined);});return()=>{live=false;};},[project?.id,JSON.stringify(project?.analysis)]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),3500);return()=>clearTimeout(t);},[notice]);
  const refreshJobs=useCallback(async(id=projectRef.current?.id)=>{if(!id||id==='sample'){setJobs([]);return;}try{setJobs(await request<JobRecord[]>(`/api/jobs?projectId=${encodeURIComponent(id)}`));}catch{/* server offline */}},[]);
  useEffect(()=>{void refreshJobs(project?.id);},[project?.id,refreshJobs]);
  const trackJob=(j:Job)=>{setJob(j);setJobs(js=>[{...j,createdAt:js.find(x=>x.id===j.id)?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()},...js.filter(x=>x.id!==j.id)]);};
  // Playback (with loop brace).
  const loopRef=useRef({loop,loopOn});loopRef.current={loop,loopOn};
  useEffect(()=>{if(!playing||!project)return;let raf=0;let previous=performance.now();let fractional=frame;const tick=(now:number)=>{fractional+=(now-previous)*project.fps/1000;previous=now;
    const L=loopRef.current;if(L.loopOn&&L.loop&&L.loop.b-L.loop.a>.05&&fractional>=L.loop.b*project.fps){fractional=L.loop.a*project.fps;}
    if(fractional>=project.duration*project.fps){if(L.loopOn){fractional=(L.loop?.a||0)*project.fps;}else{setPlaying(false);setFrame(0);return;}}
    setFrame(Math.floor(fractional));raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);},[playing,project?.fps,project?.duration]);// eslint-disable-line react-hooks/exhaustive-deps
  // Song playback follows the clip (media.audioClip): song time = t − (offset − in), silent outside [in,out).
  const syncAudio=useCallback((t:number,play:boolean)=>{const a=audio.current;const p=projectRef.current;if(!a||!p)return;
    const c=clipOf(p,songDur||songRef(p)?.duration||p.duration);const s=t-shiftOf(c);const inside=s>=c.in&&s<c.out;
    if(!play||!inside){if(!a.paused)a.pause();if(Math.abs(a.currentTime-Math.max(0,s))>.1)a.currentTime=Math.max(0,Math.min(c.out,s));return;}
    if(a.paused){a.currentTime=s;void a.play().catch(()=>{});}else if(Math.abs(a.currentTime-s)>.2)a.currentTime=s;},[songDur]);
  useEffect(()=>{const a=audio.current;if(a)a.muted=muted;},[muted,project?.id]);
  useEffect(()=>{syncAudio(time,playing);},[time,playing,project?.media.audioClip,syncAudio]);
  useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[dirty]);
  async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function save(p=projectRef.current,quiet=false){if(!p)return;if(p.id==='sample'){localStorage.setItem('typeset.sample',JSON.stringify(p));if(!quiet)setNotice('Saved');}else{await request<Project>(`/api/projects/${p.id}`,{method:'PUT',body:JSON.stringify(p)});if(!quiet)setNotice('Saved');scheduleDemo(p.id);}setDirty(false);setSavedAt(Date.now());}
  // Save → demo page: a mapped project's showcase clip re-renders once saves settle (server coalesces repeats).
  const [demo,setDemo]=useState<'idle'|'pending'|'running'|'failed'>('idle');const demoTimer=useRef<{id:string;t:number}|null>(null);
  function scheduleDemo(id:string){if(!SHOWCASE.has(id))return;if(demoTimer.current)clearTimeout(demoTimer.current.t);setDemo(d=>d==='running'?d:'pending');
    demoTimer.current={id,t:window.setTimeout(()=>{demoTimer.current=null;void refreshDemo(id);},DEMO_DEBOUNCE)};}
  async function refreshDemo(id:string){
    try{const r=await fetch(`/api/projects/${encodeURIComponent(id)}/showcase`,{method:'POST'});if(!r.ok){setDemo('idle');return;}
      setDemo('running');const done=await pollJob(await r.json() as Job,()=>{});setDemo(d=>d==='pending'?d:done.status==='done'?'idle':'failed');}
    catch{setDemo(d=>d==='pending'?d:'failed');}
  }
  // Leaving the project with a refresh still waiting: send it now.
  useEffect(()=>()=>{const d=demoTimer.current;if(d){clearTimeout(d.t);void fetch(`/api/projects/${encodeURIComponent(d.id)}/showcase`,{method:'POST',keepalive:true}).catch(()=>{});}},[]);
  // Autosave (debounced PUT). Never while a job runs: the job's result is re-fetched first, then edits resume (docs/server.md).
  useEffect(()=>{if(!dirty||busy||!project)return;const t=setTimeout(()=>{void save(projectRef.current,true).catch(e=>setError(String(e)));},1200);return()=>clearTimeout(t);},[project,dirty,busy]);// eslint-disable-line react-hooks/exhaustive-deps
  async function create(){const p=await request<Project>('/api/projects',{method:'POST',body:JSON.stringify({name:'Untitled study'})});setProjects(items=>[p,...items]);changeProject(p);setNotice('');setLeftTab('media');}
  async function openProject(id:string){if(dirty)await save();location.hash=`/studio?project=${id}`;}
  // Song swap: drop audio on the waveform → it replaces media.audio (footage and words stay); ↻ then re-runs words + beats.
  const [songStale,setSongStale]=useState(false);
  // Left panel: full, or a slim icon rail (remembered per browser).
  const [rail,setRailState]=useState(()=>{try{return localStorage.getItem('typeset.leftRail')==='1';}catch{return false;}});
  const setRail=(v:boolean)=>{setRailState(v);try{localStorage.setItem('typeset.leftRail',v?'1':'0');}catch{/* private mode */}};
  const openLeft=(tab:'pipeline'|'media')=>{setLeftTab(tab);setRail(false);};
  async function replaceSong(file:File){
    const p=projectRef.current;if(!p)return;if(p.id==='sample')throw new Error('The sample is offline. Start a project to run this.');
    if(dirty)await save(p,true);const form=new FormData();form.append('file',file);form.append('kind','audio');
    await request(`/api/projects/${p.id}/media`,{method:'POST',body:form});await refetch(p);setSongStale(true);setNotice('Song replaced');
  }
  async function realign(){setSongStale(false);await jobAction('words');
    // Beats without another save: this closure's project predates the words result.
    const id=projectRef.current!.id;const j=await optionalJob(`/api/projects/${id}/analyze/beats`,{});if(j){trackJob(await pollJob(j,trackJob));await refetch(projectRef.current!);}
    // The voice / audio fields are computed from the song, so a project that uses one gets a fresh one.
    for(const k of ['audio','voice'] as const)if(projectRef.current!.analysis[k]){const v=await optionalJob(`/api/projects/${id}/analyze/${k}`,{});if(v){trackJob(await pollJob(v,trackJob));await refetch(projectRef.current!);}}
    setNotice('Re-aligned');}
  async function upload(file:File){let p=project!;if(p.id==='sample'){p=await request<Project>('/api/projects',{method:'POST',body:JSON.stringify({name:file.name.replace(/\.[^.]+$/,'')})});}const form=new FormData();form.append('file',file);form.append('kind',file.type.startsWith('audio/')?'audio':'video');await request(`/api/projects/${p.id}/media`,{method:'POST',body:form});p=await getProject(p.id);changeProject(p);setProjects(items=>[p,...items.filter(item=>item.id!==p.id)]);setNotice('Media ready');}
  /** Re-fetch after any analysis job, before the next PUT (a stale copy would overwrite the job's fields). */
  async function refetch(p:Project){const updated=await getProject(p.id);hist.current={past:[],future:[],last:0};setProject(updated);setDirty(false);setSelected(s=>updated.words.some(w=>w.id===s)?s:'');await refreshJobs(p.id);return updated;}
  async function jobAction(kind:'words'|'matte'|'inworld'|'export'){
    if(!project)return;if(project.id==='sample')throw new Error('The sample is offline. Start a project to run this.');if(kind==='inworld'&&(!current||project.duration<=current.start))throw new Error('Pick a word first');await save(project,true);
    const path=kind==='words'||kind==='matte'?`analyze/${kind}`:kind==='inworld'?'generate/inworld':'export';
    const body=kind==='words'?{language:'auto'}:kind==='inworld'?inworldBody():kind==='export'?{layer:'composite',formats,...await prepareExport(project,'composite',formats,setNotice)}:{};
    const start=await request<Job>(`/api/projects/${project.id}/${path}`,{method:'POST',body:JSON.stringify(body)});const done=await pollJob(start,trackJob);
    if(kind==='export'){const result=done.result as {files?:Record<string,string>};setExports(Object.values(result?.files||{}));setNotice('Exported');setOutputOpen(true);await refreshJobs();}
    else{await refetch(project);setNotice(`${kind==='inworld'?'Shot':kind==='words'?'Words':'Matte'} done`);}trackJob(done);
  }
  /** In-world: the whole selected line, ≥ 2 s, through the local edit → remote MiniMax path (the LTX path cannot run here). */
  function inworldBody(){const l=currentLine;const start=l?.start??current?.start??0;
    return {wordIds:l?l.words.map(w=>w.id):current?[current.id]:[],prompt,start,end:Math.min(project!.duration,start+10,Math.max(start+2,l?.end??current?.end??start+2)),engine:'remote-minimax'};}
  /** POST that tolerates a missing endpoint (S may not have shipped it yet): returns null on 404/405. */
  async function optionalJob(path:string,body:unknown):Promise<Job|null>{
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(r.status===405)return null;if(r.status===404){const detail=await r.text();if(/surface not found/i.test(detail))throw new Error(detail);return null;}if(!r.ok)throw new Error(await r.text());return r.json();
  }
  async function analysisJob(kind:'occupancy'|'beats'|'flow'|'audio'|'voice'){
    if(!project||project.id==='sample')return;await save(project,true);
    const j=await optionalJob(`/api/projects/${project.id}/analyze/${kind}`,{});if(!j){setNotice(`${kind} unavailable`);return;}
    const done=await pollJob(j,trackJob);trackJob(done);await refetch(project);setNotice(`${kind} done`);
  }
  function runStep(id:StepId){if(id==='words'||id==='matte')void run(()=>jobAction(id));else if(id==='occupancy'||id==='beats'||id==='flow'||id==='audio'||id==='voice')void run(()=>analysisJob(id));}
  function startSurface(id?:string){
    setPlaying(false);setLooksOpen(false);
    const s=id?project?.surfaces?.find(x=>x.id===id):undefined;
    const c=cropAt(renderer.current?.crop,frame);
    setSurfaceTool({id,corners:s?s.corners.map(([x,y])=>toOut(c,x,y)):[]});
  }
  async function applySurface(){
    if(!project||!surfaceTool||surfaceTool.corners.length!==4)return;
    const c=cropAt(renderer.current?.crop,frame);
    const corners=surfaceTool.corners.map(([x,y])=>toSource(c,x,y)) as Point[];
    const id=surfaceTool.id||`s${crypto.randomUUID().slice(0,6)}`;
    const old=project.surfaces?.find(x=>x.id===id);
    const surface:Surface={id,label:old?.label||`Wall ${(project.surfaces?.length||0)+1}`,keyFrame:frame,corners,status:'drawn',material:old?.material||'paint',track:null};
    const lineId=current?.lineId;const fresh=!old;
    // A new wall takes the selected line; re-placing an existing wall keeps its lines.
    const next:Project={...project,surfaces:[...(project.surfaces||[]).filter(x=>x.id!==id),surface],
      words:project.words.map(w=>fresh&&current&&w.lineId===lineId&&(w.id===current.id||w.placement===current.placement)?{...w,placement:'surface',surfaceId:id}:w)};
    edit(()=>next);setSurfaceTool(null);setSelectedWall(id);
    await trackSurface(next,id);
  }
  async function trackSurface(p:Project,id:string){
    if(p.id==='sample'){setNotice('Wall placed');return;}
    await save(p,true);
    const j=await optionalJob(`/api/projects/${p.id}/surfaces/${id}/track`,{});
    if(!j){setNotice('Wall placed');return;}
    const done=await pollJob(j,trackJob);trackJob(done);
    const updated=await refetch(p);
    const s=updated.surfaces?.find(x=>x.id===id);setNotice(s?.status==='tracked'?'Wall tracked':`Wall ${s?.status||'saved'}`);
  }
  /** Delete a wall (undoable); its lines fall back to Behind (with a matte) or on top. */
  function deleteWall(id:string){const p=projectRef.current;if(!p)return;const r=deleteSurface(p,id);const h=hist.current;h.gesture=false;h.last=0;edit(()=>r.project);h.last=0;
    setSelectedWall('');setSurfaceTool(t=>t?.id===id?null:t);setNotice(r.lines?`Wall deleted · ${r.lines} line${r.lines>1?'s':''} → ${r.to==='behind'?'Behind':'Caption'}`:'Wall deleted');}
  // Stage drag of a wall's corner or body: new corners at this frame (one undo step; the wall is static until re-tracked).
  const wallEdit=(id:string,quad:Point[],phase:'start'|'move'|'end')=>{const p=projectRef.current;if(!p)return;
    if(phase==='start'){setPlaying(false);checkpoint();return;}if(phase==='end')return;
    const c=cropAt(renderer.current?.crop,frame);const corners=quad.map(([x,y])=>toSource(c,x/p.width,y/p.height) as Point);edit(q=>setSurfaceQuad(q,id,corners,frame));};
  const wallJob=jobs.find(j=>j.kind==='surface'&&(j.status==='running'||j.status==='queued'));
  async function makeVertical(){
    if(!project)return;
    if(project.id==='sample'){setCompare(true);setNotice('');return;}
    await save(project,true);
    const j=await optionalJob(`/api/projects/${project.id}/reframe`,{aspect:'9:16'});
    if(!j){setCompare(true);setNotice('');return;}
    const done=await pollJob(j,trackJob);const id=(done.result as {projectId?:string})?.projectId;
    if(!id)throw new Error('Reframe finished without a project id');
    setNotice('');location.hash=`/studio?project=${id}`;
  }
  const pickLook=(id:LookId)=>{edit(p=>setLook(p,id==='default'?null:id));};
  const toggleHidden=(lineId:string)=>edit(p=>setLineMeta(p,lineId,{hidden:p.lineMeta?.[lineId]?.hidden?null:true}));
  // Stage drag: move a line's preferred spot (overlay/behind) or its anchor offset (HUD). Starts from where the line is drawn now.
  const dragStart=useRef<{x:number;y:number;dx:number;dy:number}|null>(null);
  const dragLine=(lineId:string,placement:Word['placement'],dx:number,dy:number,phase:'start'|'move'|'end')=>{
    const p=projectRef.current;if(!p)return;const first=p.words.find(w=>w.lineId===lineId);if(!first)return;
    if(phase==='start'){setPlaying(false);checkpoint();const b=lineBoxes(renderer.current,p,frame).find(x=>x.lineId===lineId);const align=first.style?.align||p.style.align;
      const x=b?(b.x+(align==='left'?0:align==='right'?b.w:b.w/2))/p.width:first.position?.x??.5,y=b?(b.y+b.h/2)/p.height:first.position?.y??.72;
      dragStart.current={x,y,dx:first.anchor?.dx||0,dy:first.anchor?.dy||0};return;}
    const s=dragStart.current;if(!s)return;if(phase==='end')dragStart.current=null;if(Math.abs(dx)+Math.abs(dy)<.002)return;
    const cl=(v:number)=>Math.max(0,Math.min(1,v));
    if(placement==='anchor')edit(q=>({...q,words:q.words.map(w=>w.lineId===lineId?{...w,anchor:{trackId:w.anchor?.trackId||'person0',dx:+(s.dx+dx).toFixed(4),dy:+(s.dy+dy).toFixed(4)}}:w)}));
    else edit(q=>({...q,words:q.words.map(w=>w.lineId===lineId&&w.placement===placement?{...w,position:{x:+cl(s.x+dx).toFixed(4),y:+cl(s.y+dy).toFixed(4)}}:w)}));
  };
  // Stage resize: corner handles scale the line uniformly. Overlay/behind/HUD: every word's fontSize, with the line's spot
  // moved so the fixed point (opposite corner, or centre with ⌥) stays put. Wall: lineMeta.scale in the wall's plane.
  const resizeStart=useRef<{sizes:Map<string,number>;x:number;y:number;dx:number;dy:number;scale:number}|null>(null);
  const resizeLine=({lineId,placement,phase,k,fixed,box}:Resize)=>{
    const p=projectRef.current;if(!p)return;
    if(phase==='start'){setPlaying(false);checkpoint();const first=p.words.find(w=>w.lineId===lineId);const align=first?.style?.align||p.style.align;
      resizeStart.current={sizes:new Map(p.words.filter(w=>w.lineId===lineId).map(w=>[w.id,w.style?.fontSize??p.style.fontSize])),
        x:box.x+(align==='left'?0:align==='right'?box.w:box.w/2),y:box.y+box.h/2,dx:first?.anchor?.dx||0,dy:first?.anchor?.dy||0,scale:p.lineMeta?.[lineId]?.scale??1};return;}
    const s=resizeStart.current;if(!s)return;if(phase==='end')resizeStart.current=null;
    if(lineSizeMode(p,lineId)==='scale'){const v=+Math.max(.2,Math.min(4,s.scale*k)).toFixed(3);edit(q=>setLineMeta(q,lineId,{scale:Math.abs(v-1)<.005?null:v}));return;}
    // New origin: the old one scaled about the fixed point (project px → normalized).
    const ox=(fixed[0]+(s.x-fixed[0])*k)/p.width,oy=(fixed[1]+(s.y-fixed[1])*k)/p.height;const cl=(v:number)=>Math.max(0,Math.min(1,v));
    edit(q=>({...q,words:q.words.map(w=>{if(w.lineId!==lineId)return w;const f0=s.sizes.get(w.id)??q.style.fontSize;
      const next={...w,style:{...(w.style||{}),fontSize:+Math.max(.008,Math.min(.6,f0*k)).toFixed(4)}};
      if(placement==='anchor')return {...next,anchor:{trackId:w.anchor?.trackId||'person0',dx:+(s.dx+ox-s.x/p.width).toFixed(4),dy:+(s.dy+oy-s.y/p.height).toFixed(4)}};
      return w.placement===placement?{...next,position:{x:+cl(ox).toFixed(4),y:+cl(oy).toFixed(4)}}:next;})}));
  };
  const selectLine=(lineId:string)=>{const w=projectRef.current?.words.find(x=>x.lineId===lineId);if(w)setSelected(w.id);};
  const pickGroup=(ids:string[],title:string,additive:boolean)=>{const next=additive?[...new Set([...(multi?.ids||(current?[current.lineId]:[])),...ids])]:ids;
    if(next.length<=1){setMulti(null);if(next[0])selectLine(next[0]);}else setMulti({ids:next,title:additive?'Selection':title});};
  const toggleLine=(lineId:string)=>{const base=multi?.ids||(current?[current.lineId]:[]);const next=base.includes(lineId)?base.filter(x=>x!==lineId):[...base,lineId];
    if(next.length<=1){setMulti(null);if(next[0])selectLine(next[0]);}else setMulti({ids:next,title:'Selection'});};
  const seekFrame=(f:number)=>{setPlaying(false);setFrame(Math.max(0,Math.min(Math.round((projectRef.current?.duration||0)*(projectRef.current?.fps||24))-1,Math.round(f))));};
  function addWord(){addTextAt(time,currentLine?groupOf(currentLine):'captions');}
  const selectedLines=multi?.ids.length?multi.ids:currentLine?[currentLine.id]:[];
  const canSplit=lines.some(l=>selectedLines.includes(l.id)&&l.start<time&&l.end>time&&l.role!=='inworld');
  const canPaste=!!clipboard&&clipboard.projectId===project?.id&&clipboard.end-clipboard.start<=(project?.duration||0);
  function applyTextEdit(result:TextEdit|null){if(!result)return;
    // Keyboard commands are discrete undo steps; they must not leave a pointer gesture open.
    const h=hist.current;h.gesture=false;h.last=0;edit(()=>result.project);h.last=0;
    setSelected(result.wordId);setMulti(result.lineIds.length>1?{ids:result.lineIds,title:'Selection'}:null);}
  function copySelection(){if(project){const clip=copyText(project,selectedLines);if(clip)setClipboard(clip);}}
  function pasteSelection(){if(project&&clipboard)applyTextEdit(pasteText(project,clipboard,time));}
  function splitSelection(){if(project)applyTextEdit(splitText(project,selectedLines,time));}
  // Add / delete text on the timeline (each one undo step); a new clip opens for inline typing.
  function addTextAt(t:number,group:GroupId){if(!project)return;const r=addText(project,t,group);if(!r){setError('Add media first');return;}applyTextEdit(r);setSelScope('word');setInlineEdit({wordId:r.wordId,fresh:true});}
  function deleteSelection(t?:{lineIds:string[];wordIds:string[]}){const p=projectRef.current;if(!p)return;
    const target=t||(multi?.ids.length?{lineIds:multi.ids,wordIds:[]}:selScope==='word'&&current?{lineIds:[],wordIds:[current.id]}:currentLine?{lineIds:[currentLine.id],wordIds:[]}:null);
    if(!target)return;const r=deleteText(p,target.lineIds,target.wordIds);if(!r)return;applyTextEdit(r);if(!r.wordId){setSelected('');setMulti(null);}}
  function commitText(wordId:string,text:string){const p=projectRef.current;const fresh=inlineEdit?.fresh;setInlineEdit(null);if(!p)return;
    const w=p.words.find(x=>x.id===wordId);if(!w||w.text===text.trim())return;const r=setWordText(p,wordId,text);if(!r)return;
    // A brand-new clip and its first text are one undo step.
    if(fresh){const h=hist.current;h.last=performance.now();edit(()=>r.project);h.last=0;setSelected(r.wordId||'');}else applyTextEdit(r);}
  function cancelText(){const e=inlineEdit;setInlineEdit(null);if(e?.fresh)undoRef.current(false);}
  const textCommands=useRef({copySelection,pasteSelection,splitSelection,deleteSelection,deleteWall,applySurface});textCommands.current={copySelection,pasteSelection,splitSelection,deleteSelection,deleteWall,applySurface};
  // Arrow nudge (a line selected, focus not in a field): 0.5 % per press, ⇧ 5 %. Held: glides, speeding up; one undo
  // step per hold. Screen lines move like a stage drag; HUD lines move their head offset; wall lines move in the
  // wall's plane (lineMeta.u/v). Capture phase so the frame-step arrows below stay for when nothing is selected.
  const nudgeRef=useRef<{lineId:string;placement:Word['placement'];keys:Set<string>;dx:number;dy:number;u0:number;v0:number;t0:number;last:number;raf:number;fine:boolean}|null>(null);
  const nudgeFns=useRef({dragLine,checkpoint,edit});nudgeFns.current={dragLine,checkpoint,edit};
  useEffect(()=>{const DIR:Record<string,[number,number]>={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
    const apply=(n:NonNullable<typeof nudgeRef.current>)=>{const F=nudgeFns.current;
      if(n.placement==='surface')F.edit(q=>setLineMeta(q,n.lineId,{u:+(n.u0+n.dx).toFixed(4)||null,v:+(n.v0+n.dy).toFixed(4)||null}));
      else F.dragLine(n.lineId,n.placement,n.dx,n.dy,'move');};
    const step=(n:NonNullable<typeof nudgeRef.current>,k:number)=>{let x=0,y=0;n.keys.forEach(c=>{x+=DIR[c][0];y+=DIR[c][1];});n.dx+=x*k;n.dy+=y*k;apply(n);};
    const finish=()=>{const n=nudgeRef.current;if(!n)return;cancelAnimationFrame(n.raf);nudgeRef.current=null;
      if(n.placement!=='surface')nudgeFns.current.dragLine(n.lineId,n.placement,n.dx,n.dy,'end');const h=hist.current;h.gesture=false;h.last=0;};
    const down=(e:KeyboardEvent)=>{if(!DIR[e.code])return;const t=e.target as HTMLElement;if(t.matches('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey)return;
      const k=keyState.current;const l=k.currentLine;const p=k.project;if(!l||!p||k.surfaceTool)return;
      e.preventDefault();e.stopImmediatePropagation();
      let n=nudgeRef.current;if(n&&n.lineId!==l.id){finish();n=null;}
      if(!n){const first=l.words[0];const placement=first.placement;if(placement==='inworld')return;
        const meta=p.lineMeta?.[l.id];nudgeFns.current.checkpoint();
        n={lineId:l.id,placement,keys:new Set(),dx:0,dy:0,u0:meta?.u??0,v0:meta?.v??0,t0:performance.now(),last:performance.now(),raf:0,fine:false};nudgeRef.current=n;
        if(placement!=='surface')nudgeFns.current.dragLine(l.id,placement,0,0,'start');
        const nn=n;const loop=(now:number)=>{if(nudgeRef.current!==nn)return;const held=now-nn.t0;
          if(held>280&&nn.keys.size){const dt=Math.min(.05,(now-nn.last)/1000);const v=(nn.fine?.5:.06)*Math.min(4,1+(held-280)/700);step(nn,v*dt);}
          nn.last=now;nn.raf=requestAnimationFrame(loop);};n.raf=requestAnimationFrame(loop);}
      if(e.repeat)return;
      if(!n.keys.has(e.code)){n.keys.add(e.code);n.fine=e.shiftKey;n.t0=performance.now();const one=new Set([e.code]);const keep=n.keys;n.keys=one;step(n,e.shiftKey?.05:.005);n.keys=keep;}};
    const up=(e:KeyboardEvent)=>{const n=nudgeRef.current;if(!n||!DIR[e.code])return;n.keys.delete(e.code);if(!n.keys.size)finish();};
    const blur=()=>finish();
    window.addEventListener('keydown',down,true);window.addEventListener('keyup',up,true);window.addEventListener('blur',blur);
    return()=>{window.removeEventListener('keydown',down,true);window.removeEventListener('keyup',up,true);window.removeEventListener('blur',blur);finish();};},[]);// eslint-disable-line react-hooks/exhaustive-deps
  // Keyboard transport + tools.
  const [guidesOpen,setGuidesOpen]=useState(false);
  const keyState=useRef({project,currentLine,loop,loopOn,surfaceTool,looksOpen,overlay:false,selectedWall:''});keyState.current={project,currentLine,loop,loopOn,surfaceTool,looksOpen,overlay:outputOpen||!!wfStep||guidesOpen,selectedWall};
  useEffect(()=>{const key=(e:KeyboardEvent)=>{const target=e.target as HTMLElement;
    if(target.closest?.('input,textarea,select,[contenteditable=true]'))return;
    if((e.metaKey||e.ctrlKey)&&!e.altKey){
      const action=e.code==='KeyC'?textCommands.current.copySelection:e.code==='KeyV'?textCommands.current.pasteSelection:e.code==='KeyB'?textCommands.current.splitSelection:null;
      if(action&&!(e.code==='KeyC'&&window.getSelection()?.toString())){e.preventDefault();action();return;}}
    if((e.metaKey||e.ctrlKey)&&e.code==='KeyZ'&&!target.matches('input,textarea,select')){e.preventDefault();undoRef.current(e.shiftKey);return;}
    if((e.metaKey||e.ctrlKey)&&e.code==='KeyY'&&!target.matches('input,textarea,select')){e.preventDefault();undoRef.current(true);return;}
    if(target.matches('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey)return;const k=keyState.current;const p=k.project;if(!p)return;const last=Math.round(p.duration*p.fps)-1;
    if(e.code==='Space'){e.preventDefault();setPlaying(v=>!v);return;}
    if(e.code==='ArrowRight'){e.preventDefault();setFrame(f=>Math.min(f+(e.shiftKey?p.fps:1),last));return;}
    if(e.code==='ArrowLeft'){e.preventDefault();setFrame(f=>Math.max(0,f-(e.shiftKey?p.fps:1)));return;}
    if(e.code==='Home'){e.preventDefault();setFrame(k.loopOn&&k.loop?Math.round(k.loop.a*p.fps):0);return;}
    if(e.code==='End'){e.preventDefault();setFrame(last);return;}
    if(e.code==='Escape'){const k2=keyState.current;if(k2.surfaceTool||k2.looksOpen||k2.overlay){setSurfaceTool(null);setLooksOpen(false);setOutputOpen(false);setWfStep(null);setGuidesOpen(false);return;}if(k2.selectedWall){setSelectedWall('');return;}setMulti(null);setSelected('');return;}
    // ⌫ / Delete: the wall being edited or selected, else the selected word(s) / line(s). Never from a text field (guard above).
    if(e.code==='Backspace'||e.code==='Delete'){e.preventDefault();const wall=k.surfaceTool?.id||(!k.surfaceTool?k.selectedWall:'');if(wall){textCommands.current.deleteWall(wall);return;}if(!k.surfaceTool)textCommands.current.deleteSelection();return;}
    if(e.code==='Enter'&&k.surfaceTool){e.preventDefault();void run(()=>textCommands.current.applySurface());return;}
    if(e.code==='KeyL'){const l=k.currentLine;if(l&&(!k.loopOn||!k.loop||Math.abs(k.loop.a-l.start)>.01||Math.abs(k.loop.b-l.end)>.01)){setLoop({a:l.start,b:l.end});setLoopOn(true);}else setLoopOn(v=>!v);return;}
    if(e.code==='KeyH'&&k.currentLine){toggleHidden(k.currentLine.id);return;}
    if(e.code==='KeyG'){setLooksOpen(v=>!v);return;}
    if(e.code==='KeyO'){setGuides(g=>({...g,occupancy:!g.occupancy}));return;}
    if(e.code==='KeyR'){setGuides(g=>({...g,regions:!g.regions}));return;}
    if(e.code==='KeyW'&&!k.surfaceTool){startSurface();return;}
    const n=Number(e.key);if(n>=1&&n<=LOOKS.length&&!k.surfaceTool){pickLook(LOOKS[n-1].id);return;}
  };window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);// eslint-disable-line react-hooks/exhaustive-deps
  // Stage fit: the composition takes the largest box that fits; with the 9:16 preview both frames share the height.
  useLayoutEffect(()=>{const el=stageWrap.current;if(!el)return;const ro=new ResizeObserver(()=>setStageBox({w:el.clientWidth,h:el.clientHeight}));ro.observe(el);setStageBox({w:el.clientWidth,h:el.clientHeight});return()=>ro.disconnect();},[!!project]);// eslint-disable-line react-hooks/exhaustive-deps
  const thumbs=useLookThumbs(project,frame,!playing&&!!project&&ready&&(!current||looksOpen),mediaSignature);
  const jobMap=useMemo(()=>latestJobs(jobs),[jobs]);
  // What Behind and HUD can use, as the stage loaded it: the subject matte (none / did not load / does not match the
  // footage) and a person track. Shown on the lines that need them, with the matte step one click away.
  const subject=useMemo(()=>{const r=renderer.current;const p=projectRef.current;if(!ready||!r||!p)return undefined;
    const person=!!r.tracks?.tracks.some(t=>t.frames.length);
    if(!p.analysis.matte)return {matte:'none' as const,person};const m=r.matte,b=r.bg;if(!m)return {matte:'missing' as const,person};
    const stale=!!b&&(Math.abs((m.duration||0)-(b.duration||0))>Math.max(.3,2/p.fps)||!!m.videoWidth&&!!b.videoWidth&&Math.abs(m.videoWidth/m.videoHeight-b.videoWidth/b.videoHeight)>.02);
    return {matte:stale?'stale' as const:'ok' as const,person};},[ready,mediaSignature]);// eslint-disable-line react-hooks/exhaustive-deps
  const activeWall=project?.surfaces?.find(x=>x.id===(selectedWall||(currentLine?.role==='wall'?currentLine.words[0].surfaceId:'')));
  const occKind=useMemo(()=>{try{return ready?renderer.current?.occ().kind:undefined;}catch{return undefined;}},[ready,mediaSignature]);// eslint-disable-line react-hooks/exhaustive-deps
  const exportJobs=useMemo(()=>jobs.filter(j=>j.kind==='export').sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')).slice(0,6),[jobs]);
  const runningJob=jobs.find(j=>j.status==='running'||j.status==='queued');

  if(!project)return <div className="boot"><div className="brand-mark">T<span>↗</span></div><p>{error||'loading…'}</p>{error&&<a href="#/showcase">← showcase</a>}</div>;
  const aspect=project.width/project.height;const compareAspect=project.frame?.source?16/9:9/16;
  const gap=compare?16:0;const fitH=Math.max(120,Math.min(stageBox.h-8,(stageBox.w-gap-8)/(aspect+(compare?compareAspect:0))));
  const mainSize={width:Math.round(fitH*aspect),height:Math.round(fitH)};const compSize={width:Math.round(fitH*compareAspect),height:Math.round(fitH)};
  const hhmm=(t:number)=>new Date(t).toTimeString().slice(0,5);
  const saveLabel=busy?'working…':dirty?'unsaved':savedAt?`saved ${hhmm(savedAt)}`:'saved';

  return <div className="studio">
    <header className="s-top">
      <a className="s-brand" href="#/showcase" aria-label="Back to showcase" onClick={e=>{e.preventDefault();void run(async()=>{if(dirty)await save();location.hash='/showcase';});}}><span className="s-word">typeset</span></a>
      <div className="s-proj">
        <select className="project-switch" aria-label="Switch project" value={project.id} onChange={e=>{const v=e.target.value;void run(()=>v==='+new'?create():openProject(v));}}><option value="sample">sample</option>{projects.filter(p=>p.id!=='sample').map(p=><option key={p.id} value={p.id}>{p.name}</option>)}{!projects.some(p=>p.id===project.id)&&project.id!=='sample'&&<option value={project.id}>{project.name}</option>}<option value="+new">+ new</option></select>
        <input aria-label="Project name" title={`${project.width}×${project.height} · ${project.fps} fps · ${project.duration.toFixed(2)} s${project.frame?.source?` · ${project.frame.aspect} reframe`:''}`} value={project.name} onChange={e=>edit(p=>({...p,name:e.target.value}))}/>
        <button className={`s-save ${dirty?'dirty':''}`} onClick={()=>void run(()=>save())} disabled={busy} title={`${saveLabel} · click to save`} aria-label={saveLabel}><i/></button>
        {demo!=='idle'&&<span className={`s-demo ${demo}`} role="status" aria-label={demo==='failed'?'Demo clip failed':'Demo clip updating'} title={demo==='failed'?'demo clip failed':'demo clip updating'}/>}
      </div>
      <div className="s-actions">
        <button className={`comfy-pill ${runningJob?'busy':''}`} onClick={()=>openLeft('pipeline')} title={runningJob?`${runningJob.kind} · ${runningJob.message||''}`:'comfyui pipeline'}><i/>{runningJob?`${Math.round((runningJob.progress||0)*100)}%`:'ComfyUI'}</button>
        <button className={`primary ${outputOpen?'on':''}`} onClick={()=>setOutputOpen(o=>!o)} aria-expanded={outputOpen}>Render</button>
        <ThemeToggle/>
      </div>
      {outputOpen&&<div className="output-pop" role="dialog" aria-label="Output">
        <div className="op-sec"><div className="op-h">Frame</div>
          <div className="op-row"><span className="op-ar" style={{aspectRatio:`${project.width}/${project.height}`}}/><div><b title={`${project.width}×${project.height}`}>{project.frame?.aspect||(Math.abs(aspect/(16/9)-1)<.03?'16:9':Math.abs(aspect/(9/16)-1)<.03?'9:16':Math.abs(aspect-1)<.03?'1:1':`${project.width}:${project.height}`)}</b></div></div>
          <div className="op-btns">
            {!project.frame?.source&&<button onClick={()=>void run(makeVertical)} disabled={busy} title="new 9:16 project that follows the subject">Make 9:16</button>}
          </div>
        </div>
        <div className="op-sec"><div className="op-h">Export</div>
          {FORMATS.map(f=><label key={f.id} className="op-fmt" title={f.note}><input type="checkbox" checked={formats.includes(f.id)} onChange={e=>setFormats(fs=>e.target.checked?[...fs,f.id]:fs.filter(x=>x!==f.id))}/><b>{f.label}</b></label>)}
          <button className="primary wide" onClick={()=>void run(()=>jobAction('export'))} disabled={busy||!formats.length||project.id==='sample'} title={project.id==='sample'?'sample is offline':undefined}>{busy&&job?.kind==='export'?`${Math.round((job.progress||0)*100)}%`:'Export'}</button>
        </div>
        {(exports.length>0||exportJobs.length>0)&&<div className="op-sec"><div className="op-h">Files</div>
          {exports.length>0&&<div className="export-links">{exports.map(file=><a key={file} href={assetUrl(project,file)} target="_blank" rel="noreferrer" download>{file.split('/').pop()}</a>)}</div>}
          {exportJobs.length?exportJobs.map(j=>{const r=j.result as {urls?:Record<string,string>;files?:Record<string,string>;elapsedSeconds?:number}|undefined;return <div key={j.id} className={`op-job st-${j.status}`}><span className="mono">{(j.createdAt||'').slice(5,16).replace('T',' ')}</span>
            <span className="op-files">{j.status==='done'?Object.entries(r?.files||{}).map(([k,f])=><a key={k} href={assetUrl(project,f)} target="_blank" rel="noreferrer">{k.toUpperCase()}</a>):<em>{j.status}{j.message?` · ${j.message}`:''}</em>}</span>
            <span className="mono">{r?.elapsedSeconds?`${Math.round(r.elapsedSeconds)} s`:''}</span></div>;}):null}
        </div>}
      </div>}
    </header>

    <div className={`s-main ${rail?'railed':''}`}>
      {rail?<aside className="s-left s-rail" aria-label="Pipeline and media">
        <button className="icon-sm rail-toggle" onClick={()=>setRail(false)} aria-label="Expand panel" title="Expand panel"><Icon name="rail" size={16}/></button>
        <button className="icon-sm" onClick={()=>openLeft('pipeline')} aria-label="Pipeline" title="Pipeline"><Icon name="pipeline" size={16}/></button>
        <PipelineRail project={project} jobs={jobMap} occKind={occKind} hasBeats={!!beats} comparing={compare} onOpen={()=>openLeft('pipeline')}/>
        <button className="icon-sm" onClick={()=>openLeft('media')} aria-label="Media" title="Media"><Icon name="media" size={16}/></button>
      </aside>:
      <aside className="s-left">
        <div className="s-tabsrow"><div className="s-tabs"><button className={leftTab==='pipeline'?'active':''} onClick={()=>setLeftTab('pipeline')}>Pipeline</button><button className={leftTab==='media'?'active':''} onClick={()=>setLeftTab('media')}>Media</button></div>
          <button className="icon-sm rail-toggle" onClick={()=>setRail(true)} aria-label="Collapse panel" title="Collapse panel"><Icon name="rail" size={16}/></button></div>
        {leftTab==='pipeline'?<PipelinePanel project={project} jobs={jobMap} occKind={occKind} hasBeats={!!beats} beatsNote={beats?`${beats.bpm?Math.round(beats.bpm)+' BPM · ':''}${beats.beats.length} beats${beats.sections?.length?` · ${beats.sections.length} sections`:''}`:undefined} comparing={compare} busy={busy} onRun={runStep} onOpenWorkflow={setWfStep}/>
        :<div className="media-panel">
          <button className="upload-zone" onClick={()=>uploadInput.current?.click()} disabled={busy}><Icon name="upload" size={22}/><strong>Add media</strong></button>
          {Object.entries(project.media).filter(([key,ref])=>(key==='video'||key==='audio')&&ref!=null).map(([kind,ref])=><div className="media-card" key={kind}><span className="mono">{kind==='audio'?'♪':'▶'}</span><div><strong title={typeof ref==='object'&&ref&&'path' in ref?ref.path:''}>{typeof ref==='object'&&ref&&'path' in ref?ref.path.split('/').pop():''}</strong></div></div>)}
          {waveform&&songDur>0&&<SongMap project={project} peaks={waveform} songDur={songDur} linkWords={linkWords} edit={edit} checkpoint={checkpoint}/>}
          <label className="fld"><span className="lbl">Lyrics</span><textarea rows={8} value={project.media.lyrics||''} title="Optional: the words get aligned to these" onChange={e=>edit(p=>({...p,media:{...p.media,lyrics:e.target.value}}))}/></label>
        </div>}
      </aside>}

      <main className="s-stage">
        <div className="stage-bar">
          <div className="tool-anchor">
            <button className={`tool-btn ${guidesOpen?'active':''}`} onClick={()=>setGuidesOpen(o=>!o)} aria-expanded={guidesOpen} aria-label="Guides" title="Guides on the stage"><Icon name="guides" size={15}/></button>
            {guidesOpen&&<div className="guides-pop" role="menu" aria-label="Guides" onMouseLeave={()=>setGuidesOpen(false)}>
              {([['regions','Line boxes','R'],['occupancy','Subject','O'],['anchor','Head anchor',''],['walls','Walls','']] as const).map(([k,label,key])=>
                <label key={k} className="check" role="menuitemcheckbox" aria-checked={!!guides[k]}><input type="checkbox" checked={!!guides[k]} onChange={()=>setGuides(g=>({...g,[k]:!g[k]}))}/>{label}{key&&<kbd>{key}</kbd>}</label>)}
            </div>}
          </div>
          {activeWall&&!surfaceTool&&<div className="wall-tools" role="group" aria-label={activeWall.label||'Wall'}><span className="wt-name" title={activeWall.label||activeWall.id}><Icon name="wall" size={14}/></span>
            <WallButtons surface={activeWall} running={!!wallJob} busy={busy} fallback={wallFallback(project)} onTrack={()=>void run(()=>trackSurface(project,activeWall.id))} onRedraw={()=>startSurface(activeWall.id)} onDelete={()=>deleteWall(activeWall.id)}/></div>}
          <button className={`tool-btn ${compare?'active':''}`} onClick={()=>setCompare(c=>!c)} aria-pressed={compare} aria-label={project.frame?.source?'Compare with source':'Compare 9:16'} title={project.frame?.source?'Side by side with the source':'Side by side with a 9:16 reframe'}><Icon name="compare" size={15}/></button>
        </div>
        <div className={`stage-wrap ${compare?'comparing':''}`} ref={stageWrap}>
          <div className="stage-border" style={mainSize} onPointerDown={e=>{if(!surfaceTool&&(e.target as Element).tagName==="CANVAS"){setMulti(null);setSelected("");setSelectedWall("");}}}>
            <canvas id="stage" ref={canvas} aria-label="Video composition preview" style={mainSize}/>
            {ready&&!surfaceTool&&<StageGuides renderer={renderer.current} project={project} frame={frame} guides={guides} selectedLine={current?.lineId} onSelectLine={id=>{setMulti(null);setSelectedWall('');setSelScope('line');const w=project.words.find(x=>x.lineId===id);if(w&&current?.lineId!==id)setSelected(w.id);}} onDragLine={dragLine} onResizeLine={resizeLine} box={mainSize}
              selectedWall={selectedWall||undefined} onSelectWall={setSelectedWall} onWallEdit={wallEdit}/>}
            {!ready&&<div className="stage-loading">loading…</div>}
            {surfaceTool&&<WallTool W={project.width} H={project.height} corners={surfaceTool.corners} setCorners={f=>setSurfaceTool(t=>t&&({...t,corners:f(t.corners)}))}/>}
            {compare&&<span className="stage-label">{project.frame?.source?`${project.frame.aspect}`:'original'}</span>}
          </div>
          {compare&&<div className="stage-border compare" style={compSize}><canvas ref={compareCanvas} aria-label="Reframe comparison preview" style={compSize}/>{!compareReady&&<div className="stage-loading">loading…</div>}<span className="stage-label">{project.frame?.source?'source':'9:16'}</span></div>}
          {looksOpen&&<LookPicker project={project} thumbs={thumbs} onPick={id=>pickLook(id)} expanded onClose={()=>setLooksOpen(false)}/>}
        </div>
        {surfaceTool&&<WallBar corners={surfaceTool.corners} editing={!!surfaceTool.id} busy={busy} onRedraw={()=>setSurfaceTool(t=>t&&({...t,corners:[]}))}
          onDelete={surfaceTool.id?()=>deleteWall(surfaceTool.id!):undefined} onCancel={()=>setSurfaceTool(null)} onPlace={()=>void run(applySurface)}/>}
        <div className="transport">
          <span className="time-display mono" title={`frame ${frame} / ${totalFrames}`}>{timecode(time)}<span> / {timecode(project.duration)}</span></span>
          <div className="transport-controls">
            <button className="icon-button" aria-label="Back one frame" onClick={()=>seekFrame(frame-1)}><Icon name="prev" size={14}/></button>
            <button className="play-button" aria-label={playing?'Pause':'Play'} onClick={()=>setPlaying(p=>!p)} disabled={!ready}><Icon name={playing?'pause':'play'} size={16}/></button>
            <button className="icon-button" aria-label="Forward one frame" onClick={()=>seekFrame(frame+1)}><Icon name="next" size={14}/></button>
            <button className={`icon-button ${loopOn?'on':''}`} aria-label="Loop" title="Loop the selected line, or drag on the ruler top (L)" onClick={()=>{if(!loopOn&&!loop)setLoop(currentLine?{a:currentLine.start,b:currentLine.end}:{a:0,b:project.duration});setLoopOn(v=>!v);}}><Icon name="loop" size={14}/></button>
          </div>
          <div className="transport-right"><button className="icon-button" aria-label={muted?'Unmute':'Mute'} onClick={()=>setMuted(m=>!m)}><Icon name={muted?'mute':'sound'}/></button></div>
        </div>
      </main>

      <aside className="s-right">
        {multi&&multi.ids.length>1?<GroupInspector project={project} lineIds={multi.ids} title={multi.title} edit={edit} checkpoint={checkpoint} onClear={()=>setMulti(null)}/>
        :current&&currentLine?<LineInspector project={project} line={currentLine} word={current} selected={selected} setSelected={id=>{setSelected(id);}} edit={edit} checkpoint={checkpoint} onBack={()=>{setSelected('');setMulti(null);}} busy={busy}
          startSurface={startSurface} trackSurface={id=>void run(()=>trackSurface(project,id))} generate={()=>void run(()=>jobAction('inworld'))} prompt={prompt} setPrompt={setPrompt} wordOpen={wordOpen} setWordOpen={setWordOpen}
          box={!playing&&ready?lineBoxes(renderer.current,project,frame).find(x=>x.lineId===currentLine.id&&x.placement!=='surface'):undefined}
          subject={subject} matteRunning={jobMap.get('matte')?.status==='running'||jobMap.get('matte')?.status==='queued'} runMatte={()=>runStep('matte')} deleteWall={deleteWall} wallRunning={!!wallJob}/>
        :<LookPicker project={project} thumbs={thumbs} onPick={id=>pickLook(id)} onExpand={()=>setLooksOpen(true)} edit={edit}/>}
      </aside>
    </div>

    <Timeline project={project} frame={frame} playing={playing} selectedWord={selected} selectedLine={current?.lineId} waveform={waveform} beats={beats}
      loop={loop} loopOn={loopOn} snap={snap} zoom={zoom} setZoom={setZoom} setSnap={setSnap} setLoop={setLoop} setLoopOn={setLoopOn}
      multi={multi?.ids} onPickGroup={pickGroup} onToggleLine={toggleLine}
      onCopy={copySelection} onPaste={pasteSelection} onSplit={splitSelection} canCopy={selectedLines.length>0} canPaste={canPaste} canSplit={canSplit}
      onCheckpoint={checkpoint} onDropAudio={f=>void run(()=>replaceSong(f))} onRealign={songStale?()=>void run(realign):undefined}
      onSelect={(id,seek,scope)=>{setMulti(null);setSelectedWall('');setSelScope(scope||'line');setSelected(id);const w=project.words.find(x=>x.id===id);if(seek&&w)seekFrame((w.start+.04)*project.fps);}} onSeek={seekFrame} onEdit={edit} onToggleHidden={toggleHidden} onAddWord={addWord}
      onAddAt={addTextAt} onDelete={t=>deleteSelection(t)} inlineEdit={inlineEdit} onEditText={id=>{setSelected(id);setSelScope('word');setInlineEdit({wordId:id,fresh:false});}} onCommitText={commitText} onCancelText={cancelText}
      onSetHidden={(ids,hide)=>edit(p=>ids.reduce((q,id)=>setLineMeta(q,id,{hidden:hide?true:null}),p))} subject={subject}
      videoSrc={project.media.video?assetUrl(project,project.media.video.path):undefined} crop={ready?renderer.current?.crop:undefined}
      clip={songRef(project)&&songDur?clipOf(project,songDur):null} songDur={songDur||undefined} linkWords={linkWords} setLinkWords={setLinkWords}/>

    <footer className={`statusbar ${error?'error':''} ${error||busy||notice?'show':''}`} role="status" onClick={()=>setError('')} title={error?'dismiss':undefined}>{(error||busy||notice)&&<span><i className={busy?'pulsing':''}/>{error||(busy?`${job?.message||'working'}`:notice)}</span>}</footer>
    {wfStep&&<WorkflowSheet step={wfStep} onClose={()=>setWfStep(null)}/>}
    <input ref={uploadInput} type="file" accept="video/*,audio/*" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void run(()=>upload(file));e.target.value='';}}/>
    {(project.media.audio||project.media.video)&&<audio ref={audio} preload="auto" src={assetUrl(project,(project.media.audio||project.media.video)!.path)}/>}
  </div>;
}
