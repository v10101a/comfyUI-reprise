// Look picker: every look rendered live with the real renderer at the current frame (one offscreen StageRenderer,
// re-rendered per look when the playhead settles). Click or press 1–9 to switch; the stage restyles instantly.
import {useEffect,useRef,useState} from 'react';
import type {Project,LookId} from '../types';
import {StageRenderer} from '../renderer';
import {LOOKS,ALL_LOOKS,setLook} from '../looks';
import {LookParams} from './LookParams';
import {Crumb} from './Crumb';
import {Icon} from './icons';

const THUMB_W=480;

/** A gap or a word's first animation frame should not make every look card look empty. */
export function lookPreviewFrame(p:Project,frame:number){
  const t=frame/p.fps;const words=p.words.filter(w=>!w.hidden&&!p.lineMeta?.[w.lineId]?.hidden&&w.placement!=='inworld');
  if(!words.length)return frame;
  const visible=words.filter(w=>w.start<=t&&w.end>t);
  if(visible.some(w=>t-w.start>=.3))return frame;
  const nearest=(visible.length?visible:words).reduce((a,b)=>Math.abs((a.start+a.end)/2-t)<Math.abs((b.start+b.end)/2-t)?a:b);
  return Math.max(0,Math.min(Math.round(p.duration*p.fps)-1,Math.round(Math.min(nearest.end-1/p.fps,nearest.start+Math.max(.3,(nearest.end-nearest.start)/2))*p.fps)));
}

/** Shared thumbnail cache, keyed by look id; one render pass per settled (frame, project) state. */
export function useLookThumbs(project:Project|null,frame:number,active:boolean,mediaKey:string){
  frame=project?lookPreviewFrame(project,frame):frame;
  const [thumbs,setThumbs]=useState<Record<string,string>>({});
  const r=useRef<StageRenderer>();const loaded=useRef<Promise<void>>();const scratch=useRef<HTMLCanvasElement>();const small=useRef<HTMLCanvasElement>();
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
      const c=scratch.current||(scratch.current=document.createElement('canvas'));const s=small.current||(small.current=document.createElement('canvas'));
      s.width=THUMB_W;s.height=Math.round(THUMB_W*project.height/project.width);if(project.height>project.width){s.height=THUMB_W;s.width=Math.round(THUMB_W*project.width/project.height);}
      const out:Record<string,string>={};
      // Current look first so its card refreshes fastest.
      const order=[...(LOOKS.some(l=>l.id===(project.look?.id||'default'))?LOOKS:[...LOOKS,...ALL_LOOKS.filter(l=>l.id===project.look?.id)])].sort((a,b)=>Number(b.id===(project.look?.id||'default'))-Number(a.id===(project.look?.id||'default')));
      for(const l of order){if(!live)return;
        try{x.project=setLook(project,l.id==='default'?null:l.id as LookId);await x.render(c,frame,'composite',{proxy:true,heavyOptics:false});const g=s.getContext('2d')!;g.drawImage(c,0,0,s.width,s.height);out[l.id]=s.toDataURL('image/jpeg',.82);
          setThumbs(t=>({...t,[l.id]:out[l.id]}));}catch{/* keep previous thumb */}
        // One look per task: with the media already at this frame a render never yields on its own, and eleven in a row
        // were one 1-2 s long task that swallowed the next pointer event.
        await new Promise(res=>setTimeout(res,0));
      }
    },260);
    return()=>{live=false;clearTimeout(timer);};
  },[active,held,sig,mediaKey]);// eslint-disable-line react-hooks/exhaustive-deps
  return thumbs;
}

export function LookPicker({project,thumbs,onPick,expanded,onExpand,onClose,edit}:{project:Project;thumbs:Record<string,string>;onPick:(id:LookId)=>void;expanded?:boolean;onExpand?:()=>void;onClose?:()=>void;edit?:(f:(p:Project)=>Project)=>void}){
  const current=project.look?.id||'default';const info=ALL_LOOKS.find(l=>l.id===current)||LOOKS[0];
  // A hidden legacy look (red-glow) stays listed while the project uses it.
  const list=LOOKS.some(l=>l.id===current)?LOOKS:[...LOOKS,info];
  const cards=list.map((l,i)=><button key={l.id} className={`look-card ${current===l.id?'active':''}`} onClick={()=>onPick(l.id)} aria-pressed={current===l.id} title={`${l.name} — ${l.description} (${i+1})`}>
    <span className="look-thumb" style={{aspectRatio:`${project.width}/${project.height}`,background:`linear-gradient(135deg,${l.swatch[0]} 0 50%,${l.swatch[1]||l.swatch[0]} 50% 100%)`}}>
      {thumbs[l.id]?<img src={thumbs[l.id]} alt=""/>:<span className="look-sample" style={{color:l.swatch[0],fontFamily:`"${l.fonts[0]?.replace(/ Black$/,'')}"`}}>{project.words.find(w=>!w.hidden&&!project.lineMeta?.[w.lineId]?.hidden)?.text||'Type'}</span>}
    </span>
    <span className="look-meta"><span className="look-name">{l.name}</span><span className="look-swatch">{l.swatch.map(c=><i key={c} style={{background:c}}/>)}</span></span>
  </button>);
  if(expanded)return <div className="looks-sheet" role="dialog" aria-label="Looks">
    <div className="looks-sheet-head"><b>Looks</b><button onClick={onClose} aria-label="Close looks" title="esc">×</button></div>
    <div className="looks-grid big">{cards}</div>
  </div>;
  return <section className="panel-sec looks">
    <Crumb><button className="icon-sm" onClick={onExpand} aria-label="All looks" title="All looks on this frame (G)"><Icon name="expand" size={14}/></button></Crumb>
    <div className={`looks-grid ${project.height>project.width?'tall':''}`}>{cards}</div>
    {edit&&<LookParams project={project} edit={edit}/>}
  </section>;
}
