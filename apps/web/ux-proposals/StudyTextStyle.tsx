import {useEffect,useMemo,useRef,useState} from 'react';
import type {Project,LookId,Word} from '../src/types';
import {ALL_LOOKS,LOOKS,setLook,lookOf,FONT_FAMILIES} from '../src/looks';
import {LookParams} from '../src/studio/LookParams';
import {useLookThumbs} from '../src/studio/LookPicker';
import {Icon} from '../src/studio/icons';
import {StudyTextInspector} from './StudyTextInspector';

type Props={project:Project;word?:Word;frame:number;paint:number;playing:boolean;canvas:HTMLCanvasElement|null;
  scope:'clip'|'default';onScope:(scope:'clip'|'default')=>void;onSelect:(id:string)=>void;
  edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void;onDelete:()=>void};

/** One text-style home. Presets set the project default; clip controls retain their explicit overrides. */
export function StudyTextStyle(props:Props){
  const {project:p,word,frame,scope,onScope,edit,checkpoint}=props;
  const [expanded,setExpanded]=useState(false),[currentFrame,setCurrentFrame]=useState('');
  const modal=useRef<HTMLDivElement>(null),openGallery=useRef<HTMLButtonElement>(null);
  const current=p.look?.id||'default',info=ALL_LOOKS.find(l=>l.id===current)||LOOKS[0];
  const list=useMemo(()=>LOOKS.some(l=>l.id===current)?LOOKS:[...LOOKS,info],[current,info]);
  // Media changes invalidate the real-renderer thumbnails; selection/rename alone does not.
  const mediaKey=useMemo(()=>JSON.stringify([p.id,p.media.video,p.analysis,p.shots,p.assets?.map(a=>[a.id,a.path]),p.layers]),[p.id,p.media.video,p.analysis,p.shots,p.assets,p.layers]);
  const thumbs=useLookThumbs(p,frame,scope==='default'&&!props.playing,mediaKey);
  const scratch=useRef<HTMLCanvasElement>();
  useEffect(()=>{if(!props.canvas||!props.paint||props.playing)return;const c=scratch.current||(scratch.current=document.createElement('canvas'));
    c.width=400;c.height=Math.round(400*p.height/p.width);c.getContext('2d')!.drawImage(props.canvas,0,0,c.width,c.height);setCurrentFrame(c.toDataURL('image/jpeg',.85));
  },[props.paint,props.playing,p.width,p.height,props.canvas]);
  useEffect(()=>{if(!expanded)return;const key=(e:KeyboardEvent)=>{
      if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setExpanded(false);}
      else if(e.key==='Tab'){const nodes=modal.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];
        if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
    };
    window.addEventListener('keydown',key,true);return()=>{window.removeEventListener('keydown',key,true);openGallery.current?.focus({preventScroll:true});};
  },[expanded]);
  const pick=(id:LookId)=>{checkpoint();edit(q=>setLook(q,id==='default'?null:id));};
  const cards=list.map(l=><button key={l.id} className={`look-card ${current===l.id?'active':''}`} aria-label={`Use ${l.name} as project default`} aria-pressed={current===l.id} title={l.description} onClick={()=>pick(l.id)}>
    <span className="look-thumb" style={{aspectRatio:`${p.width}/${p.height}`}}>{thumbs[l.id]?<img src={thumbs[l.id]} alt={`${l.name} preview`}/>:<span className="study-style-loading" aria-label="Rendering preview">…</span>}</span>
    <span className="look-meta"><span className="look-name">{l.name}</span></span>
  </button>);
  return <div className="study-text-style" aria-label="Text style inspector">
    <section className="panel-sec study-style-head"><div className="sec-head"><span>Text style</span></div>
      <div className="seg" role="group" aria-label="Text style scope"><button className={scope==='clip'?'active':''} aria-pressed={scope==='clip'} disabled={!word} onClick={()=>onScope('clip')} title="Adjust only the selected text clip">Selected text</button><button className={scope==='default'?'active':''} aria-pressed={scope==='default'} onClick={()=>onScope('default')} title="Default text style for the project; clip overrides stay in place">Project default</button></div>
    </section>
    {scope==='clip'&&word?<>
      <section className="panel-sec study-current-style"><div className="study-current-thumb" style={{aspectRatio:`${p.width}/${p.height}`}}>{currentFrame&&<img src={currentFrame} alt="Selected text style preview"/>}</div><div className="study-current-meta"><span className="study-style-name">{info.name}</span><button onClick={()=>onScope('default')} title="Browse the project's default text presets">Browse defaults</button></div></section>
      <StudyTextInspector project={p} word={word} onSelect={props.onSelect} edit={edit} checkpoint={checkpoint} onDelete={props.onDelete}/>
    </>:<>
      <section className="panel-sec looks study-style-presets" aria-label="Default text style previews"><div className="sec-head"><span>Presets</span><button ref={openGallery} className="icon-button sec-more" aria-label="All text styles" title="See larger previews" onClick={()=>setExpanded(true)}><Icon name="expand" size={14}/></button></div><div className="looks-grid">{cards}</div></section>
      <section className="panel-sec study-style-settings"><LookParams project={p} showGrade={false} edit={f=>{checkpoint();edit(f);}}/>
        {!lookOf(p)&&<><label className="fld">Font<select aria-label="Default font" value={p.style.fontFamily} onChange={e=>{const fontFamily=e.target.value;checkpoint();edit(q=>({...q,style:{...q.style,fontFamily}}));}}>{FONT_FAMILIES.map(f=><option key={f}>{f}</option>)}</select></label><label className="study-default-color">Text<input type="color" aria-label="Default text colour" value={p.style.fill.slice(0,7)} onChange={e=>{const fill=e.target.value;checkpoint();edit(q=>({...q,style:{...q.style,fill}}));}}/></label></>}
      </section>
    </>}
    {expanded&&<div className="study-style-modal-backdrop" onPointerDown={e=>{if(e.target===e.currentTarget)setExpanded(false);}}><div ref={modal} className="looks-sheet study-style-modal" role="dialog" aria-label="Project default text styles" aria-modal="true"><div className="looks-sheet-head"><b>Project default text style</b><button autoFocus aria-label="Close style previews" onClick={()=>setExpanded(false)}>×</button></div><div className="looks-grid big">{cards}</div></div></div>}
  </div>;
}
