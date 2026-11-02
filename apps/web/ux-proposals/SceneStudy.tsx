// Isolated interaction study: in-memory edits, no project writes or generation requests.
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import type {Asset,MediaLayer,Project,Word} from '../src/types';
import {assetUrl} from '../src/api';
import {migrateProject,lineSizeMode,setLineMeta} from '../src/looks';
import {StageRenderer} from '../src/renderer';
import {assetOf,mediaLayer,insertLayer,splitMediaLayer} from '../src/layers';
import {clipOf} from '../src/audioClip';
import {Timeline} from '../src/studio/Timeline';
import {AssetThumb,LayerLanes,LayerInspector} from '../src/studio/LayersPanel';
import {SidebarResize} from '../src/studio/SidebarResize';
import {StageGuides,lineBoxes,type Resize} from '../src/studio/StageOverlay';
import {ThemeToggle} from '../src/studio/ThemeToggle';
import {Icon} from '../src/studio/icons';
import {useTake,auditionProject} from '../src/studio/takes';
import {SceneCanvas} from './SceneCanvas';
import {SceneName} from './SceneName';
import {StudyTextStyle} from './StudyTextStyle';
import {StudyFootageGrade} from './StudyFootageGrade';
import type {BoardView} from '../src/studio/board';
import {addText,deleteText,copyText,pasteText,splitText,setWordText,type TextClipboard,type TextEdit,type NewTextKind} from '../src/studio/timelineEdits';
import fixture from './scene-study-project.json';
import '../src/style.css';
import '../src/studio/studio.css';
import './scene-study.css';

export type Scene={id:string;name:string;clips:string[];takes:string[];refs:string[];prompt:string;x:number;y:number};
const start=migrateProject(fixture as unknown as Project);
const initialScenes:Scene[]=[
  {id:'booth',name:'Booth',clips:['playboi-shot-01','playboi-shot-03','l_scjh2c6mpx','l_bwbgpd5taf'],takes:['a_7b519b426a84','a_128d9704e1b7','a_8420ffb15702','a_b4149124f2','a_2ec379930b'],refs:['a_c1174f0375aa','a_d28975729eb7','a_73df7bd80ef9'],prompt:'Red velvet photo booth. Direct flash, natural skin, a little wind in the hair. Keep the same face and piercings.',x:24,y:24},
  {id:'pool',name:'Pool',clips:['playboi-shot-02','playboi-shot-07'],takes:['a_9ca346263bd2','a_6f7254154157'],refs:['a_fdb4e217575c'],prompt:'Poolside, soft breeze through platinum hair. Direct flash, grainy film. Lips stay closed.',x:310,y:24},
  {id:'car',name:'Car hood',clips:['playboi-shot-04','playboi-shot-08'],takes:['a_464baedc0b55','a_66646eb73c','a_d422ad0ed674'],refs:['a_345811bd07ed'],prompt:'On the car hood under a sodium streetlight. A small head turn, wind in the hair. Keep the camera still.',x:24,y:460},
  {id:'hall',name:'Hallway',clips:['playboi-shot-05'],takes:['a_8d607b0f6715'],refs:['a_5cfd2dd08de6'],prompt:'Still camera in the hallway. A small glance, loose shirt moving in the breeze.',x:310,y:460},
  {id:'mirror',name:'Mirror',clips:['playboi-shot-06'],takes:['a_599ecf18b78c'],refs:['a_bdd700f7fec0'],prompt:'Mirror shot, flash photograph. Subtle breathing and movement in the hair.',x:24,y:850},
].map(s=>({...s,takes:s.takes.filter(id=>assetOf(start,id)),refs:s.refs.filter(id=>assetOf(start,id))}));
const EMPTY_SCENE:Scene={id:'',name:'',clips:[],takes:[],refs:[],prompt:'',x:0,y:0};
const media=(p:Project)=>p.layers?.filter((l):l is MediaLayer=>l.kind==='media')||[];
const stamp=(t:number)=>`${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toFixed(2).padStart(5,'0')}`;
const noop=()=>{};

function Study(){
  const [project,setProject]=useState(start),[scenes,setScenes]=useState(initialScenes);
  const [active,setActive]=useState('booth'),[selected,setSelected]=useState('l_scjh2c6mpx');
  const [frame,setFrame]=useState(104),[playing,setPlaying]=useState(false),[muted,setMuted]=useState(true);
  const [candidate,setCandidate]=useState(''),[compare,setCompare]=useState(false),[sourceTime,setSourceTime]=useState(0),[sourcePlaying,setSourcePlaying]=useState(false);
  const [panel,setPanel]=useState<'scenes'|'board'>('scenes'),[inspector,setInspector]=useState<'generate'|'clip'|'text'>('generate');
  const [textScope,setTextScope]=useState<'clip'|'default'>('default');
  const [boardView,setBoardView]=useState<BoardView|null>(null),[undoCount,setUndoCount]=useState(0);
  const [clipboard,setClipboard]=useState<TextClipboard|null>(null),[inlineEdit,setInlineEdit]=useState<{wordId:string;fresh:boolean}|null>(null);
  const [zoom,setZoom]=useState(1),[snap,setSnap]=useState(true),[loop,setLoop]=useState<{a:number;b:number}|null>(null),[loopOn,setLoopOn]=useState(false);
  const [word,setWord]=useState(''),[waveform,setWaveform]=useState<Float32Array|null>(null);
  const [length,setLength]=useState(4),[target,setTarget]=useState<'free'|'range'>('free');
  const [error,setError]=useState(''),[ready,setReady]=useState(false),[paint,setPaint]=useState(0);
  const [box,setBox]=useState({width:640,height:366});
  const renderer=useRef<StageRenderer>(),canvas=useRef<HTMLCanvasElement>(null),stage=useRef<HTMLDivElement>(null);
  const source=useRef<HTMLVideoElement>(null),song=useRef<HTMLAudioElement>(null);
  const snapshot={project,scenes,active,selected,word,inspector,textScope};
  const history=useRef<(typeof snapshot)[]>([]),current=useRef(snapshot);current.current=snapshot;
  const request=useRef(0),rendering=useRef(false);
  const scene=scenes.find(s=>s.id===active)||EMPTY_SCENE,clips=media(project),clip=clips.find(l=>l.id===selected);
  const take=assetOf(project,candidate),time=frame/project.fps;
  const occurrences=clips.filter(l=>scene.clips.includes(l.id)).sort((a,b)=>a.start-b.start);
  const preview=useMemo(()=>compare&&candidate&&clip?auditionProject(project,{layerId:clip.id,assetId:candidate}):project,[project,compare,candidate,clip]);
  const latest=useRef({preview,frame});latest.current={preview,frame};
  const line=project.words.find(w=>w.id===word)?.lineId;
  // Reserve a real timeline row for the preview box without adding it to the authored edit.
  const timelineProject=useMemo(()=>candidate&&clip&&take?.kind==='video'?{...project,layers:[...(project.layers||[]),{...clip,id:'study-preview',assetId:candidate,name:`Preview · ${scene.takes.indexOf(candidate)+1}`}]}:project,[project,candidate,clip,take,scene.takes]);
  const edit=useCallback((f:(p:Project)=>Project)=>setProject(p=>f(p)),[]);
  const checkpoint=()=>{history.current.push(current.current);if(history.current.length>100)history.current.shift();setUndoCount(history.current.length);};
  const undo=()=>{const previous=history.current.pop();if(!previous)return;
    setProject(previous.project);setScenes(previous.scenes);setActive(previous.active);setSelected(previous.selected);setWord(previous.word);setInspector(previous.inspector);setTextScope(previous.textScope);
    setUndoCount(history.current.length);setCandidate('');setCompare(false);
  };
  const seek=(f:number)=>setFrame(Math.max(0,Math.min(Math.round(project.duration*project.fps)-1,Math.round(f))));
  const closePreview=()=>{setCandidate('');setCompare(false);setPlaying(false);};
  const pickClip=(id:string)=>{closePreview();setSelected(id);setWord('');setInspector('clip');const s=scenes.find(s=>s.clips.includes(id));setActive(s?.id||'');const l=clips.find(l=>l.id===id);if(l)seek((l.start+.08)*project.fps);};
  const pickScene=(s:Scene)=>{closePreview();setActive(s.id);setWord('');setInspector('generate');
    const uses=clips.filter(l=>s.clips.includes(l.id));const l=uses.find(l=>l.id===selected)||uses.find(l=>time>=l.start&&time<l.start+l.out-l.in)||uses[0];
    setSelected(l?.id||'');if(l)seek((l.start+.08)*project.fps);};
  const previewTake=(id:string)=>{if(id===candidate){closePreview();return;}setPlaying(false);setCompare(false);setSourceTime(0);setCandidate(id);};
  const add=()=>{if(!take||!scene.id)return;checkpoint();const l={...mediaLayer(take,project),start:time,name:`${scene.name} · ${scene.takes.indexOf(take.id)+1}`};
    edit(p=>({...insertLayer(p,l,'under-text'),duration:Math.max(p.duration,time+l.out-l.in)}));
    setScenes(ss=>ss.map(s=>s.id===active?{...s,clips:[...s.clips,l.id]}:s));setSelected(l.id);closePreview();};
  const replace=()=>{if(!take||!clip)return;checkpoint();edit(p=>useTake(p,clip.id,take.id));closePreview();};
  const newScene=()=>{checkpoint();const id=`scene-${Date.now()}`;setScenes(ss=>[...ss,{id,name:`Scene ${ss.length+1}`,clips:[],takes:[],refs:[],prompt:'',x:24,y:Math.max(-436,...ss.map(s=>s.y))+460}]);setActive(id);setSelected('');closePreview();setInspector('generate');};
  const patchScene=(update:Partial<Scene>)=>setScenes(ss=>ss.map(s=>s.id===active?{...s,...update}:s));
  const renameScene=(id:string,name:string)=>{const next=name.trim();const found=scenes.find(s=>s.id===id);if(!found||!next||next===found.name)return;
    checkpoint();setScenes(ss=>ss.map(s=>s.id===id?{...s,name:next}:s));
  };
  const deleteScene=(id:string)=>{const index=scenes.findIndex(s=>s.id===id);if(index<0)return;
    checkpoint();const remaining=scenes.filter(s=>s.id!==id);setScenes(remaining);closePreview();
    if(id===active){const next=remaining[Math.min(index,remaining.length-1)];setActive(next?.id||'');setSelected('');setWord('');setInspector('generate');}
  };

  const simulate=()=>{if(!scene.id)return;checkpoint();const examples=(scene.takes.length?scene.takes:initialScenes[0].takes).slice(0,2).map((id,i)=>({...assetOf(project,id)!,id:`study-${Date.now()}-${i}`,name:'Sample take'}));
    edit(p=>({...p,assets:[...(p.assets||[]),...examples]}));patchScene({takes:[...scene.takes,...examples.map(a=>a.id)]});};

  const pickText=(id:string,jump=false)=>{closePreview();setSelected('');setWord(id);setInspector('text');setTextScope('clip');const w=project.words.find(w=>w.id===id);if(jump&&w)seek((w.start+.04)*project.fps);};
  const showText=()=>{closePreview();setInspector('text');setTextScope(word?'clip':'default');};
  const applyText=(r:TextEdit|null,record=true)=>{if(!r)return;if(record)checkpoint();setProject(r.project);setWord(r.wordId);setSelected('');setInspector('text');setTextScope(r.wordId?'clip':'default');closePreview();};
  const addAt=(t:number,kind:NewTextKind)=>{const r=addText(project,t,kind);applyText(r);if(r)setInlineEdit({wordId:r.wordId,fresh:true});};
  const commitText=(id:string,text:string)=>{const fresh=inlineEdit?.fresh;setInlineEdit(null);applyText(setWordText(project,id,text),!fresh);};
  const split=()=>{if(clip){const r=splitMediaLayer(project,clip.id,time);if(!r)return;checkpoint();setProject(r.project);setScenes(ss=>ss.map(s=>s.clips.includes(clip.id)?{...s,clips:[...s.clips,r.layerId]}:s));setSelected(r.layerId);}else if(line)applyText(splitText(project,[line],time));};
  const toggleHidden=(id:string)=>{checkpoint();edit(p=>setLineMeta(p,id,{hidden:p.lineMeta?.[id]?.hidden?null:true}));};
  const dragStart=useRef<{x:number;y:number;dx:number;dy:number}|null>(null);
  const dragLine=(id:string,placement:Word['placement'],dx:number,dy:number,phase:'start'|'move'|'end')=>{
    const first=project.words.find(w=>w.lineId===id);if(!first)return;
    if(phase==='start'){checkpoint();setPlaying(false);const b=lineBoxes(renderer.current,project,frame).find(b=>b.lineId===id),al=first.style?.align||project.style.align;
      dragStart.current={x:b?(b.x+(al==='left'?0:al==='right'?b.w:b.w/2))/project.width:first.position?.x??.5,y:b?(b.y+b.h/2)/project.height:first.position?.y??.72,dx:first.anchor?.dx||0,dy:first.anchor?.dy||0};return;}
    const st=dragStart.current;if(!st)return;if(phase==='end')dragStart.current=null;if(Math.abs(dx)+Math.abs(dy)<.002)return;
    edit(p=>({...p,words:p.words.map(w=>w.lineId!==id?w:placement==='anchor'?{...w,anchor:{trackId:w.anchor?.trackId||'person0',dx:st.dx+dx,dy:st.dy+dy}}:{...w,autoPlace:false,position:{x:Math.max(0,Math.min(1,st.x+dx)),y:Math.max(0,Math.min(1,st.y+dy))}})}));
  };
  const resizeStart=useRef<{scale:number;sizes:Map<string,number>;x:number;y:number;dx:number;dy:number}|null>(null);
  const resizeLine=({lineId:id,placement,phase,k,fixed,box:b}:Resize)=>{
    if(phase==='start'){checkpoint();setPlaying(false);const first=project.words.find(w=>w.lineId===id),al=first?.style?.align||project.style.align;
      resizeStart.current={scale:project.lineMeta?.[id]?.scale??1,sizes:new Map(project.words.filter(w=>w.lineId===id).map(w=>[w.id,w.style?.fontSize??project.style.fontSize])),x:b.x+(al==='left'?0:al==='right'?b.w:b.w/2),y:b.y+b.h/2,dx:first?.anchor?.dx||0,dy:first?.anchor?.dy||0};return;}
    const st=resizeStart.current;if(!st)return;if(phase==='end')resizeStart.current=null;
    if(lineSizeMode(project,id)==='scale'){edit(p=>setLineMeta(p,id,{scale:Math.max(.2,Math.min(4,st.scale*k))}));return;}
    const x=(fixed[0]+(st.x-fixed[0])*k)/project.width,y=(fixed[1]+(st.y-fixed[1])*k)/project.height;
    edit(p=>({...p,words:p.words.map(w=>w.lineId!==id?w:{...w,style:{...w.style,fontSize:Math.max(.008,Math.min(.6,(st.sizes.get(w.id)||p.style.fontSize)*k))},...(placement==='anchor'?{anchor:{trackId:w.anchor?.trackId||'person0',dx:st.dx+x-st.x/p.width,dy:st.dy+y-st.y/p.height}}:{autoPlace:false,position:{x,y}})})}));
  };

  useEffect(()=>{const r=new StageRenderer(start);r.draftMedia=true;renderer.current=r;let live=true;
    r.load().then(()=>{if(live)setReady(true);}).catch(e=>{if(live)setError(String(e));});return()=>{live=false;r.dispose();};},[]);
  useEffect(()=>{const el=stage.current;if(!el)return;const resize=()=>{const scale=Math.max(.1,Math.min((el.clientWidth-32)/project.width,(el.clientHeight-24)/project.height));setBox({width:Math.floor(project.width*scale),height:Math.floor(project.height*scale)});};
    const ro=new ResizeObserver(resize);ro.observe(el);resize();return()=>ro.disconnect();},[project.width,project.height]);
  useEffect(()=>{request.current++;if(!ready||!canvas.current||!renderer.current)return;
    const draw=async()=>{if(rendering.current)return;rendering.current=true;try{let version:number;do{version=request.current;const {preview:p,frame:f}=latest.current;renderer.current!.project=p;
      await renderer.current!.render(canvas.current!,f,'composite',{heavyOptics:false,cacheMedia:true,cacheLayouts:true,previewScale:Math.min(1,box.width/p.width),stale:()=>request.current!==version});
    }while(version!==request.current);setPaint(v=>v+1);}catch(e){setError(String(e));}finally{rendering.current=false;}};void draw();
  },[ready,preview,frame,box.width]);
  useEffect(()=>{const path=start.media.audio?.path;if(!path)return;let live=true;const ctx=new AudioContext();
    fetch(assetUrl(start,path)).then(r=>r.arrayBuffer()).then(b=>ctx.decodeAudioData(b)).then(b=>{const data=b.getChannelData(0),bins=2400,out=new Float32Array(bins*2);for(let i=0;i<bins;i++){let lo=0,hi=0;for(let j=Math.floor(i*data.length/bins);j<Math.floor((i+1)*data.length/bins);j++){lo=Math.min(lo,data[j]);hi=Math.max(hi,data[j]);}out[i*2]=lo;out[i*2+1]=hi;}if(live)setWaveform(out);}).catch(noop).finally(()=>void ctx.close());return()=>{live=false;};},[]);
  useEffect(()=>{if(!playing)return;const from=performance.now(),first=frame;let raf=0;
    const tick=()=>{const f=first+(performance.now()-from)/1000*project.fps;if(f>=project.duration*project.fps){setPlaying(false);return;}setFrame(Math.round(f));raf=requestAnimationFrame(tick);};raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);
  },[playing]);
  useEffect(()=>{const a=song.current;if(!a)return;a.currentTime=Math.max(0,time-(project.media.audioClip?.offset||0)+(project.media.audioClip?.in||0));if(playing)void a.play().catch(noop);else a.pause();},[playing]);
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){closePreview();return;}if((e.target as HTMLElement).closest('input,textarea,select,button,.study-canvas'))return;
    if((e.metaKey||e.ctrlKey)&&e.key==='z'){e.preventDefault();undo();return;}
    if((e.key==='Delete'||e.key==='Backspace')&&line){e.preventDefault();applyText(deleteText(project,[line]));return;}
    if(e.code==='Space'){e.preventDefault();if(candidate&&!compare&&source.current){if(source.current.paused)void source.current.play().catch(noop);else source.current.pause();}else setPlaying(v=>!v);}
  };window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);});
  useEffect(()=>{document.querySelectorAll<HTMLElement>('.ly-clip[data-layer-id]').forEach(el=>el.classList.toggle('scene-linked',scene.clips.includes(el.dataset.layerId||'')));},[active,selected,project,scene.clips,candidate]);
  useEffect(()=>{if(panel==='scenes')document.querySelector('.study-chapter.selected>.study-scene')?.scrollIntoView({block:'nearest'});},[active,panel]);
  Object.assign(window,{sceneStudy:{active,selected,frame,candidate,compare,project,scenes,ready,paint,target,loop,inspector,word,boardView,textScope}});
  const thumb=(id:string)=>{const a=assetOf(project,id);return a?<AssetThumb project={project} asset={a}/>:<Icon name="media"/>;};
  const takes=(s:Scene)=><div className="study-takes">{s.takes.map((id,i)=>{const used=clips.filter(l=>s.clips.includes(l.id)&&l.assetId===id),previewed=candidate===id;
    return <button key={id} className={`study-take ${previewed?'previewed':''} ${clip?.assetId===id?'in-clip':''}`} aria-label={`Preview ${s.name} take ${i+1}`} aria-pressed={previewed} title={`${assetOf(project,id)?.name}${used.length?` · ${used.length} timeline clips`:''}`} onClick={()=>{if(active!==s.id)pickScene(s);previewTake(id);}}>
      <span className="study-take-image">{thumb(id)}{used.length>0&&<span className="study-used" title="Used on timeline">✓</span>}{previewed&&<span className="study-eye"><Icon name="eye" size={14}/></span>}</span>
      <span className="study-take-meta"><span className="mono">{String(i+1).padStart(2,'0')}</span><span className="mono">{assetOf(project,id)?.duration?.toFixed(1)}s</span></span></button>;})}</div>;
  return <div className="studio scene-study">
    <header className="s-top"><a className="s-brand" href="/#/showcase"><span className="s-word">typeset</span></a><div className="s-proj"><input aria-label="Project name" value={project.name} readOnly/></div><div className="s-actions"><span className="study-label" title="Interaction study. Edits stay in this tab. Sample generation reuses existing footage.">Design study</span><button onClick={undo} disabled={!undoCount} title="Undo study edit">Undo</button><a className="study-back" href={`/#/studio?project=${project.id}`}>Open project ↗</a><ThemeToggle/></div></header>
    <div className="s-main">
      <aside className="s-left" id="studio-left-panel" onClick={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label,.study-canvas'))closePreview();}}><div className="study-nav"><div className="seg" aria-label="Scene view">{(['scenes','board'] as const).map(id=><button key={id} className={panel===id?'active':''} aria-pressed={panel===id} onClick={()=>{closePreview();setPanel(id);}}>{id==='scenes'?'Scenes':'Board'}</button>)}</div><button className="icon-button" aria-label="New scene" title="New scene" onClick={newScene}>+</button></div>
        {panel==='scenes'?<div className="study-chapters" tabIndex={0} aria-label="Scene list" onKeyDown={e=>{
          if((e.target as Element).closest('input,textarea,select,[contenteditable=true]'))return;
          if((e.metaKey||e.ctrlKey)&&e.key==='z'){e.preventDefault();e.stopPropagation();undo();}
          else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();e.stopPropagation();const id=(e.target as HTMLElement).closest<HTMLElement>('[data-list-scene-id]')?.dataset.listSceneId||active;e.currentTarget.focus({preventScroll:true});deleteScene(id);}
        }}>{scenes.map((s,i)=><section key={s.id} data-list-scene-id={s.id} className={`study-chapter ${active===s.id?'selected':''}`}>
          <button className="study-scene" aria-label={`Select scene ${s.name}`} aria-expanded={active===s.id} onClick={()=>pickScene(s)}><span className="study-cover">{thumb(s.refs[0]||s.takes[0])}</span><span className="study-scene-name">{s.name}<small>{s.takes.length} {s.takes.length===1?'take':'takes'}</small></span><span className="study-index mono">{String(i+1).padStart(2,'0')}</span></button>
          {active===s.id&&<div className="study-chapter-body">{takes(s)}<div className="study-occurrences">{occurrences.map(l=><button key={l.id} className={l.id===selected?'active':''} title={`Go to ${l.name}`} aria-label={`Go to clip ${l.name}`} onClick={()=>pickClip(l.id)}><Icon name="media" size={12}/><span className="mono">{stamp(l.start)}</span></button>)}</div></div>}
        </section>)}</div>:<SceneCanvas scenes={scenes} active={active} view={boardView} onView={setBoardView} onSelect={pickScene} onBlank={closePreview} onUndo={undo} onRename={renameScene} onDelete={deleteScene}
          onMove={(id,x,y)=>{checkpoint();setScenes(ss=>ss.map(s=>s.id===id?{...s,x,y}:s));}} takes={takes}
          references={s=><div className="study-board-refs">{s.refs.map((id,i)=><button key={id} title={i===0?'Start frame':i===1?'Identity':'Hair'} aria-label={`Preview ${s.name} reference ${i+1}`} onClick={()=>{if(active!==s.id)pickScene(s);previewTake(id);}}>{thumb(id)}</button>)}</div>}/>}

      </aside><SidebarResize/>
      <main className="s-stage"><div className="stage-bar">
        {candidate?<><button onClick={closePreview} title="Return to the composition">← Edit</button><span className="study-preview-name">{take?.kind==='image'?'Reference':`Take ${scene.takes.indexOf(candidate)+1}`}</span><div className="study-preview-actions">
          {clip&&take?.kind==='video'&&<button aria-pressed={compare} className={compare?'active':''} title="Preview this take inside the selected clip" onClick={()=>{setCompare(v=>!v);setPlaying(false);seek((clip.start+.25)*project.fps);}}>{compare?'Full take':'In edit'}</button>}
          {take?.kind==='video'&&<><button onClick={add}>Add</button><button onClick={replace} disabled={!clip} title={clip?`Replace ${clip.name}`:'Select a timeline clip to replace'}>Replace</button></>}
        </div></>:<><span className="study-preview-name">Composition</span><div className="study-preview-actions"><button className={inspector==='text'?'active':''} onClick={showText} title="Text styles and typography"><Icon name="caption" size={14}/>Text style</button></div></>}
      </div>
        <div className="stage-wrap" ref={stage}><div className={`stage-border ${candidate?'study-preview-box':''}`} style={box}><canvas ref={canvas} aria-label="Video composition preview" style={{...box,visibility:candidate&&!compare?'hidden':'visible'}}/>
          {ready&&(!candidate||compare)&&<StageGuides renderer={renderer.current} project={preview} frame={frame} guides={{occupancy:false,regions:true,anchor:true}} selectedLine={line} onSelectLine={id=>pickText(project.words.find(w=>w.lineId===id)?.id||'')} onDragLine={dragLine} onResizeLine={resizeLine} box={box}/>}
          {candidate&&!compare&&(take?.kind==='video'?<video key={candidate} ref={source} className="study-source" src={assetUrl(project,take.path)} autoPlay playsInline controls muted={muted} onPlay={()=>setSourcePlaying(true)} onPause={()=>setSourcePlaying(false)} onEnded={()=>setSourcePlaying(false)} onTimeUpdate={e=>setSourceTime(e.currentTarget.currentTime)} aria-label="Full take preview"/>:<img className="study-source" src={take?assetUrl(project,take.path):''} alt="Scene reference"/>)}{!ready&&!candidate&&<div className="stage-loading">Loading…</div>}</div></div>
        <div className="transport"><span className="time-display mono">{stamp(candidate&&!compare?sourceTime:time)}<span> / {stamp(candidate&&!compare?take?.duration||0:project.duration)}</span></span><div className="transport-controls"><button className="icon-button" aria-label="Back one frame" onClick={()=>candidate&&!compare&&source.current?source.current.currentTime=Math.max(0,source.current.currentTime-1/project.fps):seek(frame-1)}><Icon name="prev" size={14}/></button><button className="play-button" aria-label="Play or pause" onClick={()=>{if(candidate&&!compare&&source.current){if(source.current.paused)void source.current.play().catch(noop);else source.current.pause();}else setPlaying(v=>!v);}}><Icon name={(candidate&&!compare?sourcePlaying:playing)?'pause':'play'}/></button><button className="icon-button" aria-label="Forward one frame" onClick={()=>candidate&&!compare&&source.current?source.current.currentTime+=1/project.fps:seek(frame+1)}><Icon name="next" size={14}/></button></div><div className="transport-right"><button className="icon-button" aria-label={muted?'Unmute':'Mute'} onClick={()=>setMuted(v=>!v)}><Icon name={muted?'mute':'sound'}/></button></div></div>
      </main>
      <aside className="s-right">
        {inspector==='text'?<StudyTextStyle project={project} word={project.words.find(w=>w.id===word)} frame={frame} paint={paint} playing={playing} canvas={canvas.current}
          scope={textScope} onScope={setTextScope} onSelect={id=>pickText(id)} edit={edit} checkpoint={checkpoint} onDelete={()=>applyText(deleteText(project,line?[line]:[]))}/>
        :inspector==='clip'&&clip?<><LayerInspector project={project} id={clip.id} time={time} edit={edit} checkpoint={checkpoint} onClose={()=>pickScene(scene)} onCreate={()=>pickScene(scene)} onSeek={t=>seek(t*project.fps)}/><StudyFootageGrade project={project} edit={f=>{checkpoint();edit(f);}}/></>
        :!scene.id?<section className="panel-sec study-empty-scenes"><button onClick={newScene}>New scene</button></section>
        :<><div className="panel-sec study-inspector-head"><div className="sec-head"><SceneName key={scene.id} name={scene.name} label="Scene name" className="study-inspector-name" onRename={name=>renameScene(scene.id,name)}/><button className="icon-button" aria-label="Delete scene" title="Remove scene from board · keeps timeline clips and media" onClick={()=>deleteScene(scene.id)}><Icon name="trash" size={14}/></button></div></div><section className="panel-sec"><div className="fld"><label>References</label><div className="study-refs">{scene.refs.map((id,i)=><button key={id} aria-label={`Preview reference ${i+1}`} title={assetOf(project,id)?.name} onClick={()=>previewTake(id)}>{thumb(id)}<span>{i===0?'Frame':i===1?'Face':'Hair'}</span></button>)}<label className="study-ref-add" title="Add a reference">+<input type="file" accept="image/*" aria-label="Add reference" onChange={e=>{const file=e.target.files?.[0];if(!file)return;const id=`ref-${Date.now()}`,a:Asset={id,kind:'image',path:URL.createObjectURL(file),name:file.name};edit(p=>({...p,assets:[...(p.assets||[]),a]}));patchScene({refs:[...scene.refs,id]});}}/></label></div></div>
          <div className="fld"><label htmlFor="study-workflow">Workflow</label><select id="study-workflow"><option>Scene take · face + hair</option><option>Singing take · Wan 2.2 S2V</option></select></div><div className="fld"><label htmlFor="study-prompt">Prompt</label><textarea id="study-prompt" rows={4} value={scene.prompt} onChange={e=>patchScene({prompt:e.target.value})}/></div>
          <div className="fld"><label>Timing</label><div className="seg"><button className={target==='free'?'active':''} onClick={()=>setTarget('free')}>Free</button><button className={target==='range'?'active':''} disabled={!loop} title="Drag a section on the timeline ruler" onClick={()=>setTarget('range')}>Selection</button></div>{target==='range'&&loop?<span className="mono study-range">{stamp(loop.a)} — {stamp(loop.b)}</span>:<div className="row2"><input type="number" aria-label="Generation duration" value={length} min={1} max={30} step={.5} onChange={e=>setLength(Number(e.target.value))}/><span>s</span></div>}</div><button className="primary wide" onClick={simulate} title="Prototype: adds two sample takes using existing footage; no model runs">Try sample takes</button></section></>}
      </aside>
    </div>
    <div className="study-timeline" onPointerDownCapture={()=>{if(candidate)closePreview();}}><Timeline project={timelineProject} frame={frame} playing={playing} selectedWord={word} selectedLine={line} waveform={waveform} loop={loop} loopOn={loopOn} snap={snap} zoom={zoom} setZoom={setZoom} setSnap={setSnap} setLoop={l=>{setLoop(l);if(l){setTarget('range');setInspector('generate');}}} setLoopOn={setLoopOn}
      onSelect={(id,jump)=>pickText(id,jump)} onSeek={seek} onEdit={edit} onToggleHidden={toggleHidden} onAddWord={()=>addAt(time,'captions')} onAddAt={addAt}
      onDelete={t=>applyText(deleteText(project,t.lineIds,t.wordIds))} inlineEdit={inlineEdit} onEditText={id=>{pickText(id);setInlineEdit({wordId:id,fresh:false});}} onCommitText={commitText} onCancelText={()=>{if(inlineEdit?.fresh)undo();setInlineEdit(null);}}
      onCopy={()=>setClipboard(copyText(project,line?[line]:[]))} onPaste={()=>clipboard&&applyText(pasteText(project,clipboard,time))} onSplit={split} canCopy={!!line} canPaste={!!clipboard} canSplit={clip?time>clip.start&&time<clip.start+clip.out-clip.in:!!line&&project.words.some(w=>w.lineId===line&&w.start<time)&&project.words.some(w=>w.lineId===line&&w.end>time)} onCheckpoint={checkpoint}
      lanes={m=><LayerLanes project={timelineProject} {...m} selected={selected} onSelect={id=>id==='study-preview'?closePreview():pickClip(id)} edit={edit} checkpoint={checkpoint}/>}

      clip={clipOf(project,project.media.audio?.duration||project.duration)} songDur={project.media.audio?.duration||project.duration}/></div>
    {project.media.audio&&<audio ref={song} src={assetUrl(project,project.media.audio.path)} muted={muted}/>}{error&&<div className="statusbar error show" role="alert" onClick={()=>setError('')}>{error}</div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<Study/>);
