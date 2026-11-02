// Typeset Studio v3: stage-first editor. Layout: top bar · [Pipeline/Media | Stage | Look + Line] · Arrangement · status.
import {useState,useEffect,useLayoutEffect,useRef,useCallback,useMemo} from 'react';
import type {Project,Word,Job,LookId,Surface,Point,HeadSpot} from '../types';
import {request,getProject,assetUrl,pollJob} from '../api';
import {StageRenderer,loadFonts,surfaceCornersAt,surfaceBaseAt,type RenderOpts} from '../renderer';
import {reframeProject} from '../reframe';
import {prepareExport} from '../exportFrames';
import {cropAt,toOut,toSource,quadIsConvex} from '../geometry';
import {LOOKS,setLook,setLineMeta,lineSizeMode} from '../looks';
import {Timeline,lineInfos} from './Timeline';
import {copyText,pasteText,nudgeText,splitText,deleteText,addText,setWordText,type TextClipboard,type TextEdit} from './timelineEdits';
import {WallTool,WallBar,WallButtons} from './WallTool';
import {setSurfaceQuad,setSurfaceInPlane,bakeSurface,deleteSurface,wallFallback,keyAt,setSurfaceKey,deleteSurfaceKey,setSurfaceKeys} from './walls';
import type {WallKeyProps} from './WallTool';
import {groupOf,type GroupId} from './groups';
import {StageGuides,lineBoxes,type Guides,type Resize} from './StageOverlay';
import {LookPicker,useLookThumbs} from './LookPicker';
import {LineInspector} from './LineInspector';
import {generationPlan} from './generation';
import {GroupInspector} from './GroupInspector';
import {PipelinePanel,WorkflowSheet} from './PipelinePanel';
import {latestJobs,parseBeats,type Beats,type JobRecord,type StepDef,type StepId} from './pipeline';
import {ThemeToggle} from './ThemeToggle';
import {Icon} from './icons';
import {SongMap} from './SongMap';
import {LayersPanel,LayerInspector,LayerLanes,uploadAssets} from './LayersPanel';
import {mapLayer,editMedia,assetOf,splitMediaLayer} from '../layers';
import {headSourcePaths,headSourceAt} from '../heads';
import {setHudPointer} from '../hud';
import {placeTimelineAssets,type MediaDrop} from './duration';
import {WorkflowsPanel} from './WorkflowsPanel';
import {setSession} from './workflows';
import {auditionProject,useTake,mergeAssets,type Audition} from './takes';
import {ScenesPanel,SceneHeading} from './ScenesPanel';
import {SceneReferences} from './SceneReferences';
import {scenesOf,sceneClips,patchScene,setScenes,newScene,attachSceneClip,type Scene} from './scenes';
import type {BoardView} from './board';
import {TextStyle} from './TextStyle';
import {FootageGrade} from './FootageGrade';
import {visualLayer} from './takes';
import './scenes.css';
import {SidebarResize} from './SidebarResize';
import {matteLayer} from '../matte';
import {clipOf,shiftOf,songRef} from '../audioClip';
import PIECES from '../showcase-pieces.json';
import './studio.css';

/** Projects whose demo-page clip re-renders after a save (showcase-pieces.json pieces with `encode`). */
const SHOWCASE=new Set((PIECES.pieces as {project?:string;encode?:object}[]).filter(x=>x.project&&x.encode).map(x=>x.project!));
const DEMO_DEBOUNCE=5000;
/** Stage quality per render request. Draft while dragging the timeline, stage or inspector (preview proxies + light
 *  optics: ~43 ms a frame on the hero instead of ~160), proxies only during playback, full quality once settled. */
const DRAFT:RenderOpts={proxy:true,heavyOptics:false,cacheMedia:true};const PLAYBACK:RenderOpts={proxy:true};const SETTLED:RenderOpts={full:true,cacheMedia:true};
type Req={frame:number;opts?:RenderOpts};

const timecode=(time:number)=>`${Math.floor(time/60).toString().padStart(2,'0')}:${Math.floor(time%60).toString().padStart(2,'0')}.${Math.floor((time%1)*100).toString().padStart(2,'0')}`;
type Fmt='mp4'|'mov'|'webm';
const FORMATS:{id:Fmt;label:string;note:string}[]=[{id:'mp4',label:'mp4',note:'composite · H.264 + audio'},{id:'mov',label:'mov',note:'text layer · ProRes 4444 alpha'},{id:'webm',label:'webm',note:'text layer · VP9 alpha'}];


export default function Studio({initialProjectId='sample'}:{initialProjectId?:string}){
  const [project,setProject]=useState<Project|null>(null);const [projects,setProjects]=useState<Project[]>([]);const [selected,setSelected]=useState('');const [frame,setFrame]=useState(24);const [playing,setPlaying]=useState(false);const [muted,setMuted]=useState(false);const [busy,setBusy]=useState(false);const [job,setJob]=useState<Job|null>(null);const [notice,setNotice]=useState('');const [error,setError]=useState('');const [dirty,setDirty]=useState(false);const [ready,setReady]=useState(false);
  const [waveform,setWaveform]=useState<Float32Array|null>(null);const [songDur,setSongDur]=useState(0);const [linkWords,setLinkWords]=useState(true);const [leftTab,setLeftTab]=useState<'pipeline'|'media'|'scenes'|'board'>('scenes');const [selectedLayer,setSelectedLayer]=useState('');const layerSel=useRef('');layerSel.current=selectedLayer;const [exports,setExports]=useState<string[]>([]);
  const [audition,setAudition]=useState<Audition|null>(null);
  const [sourcePreviewId,setSourcePreviewId]=useState('');
  const sourcePreview=project?assetOf(project,sourcePreviewId):undefined;
  const sourceVideo=useRef<HTMLVideoElement>(null),sourceMode=useRef('');sourceMode.current=sourcePreviewId;
  const [activeScene,setActiveScene]=useState(''),[inspector,setInspector]=useState<'generate'|'clip'|'text'>('generate');
  const [textScope,setTextScope]=useState<'clip'|'default'>('default'),[paint,setPaint]=useState(0);
  const [sceneView,setSceneView]=useState<BoardView|null>(null);
  const scenes=useMemo(()=>project?scenesOf(project):[],[project]);
  const scene=scenes.find(s=>s.id===activeScene)||scenes.find(s=>s.clips.includes(selectedLayer))||scenes[0];
  const sceneRef=useRef(scene);sceneRef.current=scene;
  useEffect(()=>{setActiveScene('');setSceneView(null);setInspector('generate');},[project?.id]);
  const [matteTarget,setMatteTarget]=useState('');
  useEffect(()=>{if(selectedLayer)setMatteTarget(selectedLayer);},[selectedLayer]);
  const previewProject=useMemo(()=>project?auditionProject(project,audition&&audition.layerId===selectedLayer?audition:null):null,[project,audition,selectedLayer]);
  const isAuditioning=!!project&&previewProject!==project;
  useEffect(()=>{setAudition(null);setSourcePreviewId('');},[project?.id]);
  const [jobs,setJobs]=useState<JobRecord[]>([]);const [beats,setBeats]=useState<Beats|undefined>();const [guides,setGuides]=useState<Guides>({occupancy:false,regions:true,anchor:true,walls:false});
  const [multi,setMulti]=useState<{ids:string[];title:string}|null>(null);const [zoom,setZoom]=useState(1);const [snap,setSnap]=useState(true);const [loop,setLoop]=useState<{a:number;b:number}|null>(null);const [loopOn,setLoopOn]=useState(false);
  useEffect(()=>{if(selected||multi){setInspector('text');setTextScope('clip');setSourcePreviewId('');setAudition(null);}},[selected,multi]);
  const [wordOpen,setWordOpen]=useState(false);const [looksOpen,setLooksOpen]=useState(false);const [outputOpen,setOutputOpen]=useState(false);const [wfStep,setWfStep]=useState<StepDef|null>(null);const [formats,setFormats]=useState<Fmt[]>(['mp4']);const [exportScale,setExportScale]=useState<1|2>(1);const [savedAt,setSavedAt]=useState<number|null>(null);
  const [saving,setSaving]=useState(false);const saveQueue=useRef<Promise<void>>(Promise.resolve());
  const [clipboard,setClipboard]=useState<TextClipboard|null>(null);
  // Surface tool: corners in OUTPUT-normalized coords while drawing; `id` set when re-drawing an existing surface.
  const [surfaceTool,setSurfaceTool]=useState<{corners:Point[];id?:string}|null>(null);
  // Selected wall (stage quad click / wall mode): ⌫ deletes it. selScope: what ⌫ removes when a line is selected.
  const [selectedWall,setSelectedWall]=useState('');const [selScope,setSelScope]=useState<'word'|'line'>('line');
  useEffect(()=>{if(selected||multi||selectedWall)setSelectedLayer('');},[selected,multi,selectedWall]);
  const [inlineEdit,setInlineEdit]=useState<{wordId:string;fresh:boolean}|null>(null);
  // Side-by-side: original vs. client-side 9:16 reframe (or, in a reframed project, its source).
  const [compare,setCompare]=useState(false);const compareCanvas=useRef<HTMLCanvasElement>(null);const compareRenderer=useRef<StageRenderer>();const [compareReady,setCompareReady]=useState(false);const comparing=useRef(false);const compareRequested=useRef<Req>({frame:0});
  const canvas=useRef<HTMLCanvasElement>(null);const renderer=useRef<StageRenderer>();const rendering=useRef(false);const requested=useRef<Req>({frame:0});const uploadInput=useRef<HTMLInputElement>(null);const audio=useRef<HTMLAudioElement>(null);const stageWrap=useRef<HTMLDivElement>(null);const projectRef=useRef(project);projectRef.current=project;
  const [stageBox,setStageBox]=useState({w:800,h:450});
  const current=project?.words.find(w=>w.id===selected);const time=project?frame/project.fps:0;
  const lines=useMemo(()=>project?lineInfos(project):[],[project]);const currentLine=lines.find(l=>l.id===current?.lineId);
  const totalFrames=project?Math.max(1,Math.round(project.duration*project.fps)):1;
  const timelineOrigin=useRef({id:'',offset:0});
  useEffect(()=>{if(!project)return;const offset=project.timing?.sceneOffset||0,prev=timelineOrigin.current;
    const shift=prev.id===project.id?offset-prev.offset:0;timelineOrigin.current={id:project.id,offset};
    setFrame(f=>Math.max(0,Math.min(f+Math.round(shift*project.fps),totalFrames-1)));
    setLoop(l=>l?(l.a+shift>=project.duration||l.b+shift<=0?null:{a:Math.max(0,l.a+shift),b:Math.min(l.b+shift,project.duration)}):l);
  },[project?.id,project?.duration,project?.timing?.sceneOffset,totalFrames]);
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
  useEffect(()=>{const down=(e:PointerEvent)=>{if((e.target as Element|null)?.closest?.('.tl,.stage-wrap,.s-right input[type="range"],.s-right .scrub-l'))setHeld(true);};const up=()=>setHeld(false);const ups=['pointerup','pointercancel','blur'];
    window.addEventListener('pointerdown',down,true);for(const n of ups)window.addEventListener(n,up,true);
    return()=>{window.removeEventListener('pointerdown',down,true);for(const n of ups)window.removeEventListener(n,up,true);};},[]);
  const undo=(redo:boolean)=>{setAudition(null);const h=hist.current;const cur=projectRef.current;const prev=(redo?h.future:h.past).pop();if(!prev||!cur)return;(redo?h.past:h.future).push(cur);h.last=0;setProject({...prev,analysis:{...prev.analysis,headTracks:{...prev.analysis.headTracks,...cur.analysis.headTracks}}});setDirty(true);};
  const undoRef=useRef(undo);undoRef.current=undo;
  const changeProject=useCallback((p:Project)=>{const first=p.layers?.find(l=>l.kind==='media');const start=first?.kind==='media'?Math.max(.8,first.start+.04):.8;hist.current={past:[],future:[],last:0};setSongStale(false);setMatteTarget(p.layers?.find(l=>l.kind==='media')?.id||'');setProject(p);setSelected('');setSelectedLayer(p.layers?.find(l=>l.kind==='media')?.id||'');setAudition(null);setFrame(Math.min(Math.round(start*p.fps),Math.max(0,Math.round(p.duration*p.fps)-1)));setPlaying(false);setDirty(false);setExports([]);setError('');setLoop(null);setLoopOn(false);setCompare(false);setSurfaceTool(null);setSelectedWall('');setInlineEdit(null);},[]);
  useEffect(()=>{if(project?.id&&project.id!=='sample')void setSession(project.id);},[project?.id]); // ComfyUI's "add to <project>" target
  useEffect(()=>{let live=true;const initial=initialProjectId==='sample'?request<Project>('/sample/project.json'):getProject(initialProjectId);initial.then(p=>{if(live){const saved=initialProjectId==='sample'?localStorage.getItem('typeset.sample'):null;if(saved){try{p=JSON.parse(saved);}catch{/* fresh sample */}}changeProject(p);}}).catch(e=>{if(live)setError(String(e));});request<Project[]>('/api/projects').then(p=>{if(live)setProjects(p);}).catch(()=>{});return()=>{live=false;};},[changeProject,initialProjectId]);
  const mediaSignature=JSON.stringify([project?.id,project?.media.video,project?.analysis,project?.shots,project?.timing?.sceneOffset]);
  useEffect(()=>{if(!projectRef.current)return;let live=true;const r=new StageRenderer(projectRef.current);r.draftMedia=true;setReady(false);renderer.current?.dispose();renderer.current=r;
    r.load().then(()=>{if(live)setReady(true);}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;r.dispose();};
  },[mediaSignature]);
  // One request object per (frame, project, quality): the loop runs until the request it just drew is still the latest, so
  // the same frame with different text is a new result (the last edit of a drag used to be dropped when it landed mid-render).
  useEffect(()=>{const r=renderer.current;if(r&&previewProject)r.project=previewProject;if(!ready||!r||!canvas.current)return;{const q:Req={frame};q.opts={...(held?DRAFT:playing?PLAYBACK:SETTLED),stale:()=>requested.current!==q};requested.current=q;}
    const draw=async()=>{if(rendering.current)return;rendering.current=true;try{do{const q=requested.current;await r.render(canvas.current!,q.frame,'composite',q.opts);if(q===requested.current){if(!held&&!playing)setPaint(v=>v+1);break;}}while(true);}catch(e){setError(String(e));}finally{rendering.current=false;}};void draw();
  },[frame,previewProject,ready,held,playing]);
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
  async function save(p=projectRef.current,quiet=false){
    if(!p)return;
    const pending=saveQueue.current.catch(()=>{}).then(async()=>{
      setSaving(true);
      try{
        if(p.id==='sample')localStorage.setItem('typeset.sample',JSON.stringify(p));
        else{
          const saved=await request<Project>(`/api/projects/${p.id}`,{method:'PUT',body:JSON.stringify(p)});
          // The server may have completed a matte since this editor loaded.
          const cur=projectRef.current;
          if(cur?.id===p.id&&JSON.stringify(cur.media.video)===JSON.stringify(saved.media.video)&&JSON.stringify(cur.analysis)!==JSON.stringify(saved.analysis)){
            setProject(q=>q?.id===p.id?{...q,analysis:saved.analysis}:q);
          }
          scheduleDemo(p.id);
        }
        if(projectRef.current===p)setDirty(false);
        setSavedAt(Date.now());if(!quiet)setNotice('Saved');
      }finally{setSaving(false);}
    });
    saveQueue.current=pending;await pending;
  }

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
  // Autosave may continue during snapshot exports; analysis jobs re-fetch their result before saves resume.
  useEffect(()=>{if(!dirty||busy&&job?.kind!=='export'||!project)return;const t=setTimeout(()=>{void save(projectRef.current,true).catch(e=>setError(String(e)));},1200);return()=>clearTimeout(t);},[project,dirty,busy,job?.kind]);// eslint-disable-line react-hooks/exhaustive-deps
  async function create(){const p=await request<Project>('/api/projects',{method:'POST',body:JSON.stringify({name:'Untitled study'})});setProjects(items=>[p,...items]);changeProject(p);setNotice('');setLeftTab('media');}
  async function openProject(id:string){if(dirty)await save();location.hash=`/studio?project=${id}`;}
  // Song swap: drop audio on the waveform → it replaces media.audio (footage and words stay); ↻ then re-runs words + beats.
  const [songStale,setSongStale]=useState(false);
  // Left panel: full, or a slim icon rail (remembered per browser).
  const [rail,setRailState]=useState(()=>{try{return localStorage.getItem('typeset.leftRail')==='1';}catch{return false;}});
  const setRail=(v:boolean)=>{setRailState(v);try{localStorage.setItem('typeset.leftRail',v?'1':'0');}catch{/* private mode */}};
  const openLeft=(tab:'pipeline'|'media'|'layers'|'workflows'|'scenes'|'board')=>{setLeftTab(tab==='layers'?'media':tab==='workflows'?'scenes':tab);setRail(false);if(tab==='workflows')setInspector('generate');};
  const selectVisual=(id:string)=>{setSelectedLayer(id);setSelected('');setMulti(null);setSelectedWall('');setAudition(null);setSourcePreviewId('');setInspector(id?'clip':'generate');
    const s=projectRef.current&&scenesOf(projectRef.current).find(s=>s.clips.includes(id));if(s)setActiveScene(s.id);
  };
  const closePreview=()=>{setSourcePreviewId('');setAudition(null);};
  const selectScene=(s:Scene)=>{const p=projectRef.current;if(!p)return;const clips=sceneClips(p,s),l=clips.find(l=>l.id===layerSel.current)||clips[0];selectVisual(l?.id||'');setActiveScene(s.id);setInspector('generate');if(l)seekFrame(l.start*p.fps);};
  const previewSceneTake=(s:Scene,id:string)=>{if(scene?.id!==s.id)selectScene(s);if(sourcePreviewId===id){closePreview();return;}previewSource(id);};
  const renameScene=(id:string,name:string)=>{checkpoint();edit(p=>patchScene(p,id,{name}));};
  const deleteScene=(id:string)=>{checkpoint();edit(p=>setScenes(p,scenesOf(p).filter(s=>s.id!==id)));closePreview();selectVisual('');setActiveScene('');};
  const attachAddedClip=(id:string,assetId:string)=>{const p=projectRef.current;if(!p)return;const s=sceneRef.current||newScene(p);edit(q=>attachSceneClip(sceneRef.current?q:setScenes(q,[...scenesOf(q),s]),s.id,id,assetId));setActiveScene(s.id);};
  const addScene=()=>{const p=projectRef.current;if(!p)return;const s=newScene(p);checkpoint();edit(q=>setScenes(q,[...scenesOf(q),s]));selectScene(s);setRail(false);if(leftTab!=='board')setLeftTab('scenes');};
  function previewSource(id:string){
    setSourcePreviewId(id);if(!id)return;
    setPlaying(false);audio.current?.pause();setAudition(null);setCompare(false);setLooksOpen(false);setSurfaceTool(null);
    // Clicking a finished take again restarts it, even when its source id has not changed.
    if(sourcePreviewId===id&&sourceVideo.current){sourceVideo.current.currentTime=0;void sourceVideo.current.play().catch(()=>{});}
  }
  async function dropTimelineMedia(drop:MediaDrop,at:number){
    const source=projectRef.current;if(!source)return;const targetScene=sceneRef.current;
    const assets=drop.assetId?[assetOf(source,drop.assetId)].filter((a):a is NonNullable<typeof a>=>!!a):
      await uploadAssets(source.id,drop.files||[]);
    const current=projectRef.current;if(!current||current.id!==source.id)return;
    const withAssets=mergeAssets(current,current.id,assets);
    // Uploaded files already belong to the server bin; undo should remove only their timeline placement.
    if(withAssets!==current){projectRef.current=withAssets;setProject(withAssets);}
    const placed=placeTimelineAssets(withAssets,assets,at);if(!placed.layerId)return;
    if(targetScene){const old=new Set((withAssets.layers||[]).map(l=>l.id));for(const l of placed.project.layers||[])if(l.kind==='media'&&!old.has(l.id))placed.project=attachSceneClip(placed.project,targetScene.id,l.id,l.assetId);if(!drop.generation&&targetScene.generation)drop={...drop,generation:targetScene.generation};}
    if(drop.generation)placed.project=editMedia(placed.project,placed.layerId,l=>({...l,generation:structuredClone(drop.generation)}));
    checkpoint();edit(()=>placed.project);selectVisual(placed.layerId);setPlaying(false);setFrame(Math.round(at*current.fps));
  }
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
    const body=kind==='words'?{language:'auto'}:kind==='inworld'?inworldBody():kind==='export'?{layer:'composite',formats,scale:exportScale,...await prepareExport(project,'composite',formats,setNotice,exportScale)}:{layerId:matteTarget||null};
    const start=await request<Job>(`/api/projects/${project.id}/${path}`,{method:'POST',body:JSON.stringify(body)});const done=await pollJob(start,trackJob);
    if(kind==='export'){const result=done.result as {files?:Record<string,string>};setExports(Object.values(result?.files||{}));setNotice('Exported');setOutputOpen(true);await refreshJobs();}
    else{await refetch(project);setNotice(`${kind==='inworld'?'Shot':kind==='words'?'Words':'Matte'} done`);}trackJob(done);
  }
  /** Saved per-line direction, with appearance and animation sent to their respective models. */
  function inworldBody(){
    if(!project||!current)throw new Error('Choose a line first.');
    const plan=generationPlan(project,current);if(plan.reason)throw new Error(plan.reason);return plan.body;
  }
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
  async function trackHeads(){
    const p=projectRef.current;if(!p||p.id==='sample')return;await save(p,true);
    const start=await request<Job>(`/api/projects/${p.id}/analyze/heads`,{method:'POST',body:'{}'});trackJob(start);
    const done=await pollJob(start,trackJob);trackJob(done);const updated=await getProject(p.id);
    // Keep edits and undo history made while tracking. The job only adds source-time analysis.
    setProject(q=>q?.id===p.id?{...q,analysis:{...q.analysis,headTracks:{...q.analysis.headTracks,...updated.analysis.headTracks}}}:q);
    setNotice('Head tracking ready');
  }
  const hasHud=lines.some(l=>l.role==='hud'||l.role==='anchor');
  const missingHeads=project?headSourcePaths(project).filter(path=>!project.analysis.headTracks?.[path]):[];
  const headRequestKey=JSON.stringify([project?.id,hasHud?missingHeads:[]]);const headAttempt=useRef('');
  useEffect(()=>{if(!project||project.id==='sample'||!ready||busy||!hasHud||!missingHeads.length||headAttempt.current===headRequestKey)return;
    headAttempt.current=headRequestKey;void run(trackHeads);
  },[headRequestKey,ready,busy]);// eslint-disable-line react-hooks/exhaustive-deps
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
    // A moved tracked wall: its current corners become the key quad, so the new track starts where it is now.
    {const s=p.surfaces?.find(x=>x.id===id);const tr=s?.track?renderer.current?.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;
      if(s&&(s.keys?.length||s.inPlane&&tr)){p=bakeSurface(p,id,surfaceCornersAt(s,tr,frame),frame);edit(()=>p);}}
    await save(p,true);
    const j=await optionalJob(`/api/projects/${p.id}/surfaces/${id}/track`,{});
    if(!j){setNotice('Wall placed');return;}
    const done=await pollJob(j,trackJob);trackJob(done);
    // The new track is written to the same path: drop the cached one so the stage loads it.
    const tracks=renderer.current?.surfaceTracks;if(tracks)for(const k of [...tracks.keys()])if(k.startsWith(`${id}:`))tracks.delete(k);
    const updated=await refetch(p);
    const s=updated.surfaces?.find(x=>x.id===id);setNotice(s?.status==='tracked'?'Wall tracked':`Wall ${s?.status||'saved'}`);
  }
  /** Delete a wall (undoable); its lines fall back to Behind (with a matte) or on top. */
  function deleteWall(id:string){const p=projectRef.current;if(!p)return;const r=deleteSurface(p,id);const h=hist.current;h.gesture=false;h.last=0;edit(()=>r.project);h.last=0;
    setSelectedWall('');setSurfaceTool(t=>t?.id===id?null:t);setNotice(r.lines?`Wall deleted · ${r.lines} line${r.lines>1?'s':''} → ${r.to==='behind'?'Behind':'Caption'}`:'Wall deleted');}
  // Stage drag of a wall's corner or body (one undo step). A tracked wall keeps following its track (corners stored in
  // the track's plane); an untracked one is re-placed at this frame.
  const wallEdit=(id:string,quad:Point[],phase:'start'|'move'|'end')=>{const p=projectRef.current;if(!p)return;
    if(phase==='start'){setPlaying(false);checkpoint();return;}if(phase==='end')return;
    const c=cropAt(renderer.current?.crop,frame);const corners=quad.map(([x,y])=>toSource(c,x/p.width,y/p.height) as Point);
    const s=p.surfaces?.find(x=>x.id===id);const tr=s?.track?renderer.current?.surfaceTracks.get(`${s.id}:${s.track}`)||undefined:undefined;
    if(s?.keys?.length){edit(q=>setSurfaceKey(q,id,frame,corners));return;}
    const tracked=s&&tr?surfaceCornersAt({...s,inPlane:null},tr,frame):undefined;
    edit(q=>tracked&&quadIsConvex(tracked)?setSurfaceInPlane(q,id,corners,tracked):setSurfaceQuad(q,id,corners,frame));};
  /** Wall keyframes: the first press turns the wall's motion into smooth keys; then add/remove the key on this frame. */
  const wallKeys=(id:string):WallKeyProps=>{const p=projectRef.current;const s=p?.surfaces?.find(x=>x.id===id);const keys=s?.keys||[];
    const trackOf=(x:typeof s)=>x?.track?renderer.current?.surfaceTracks.get(`${x.id}:${x.track}`)||undefined:undefined;
    const prev=[...keys].reverse().find(k=>k.f<frame),next=keys.find(k=>k.f>frame);
    return {keyed:keys.length>0,at:!!keyAt(s,frame),
      onKey:()=>{const q=projectRef.current;const w=q?.surfaces?.find(x=>x.id===id);if(!q||!w)return;checkpoint();const tr=trackOf(w);
        // First key: the smoothed path here (no jump, the wobble goes). Then add the wall as shown, or remove this key.
        if(!w.keys?.length){const c=surfaceBaseAt(w,tr,frame);if(c)edit(r=>setSurfaceKeys(r,id,[{f:frame,corners:c}]));setNotice('Wall keyframed · drag it on any frame to set a key');return;}
        if(keyAt(w,frame))edit(r=>deleteSurfaceKey(r,id,frame));else{const c=surfaceCornersAt(w,tr,frame);if(c)edit(r=>setSurfaceKey(r,id,frame,c));}},
      onPrev:prev?()=>{setPlaying(false);setFrame(prev.f);}:undefined,onNext:next?()=>{setPlaying(false);setFrame(next.f);}:undefined};};
  const wallJob=jobs.find(j=>j.kind==='surface'&&(j.status==='running'||j.status==='queued'));
  async function makeVertical(){
    if(!project)return;
    if(project.id==='sample'){setCompare(true);setNotice('');return;}
    await save(project,true);
    const j=await optionalJob(`/api/projects/${project.id}/reframe`,{aspect:'9:16'});
    if(!j){setCompare(true);setNotice('');return;}
    const done=await pollJob(j,trackJob);const id=(done.result as {projectId?:string})?.projectId;
    if(!id)throw new Error('Reframe finished without a project id');
    setNotice('9:16 copy created · original preserved');location.hash=`/studio?project=${id}`;
  }
  const pickLook=(id:LookId)=>{edit(p=>setLook(p,id==='default'?null:id));};
  const toggleHidden=(lineId:string)=>edit(p=>setLineMeta(p,lineId,{hidden:p.lineMeta?.[lineId]?.hidden?null:true}));
  const anchorDragStart=useRef<{id:string;time:number;trackId:string;point:HeadSpot|null;changed:boolean}|null>(null);
  const dragAnchor=(lineId:string,point:Point,phase:'start'|'move'|'end'|'cancel')=>{
    const p=projectRef.current;if(!p)return;
    if(phase==='start'){setPlaying(false);checkpoint();anchorDragStart.current={id:lineId,time:frame/p.fps,trackId:p.words.find(w=>w.lineId===lineId)?.anchor?.trackId||'person0',point:p.lineMeta?.[lineId]?.hud?.point??null,changed:false};return;}
    const d=anchorDragStart.current;if(!d||d.id!==lineId)return;
    if(phase==='end'||phase==='cancel'){anchorDragStart.current=null;if(phase==='cancel'&&d.changed)edit(q=>setHudPointer(q,[lineId],{point:d.point}));hist.current.gesture=false;hist.current.last=0;return;}
    const spot=renderer.current?.headSpot(d.time,point,d.trackId,p);if(!spot)return;
    d.changed=true;edit(q=>setHudPointer(q,[lineId],{point:spot}));
  };
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
    setSelectedLayer('');setSelectedWall('');setSelScope('line');
    if(next.length<=1){setMulti(null);if(next[0])selectLine(next[0]);else setSelected('');}else setMulti({ids:next,title:additive?'Selection':title});};
  const toggleLine=(lineId:string)=>{const base=multi?.ids||(current?[current.lineId]:[]);const next=base.includes(lineId)?base.filter(x=>x!==lineId):[...base,lineId];
    setSelectedLayer('');setSelectedWall('');setSelScope('line');
    if(next.length<=1){setMulti(null);if(next[0])selectLine(next[0]);else setSelected('');}else setMulti({ids:next,title:'Selection'});};
  const seekFrame=(f:number)=>{setPlaying(false);setFrame(Math.max(0,Math.min(Math.round((projectRef.current?.duration||0)*(projectRef.current?.fps||24))-1,Math.round(f))));};
  function addWord(){addTextAt(time,currentLine?groupOf(currentLine):'captions');}
  const selectedLines=multi?.ids.length?multi.ids:currentLine?[currentLine.id]:[];
  const splitVisual=project?.layers?.find(l=>l.id===selectedLayer&&l.kind==='media');
  const canSplit=splitVisual?.kind==='media'?time>=splitVisual.start+1/project!.fps-1e-6&&time<=splitVisual.start+splitVisual.out-splitVisual.in-1/project!.fps+1e-6:
    lines.some(l=>selectedLines.includes(l.id)&&l.start<time&&l.end>time&&l.role!=='inworld');
  const canPaste=!!clipboard&&clipboard.projectId===project?.id&&clipboard.end-clipboard.start<=(project?.duration||0);
  function applyTextEdit(result:TextEdit|null){if(!result)return;
    // Keyboard commands are discrete undo steps; they must not leave a pointer gesture open.
    const h=hist.current;h.gesture=false;h.last=0;edit(()=>result.project);h.last=0;
    setSelected(result.wordId);setMulti(result.lineIds.length>1?{ids:result.lineIds,title:'Selection'}:null);}
  function copySelection(){if(project){const clip=copyText(project,selectedLines);if(clip)setClipboard(clip);}}
  function pasteSelection(){if(project&&clipboard)applyTextEdit(pasteText(project,clipboard,time));}
  function splitSelection(){if(!project)return;
    if(selectedLayer){const result=splitMediaLayer(project,selectedLayer,time);if(!result)return;
      const h=hist.current;checkpoint();edit(()=>result.project);h.gesture=false;h.last=-Infinity;selectVisual(result.layerId);
    }else applyTextEdit(splitText(project,selectedLines,time));}
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
  function nudgeSelection(frames:number){const p=projectRef.current;if(!p)return;
    const t=multi?.ids.length?{lineIds:multi.ids,wordIds:[]}:selScope==='word'&&current?{lineIds:[],wordIds:[current.id]}:currentLine?{lineIds:[currentLine.id],wordIds:[]}:null;
    if(!t)return;const r=nudgeText(p,t.lineIds,t.wordIds,frames);if(r)edit(()=>r.project);}
  const textCommands=useRef({copySelection,pasteSelection,splitSelection,deleteSelection,deleteWall,applySurface,nudgeSelection});textCommands.current={copySelection,pasteSelection,splitSelection,deleteSelection,deleteWall,applySurface,nudgeSelection};
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
    const down=(e:KeyboardEvent)=>{if(!DIR[e.code])return;const t=e.target as HTMLElement;if(t.closest('.scene-browser')||sourceMode.current)return;if(t.matches('input,textarea,select,.s-left-resize,.g-anchor-hit')||e.metaKey||e.ctrlKey||e.altKey)return;
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
    if(e.defaultPrevented||target.closest?.('input,textarea,select,[contenteditable=true],.reference-board'))return;
    if(sourceMode.current){
      if(e.code==='Escape'){e.preventDefault();setSourcePreviewId('');return;}
      // Source transport belongs to the full take, never the timeline clip underneath it.
      if(['Space','ArrowLeft','ArrowRight','Home','End','Backspace','Delete'].includes(e.code)&&!e.metaKey&&!e.ctrlKey&&!e.altKey){
        if(target.closest('video'))return;e.preventDefault();const v=sourceVideo.current;if(!v)return;
        if(e.code==='Space'){if(v.paused)void v.play().catch(()=>{});else v.pause();}
        else if(e.code==='Home')v.currentTime=0;
        else if(e.code==='End'&&Number.isFinite(v.duration))v.currentTime=Math.max(0,v.duration-.001);
        else if(e.code.startsWith('Arrow')&&Number.isFinite(v.duration))v.currentTime=Math.max(0,Math.min(v.duration-.001,v.currentTime+(e.code==='ArrowLeft'?-1:1)*(e.shiftKey?1:1/(keyState.current.project?.fps||24))));
        return;
      }
    }
    if((e.metaKey||e.ctrlKey)&&!e.altKey){
      const action=e.code==='KeyC'?textCommands.current.copySelection:e.code==='KeyV'?textCommands.current.pasteSelection:e.code==='KeyB'?textCommands.current.splitSelection:null;
      if(action&&!(e.code==='KeyC'&&window.getSelection()?.toString())){e.preventDefault();action();return;}}
    if((e.metaKey||e.ctrlKey)&&e.code==='KeyZ'&&!target.matches('input,textarea,select')){e.preventDefault();undoRef.current(e.shiftKey);return;}
    if((e.metaKey||e.ctrlKey)&&e.code==='KeyY'&&!target.matches('input,textarea,select')){e.preventDefault();undoRef.current(true);return;}
    // ⌥←/→ nudges the selected text 1 frame in time (⇧ 5 frames), like Premiere.
    if(e.altKey&&!e.metaKey&&!e.ctrlKey&&(e.code==='ArrowLeft'||e.code==='ArrowRight')&&!target.matches('input,textarea,select')){e.preventDefault();textCommands.current.nudgeSelection((e.code==='ArrowLeft'?-1:1)*(e.shiftKey?5:1));return;}
    if(target.matches('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey)return;const k=keyState.current;const p=k.project;if(!p)return;const last=Math.round(p.duration*p.fps)-1;
    if(e.code==='Space'){e.preventDefault();setPlaying(v=>!v);return;}
    if(e.code==='ArrowRight'){e.preventDefault();setFrame(f=>Math.min(f+(e.shiftKey?p.fps:1),last));return;}
    if(e.code==='ArrowLeft'){e.preventDefault();setFrame(f=>Math.max(0,f-(e.shiftKey?p.fps:1)));return;}
    if(e.code==='Home'){e.preventDefault();setFrame(k.loopOn&&k.loop?Math.round(k.loop.a*p.fps):0);return;}
    if(e.code==='End'){e.preventDefault();setFrame(last);return;}
    if(e.code==='Escape'){const k2=keyState.current;if(k2.surfaceTool||k2.looksOpen||k2.overlay){setSurfaceTool(null);setLooksOpen(false);setOutputOpen(false);setWfStep(null);setGuidesOpen(false);return;}if(k2.selectedWall){setSelectedWall('');return;}setAudition(null);setSelectedLayer('');setMulti(null);setSelected('');return;}
    // ⌫ / Delete: the wall being edited or selected, else the selected word(s) / line(s). Never from a text field (guard above).
    if((e.code==='Backspace'||e.code==='Delete')&&layerSel.current){e.preventDefault();const id=layerSel.current;checkpoint();edit(q=>mapLayer(q,id,l=>l.kind==='media'?null:l));setSelectedLayer('');return;}
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
  const thumbs=useLookThumbs(project,frame,!playing&&!!project&&ready&&((inspector==='text'&&(textScope==='default'||!current&&!multi))||looksOpen),mediaSignature);
  const jobMap=useMemo(()=>latestJobs(jobs,matteTarget),[jobs,matteTarget]);
  // What Behind and HUD can use, as the stage loaded it: the subject matte (none / did not load / does not match the
  // footage) and a person track. Shown on the lines that need them, with the matte step one click away.
  const subject=useMemo(()=>{const r=renderer.current;const p=projectRef.current;if(!ready||!r||!p)return undefined;
    const personLines=lines.filter(l=>{const a=Math.max(0,l.start),b=Math.min(p.duration,l.end);for(let t=a+Math.min(.05,(b-a)/2);t<b;t+=.25)if(r.head(t,l.words[0].anchor?.trackId||'person0',p).state==='tracked')return true;return false;}).map(l=>l.id);
    const person=currentLine?personLines.includes(currentLine.id):personLines.length>0;
    if(!p.analysis.matte)return {matte:'none' as const,person,personLines};const m=r.matte,b=r.bg;if(!m)return {matte:'missing' as const,person,personLines};
    const stale=p.analysis.matteSource?!matteLayer(p):!!b&&(Math.abs((m.duration||0)-(b.duration||0))>Math.max(.3,2/p.fps)||!!m.videoWidth&&!!b.videoWidth&&Math.abs(m.videoWidth/m.videoHeight-b.videoWidth/b.videoHeight)>.02);
    return {matte:stale?'stale' as const:'ok' as const,person,personLines};},[ready,mediaSignature,project,currentLine?.id]);// eslint-disable-line react-hooks/exhaustive-deps
  const headsRunning=jobMap.get('heads')?.status==='running'||jobMap.get('heads')?.status==='queued';
  const headTime=currentLine&&!(time>=currentLine.start&&time<currentLine.end)?currentLine.start+.05:time;
  const headHere=project&&ready?renderer.current?.head(headTime,'person0',project).state==='tracked':false;
  const showHeadControls=hasHud&&(!selectedLayer)&&(!currentLine||currentLine.role==='hud'||currentLine.role==='anchor'||multi?.ids.some(id=>lines.some(l=>l.id===id&&(l.role==='hud'||l.role==='anchor'))));
  const activeWall=project?.surfaces?.find(x=>x.id===(selectedWall||(currentLine?.role==='wall'?currentLine.words[0].surfaceId:'')));
  const occKind=useMemo(()=>{try{return ready?renderer.current?.occ().kind:undefined;}catch{return undefined;}},[ready,mediaSignature]);// eslint-disable-line react-hooks/exhaustive-deps
  const exportJobs=useMemo(()=>jobs.filter(j=>j.kind==='export').sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')).slice(0,6),[jobs]);
  const runningJob=jobs.find(j=>j.status==='running'||j.status==='queued');

  if(!project)return <div className="boot"><div className="brand-mark">T<span>↗</span></div><p>{error||'loading…'}</p>{error&&<a href="#/showcase">← showcase</a>}</div>;
  const aspect=project.width/project.height;const compareAspect=project.frame?.source?16/9:9/16;
  const gap=compare?16:0;const fitH=Math.max(120,Math.min(stageBox.h-8,(stageBox.w-gap-8)/(aspect+(compare?compareAspect:0))));
  const mainSize={width:Math.round(fitH*aspect),height:Math.round(fitH)};const compSize={width:Math.round(fitH*compareAspect),height:Math.round(fitH)};
  const hhmm=(t:number)=>new Date(t).toTimeString().slice(0,5);
  const saveLabel=saving?'saving…':dirty?'unsaved':savedAt?`saved ${hhmm(savedAt)}`:'saved';

  return <div className="studio scene-workspace" onPointerDownCapture={e=>{if(sourcePreview&&(e.target as Element).closest('.tl'))setSourcePreviewId('');}}>
    <header className="s-top">
      <a className="s-brand" href="#/showcase" aria-label="Back to showcase" onClick={e=>{e.preventDefault();void run(async()=>{if(dirty)await save();location.hash='/showcase';});}}><span className="s-word">typeset</span></a>
      <div className="s-proj">
        <select className="project-switch" aria-label="Switch project" value={project.id} onChange={e=>{const v=e.target.value;void run(()=>v==='+new'?create():openProject(v));}}><option value="sample">sample</option>{projects.filter(p=>p.id!=='sample').map(p=><option key={p.id} value={p.id}>{p.name}</option>)}{!projects.some(p=>p.id===project.id)&&project.id!=='sample'&&<option value={project.id}>{project.name}</option>}<option value="+new">+ new</option></select>
        <input aria-label="Project name" title={`${project.width}×${project.height} · ${project.fps} fps · ${project.duration.toFixed(2)} s${project.frame?.source?` · ${project.frame.aspect} reframe`:''}`} value={project.name} onChange={e=>edit(p=>({...p,name:e.target.value}))}/>
        <button className={`s-save ${dirty?'dirty':''}`} onClick={()=>void save().catch(e=>setError(String(e)))} disabled={saving||busy&&job?.kind!=='export'} title={`${saveLabel} · click to save`} aria-label={saveLabel}><i/></button>
        {demo!=='idle'&&<span className={`s-demo ${demo}`} role="status" aria-label={demo==='failed'?'Demo clip failed':'Demo clip updating'} title={demo==='failed'?'demo clip failed':'demo clip updating'}/>}
      </div>
      <div className="s-actions">
        {project.frame?.source&&<button onClick={()=>void run(()=>openProject(project.frame!.source!.projectId))} disabled={busy} title="Return to the unchanged original project">← Back to original</button>}
        <button className={`comfy-pill ${runningJob?'busy':''}`} onClick={()=>openLeft('pipeline')} title={runningJob?`${runningJob.kind} · ${runningJob.message||''}`:'comfyui pipeline'}><i/>{runningJob?`${Math.round((runningJob.progress||0)*100)}%`:'ComfyUI'}</button>
        <button className={`primary ${outputOpen?'on':''}`} onClick={()=>setOutputOpen(o=>!o)} aria-expanded={outputOpen}>Render</button>
        <ThemeToggle/>
      </div>
      {outputOpen&&<div className="output-pop" role="dialog" aria-label="Output">
        <div className="op-sec"><div className="op-h">Frame</div>
          <div className="op-row"><span className="op-ar" style={{aspectRatio:`${project.width}/${project.height}`}}/><div><b title={`${project.width}×${project.height}`}>{project.frame?.aspect||(Math.abs(aspect/(16/9)-1)<.03?'16:9':Math.abs(aspect/(9/16)-1)<.03?'9:16':Math.abs(aspect-1)<.03?'1:1':`${project.width}:${project.height}`)}</b></div></div>
          <div className="op-btns">
            {!project.frame?.source&&<>
              <button onClick={()=>{setCompare(c=>!c);setOutputOpen(false);}} aria-pressed={compare}>Preview 9:16</button>
              <button onClick={()=>void run(makeVertical)} disabled={busy} title="Create a separate 9:16 project; your original stays available">Create 9:16 copy</button>
            </>}
          </div>
        </div>
        <div className="op-sec"><div className="op-h">Export</div>
          {FORMATS.map(f=><label key={f.id} className="op-fmt" title={f.note}><input type="checkbox" checked={formats.includes(f.id)} onChange={e=>setFormats(fs=>e.target.checked?[...fs,f.id]:fs.filter(x=>x!==f.id))}/><b>{f.label}</b></label>)}
          <div className="seg mini op-scale" role="radiogroup" aria-label="Export size" title={`2× = ${project.width*2}×${project.height*2}: type stays sharp, footage is upscaled`}>{([1,2] as const).map(s=>
            <button key={s} role="radio" aria-checked={exportScale===s} className={exportScale===s?'active':''} onClick={()=>setExportScale(s)}>{s}×</button>)}</div>
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
      {rail?<aside className="s-left s-rail" aria-label="Scenes and media">
        <button className="icon-sm rail-toggle" onClick={()=>setRail(false)} aria-label="Expand panel" title="Expand panel"><Icon name="rail" size={16}/></button>
        <button className="icon-sm" onClick={()=>openLeft('scenes')} aria-label="Scenes" title="Scenes"><Icon name="layers" size={16}/></button>
        <button className="icon-sm" onClick={()=>openLeft('media')} aria-label="Media" title="Media"><Icon name="media" size={16}/></button>
        <button className="icon-sm" onClick={()=>openLeft('pipeline')} aria-label="Pipeline" title="Pipeline"><Icon name="pipeline" size={16}/></button>
      </aside>:<aside className="s-left" id="studio-left-panel">
        {(leftTab==='scenes'||leftTab==='board')?<ScenesPanel project={project} scenes={scenes} active={scene?.id||''} selected={selectedLayer} preview={sourcePreviewId||audition?.assetId||''} mode={leftTab}
          view={sceneView} onView={setSceneView} onMode={setLeftTab} onNew={addScene} onSelect={selectScene} onBlank={closePreview} onPreview={previewSceneTake}
          onClip={id=>{selectVisual(id);const l=visualLayer(project,id);if(l)seekFrame(l.start*project.fps);}} onUndo={()=>undo(false)} onRename={renameScene} onDelete={deleteScene}
          onMove={(id,x,y)=>{checkpoint();edit(p=>patchScene(p,id,{x,y}));}}/>
        :<><div className="study-nav"><button className="icon-sm" aria-label="Back to scenes" onClick={()=>setLeftTab('scenes')}>←</button><span>{leftTab==='media'?'Media':'Pipeline'}</span></div><div className="scene-utility-content">
          {leftTab==='pipeline'?<PipelinePanel project={project} matteLayerId={matteTarget} onMatteLayer={setMatteTarget} jobs={jobMap} occKind={occKind} hasBeats={!!beats} beatsNote={beats?`${beats.bpm?Math.round(beats.bpm)+' BPM · ':''}${beats.beats.length} beats`:undefined} comparing={compare} busy={busy} onRun={runStep} onOpenWorkflow={setWfStep}/>:
          <><div className="media-panel">
            <button className="upload-zone" onClick={()=>uploadInput.current?.click()} disabled={busy}><Icon name="upload" size={22}/><strong>Add song / base video</strong></button>
            {waveform&&songDur>0&&<SongMap project={project} peaks={waveform} songDur={songDur} linkWords={linkWords} edit={edit} checkpoint={checkpoint}/>}
            <label className="fld"><span className="lbl">Lyrics</span><textarea rows={8} value={project.media.lyrics||''} title="Optional: align the words to these lyrics" onChange={e=>edit(p=>({...p,media:{...p.media,lyrics:e.target.value}}))}/></label>
          </div><FootageGrade project={project} edit={edit}/><LayersPanel onAdded={attachAddedClip} project={project} edit={edit} checkpoint={checkpoint} selected={selectedLayer} onSelect={selectVisual} run={a=>void run(a)}/></>}
        </div></>}
        <div className="scene-utilities"><button className={leftTab==='media'?'active':''} onClick={()=>openLeft('media')}><Icon name="media" size={14}/>Media</button><button className={leftTab==='pipeline'?'active':''} onClick={()=>openLeft('pipeline')}><Icon name="pipeline" size={14}/>Pipeline</button><button className="icon-sm" aria-label="Collapse panel" title="Collapse panel" onClick={()=>setRail(true)}><Icon name="rail" size={14}/></button></div>
      </aside>}

      <SidebarResize/>

      <main className="s-stage">
        <div className="stage-bar">
          <button className={`tool-btn scene-text-button ${inspector==='text'?'active':''}`} aria-pressed={inspector==='text'} onClick={()=>{closePreview();setInspector('text');setTextScope(current||multi?'clip':'default');}} title="Text style and animation">Text style</button>
          {sourcePreview&&<div className="take-preview-status source-preview-status" role="status">
            <span title={sourcePreview.name||'Generated footage'}>Source preview · {sourcePreview.name||'Generated footage'}</span>
            <button onClick={()=>setSourcePreviewId('')}>Return to edit</button>
            <button className="primary" onClick={()=>void run(()=>dropTimelineMedia({assetId:sourcePreview.id},time))}>Add to timeline</button>
            {selectedLayer&&<><button aria-label="Preview take in edit" onClick={()=>{setAudition({layerId:selectedLayer,assetId:sourcePreview.id});setSourcePreviewId('');const l=visualLayer(project,selectedLayer);if(l)seekFrame(l.start*project.fps);}}>In edit</button><button onClick={()=>{checkpoint();edit(p=>useTake(p,selectedLayer,sourcePreview.id));closePreview();}}>Replace clip</button></>}
          </div>}
          {isAuditioning&&audition&&<div className="take-preview-status" role="status"><span title="Preview only; the saved edit is unchanged">Candidate preview</span>
            <button onClick={()=>setAudition(null)}>Return to current</button>
            <button className="primary" onClick={()=>void run(()=>dropTimelineMedia({assetId:audition.assetId},time))}>Add to timeline</button>
            <button onClick={()=>{checkpoint();edit(p=>useTake(p,audition.layerId,audition.assetId));setAudition(null);}}>Replace selected clip</button></div>}
          <div className="tool-anchor">
            <button className={`tool-btn ${guidesOpen?'active':''}`} onClick={()=>setGuidesOpen(o=>!o)} aria-expanded={guidesOpen} aria-label="Guides" title="Guides on the stage"><Icon name="guides" size={15}/></button>
            {guidesOpen&&<div className="guides-pop" role="menu" aria-label="Guides" onMouseLeave={()=>setGuidesOpen(false)}>
              {([['regions','Line boxes','R'],['occupancy','Subject','O'],['anchor','Head anchor',''],['walls','Walls','']] as const).map(([k,label,key])=>
                <label key={k} className="check" role="menuitemcheckbox" aria-checked={!!guides[k]}><input type="checkbox" checked={!!guides[k]} onChange={()=>setGuides(g=>({...g,[k]:!g[k]}))}/>{label}{key&&<kbd>{key}</kbd>}</label>)}
            </div>}
          </div>
          {activeWall&&!surfaceTool&&<div className="wall-tools" role="group" aria-label={activeWall.label||'Wall'}><span className="wt-name" title={activeWall.label||activeWall.id}><Icon name="wall" size={14}/></span>
            <WallButtons surface={activeWall} running={!!wallJob} busy={busy} fallback={wallFallback(project)} onTrack={()=>void run(()=>trackSurface(project,activeWall.id))} onRedraw={()=>startSurface(activeWall.id)} onDelete={()=>deleteWall(activeWall.id)} keys={wallKeys(activeWall.id)}/></div>}
          <button className={`tool-btn ${compare?'active':''}`} onClick={()=>setCompare(c=>!c)} aria-pressed={compare} aria-label={project.frame?.source?'Compare with source':'Compare 9:16'} title={project.frame?.source?'Side by side with the source':'Side by side with a 9:16 reframe'}><Icon name="compare" size={15}/></button>
        </div>
        <div className={`stage-wrap ${compare?'comparing':''}`} ref={stageWrap}>
          <div className={`stage-border ${sourcePreview||isAuditioning?'study-preview-box':''}`} style={mainSize} onPointerDown={e=>{if(!surfaceTool&&(e.target as Element).tagName==="CANVAS"){setSelectedLayer('');setMulti(null);setSelected("");setSelectedWall("");}}}>
          {sourcePreview&&<div className="source-viewer" role="region" aria-label="Full take preview">
            {sourcePreview.kind==='video'?<video key={sourcePreview.id} ref={sourceVideo} src={assetUrl(project,sourcePreview.path)} controls autoPlay playsInline preload="auto" aria-label={`Source: ${sourcePreview.name||'take'}`}/>:
              <img src={assetUrl(project,sourcePreview.path)} alt={sourcePreview.name||'Generated image'}/>}
          </div>}
            <canvas id="stage" ref={canvas} aria-label="Video composition preview" style={mainSize}/>
            {ready&&!surfaceTool&&!sourcePreview&&!isAuditioning&&<StageGuides renderer={renderer.current} project={project} frame={frame} guides={guides} selectedLine={current?.lineId} onSelectLine={id=>{setInspector('text');setTextScope('clip');setMulti(null);setSelectedWall('');setSelScope('line');const w=project.words.find(x=>x.lineId===id);if(w&&current?.lineId!==id)setSelected(w.id);}} onDragLine={dragLine} onResizeLine={resizeLine} onDragAnchor={dragAnchor} box={mainSize}
              selectedWall={selectedWall||undefined} onSelectWall={setSelectedWall} onWallEdit={wallEdit}/>}
            {!ready&&<div className="stage-loading">loading…</div>}
            {surfaceTool&&<WallTool W={project.width} H={project.height} corners={surfaceTool.corners} setCorners={f=>setSurfaceTool(t=>t&&({...t,corners:f(t.corners)}))}/>}
            {compare&&<span className="stage-label">{project.frame?.source?`${project.frame.aspect}`:'original'}</span>}
          </div>
          {compare&&<div className="stage-border compare" style={compSize}><canvas ref={compareCanvas} aria-label="Reframe comparison preview" style={compSize}/>{!compareReady&&<div className="stage-loading">loading…</div>}<span className="stage-label">{project.frame?.source?'source':'9:16'}</span></div>}
          {looksOpen&&<LookPicker textStyle project={project} thumbs={thumbs} onPick={id=>pickLook(id)} expanded onClose={()=>setLooksOpen(false)} edit={edit}/>}
        </div>
        {surfaceTool&&<WallBar corners={surfaceTool.corners} editing={!!surfaceTool.id} busy={busy} onRedraw={()=>setSurfaceTool(t=>t&&({...t,corners:[]}))}
          onDelete={surfaceTool.id?()=>deleteWall(surfaceTool.id!):undefined} onCancel={()=>setSurfaceTool(null)} onPlace={()=>void run(applySurface)}/>}
        {sourcePreview?<div className="source-transport"><span>Full source · preview only</span><span>Add at edit playhead {timecode(time)} · Esc to return</span></div>:<div className="transport">
          <span className="time-display mono" title={`frame ${frame} / ${totalFrames}`}>{timecode(time)}<span> / {timecode(project.duration)}</span></span>
          <div className="transport-controls">
            <button className="icon-button" aria-label="Back one frame" onClick={()=>seekFrame(frame-1)}><Icon name="prev" size={14}/></button>
            <button className="play-button" aria-label={playing?'Pause':'Play'} onClick={()=>setPlaying(p=>!p)} disabled={!ready}><Icon name={playing?'pause':'play'} size={16}/></button>
            <button className="icon-button" aria-label="Forward one frame" onClick={()=>seekFrame(frame+1)}><Icon name="next" size={14}/></button>
            <button className={`icon-button ${loopOn?'on':''}`} aria-label="Loop" title="Loop the selected line, or drag on the ruler top (L)" onClick={()=>{if(!loopOn&&!loop)setLoop(currentLine?{a:currentLine.start,b:currentLine.end}:{a:0,b:project.duration});setLoopOn(v=>!v);}}><Icon name="loop" size={14}/></button>
          </div>
          <div className="transport-right"><button className="icon-button" aria-label={muted?'Unmute':'Mute'} onClick={()=>setMuted(m=>!m)}><Icon name={muted?'mute':'sound'}/></button></div>
        </div>}
      </main>

      <aside className="s-right">
        <div className="scene-inspector-tabs seg" aria-label="Inspector"><button className={inspector==='generate'?'active':''} onClick={()=>setInspector('generate')}>Generate</button><button disabled={!selectedLayer} className={inspector==='clip'?'active':''} onClick={()=>setInspector('clip')}>Clip</button><button className={inspector==='text'?'active':''} onClick={()=>{setInspector('text');if(!current&&!multi)setTextScope('default');}}>Text style</button></div>
        <div hidden={inspector!=='generate'}>
          {scene?<section className="panel-sec"><SceneHeading scene={scene} onRename={name=>renameScene(scene.id,name)} onDelete={()=>deleteScene(scene.id)}/>
            <SceneReferences project={project} scene={scene} edit={edit} onPreview={id=>previewSceneTake(scene,id)} onError={setError}/>
            {loop&&<div className="scene-target mono">Song range · {timecode(loop.a)}–{timecode(loop.b)}</div>}
          </section>:<section className="panel-sec"><button onClick={addScene}>+ Add a scene</button></section>}
        </div>
        <div hidden={inspector!=='generate'||!scene}><WorkflowsPanel key={project.id} scene={scene} project={project} edit={edit} checkpoint={checkpoint} time={time} range={loop&&loop.b>loop.a?loop:null}
          selected={scene?.clips.includes(selectedLayer)?selectedLayer:scene?sceneClips(project,scene)[0]?.id||'':''} onSelect={selectVisual} audition={audition} onAudition={setAudition} onSeek={t=>seekFrame(Math.round(t*project.fps))}
          sourcePreview={sourcePreviewId} onPreview={previewSource} onPlace={(assetId,at,generation)=>void run(()=>dropTimelineMedia({assetId,generation},at))} prepare={()=>save(projectRef.current,true)}/></div>
        {inspector==='clip'&&<>{selectedLayer&&<LayerInspector project={project} id={selectedLayer} time={time} edit={edit} checkpoint={checkpoint} onClose={()=>setInspector('generate')} onSeek={t=>seekFrame(Math.round(t*project.fps))} onCreate={()=>setInspector('generate')}/>}<FootageGrade project={project} edit={edit}/></>}
        {inspector==='text'&&<TextStyle project={project} scope={textScope} onScope={setTextScope} selected={!!current||!!multi} canvas={canvas.current} paint={paint} playing={playing}
          defaults={<LookPicker textStyle project={project} thumbs={thumbs} onPick={id=>pickLook(id)} onExpand={()=>setLooksOpen(true)} edit={edit}/>}>
        {showHeadControls&&<section className="panel-sec head-tracking" aria-label="Head tracking">
          <div className="sec-head"><span>Head tracking</span><button disabled={busy||headsRunning||project.id==='sample'||!headSourcePaths(project).length} onClick={()=>void run(trackHeads)}>{headsRunning?'Tracking…':'Track head'}</button></div>
          <p className="clip-hint">{headsRunning?'Finding the head in each timeline shot…':headHere?'Following the head in this shot.':!headSourceAt(project,headTime)?'No footage under this text.':missingHeads.length?'Track the people in your timeline footage.':'No face detected here. The label stays on screen.'}</p>
        </section>}
        {multi&&multi.ids.length>1?<GroupInspector project={project} lineIds={multi.ids} title={multi.title} edit={edit} checkpoint={checkpoint} onClear={()=>setMulti(null)}/>
        :current&&currentLine?<LineInspector project={project} line={currentLine} word={current} selected={selected} setSelected={id=>{setSelected(id);}} edit={edit} checkpoint={checkpoint} onBack={()=>{setSelected('');setMulti(null);}} busy={busy}
          startSurface={startSurface} trackSurface={id=>void run(()=>trackSurface(project,id))} generate={()=>void run(()=>jobAction('inworld'))} wordOpen={wordOpen} setWordOpen={setWordOpen}
          box={!playing&&ready?lineBoxes(renderer.current,project,frame).find(x=>x.lineId===currentLine.id&&x.placement!=='surface'):undefined}
          subject={subject} matteRunning={jobMap.get('matte')?.status==='running'||jobMap.get('matte')?.status==='queued'} runMatte={()=>runStep('matte')} deleteWall={deleteWall} wallKeys={wallKeys} wallRunning={!!wallJob}/>
        :null}
        </TextStyle>}
      </aside>
    </div>

    <Timeline project={project} frame={frame} playing={playing} selectedWord={selected} selectedLine={current?.lineId} waveform={waveform} beats={beats}
      loop={loop} loopOn={loopOn} snap={snap} zoom={zoom} setZoom={setZoom} setSnap={setSnap} setLoop={setLoop} setLoopOn={setLoopOn}
      multi={multi?.ids} onPickGroup={pickGroup} onToggleLine={toggleLine}
      onCopy={copySelection} onPaste={pasteSelection} onSplit={splitSelection} canCopy={selectedLines.length>0} canPaste={canPaste} canSplit={canSplit}
      onDropMedia={project.id==='sample'||busy?undefined:(drop,at)=>void run(()=>dropTimelineMedia(drop,at))}
      onCheckpoint={checkpoint} onDropAudio={f=>void run(()=>replaceSong(f))} onRealign={songStale?()=>void run(realign):undefined}
      lanes={m=><LayerLanes project={project} {...m} selected={selectedLayer} onSelect={selectVisual} linked={scene?.clips} candidate={(sourcePreview||isAuditioning)&&selectedLayer?{layerId:selectedLayer,name:sourcePreview?.name||(audition?assetOf(project,audition.assetId)?.name:'')||'Take'}:undefined} edit={edit} checkpoint={checkpoint}/>}
      onSelect={(id,seek,scope)=>{setInspector('text');setTextScope('clip');setSelectedLayer('');setMulti(null);setSelectedWall('');setSelScope(scope||'line');setSelected(id);const w=project.words.find(x=>x.id===id);if(seek&&w)seekFrame((w.start+.04)*project.fps);}} onSeek={seekFrame} onEdit={edit} onToggleHidden={toggleHidden} onAddWord={addWord}
      onAddAt={addTextAt} onDelete={t=>deleteSelection(t)} inlineEdit={inlineEdit} onEditText={id=>{setInspector('text');setTextScope('clip');setSelected(id);setSelScope('word');setInlineEdit({wordId:id,fresh:false});}} onCommitText={commitText} onCancelText={cancelText}
      onSetHidden={(ids,hide)=>edit(p=>ids.reduce((q,id)=>setLineMeta(q,id,{hidden:hide?true:null}),p))} subject={subject}
      videoSrc={project.media.video?assetUrl(project,project.media.video.path):undefined} crop={ready?renderer.current?.crop:undefined}
      clip={songRef(project)&&songDur?clipOf(project,songDur):null} songDur={songDur||undefined} linkWords={linkWords} setLinkWords={setLinkWords}/>

    <footer className={`statusbar ${error?'error':''} ${error||busy||notice?'show':''}`} role="status" onClick={()=>setError('')} title={error?'dismiss':undefined}>{(error||busy||notice)&&<span><i className={busy?'pulsing':''}/>{error||(busy?`${job?.message||'working'}`:notice)}</span>}</footer>
    {wfStep&&<WorkflowSheet step={wfStep} onClose={()=>setWfStep(null)}/>}
    <input ref={uploadInput} type="file" accept="video/*,audio/*" hidden onChange={e=>{const file=e.target.files?.[0];if(file)void run(()=>upload(file));e.target.value='';}}/>
    {(project.media.audio||project.media.video)&&<audio ref={audio} preload="auto" src={assetUrl(project,(project.media.audio||project.media.video)!.path)}/>}
  </div>;
}
