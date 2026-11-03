import {useEffect,useRef,useState} from 'react';
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
  onClip:(id:string)=>void;onPreview:(s:Scene,id:string)=>void;onBlank:()=>void;onUndo:(redo?:boolean)=>void;
  onMove:(positions:{id:string;x:number;y:number}[])=>void;onRename:(id:string,name:string)=>void;onDelete:(ids:string[])=>void;
  onCombine:(target:string,ids:string[],name:string)=>void;onReorder:(id:string,target:string,after:boolean)=>void;
  onTakeMove:(id:string,target:string,point?:{x:number;y:number})=>void;onTakeDelete:(scene:string,id:string)=>void;onCollapse:(id:string)=>void};
export const TAKE_MIME='application/x-typeset-scene-take',SCENE_MIME='application/x-typeset-scene';
const stamp=(t:number)=>`${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;

export function ScenesPanel(p:Props){
  const list=useRef<HTMLDivElement>(null),[selection,setSelection]=useState<string[]>([p.active]);
  const [drop,setDrop]=useState<{id:string;kind:'take'|'combine'|'before'|'after'}|null>(null);
  const selected=selection.filter(id=>p.scenes.some(s=>s.id===id));
  useEffect(()=>{setSelection(ids=>ids.includes(p.active)?ids:p.active?[p.active]:[]);},[p.active]);
  useEffect(()=>{list.current?.querySelector('.study-chapter.selected')?.scrollIntoView({block:'nearest'});},[p.active,p.mode]);
  const select=(s:Scene,add=false)=>{setSelection(ids=>add?ids.includes(s.id)?ids.filter(id=>id!==s.id):[...ids,s.id]:[s.id]);if(!add)p.onSelect(s);else p.onBlank();};
  const combine=(target?:string)=>{const s=p.scenes.find(s=>s.id===(target||selected[0]));if(s&&selected.length>1){p.onCombine(s.id,selected,s.name);setSelection([s.id]);}};
  const remove=()=>{if(selected.length){p.onDelete(selected);setSelection([]);}};
  const dropProps=(s:Scene)=>({onDragOver:(e:React.DragEvent)=>{
    const take=e.dataTransfer.types.includes(TAKE_MIME),scene=e.dataTransfer.types.includes(SCENE_MIME);if(!take&&!scene)return;
    e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='move';const r=e.currentTarget.getBoundingClientRect();
    setDrop({id:s.id,kind:take?'take':p.mode==='board'?'combine':e.clientY<r.top+14?'before':e.clientY>r.bottom-14?'after':'combine'});
  },onDragLeave:(e:React.DragEvent)=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))setDrop(null);},onDrop:(e:React.DragEvent)=>{
    const take=e.dataTransfer.getData(TAKE_MIME),scene=e.dataTransfer.getData(SCENE_MIME);if(!take&&!scene)return;e.preventDefault();e.stopPropagation();
    if(take)p.onTakeMove(take,s.id);else if(scene!==s.id){if(drop?.kind==='before'||drop?.kind==='after')p.onReorder(scene,s.id,drop.kind==='after');else p.onCombine(s.id,[scene,s.id],s.name);}
    setDrop(null);setSelection([s.id]);
  }});
  const key=(e:React.KeyboardEvent)=>{
    if((e.target as Element).closest('input,textarea,select,[contenteditable=true]'))return;
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.stopPropagation();p.onUndo(e.shiftKey);}
    else if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='g'){e.preventDefault();e.stopPropagation();combine();}
    else if(e.key==='Backspace'||e.key==='Delete'){
      e.preventDefault();e.stopPropagation();const take=(e.target as Element).closest<HTMLElement>('[data-take-id]');
      if(take){p.onTakeDelete(take.dataset.takeScene!,take.dataset.takeId!);p.onBlank();}
      else remove();(e.currentTarget as HTMLElement).focus({preventScroll:true});
    }
  };
  const thumb=(id:string)=>{const a=assetOf(p.project,id);return a?<AssetThumb project={p.project} asset={a}/>:<Icon name="media"/>;};
  const takes=(s:Scene)=><><div className="study-takes">{(p.mode==='board'?s.takes.slice(0,6):s.takes).map((id,i)=>{
    const a=assetOf(p.project,id),used=sceneClips(p.project,s).some(l=>l.assetId===id),preview=p.preview===id;
    return <button key={id} data-take-id={id} data-take-scene={s.id} className={`study-take ${preview?'previewed':''}`} aria-label={`Preview ${s.name} take ${i+1}`} aria-pressed={preview}
      draggable onDragStart={e=>{e.stopPropagation();e.dataTransfer.setData(ASSET_MIME,id);e.dataTransfer.setData(TAKE_MIME,id);e.dataTransfer.effectAllowed='copyMove';setSelection([s.id]);p.onSelect(s);p.onBlank();}} onDragEnd={()=>setDrop(null)}
      title={`${a?.name||'Take'}${used?' · Used on timeline':''} · Drag to a scene or timeline`} onClick={()=>{setSelection([s.id]);p.onPreview(s,id);}}>
      <span className="study-take-image">{thumb(id)}{used&&<span className="study-used" title="Used on timeline">✓</span>}{preview&&<span className="study-eye"><Icon name="eye" size={14}/></span>}</span>
      <span className="study-take-meta"><span className="mono">{String(i+1).padStart(2,'0')}</span><span>{a?.duration?`${a.duration.toFixed(1)}s`:'Image'}</span></span>
    </button>;
  })}</div>{p.mode==='board'&&s.takes.length>6&&<button className="scene-all-takes" onClick={()=>{p.onSelect(s);p.onMode('scenes');}}>All {s.takes.length} takes ↗</button>}</>;
  return <div className="scene-browser" tabIndex={-1} onKeyDown={e=>{if(!e.defaultPrevented)key(e);}} onClick={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label,.study-canvas'))p.onBlank();}}>
    <div className="study-nav"><div className="seg" aria-label="Scene view">{(['scenes','board'] as const).map(m=><button key={m} className={p.mode===m?'active':''} aria-pressed={p.mode===m} onClick={()=>{p.onBlank();p.onMode(m);}}>{m==='scenes'?'Scenes':'Board'}</button>)}</div><button className="icon-sm" aria-label="New scene" title="New scene" onClick={p.onNew}><Icon name="plus" size={16}/></button></div>
    {selected.length>1&&<div className="scene-selection-actions"><span>{selected.length} scenes</span><button onClick={()=>combine()} title="Combine selected scenes (⌘/Ctrl G)">Combine</button><button className="icon-sm" aria-label="Delete selected scenes" title="Delete selected scene groups" onClick={remove}><Icon name="trash" size={14}/></button></div>}
    {p.mode==='scenes'?<div ref={list} className="study-chapters" tabIndex={0} aria-label="Scene list" onKeyDown={key}>
      {p.scenes.map((s,i)=><section key={s.id} data-list-scene-id={s.id} {...dropProps(s)} className={`study-chapter ${selected.includes(s.id)?'selected':''} ${drop?.id===s.id?`scene-drop-${drop.kind}`:''}`}>
        <button className="study-scene" draggable aria-label={`Select scene ${s.name}`} aria-expanded={p.active===s.id} onClick={e=>select(s,e.shiftKey||e.metaKey||e.ctrlKey)}
          onDragStart={e=>{e.dataTransfer.setData(SCENE_MIME,s.id);e.dataTransfer.effectAllowed='move';}} onDragEnd={()=>setDrop(null)}>
          <span className="study-cover">{thumb(s.refs[0]||s.takes[0])}</span><span className="study-scene-name">{s.name}<small>{s.takes.length} {s.takes.length===1?'take':'takes'}</small></span><span className="study-index mono">{String(i+1).padStart(2,'0')}</span>
        </button>
        {drop?.id===s.id&&drop.kind==='combine'&&<span className="scene-drop-label">Release to combine</span>}
        {p.active===s.id&&<div className="study-chapter-body">{takes(s)}<div className="study-occurrences">{sceneClips(p.project,s).map(l=><button key={l.id} className={p.selected===l.id?'active':''} title={`Go to ${l.name}`} aria-label={`Go to clip ${l.name}`} onClick={()=>p.onClip(l.id)}><Icon name="media" size={12}/><span className="mono">{stamp(l.start)}</span></button>)}</div></div>}
      </section>)}{!p.scenes.length&&<button className="scene-empty" onClick={p.onNew}>+ Add a scene</button>}
    </div>:<SceneCanvas scenes={p.scenes} active={p.active} selection={selected} onSelection={setSelection} view={p.view} onView={p.onView}
      onSelect={p.onSelect} onMove={p.onMove} onBlank={p.onBlank} onKeyDown={key} onRename={p.onRename} onCombine={p.onCombine}
      takes={takes} dropTarget={drop?.id||''} dropProps={dropProps} onCollapse={s=>p.onCollapse(s.id)} onTakeMove={p.onTakeMove}
      references={s=><div className="study-board-refs">{s.refs.slice(0,3).map(id=><button key={id} aria-label={`Preview reference ${assetOf(p.project,id)?.name||''}`} title={s.roles?.[id]||'Reference'} onClick={()=>p.onPreview(s,id)}>{thumb(id)}</button>)}{s.refs.length>3&&<span className="scene-ref-count" title={`${s.refs.length} references; select the scene to browse them in the inspector`}>+{s.refs.length-3}</span>}</div>}/>}
  </div>;
}

export function SceneHeading({scene,onRename,onDelete}:{scene:Scene;onRename:(name:string)=>void;onDelete:()=>void}){
  return <div className="sec-head scene-heading"><SceneName name={scene.name} label="Scene name" className="study-inspector-name" onRename={onRename}/><button className="icon-sm" aria-label="Delete scene" title="Delete scene grouping; keep footage and timeline clips" onClick={onDelete}><Icon name="trash" size={14}/></button></div>;
}
