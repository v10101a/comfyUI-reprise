// Look picker: every look rendered live with the real renderer at the current frame (one offscreen StageRenderer,
// re-rendered per look when the playhead settles). Click or press 1–9 to switch; the stage restyles instantly.
import {useEffect,useRef,useState} from 'react';
import type {Project,LookId,LookRef} from '../types';
import {request} from '../api';
import {StageRenderer} from '../renderer';
import {LOOKS,ALL_LOOKS,setLook,lookOf,FONT_FAMILIES} from '../looks';
import {LookParams} from './LookParams';
import {Crumb} from './Crumb';
import {Icon} from './icons';

const THUMB_W=480;

/** A saved look: a named recipe (look ref only, never song, placement or references), shared by every project
 *  (server data/looks/saved.json). */
export type SavedLook={id:string;name:string;ref:LookRef};
let savedCache:SavedLook[]|null=null;const savedSubs=new Set<(v:SavedLook[])=>void>();
const publish=(v:SavedLook[])=>{savedCache=v;savedSubs.forEach(f=>f(v));};
export function useSavedLooks(){
  const [saved,setSaved]=useState<SavedLook[]>(savedCache||[]);
  useEffect(()=>{savedSubs.add(setSaved);if(!savedCache)request<SavedLook[]>('/api/looks/saved').then(publish).catch(()=>publish([]));return()=>{savedSubs.delete(setSaved);};},[]);
  const write=(v:SavedLook[])=>{const prev=savedCache||[];publish(v);request('/api/looks/saved',{method:'PUT',body:JSON.stringify(v)}).catch(()=>publish(prev));};
  return {saved,write};
}
const sameRef=(a?:LookRef|null,b?:LookRef|null)=>JSON.stringify(a??null)===JSON.stringify(b??null);

/** Render at the thumbnail's size, rather than allocating and shading a full-resolution frame first.
 * Coordinates and font sizes are normalized; this copy never changes the saved project or stage renderer. */
export function lookPreviewProject(project:Project):Project{
  const scale=Math.min(1,THUMB_W/Math.max(project.width,project.height));
  return {...project,width:Math.max(1,Math.round(project.width*scale)),height:Math.max(1,Math.round(project.height*scale))};
}

/** A gap or a word's first animation frame should not make every look card look empty. */
export function lookPreviewFrame(p:Project,frame:number){
  const t=frame/p.fps;const words=p.words.filter(w=>!w.hidden&&!p.lineMeta?.[w.lineId]?.hidden&&w.placement!=='inworld');
  if(!words.length)return frame;
  // Presets animate whole text clips. A 60 ms first word used to clamp every thumbnail
  // to the entrance's nearly invisible first frame, even when its phrase lasted seconds.
  const lines=new Map<string,{start:number;end:number}>();
  for(const w of words){const l=lines.get(w.lineId);lines.set(w.lineId,{start:Math.min(l?.start??w.start,w.start),end:Math.max(l?.end??w.end,w.end)});}
  const clips=[...lines.values()],visible=clips.filter(l=>l.start<=t&&l.end>t);
  if(visible.some(l=>t-l.start>=.6&&l.end-t>.1))return frame;
  const nearest=(visible.length?visible:clips).reduce((a,b)=>Math.abs((a.start+a.end)/2-t)<Math.abs((b.start+b.end)/2-t)?a:b);
  return Math.max(0,Math.min(Math.round(p.duration*p.fps)-1,Math.round(Math.min(nearest.end-1/p.fps,nearest.start+Math.max(.3,(nearest.end-nearest.start)/2))*p.fps)));
}

/** Shared thumbnail cache, keyed by look id; one render pass per settled (frame, project) state. */
export function useLookThumbs(project:Project|null,frame:number,active:boolean,mediaKey:string){
  frame=project?lookPreviewFrame(project,frame):frame;
  const [thumbs,setThumbs]=useState<Record<string,string>>({});const {saved}=useSavedLooks();const savedSig=JSON.stringify(saved);
  const r=useRef<StageRenderer>();const loaded=useRef<Promise<void>>();const scratch=useRef<HTMLCanvasElement>();
  const projectRef=useRef(project);projectRef.current=project;
  // Never render thumbs while a pointer is down (a drag or scrub is live); the pass starts 260 ms after release.
  const [held,setHeld]=useState(false);
  useEffect(()=>{const down=()=>setHeld(true),up=()=>setHeld(false);const ups=['pointerup','pointercancel','blur'];
    window.addEventListener('pointerdown',down,true);for(const n of ups)window.addEventListener(n,up,true);
    return()=>{window.removeEventListener('pointerdown',down,true);for(const n of ups)window.removeEventListener(n,up,true);};},[]);
  // Thumbs are draft quality: preview proxies (seek ~17 ms, not ~100) and light optics; invisible at 480 px.
  useEffect(()=>{const p=projectRef.current;if(!p)return;const x=new StageRenderer(p);x.draftMedia=true;r.current=x;loaded.current=x.load().catch(()=>{});setThumbs({});
    return()=>{x.dispose();if(r.current===x){r.current=undefined;loaded.current=undefined;}};},[mediaKey]);
  // What this frame's thumbs depend on: everything except the timing of words more than a second from the playhead,
  // so slipping a far-away line does not re-render eleven looks. Memoized by hand on (project, frame) identity.
  const sigRef=useRef<{p:Project|null;f:number;s:string}>({p:null,f:-1,s:''});
  if(sigRef.current.p!==project||sigRef.current.f!==frame){
    let s='';if(project){const t=frame/project.fps;const x=project as unknown as Record<string,unknown>;
      s=JSON.stringify([frame,project.width,project.height,project.look,project.style,project.lineMeta,x.grade,x.timing,
        project.words.map(w=>w.end>=t-1&&w.start<=t+1?w:{...w,start:0,end:0})]);}
    sigRef.current={p:project,f:frame,s};}
  const sig=sigRef.current.s;
  useEffect(()=>{if(!active||held||!sig)return;let live=true;
    const timer=setTimeout(async()=>{const x=r.current;const project=projectRef.current;if(!x||!project)return;await loaded.current;if(!live)return;
      const c=scratch.current||(scratch.current=document.createElement('canvas'));const preview=lookPreviewProject(project);
      const out:Record<string,string>={};
      // Current look first so its card refreshes fastest.
      const order=[...(LOOKS.some(l=>l.id===(project.look?.id||'default'))?LOOKS:[...LOOKS,...ALL_LOOKS.filter(l=>l.id===project.look?.id)])].sort((a,b)=>Number(b.id===(project.look?.id||'default'))-Number(a.id===(project.look?.id||'default')));
      for(const l of order){if(!live)return;
        try{x.project=setLook(preview,l.id==='default'?null:l.id as LookId);await x.render(c,frame,'composite',{proxy:true,heavyOptics:false,cacheMedia:true,cacheLayouts:true,previewScale:preview.height/project.height,stale:()=>!live});if(!live)return;out[l.id]=c.toDataURL('image/jpeg',.82);
          setThumbs(t=>({...t,[l.id]:out[l.id]}));}catch{/* keep previous thumb */}
        // One look per task: with the media already at this frame a render never yields on its own, and eleven in a row
        // were one 1-2 s long task that swallowed the next pointer event.
        await new Promise(res=>setTimeout(res,0));
      }
      for(const s of saved){if(!live)return;
        try{x.project={...preview,look:structuredClone(s.ref)};await x.render(c,frame,'composite',{proxy:true,heavyOptics:false,cacheMedia:true,cacheLayouts:true,previewScale:preview.height/project.height,stale:()=>!live});if(!live)return;
          const url=c.toDataURL('image/jpeg',.82);setThumbs(t=>({...t,[`saved:${s.id}`]:url}));}catch{/* keep previous thumb */}
        await new Promise(res=>setTimeout(res,0));
      }
    },260);
    return()=>{live=false;clearTimeout(timer);};
  },[active,held,sig,mediaKey,savedSig]);// eslint-disable-line react-hooks/exhaustive-deps
  return thumbs;
}

export function LookPicker({project,thumbs,onPick,expanded,onExpand,onClose,edit,textStyle=false}:{project:Project;thumbs:Record<string,string>;onPick:(id:LookId)=>void;expanded?:boolean;onExpand?:()=>void;onClose?:()=>void;edit?:(f:(p:Project)=>Project)=>void;textStyle?:boolean}){
  const current=project.look?.id||'default';const info=ALL_LOOKS.find(l=>l.id===current)||LOOKS[0];
  // A hidden legacy look (red-glow) stays listed while the project uses it.
  const list=LOOKS.some(l=>l.id===current)?LOOKS:[...LOOKS,info];
  const {saved,write}=useSavedLooks();const [naming,setNaming]=useState<string|null>(null);
  const savedHit=saved.find(s=>sameRef(s.ref,project.look));
  const saveCurrent=(name:string)=>{const n=name.trim();setNaming(null);if(!n||!project.look)return;
    const id=n.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'look';const ref=structuredClone(project.look);
    write([...saved.filter(s=>s.name!==n),{id:saved.some(s=>s.id===id&&s.name!==n)?`${id}-${Date.now().toString(36)}`:id,name:n,ref}]);};
  const savedCards=saved.map(s=>{const info=ALL_LOOKS.find(l=>l.id===s.ref.id);const on=savedHit?.id===s.id;
    return <div key={`saved:${s.id}`} className={`look-card saved ${on?'active':''}`}>
      <button className="look-card-hit" onClick={()=>edit?.(p=>({...p,look:structuredClone(s.ref)}))} aria-pressed={on} title={`${s.name} · ${info?.name||s.ref.id}`}>
        <span className="look-thumb" style={{aspectRatio:`${project.width}/${project.height}`,background:info?`linear-gradient(135deg,${info.swatch[0]} 0 50%,${info.swatch[1]||info.swatch[0]} 50% 100%)`:undefined}}>
          {thumbs[`saved:${s.id}`]&&<img src={thumbs[`saved:${s.id}`]} alt=""/>}
        </span>
        <span className="look-meta"><span className="look-name">{s.name}</span></span>
      </button>
      <button className="look-del" onClick={()=>write(saved.filter(x=>x.id!==s.id))} aria-label={`Remove ${s.name}`} title="Remove">×</button>
    </div>;});
  const saveCard=project.look&&!savedHit&&edit?<div key="save" className="look-card save">
    {naming===null?<button className="look-card-hit" onClick={()=>setNaming(info.name)} title="Save this look"><span className="look-thumb add" style={{aspectRatio:`${project.width}/${project.height}`}}><Icon name="plus" size={16}/></span><span className="look-meta"><span className="look-name">Save</span></span></button>
      :<form onSubmit={e=>{e.preventDefault();saveCurrent(naming);}}><span className="look-thumb add" style={{aspectRatio:`${project.width}/${project.height}`}}/>
        <input autoFocus aria-label="Look name" value={naming} onChange={e=>setNaming(e.target.value)} onBlur={()=>saveCurrent(naming)} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setNaming(null);}}}/></form>}
  </div>:null;
  const cards=list.map((l,i)=><button key={l.id} className={`look-card ${current===l.id?'active':''}`} onClick={()=>onPick(l.id)} aria-pressed={current===l.id} title={`${l.name} — ${l.description} (${i+1})`}>
    <span className="look-thumb" style={{aspectRatio:`${project.width}/${project.height}`,background:`linear-gradient(135deg,${l.swatch[0]} 0 50%,${l.swatch[1]||l.swatch[0]} 50% 100%)`}}>
      {thumbs[l.id]?<img src={thumbs[l.id]} alt=""/>:<span className="look-sample" style={{color:l.swatch[0],fontFamily:`"${l.fonts[0]?.replace(/ Black$/,'')}"`}}>{project.words.find(w=>!w.hidden&&!project.lineMeta?.[w.lineId]?.hidden)?.text||'Type'}</span>}
    </span>
    <span className="look-meta"><span className="look-name">{l.name}</span><span className="look-swatch">{l.swatch.map(c=><i key={c} style={{background:c}}/>)}</span></span>
  </button>);
  if(expanded)return <div className="looks-sheet" role="dialog" aria-label="Looks">
    <div className="looks-sheet-head"><b>{textStyle?'Project default text styles':'Looks'}</b><button onClick={onClose} aria-label="Close looks" title="esc">×</button></div>
    <div className="looks-grid big">{cards}{savedCards}{saveCard}</div>
  </div>;
  return <section className="panel-sec looks">
    {textStyle?<div className="sec-head"><span>Presets</span><button className="icon-sm" onClick={onExpand} aria-label="All text styles" title="Larger previews (G)"><Icon name="expand" size={14}/></button></div>:<Crumb><button className="icon-sm" onClick={onExpand} aria-label="All looks" title="All looks on this frame (G)"><Icon name="expand" size={14}/></button></Crumb>}
    {!textStyle&&edit&&<LookParams project={project} edit={edit}/>}
    <div className={`looks-grid ${project.height>project.width?'tall':''}`}>{cards}{savedCards}{saveCard}</div>
    {textStyle&&edit&&<LookParams project={project} edit={edit} showGrade={false}/>}
    {textStyle&&edit&&!lookOf(project)&&<div className="lp-group">
      <label className="lp-select"><span>Font</span><select aria-label="Default font" value={project.style.fontFamily} onChange={e=>{const fontFamily=e.target.value;edit(p=>({...p,style:{...p.style,fontFamily}}));}}>{FONT_FAMILIES.map(f=><option key={f}>{f}</option>)}</select></label>
      <label className="lp-select"><span>Text</span><input type="color" aria-label="Default text colour" value={project.style.fill.slice(0,7)} onChange={e=>{const fill=e.target.value;edit(p=>({...p,style:{...p.style,fill}}));}}/></label>
    </div>}
  </section>;
}
