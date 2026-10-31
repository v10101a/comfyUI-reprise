// Look picker: every look rendered live with the real renderer at the current frame (one offscreen StageRenderer,
// re-rendered per look when the playhead settles). Click or press 1–9 to switch; the stage restyles instantly.
import {useEffect,useRef,useState} from 'react';
import type {Project,LookId} from '../types';
import {StageRenderer} from '../renderer';
import {LOOKS,ALL_LOOKS,setLook} from '../looks';
import {LookParams} from './LookParams';

const THUMB_W=480;

/** Shared thumbnail cache, keyed by look id; one render pass per settled (frame, project) state. */
export function useLookThumbs(project:Project|null,frame:number,active:boolean,mediaKey:string){
  const [thumbs,setThumbs]=useState<Record<string,string>>({});
  const r=useRef<StageRenderer>();const loaded=useRef<Promise<void>>();const scratch=useRef<HTMLCanvasElement>();const small=useRef<HTMLCanvasElement>();
  const projectRef=useRef(project);projectRef.current=project;
  useEffect(()=>{const p=projectRef.current;if(!p)return;const x=new StageRenderer(p);r.current=x;loaded.current=x.load().catch(()=>{});setThumbs({});
    return()=>{x.dispose();if(r.current===x){r.current=undefined;loaded.current=undefined;}};},[mediaKey]);
  useEffect(()=>{if(!active||!project)return;let live=true;
    const timer=setTimeout(async()=>{const x=r.current;if(!x)return;await loaded.current;if(!live)return;
      const c=scratch.current||(scratch.current=document.createElement('canvas'));const s=small.current||(small.current=document.createElement('canvas'));
      s.width=THUMB_W;s.height=Math.round(THUMB_W*project.height/project.width);if(project.height>project.width){s.height=THUMB_W;s.width=Math.round(THUMB_W*project.width/project.height);}
      const out:Record<string,string>={};
      // Current look first so its card refreshes fastest.
      const order=[...(LOOKS.some(l=>l.id===(project.look?.id||'default'))?LOOKS:[...LOOKS,...ALL_LOOKS.filter(l=>l.id===project.look?.id)])].sort((a,b)=>Number(b.id===(project.look?.id||'default'))-Number(a.id===(project.look?.id||'default')));
      for(const l of order){if(!live)return;
        try{x.project=setLook(project,l.id==='default'?null:l.id as LookId);await x.render(c,frame);const g=s.getContext('2d')!;g.drawImage(c,0,0,s.width,s.height);out[l.id]=s.toDataURL('image/jpeg',.82);
          setThumbs(t=>({...t,[l.id]:out[l.id]}));}catch{/* keep previous thumb */}
      }
    },260);
    return()=>{live=false;clearTimeout(timer);};
  },[active,project,frame,mediaKey]);
  return thumbs;
}

export function LookPicker({project,thumbs,onPick,expanded,onExpand,onClose,edit}:{project:Project;thumbs:Record<string,string>;onPick:(id:LookId)=>void;expanded?:boolean;onExpand?:()=>void;onClose?:()=>void;edit?:(f:(p:Project)=>Project)=>void}){
  const current=project.look?.id||'default';const info=ALL_LOOKS.find(l=>l.id===current)||LOOKS[0];
  // A hidden legacy look (red-glow) stays listed while the project uses it.
  const list=LOOKS.some(l=>l.id===current)?LOOKS:[...LOOKS,info];
  const cards=list.map((l,i)=><button key={l.id} className={`look-card ${current===l.id?'active':''}`} onClick={()=>onPick(l.id)} aria-pressed={current===l.id} title={`${l.name} — ${l.description} (${i+1})`}>
    <span className="look-thumb" style={{aspectRatio:`${project.width}/${project.height}`,background:`linear-gradient(135deg,${l.swatch[0]} 0 50%,${l.swatch[1]||l.swatch[0]} 50% 100%)`}}>
      {thumbs[l.id]?<img src={thumbs[l.id]} alt=""/>:<span className="look-sample" style={{color:l.swatch[0],fontFamily:`"${l.fonts[0]?.replace(/ Black$/,'')}"`}}>Aa</span>}
    </span>
    <span className="look-meta"><span className="look-name">{l.name}</span><span className="look-swatch">{l.swatch.map(c=><i key={c} style={{background:c}}/>)}</span></span>
  </button>);
  if(expanded)return <div className="looks-sheet" role="dialog" aria-label="Looks">
    <div className="looks-sheet-head"><b>Looks</b><button onClick={onClose} aria-label="Close looks" title="esc">×</button></div>
    <div className="looks-grid big">{cards}</div>
  </div>;
  return <section className="panel-sec looks">
    <header className="sec-head"><span>Look</span><b title={info.description}>{info.name}</b><button className="sec-more" onClick={onExpand} title="all looks on this frame (G)">All</button></header>
    <div className="looks-grid">{cards}</div>
    {edit&&<LookParams project={project} edit={edit}/>}
  </section>;
}
