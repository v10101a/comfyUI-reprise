import {useEffect,useRef} from 'react';
import type {Project} from '../types';
import {assetOf} from '../layers';
import {SceneThumb as AssetThumb} from './SceneThumb';
import {SceneCanvas} from './SceneCanvas';
import {SceneName} from './SceneName';
import {Icon} from './icons';
import {ASSET_MIME} from './duration';
import {sceneClips,type Scene} from './scenes';
import type {BoardView} from './board';

type Props={project:Project;scenes:Scene[];active:string;selected:string;preview:string;mode:'scenes'|'board';view:BoardView|null;
  onView:(v:BoardView)=>void;onMode:(m:'scenes'|'board')=>void;onNew:()=>void;onSelect:(s:Scene)=>void;
  onClip:(id:string)=>void;onPreview:(s:Scene,id:string)=>void;onBlank:()=>void;onUndo:()=>void;
  onMove:(id:string,x:number,y:number)=>void;onRename:(id:string,name:string)=>void;onDelete:(id:string)=>void};
const stamp=(t:number)=>`${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;
export function ScenesPanel(p:Props){
  const list=useRef<HTMLDivElement>(null);
  useEffect(()=>{list.current?.querySelector('.study-chapter.selected')?.scrollIntoView({block:'nearest'});},[p.active,p.mode]);
  const thumb=(id:string)=>{const a=assetOf(p.project,id);return a?<AssetThumb project={p.project} asset={a}/>:<Icon name="media"/>;};
  const takes=(s:Scene)=><><div className="study-takes">{(p.mode==='board'?s.takes.slice(0,6):s.takes).map((id,i)=>{
    const a=assetOf(p.project,id),used=sceneClips(p.project,s).some(l=>l.assetId===id),preview=p.preview===id;
    return <button key={id} className={`study-take ${preview?'previewed':''}`} aria-label={`Preview ${s.name} take ${i+1}`} aria-pressed={preview}
      draggable onDragStart={e=>{e.dataTransfer.setData(ASSET_MIME,id);e.dataTransfer.effectAllowed='copy';p.onSelect(s);p.onBlank();}}
      title={`${a?.name||'Take'}${used?' · Used on timeline':''} · Drag to timeline`} onClick={()=>p.onPreview(s,id)}>
      <span className="study-take-image">{thumb(id)}{used&&<span className="study-used" title="Used on timeline">✓</span>}{preview&&<span className="study-eye"><Icon name="eye" size={14}/></span>}</span>
      <span className="study-take-meta"><span className="mono">{String(i+1).padStart(2,'0')}</span><span>{a?.duration?`${a.duration.toFixed(1)}s`:'Image'}</span></span>
    </button>;
  })}</div>{p.mode==='board'&&s.takes.length>6&&<button className="scene-all-takes" onClick={()=>{p.onSelect(s);p.onMode('scenes');}}>All {s.takes.length} takes ↗</button>}</>;
  return <div className="scene-browser" onClick={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label,.study-canvas'))p.onBlank();}}>
    <div className="study-nav"><div className="seg" aria-label="Scene view">{(['scenes','board'] as const).map(m=><button key={m} className={p.mode===m?'active':''} aria-pressed={p.mode===m} onClick={()=>{p.onBlank();p.onMode(m);}}>{m==='scenes'?'Scenes':'Board'}</button>)}</div><button className="icon-sm" aria-label="New scene" title="New scene" onClick={p.onNew}><Icon name="plus" size={16}/></button></div>
    {p.mode==='scenes'?<div ref={list} className="study-chapters" tabIndex={0} aria-label="Scene list" onKeyDown={e=>{
      if((e.target as Element).closest('input,textarea,select,[contenteditable=true]'))return;
      if((e.metaKey||e.ctrlKey)&&e.key==='z'){e.preventDefault();e.stopPropagation();p.onUndo();}
      else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();e.stopPropagation();const id=(e.target as Element).closest<HTMLElement>('[data-list-scene-id]')?.dataset.listSceneId||p.active;e.currentTarget.focus({preventScroll:true});p.onDelete(id);}
    }}>{p.scenes.map((s,i)=><section key={s.id} data-list-scene-id={s.id} className={`study-chapter ${p.active===s.id?'selected':''}`}>
      <button className="study-scene" aria-label={`Select scene ${s.name}`} aria-expanded={p.active===s.id} onClick={()=>p.onSelect(s)}><span className="study-cover">{thumb(s.refs[0]||s.takes[0])}</span><span className="study-scene-name">{s.name}<small>{s.takes.length} {s.takes.length===1?'take':'takes'}</small></span><span className="study-index mono">{String(i+1).padStart(2,'0')}</span></button>
      {p.active===s.id&&<div className="study-chapter-body">{takes(s)}<div className="study-occurrences">{sceneClips(p.project,s).map(l=><button key={l.id} className={p.selected===l.id?'active':''} title={`Go to ${l.name}`} aria-label={`Go to clip ${l.name}`} onClick={()=>p.onClip(l.id)}><Icon name="media" size={12}/><span className="mono">{stamp(l.start)}</span></button>)}</div></div>}
    </section>)}{!p.scenes.length&&<button className="scene-empty" onClick={p.onNew}>+ Add a scene</button>}</div>:
    <SceneCanvas scenes={p.scenes} active={p.active} view={p.view} onView={p.onView} onSelect={p.onSelect} onMove={p.onMove} onBlank={p.onBlank} onUndo={p.onUndo} onRename={p.onRename} onDelete={p.onDelete} takes={takes}
      references={s=><div className="study-board-refs">{s.refs.slice(0,3).map(id=><button key={id} aria-label={`Preview reference ${assetOf(p.project,id)?.name||''}`} title={s.roles?.[id]||'Reference'} onClick={()=>p.onPreview(s,id)}>{thumb(id)}</button>)}{s.refs.length>3&&<span className="scene-ref-count" title={`${s.refs.length} references; select the scene to browse them in the inspector`}>+{s.refs.length-3}</span>}</div>}/>}
  </div>;
}

export function SceneHeading({scene,onRename,onDelete}:{scene:Scene;onRename:(name:string)=>void;onDelete:()=>void}){
  return <div className="sec-head scene-heading"><SceneName name={scene.name} label="Scene name" className="study-inspector-name" onRename={onRename}/><button className="icon-sm" aria-label="Delete scene" title="Delete scene grouping; keep footage and timeline clips" onClick={onDelete}><Icon name="trash" size={14}/></button></div>;
}
