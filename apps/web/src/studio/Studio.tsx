// Typeset Studio v3: stage-first editor. Layout: top bar · [Pipeline/Media | Stage | Look + Line] · Arrangement · status.
import {useState,useEffect,useLayoutEffect,useRef,useCallback,useMemo} from 'react';
import type {Project,Word,Job,LookId,Surface,Point} from '../types';
import {request,getProject,assetUrl,pollJob} from '../api';
import {StageRenderer,loadFonts} from '../renderer';
import {reframeProject} from '../reframe';
import {prepareExport} from '../exportFrames';
import {squareToQuad,applyH,quadIsConvex,cropAt,toOut,toSource} from '../geometry';
import {LOOKS,setLook,setLineMeta} from '../looks';
import {Timeline,lineInfos} from './Timeline';
import {StageGuides,lineBoxes,type Guides} from './StageOverlay';
import {LookPicker,useLookThumbs} from './LookPicker';
import {LineInspector} from './LineInspector';
import {PipelinePanel,WorkflowSheet} from './PipelinePanel';
import {latestJobs,parseBeats,type Beats,type JobRecord,type StepDef,type StepId} from './pipeline';
import {ThemeToggle} from './ThemeToggle';
import './studio.css';

const timecode=(time:number)=>`${Math.floor(time/60).toString().padStart(2,'0')}:${Math.floor(time%60).toString().padStart(2,'0')}.${Math.floor((time%1)*100).toString().padStart(2,'0')}`;
type Fmt='mp4'|'mov'|'webm';
const FORMATS:{id:Fmt;label:string;note:string}[]=[{id:'mp4',label:'mp4',note:'composite · H.264 + audio'},{id:'mov',label:'mov',note:'text layer · ProRes 4444 alpha'},{id:'webm',label:'webm',note:'text layer · VP9 alpha'}];

function Icon({name,size=16}:{name:string;size?:number}){const paths:Record<string,React.ReactNode>={play:<path d="m8 5 11 7-11 7Z"/>,pause:<path d="M8 5v14M16 5v14"/>,upload:<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>,download:<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>,sound:<path d="M4 10v4h4l5 4V6l-5 4Zm13-3a8 8 0 0 1 0 10"/>,mute:<path d="M4 10v4h4l5 4V6l-5 4Zm13-1 5 6m0-6-5 6"/>,loop:<path d="M17 2l3 3-3 3M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3m13-3v2a4 4 0 0 1-4 4H4"/>,prev:<path d="M6 5v14M18 5 9 12l9 7Z"/>,next:<path d="M18 5v14M6 5l9 7-9 7Z"/>};return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;}

export default function Studio({initialProjectId='sample'}:{initialProjectId?:string}){
  const [project,setProject]=useState<Project|null>(null);const [projects,setProjects]=useState<Project[]>([]);const [selected,setSelected]=useState('');const [frame,setFrame]=useState(24);const [playing,setPlaying]=useState(false);const [muted,setMuted]=useState(true);const [busy,setBusy]=useState(false);const [job,setJob]=useState<Job|null>(null);const [notice,setNotice]=useState('');const [error,setError]=useState('');const [dirty,setDirty]=useState(false);const [ready,setReady]=useState(false);
  const [waveform,setWaveform]=useState<Float32Array|null>(null);const [prompt,setPrompt]=useState('Sculptural letters made from polished chrome, gentle camera push in, studio lighting');const [leftTab,setLeftTab]=useState<'pipeline'|'media'>('pipeline');const [exports,setExports]=useState<string[]>([]);
  const [jobs,setJobs]=useState<JobRecord[]>([]);const [beats,setBeats]=useState<Beats|undefined>();const [guides,setGuides]=useState<Guides>({occupancy:false,regions:true,anchor:true});
  const [zoom,setZoom]=useState(1);const [snap,setSnap]=useState(true);const [loop,setLoop]=useState<{a:number;b:number}|null>(null);const [loopOn,setLoopOn]=useState(false);
  const [wordOpen,setWordOpen]=useState(false);const [looksOpen,setLooksOpen]=useState(false);const [outputOpen,setOutputOpen]=useState(false);const [wfStep,setWfStep]=useState<StepDef|null>(null);const [formats,setFormats]=useState<Fmt[]>(['mp4','mov','webm']);const [savedAt,setSavedAt]=useState<number|null>(null);
  // Surface tool: corners in OUTPUT-normalized coords while drawing; `id` set when re-drawing an existing surface.
  const [surfaceTool,setSurfaceTool]=useState<{corners:Point[];id?:string}|null>(null);const dragCorner=useRef<number|null>(null);const overlay=useRef<SVGSVGElement>(null);
  // Side-by-side: original vs. client-side 9:16 reframe (or, in a reframed project, its source).
  const [compare,setCompare]=useState(false);const compareCanvas=useRef<HTMLCanvasElement>(null);const compareRenderer=useRef<StageRenderer>();const [compareReady,setCompareReady]=useState(false);const comparing=useRef(false);const compareRequested=useRef(0);
  const canvas=useRef<HTMLCanvasElement>(null);const renderer=useRef<StageRenderer>();const rendering=useRef(false);const requested=useRef(0);const uploadInput=useRef<HTMLInputElement>(null);const audio=useRef<HTMLAudioElement>(null);const stageWrap=useRef<HTMLDivElement>(null);const projectRef=useRef(project);projectRef.current=project;
  const [stageBox,setStageBox]=useState({w:800,h:450});
  const current=project?.words.find(w=>w.id===selected);const time=project?frame/project.fps:0;
  const lines=useMemo(()=>project?lineInfos(project):[],[project]);const currentLine=lines.find(l=>l.id===current?.lineId);
  const totalFrames=project?Math.max(1,Math.round(project.duration*project.fps)):1;
  const edit=useCallback((update:(p:Project)=>Project)=>{setProject(p=>p?update(p):p);setDirty(true);},[]);
  const changeProject=useCallback((p:Project)=>{setProject(p);setSelected(p.words[0]?.id||'');setFrame(Math.min(Math.round(.8*p.fps),Math.max(0,Math.round(p.duration*p.fps)-1)));setPlaying(false);setDirty(false);setExports([]);setError('');setLoop(null);setLoopOn(false);setCompare(false);setSurfaceTool(null);},[]);
  useEffect(()=>{let live=true;const initial=initialProjectId==='sample'?request<Project>('/sample/project.json'):getProject(initialProjectId);initial.then(p=>{if(live){const saved=initialProjectId==='sample'?localStorage.getItem('typeset.sample'):null;if(saved){try{p=JSON.parse(saved);}catch{/* fresh sample */}}changeProject(p);}}).catch(e=>{if(live)setError(String(e));});request<Project[]>('/api/projects').then(p=>{if(live)setProjects(p);}).catch(()=>{});return()=>{live=false;};},[changeProject,initialProjectId]);
  const mediaSignature=JSON.stringify([project?.id,project?.media.video,project?.analysis,project?.shots]);
  useEffect(()=>{if(!projectRef.current)return;let live=true;const r=new StageRenderer(projectRef.current);setReady(false);renderer.current?.dispose();renderer.current=r;
    r.load().then(()=>{if(live)setReady(true);}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;r.dispose();};
  },[mediaSignature]);
  useEffect(()=>{const r=renderer.current;if(r&&project)r.project=project;if(!ready||!r||!canvas.current)return;requested.current=frame;
    const draw=async()=>{if(rendering.current)return;rendering.current=true;try{do{const f=requested.current;await r.render(canvas.current!,f);if(f===requested.current)break;}while(true);}catch(e){setError(String(e));}finally{rendering.current=false;}};void draw();
  },[frame,project,ready]);
  useEffect(()=>{if(!compare||!ready||!projectRef.current||!renderer.current){compareRenderer.current?.dispose();compareRenderer.current=undefined;setCompareReady(false);return;}
    let live=true;const base=projectRef.current;const source=base.frame?.source?.projectId;
    const make=async()=>{let r:StageRenderer;
      if(source){r=new StageRenderer(await getProject(source));}
      else{await loadFonts();const {project:rp,crop}=reframeProject(base,'9:16',renderer.current?.tracks);r=new StageRenderer(rp);r.crop=crop;}
      await r.load();if(!live){r.dispose();return;}compareRenderer.current=r;setCompareReady(true);};
    make().catch(e=>{if(live)setError(String(e));});
    return()=>{live=false;compareRenderer.current?.dispose();compareRenderer.current=undefined;setCompareReady(false);};
  },[compare,ready,mediaSignature]);
  useEffect(()=>{const r=compareRenderer.current;const p=projectRef.current;if(!compareReady||!r||!p||!compareCanvas.current)return;
    if(!p.frame?.source)r.project=reframeProject(p,'9:16',renderer.current?.tracks,r.crop).project;
    compareRequested.current=frame;
    const draw=async()=>{if(comparing.current)return;comparing.current=true;try{do{const f=compareRequested.current;await r.render(compareCanvas.current!,f);if(f===compareRequested.current)break;}while(true);}catch(e){setError(String(e));}finally{comparing.current=false;}};void draw();
  },[frame,project,compareReady]);
  // Waveform: min/max peaks (2 floats per bin) so the arrangement can redraw at any zoom.
  useEffect(()=>{if(!project)return;const path=project.media.audio?.path||project.media.video?.path;if(!path){setWaveform(null);return;}let live=true;const context=new AudioContext();
    fetch(assetUrl(project,path)).then(r=>r.arrayBuffer()).then(b=>context.decodeAudioData(b)).then(buffer=>{const data=buffer.getChannelData(0);const bins=Math.min(6000,Math.max(400,Math.round(buffer.duration*200)));const size=Math.max(1,Math.floor(data.length/bins));const out=new Float32Array(bins*2);let max=.001;
      for(let i=0;i<bins;i++){let lo=0,hi=0;for(let j=i*size;j<Math.min(data.length,(i+1)*size);j+=4){const v=data[j];if(v<lo)lo=v;if(v>hi)hi=v;}out[i*2]=lo;out[i*2+1]=hi;max=Math.max(max,hi,-lo);}
      for(let i=0;i<out.length;i++)out[i]/=max;if(live)setWaveform(out);}).catch(()=>{if(live)setWaveform(null);}).finally(()=>{void context.close();});return()=>{live=false;};},[project?.id,project?.media.audio?.path,project?.media.video?.path]);// eslint-disable-line react-hooks/exhaustive-deps
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
    const L=loopRef.current;if(L.loopOn&&L.loop&&L.loop.b-L.loop.a>.05&&fractional>=L.loop.b*project.fps){fractional=L.loop.a*project.fps;if(audio.current)audio.current.currentTime=L.loop.a;}
    if(fractional>=project.duration*project.fps){if(L.loopOn){fractional=(L.loop?.a||0)*project.fps;if(audio.current)audio.current.currentTime=fractional/project.fps;}else{setPlaying(false);setFrame(0);return;}}
    setFrame(Math.floor(fractional));raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);},[playing,project?.fps,project?.duration]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{const a=audio.current;if(!a)return;a.muted=muted;if(playing){a.currentTime=time;void a.play().catch(()=>{});}else a.pause();},[playing,muted,project?.id]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{if(!playing&&audio.current&&Math.abs(audio.current.currentTime-time)>.1)audio.current.currentTime=time;},[time,playing]);
  useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before);},[dirty]);
  async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function save(p=projectRef.current,quiet=false){if(!p)return;if(p.id==='sample'){localStorage.setItem('typeset.sample',JSON.stringify(p));if(!quiet)setNotice('Saved');}else{await request<Project>(`/api/projects/${p.id}`,{method:'PUT',body:JSON.stringify(p)});if(!quiet)setNotice('Saved');}setDirty(false);setSavedAt(Date.now());}
  // Autosave (debounced PUT). Never while a job runs: the job's result is re-fetched first, then edits resume (docs/server.md).
  useEffect(()=>{if(!dirty||busy||!project)return;const t=setTimeout(()=>{void save(projectRef.current,true).catch(e=>setError(String(e)));},1200);return()=>clearTimeout(t);},[project,dirty,busy]);// eslint-disable-line react-hooks/exhaustive-deps
  async function create(){const p=await request<Project>('/api/projects',{method:'POST',body:JSON.stringify({name:'Untitled study'})});setProjects(items=>[p,...items]);changeProject(p);setNotice('');setLeftTab('media');}
  async function openProject(id:string){if(dirty)await save();location.hash=`/studio?project=${id}`;}
  async function upload(file:File){let p=project!;if(p.id==='sample'){p=await request<Project>('/api/projects',{method:'POST',body:JSON.stringify({name:file.name.replace(/\.[^.]+$/,'')})});}const form=new FormData();form.append('file',file);form.append('kind',file.type.startsWith('audio/')?'audio':'video');await request(`/api/projects/${p.id}/media`,{method:'POST',body:form});p=await getProject(p.id);changeProject(p);setProjects(items=>[p,...items.filter(item=>item.id!==p.id)]);setNotice('Media ready');}
  /** Re-fetch after any analysis job, before the next PUT (a stale copy would overwrite the job's fields). */
  async function refetch(p:Project){const updated=await getProject(p.id);setProject(updated);setDirty(false);setSelected(s=>updated.words.some(w=>w.id===s)?s:updated.words[0]?.id||'');await refreshJobs(p.id);return updated;}
  async function jobAction(kind:'words'|'matte'|'inworld'|'export'){
    if(!project)return;if(project.id==='sample')throw new Error('The sample is offline. Start a project to run this.');if(kind==='inworld'&&(!current||project.duration<=current.start))throw new Error('Pick a word first');await save(project,true);
    const path=kind==='words'||kind==='matte'?`analyze/${kind}`:kind==='inworld'?'generate/inworld':'export';
    const body=kind==='words'?{language:'auto'}:kind==='inworld'?{wordIds:current?[current.id]:[],prompt,start:current?.start||0,end:Math.min(project.duration,Math.max((current?.start||0)+2,current?.end||2))}:kind==='export'?{layer:'composite',formats,...await prepareExport(project,'composite',formats,setNotice)}:{};
    const start=await request<Job>(`/api/projects/${project.id}/${path}`,{method:'POST',body:JSON.stringify(body)});const done=await pollJob(start,trackJob);
    if(kind==='export'){const result=done.result as {files?:Record<string,string>};setExports(Object.values(result?.files||{}));setNotice('Exported');setOutputOpen(true);await refreshJobs();}
    else{await refetch(project);setNotice(`${kind==='inworld'?'Shot':kind==='words'?'Words':'Matte'} done`);}trackJob(done);
  }
  /** POST that tolerates a missing endpoint (S may not have shipped it yet): returns null on 404/405. */
  async function optionalJob(path:string,body:unknown):Promise<Job|null>{
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(r.status===405)return null;if(r.status===404){const detail=await r.text();if(/surface not found/i.test(detail))throw new Error(detail);return null;}if(!r.ok)throw new Error(await r.text());return r.json();
  }
  async function analysisJob(kind:'occupancy'|'beats'|'flow'|'voice'){
    if(!project||project.id==='sample')return;await save(project,true);
    const j=await optionalJob(`/api/projects/${project.id}/analyze/${kind}`,{});if(!j){setNotice(`${kind} unavailable`);return;}
    const done=await pollJob(j,trackJob);trackJob(done);await refetch(project);setNotice(`${kind} done`);
  }
  function runStep(id:StepId){if(id==='words'||id==='matte')void run(()=>jobAction(id));else if(id==='occupancy'||id==='beats'||id==='flow'||id==='voice')void run(()=>analysisJob(id));}
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
    const lineId=current?.lineId;
    const next:Project={...project,surfaces:[...(project.surfaces||[]).filter(x=>x.id!==id),surface],
      words:project.words.map(w=>current&&w.lineId===lineId&&(w.id===current.id||w.placement===current.placement)?{...w,placement:'surface',surfaceId:id}:w)};
    setProject(next);setDirty(true);setSurfaceTool(null);
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
    if(phase==='start'){setPlaying(false);const b=lineBoxes(renderer.current,p,frame).find(x=>x.lineId===lineId);const align=first.style?.align||p.style.align;
      const x=b?(b.x+(align==='left'?0:align==='right'?b.w:b.w/2))/p.width:first.position?.x??.5,y=b?(b.y+b.h/2)/p.height:first.position?.y??.72;
      dragStart.current={x,y,dx:first.anchor?.dx||0,dy:first.anchor?.dy||0};return;}
    const s=dragStart.current;if(!s)return;if(phase==='end')dragStart.current=null;if(Math.abs(dx)+Math.abs(dy)<.002)return;
    const cl=(v:number)=>Math.max(0,Math.min(1,v));
    if(placement==='anchor')edit(q=>({...q,words:q.words.map(w=>w.lineId===lineId?{...w,anchor:{trackId:w.anchor?.trackId||'person0',dx:+(s.dx+dx).toFixed(4),dy:+(s.dy+dy).toFixed(4)}}:w)}));
    else edit(q=>({...q,words:q.words.map(w=>w.lineId===lineId&&w.placement===placement?{...w,position:{x:+cl(s.x+dx).toFixed(4),y:+cl(s.y+dy).toFixed(4)}}:w)}));
  };
  const seekFrame=(f:number)=>{setPlaying(false);setFrame(Math.max(0,Math.min(Math.round((projectRef.current?.duration||0)*(projectRef.current?.fps||24))-1,Math.round(f))));};
  function addWord(){if(!project)return;if(project.duration<=0){setError('Add media first');return;}const start=Math.min(time,Math.max(0,project.duration-.1));const word:Word={id:crypto.randomUUID(),text:'word',start,end:Math.min(project.duration,start+.8),lineId:crypto.randomUUID(),placement:'overlay',preset:'pop'};edit(p=>({...p,words:[...p.words,word].sort((a,b)=>a.start-b.start)}));setSelected(word.id);setWordOpen(true);}
  // Keyboard transport + tools.
  const keyState=useRef({project,currentLine,loop,loopOn,surfaceTool,looksOpen});keyState.current={project,currentLine,loop,loopOn,surfaceTool,looksOpen};
  useEffect(()=>{const key=(e:KeyboardEvent)=>{const target=e.target as HTMLElement;if(target.matches('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey)return;const k=keyState.current;const p=k.project;if(!p)return;const last=Math.round(p.duration*p.fps)-1;
    if(e.code==='Space'){e.preventDefault();setPlaying(v=>!v);return;}
    if(e.code==='ArrowRight'){e.preventDefault();setFrame(f=>Math.min(f+(e.shiftKey?p.fps:1),last));return;}
    if(e.code==='ArrowLeft'){e.preventDefault();setFrame(f=>Math.max(0,f-(e.shiftKey?p.fps:1)));return;}
    if(e.code==='Home'){e.preventDefault();setFrame(k.loopOn&&k.loop?Math.round(k.loop.a*p.fps):0);return;}
    if(e.code==='End'){e.preventDefault();setFrame(last);return;}
    if(e.code==='Escape'){setSurfaceTool(null);setLooksOpen(false);setOutputOpen(false);setWfStep(null);return;}
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
  const thumbs=useLookThumbs(project,frame,!playing&&!!project&&ready,mediaSignature);
  const jobMap=useMemo(()=>latestJobs(jobs),[jobs]);
  const occKind=useMemo(()=>{try{return ready?renderer.current?.occ().kind:undefined;}catch{return undefined;}},[ready,mediaSignature]);// eslint-disable-line react-hooks/exhaustive-deps
  const exportJobs=useMemo(()=>jobs.filter(j=>j.kind==='export').sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')).slice(0,6),[jobs]);
  const runningJob=jobs.find(j=>j.status==='running'||j.status==='queued');

  if(!project)return <div className="boot"><div className="brand-mark">T<span>↗</span></div><p>{error||'loading…'}</p>{error&&<a href="#/showcase">← showcase</a>}</div>;
  const aspect=project.width/project.height;const compareAspect=project.frame?.source?16/9:9/16;
  const gap=compare?16:0;const fitH=Math.max(120,Math.min(stageBox.h-8,(stageBox.w-gap-8)/(aspect+(compare?compareAspect:0))));
  const mainSize={width:Math.round(fitH*aspect),height:Math.round(fitH)};const compSize={width:Math.round(fitH*compareAspect),height:Math.round(fitH)};
  const surfaceOverlay=()=>{
    if(!surfaceTool)return null;const W=project.width,H=project.height;const pts=surfaceTool.corners.map(([x,y])=>[x*W,y*H] as Point);
    const grid:[Point,Point][]=[];
    if(pts.length===4&&quadIsConvex(pts)){const h=squareToQuad(pts);for(let i=1;i<8;i++)grid.push([applyH(h,i/8,0),applyH(h,i/8,1)]);for(let j=1;j<4;j++)grid.push([applyH(h,0,j/4),applyH(h,1,j/4)]);}
    const r=Math.max(W,H)*.011;
    const pt=(e:React.PointerEvent):Point|null=>{const svg=overlay.current;if(!svg)return null;const b=svg.getBoundingClientRect();return [Math.min(1.2,Math.max(-.2,(e.clientX-b.left)/b.width)),Math.min(1.2,Math.max(-.2,(e.clientY-b.top)/b.height))];};
    return <svg ref={overlay} className="surface-overlay" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
      onPointerDown={e=>{if((e.target as Element).closest('.handle')||surfaceTool.corners.length>=4)return;const q=pt(e);if(q)setSurfaceTool(t=>t&&({...t,corners:[...t.corners,q]}));}}
      onPointerMove={e=>{const i=dragCorner.current;if(i===null)return;const q=pt(e);if(q)setSurfaceTool(t=>t&&({...t,corners:t.corners.map((c,k)=>k===i?q:c)}));}}
      onPointerUp={e=>{dragCorner.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}>
      {pts.length===4&&<polygon points={pts.map(p=>p.join(',')).join(' ')} className={quadIsConvex(pts)?'quad':'quad bad'} style={{strokeWidth:r*.22}}/>}
      {pts.length>1&&pts.length<4&&<polyline points={pts.map(p=>p.join(',')).join(' ')} className="quad open" style={{strokeWidth:r*.22}}/>}
      {grid.map(([a,b],i)=><line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="grid" style={{strokeWidth:r*.1}}/>)}
      {pts.map((p,i)=><g key={i} className="handle" onPointerDown={e=>{e.stopPropagation();dragCorner.current=i;overlay.current?.setPointerCapture(e.pointerId);}}><circle cx={p[0]} cy={p[1]} r={r} style={{strokeWidth:r*.22}}/><text x={p[0]+r*1.4} y={p[1]-r*1.2} style={{fontSize:r*1.5}}>{['TL','TR','BR','BL'][i]}</text></g>)}
    </svg>;
  };
  const lineText=current?project.words.filter(w=>w.lineId===current.lineId).map(w=>w.text).join(' '):'';
  const hhmm=(t:number)=>new Date(t).toTimeString().slice(0,5);
  const saveLabel=busy?'working…':dirty?'unsaved':savedAt?`saved ${hhmm(savedAt)}`:'saved';

  return <div className="studio">
    <header className="s-top">
      <a className="s-brand" href="#/showcase" aria-label="Back to showcase" onClick={e=>{e.preventDefault();void run(async()=>{if(dirty)await save();location.hash='/showcase';});}}><span className="s-word">typeset</span></a>
      <div className="s-proj">
        <select className="project-switch" aria-label="Switch project" value={project.id} onChange={e=>{const v=e.target.value;void run(()=>v==='+new'?create():openProject(v));}}><option value="sample">sample</option>{projects.filter(p=>p.id!=='sample').map(p=><option key={p.id} value={p.id}>{p.name}</option>)}{!projects.some(p=>p.id===project.id)&&project.id!=='sample'&&<option value={project.id}>{project.name}</option>}<option value="+new">+ new</option></select>
        <input aria-label="Project name" title={`${project.width}×${project.height} · ${project.fps} fps · ${project.duration.toFixed(2)} s${project.frame?.source?` · ${project.frame.aspect} reframe`:''}`} value={project.name} onChange={e=>edit(p=>({...p,name:e.target.value}))}/>
        <button className={`s-save ${dirty?'dirty':''}`} onClick={()=>void run(()=>save())} disabled={busy} title={`${saveLabel} · click to save`} aria-label={saveLabel}><i/></button>
      </div>
      <div className="s-actions">
        <button className={`comfy-pill ${runningJob?'busy':''}`} onClick={()=>setLeftTab('pipeline')} title={runningJob?`${runningJob.kind} · ${runningJob.message||''}`:'comfyui pipeline'}><i/>{runningJob?`${Math.round((runningJob.progress||0)*100)}%`:'ComfyUI'}</button>
        <button className={`primary ${outputOpen?'on':''}`} onClick={()=>setOutputOpen(o=>!o)} aria-expanded={outputOpen}>Render</button>
        <ThemeToggle/>
      </div>
      {outputOpen&&<div className="output-pop" role="dialog" aria-label="Output">
        <div className="op-sec"><div className="op-h">Frame</div>
          <div className="op-row"><span className="op-ar" style={{aspectRatio:`${project.width}/${project.height}`}}/><div><b title={`${project.width}×${project.height}`}>{project.frame?.aspect||(Math.abs(aspect/(16/9)-1)<.03?'16:9':Math.abs(aspect/(9/16)-1)<.03?'9:16':Math.abs(aspect-1)<.03?'1:1':`${project.width}:${project.height}`)}</b></div></div>
          <div className="op-btns">
            {!project.frame?.source&&<button onClick={()=>void run(makeVertical)} disabled={busy} title="new 9:16 project that follows the subject">Make 9:16</button>}
            <button className={compare?'on':''} onClick={()=>setCompare(c=>!c)} title="side by side">Compare</button>
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

    <div className="s-main">
      <aside className="s-left">
        <div className="s-tabs"><button className={leftTab==='pipeline'?'active':''} onClick={()=>setLeftTab('pipeline')}>Pipeline</button><button className={leftTab==='media'?'active':''} onClick={()=>setLeftTab('media')}>Media</button></div>
        {leftTab==='pipeline'?<PipelinePanel project={project} jobs={jobMap} occKind={occKind} hasBeats={!!beats} beatsNote={beats?`${beats.bpm?Math.round(beats.bpm)+' BPM · ':''}${beats.beats.length} beats${beats.sections?.length?` · ${beats.sections.length} sections`:''}`:undefined} comparing={compare} busy={busy} onRun={runStep} onOpenWorkflow={setWfStep}/>
        :<div className="media-panel">
          <button className="upload-zone" onClick={()=>uploadInput.current?.click()} disabled={busy}><Icon name="upload" size={22}/><strong>Add media</strong></button>
          {Object.entries(project.media).filter(([key,ref])=>key!=='lyrics'&&ref!=null).map(([kind,ref])=><div className="media-card" key={kind}><span className="mono">{kind==='audio'?'♪':'▶'}</span><div><strong title={typeof ref==='object'&&ref?ref.path:''}>{typeof ref==='object'&&ref?ref.path.split('/').pop():''}</strong></div></div>)}
          <label className="fld"><span className="lbl">Lyrics</span><textarea rows={8} value={project.media.lyrics||''} title="optional: the words get aligned to these" onChange={e=>edit(p=>({...p,media:{...p.media,lyrics:e.target.value}}))}/></label>
        </div>}
      </aside>

      <main className="s-stage">
        <div className="stage-bar">
          <div className="tool-group">
            <button className={surfaceTool?'active':''} onClick={()=>surfaceTool?setSurfaceTool(null):startSurface()} title="draw a wall and put the selected line on it (W)">Wall</button>
          </div>
          <div className="tool-group">
            <button className={guides.regions?'active':''} onClick={()=>setGuides(g=>({...g,regions:!g.regions}))} title="line regions and walls (R)">Regions</button>
            <button className={guides.occupancy?'active':''} onClick={()=>setGuides(g=>({...g,occupancy:!g.occupancy}))} title="subject occupancy from the matte (O)">Subject</button>
            <button className={guides.anchor?'active':''} onClick={()=>setGuides(g=>({...g,anchor:!g.anchor}))} title="hud head anchor">Anchor</button>
          </div>
          <div className="tool-group">
            <button className={compare?'active':''} onClick={()=>setCompare(c=>!c)} title="side-by-side reframe">{project.frame?.source?'Source':'9:16'}</button>
            <button className={looksOpen?'active':''} onClick={()=>setLooksOpen(o=>!o)} title="all looks on this frame (G)">Looks</button>
          </div>
        </div>
        <div className={`stage-wrap ${compare?'comparing':''}`} ref={stageWrap}>
          <div className="stage-border" style={mainSize}>
            <canvas id="stage" ref={canvas} aria-label="Video composition preview" style={mainSize}/>
            {ready&&!surfaceTool&&<StageGuides renderer={renderer.current} project={project} frame={frame} guides={guides} selectedLine={current?.lineId} onSelectLine={id=>{const w=project.words.find(x=>x.lineId===id);if(w&&current?.lineId!==id)setSelected(w.id);}} onDragLine={dragLine} box={mainSize}/>}
            {!ready&&<div className="stage-loading">loading…</div>}
            {surfaceOverlay()}
            {compare&&<span className="stage-label">{project.frame?.source?`${project.frame.aspect}`:'original'}</span>}
          </div>
          {compare&&<div className="stage-border compare" style={compSize}><canvas ref={compareCanvas} aria-label="Reframe comparison preview" style={compSize}/>{!compareReady&&<div className="stage-loading">loading…</div>}<span className="stage-label">{project.frame?.source?'source':'9:16'}</span></div>}
          {looksOpen&&<LookPicker project={project} thumbs={thumbs} onPick={id=>pickLook(id)} expanded onClose={()=>setLooksOpen(false)}/>}
        </div>
        {surfaceTool&&<div className="surface-bar"><span className="sb-step">{surfaceTool.corners.length<4?<><b>{['top-left','top-right','bottom-right','bottom-left'][surfaceTool.corners.length]}</b> {surfaceTool.corners.length}/4</>:quadIsConvex(surfaceTool.corners)?'4/4':'corners cross'}</span><button onClick={()=>setSurfaceTool(t=>t&&({...t,corners:[]}))}>Reset</button><button onClick={()=>setSurfaceTool(null)} title="esc">Cancel</button><button className="primary" disabled={busy||surfaceTool.corners.length!==4||!quadIsConvex(surfaceTool.corners)||!current} title={current?lineText:'Pick a word first'} onClick={()=>void run(applySurface)}>Place</button></div>}
        <div className="transport">
          <span className="time-display mono" title={`frame ${frame} / ${totalFrames}`}>{timecode(time)}<span> / {timecode(project.duration)}</span></span>
          <div className="transport-controls">
            <button className="icon-button" aria-label="Back one frame" onClick={()=>seekFrame(frame-1)}><Icon name="prev" size={14}/></button>
            <button className="play-button" aria-label={playing?'Pause':'Play'} onClick={()=>setPlaying(p=>!p)} disabled={!ready}><Icon name={playing?'pause':'play'} size={16}/></button>
            <button className="icon-button" aria-label="Forward one frame" onClick={()=>seekFrame(frame+1)}><Icon name="next" size={14}/></button>
            <button className={`icon-button ${loopOn?'on':''}`} aria-label="Loop" title="Loop the selected line (L)" onClick={()=>{if(!loopOn&&!loop&&currentLine)setLoop({a:currentLine.start,b:currentLine.end});setLoopOn(v=>!v);}}><Icon name="loop" size={14}/></button>
          </div>
          <div className="transport-right"><button className="icon-button" aria-label={muted?'Unmute':'Mute'} onClick={()=>setMuted(m=>!m)}><Icon name={muted?'mute':'sound'}/></button></div>
        </div>
      </main>

      <aside className="s-right">
        <LookPicker project={project} thumbs={thumbs} onPick={id=>pickLook(id)} onExpand={()=>setLooksOpen(true)} edit={edit}/>
        <LineInspector project={project} line={currentLine} word={current} selected={selected} setSelected={id=>{setSelected(id);}} edit={edit} busy={busy}
          startSurface={startSurface} trackSurface={id=>void run(()=>trackSurface(project,id))} generate={()=>void run(()=>jobAction('inworld'))} prompt={prompt} setPrompt={setPrompt} wordOpen={wordOpen} setWordOpen={setWordOpen}/>
      </aside>
    </div>

    <Timeline project={project} frame={frame} playing={playing} selectedWord={selected} selectedLine={current?.lineId} waveform={waveform} beats={beats}
      loop={loop} loopOn={loopOn} snap={snap} zoom={zoom} setZoom={setZoom} setSnap={setSnap} setLoop={setLoop} setLoopOn={setLoopOn}
      onSelect={(id,seek)=>{setSelected(id);const w=project.words.find(x=>x.id===id);if(seek&&w)seekFrame((w.start+.04)*project.fps);}} onSeek={seekFrame} onEdit={edit} onToggleHidden={toggleHidden} onAddWord={addWord}
      videoSrc={project.media.video?assetUrl(project,project.media.video.path):undefined} crop={ready?renderer.current?.crop:undefined}/>

    <footer className={`statusbar ${error?'error':''} ${error||busy||notice?'show':''}`} role="status" onClick={()=>setError('')} title={error?'dismiss':undefined}>{(error||busy||notice)&&<span><i className={busy?'pulsing':''}/>{error||(busy?`${job?.message||'working'}`:notice)}</span>}</footer>
    {wfStep&&<WorkflowSheet step={wfStep} onClose={()=>setWfStep(null)}/>}
    <input ref={uploadInput} type="file" accept="video/*,audio/*" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void run(()=>upload(file));e.target.value='';}}/>
    {(project.media.audio||project.media.video)&&<audio ref={audio} preload="auto" src={assetUrl(project,(project.media.audio||project.media.video)!.path)}/>}
  </div>;
}
