import {useEffect,useRef,useState,type ReactNode} from 'react';
import type {Project} from '../types';
import {ALL_LOOKS} from '../looks';

export function TextStyle({project,scope,onScope,selected,canvas,paint,playing,children,defaults}:{project:Project;scope:'clip'|'default';onScope:(s:'clip'|'default')=>void;selected:boolean;canvas:HTMLCanvasElement|null;paint:number;playing:boolean;children:ReactNode;defaults:ReactNode}){
  const [preview,setPreview]=useState(''),scratch=useRef<HTMLCanvasElement>();
  useEffect(()=>{if(!canvas||!paint||playing||scope!=='clip')return;const c=scratch.current||(scratch.current=document.createElement('canvas'));
    c.width=400;c.height=Math.round(400*project.height/project.width);c.getContext('2d')!.drawImage(canvas,0,0,c.width,c.height);setPreview(c.toDataURL('image/jpeg',.85));
  },[canvas,paint,playing,scope,project.width,project.height]);
  const clip=selected&&scope==='clip';
  return <div className="study-text-style" aria-label="Text style inspector">
    <section className="panel-sec study-style-head"><div className="sec-head"><span>Text style</span></div><div className="seg" aria-label="Text style scope">
      <button disabled={!selected} aria-pressed={clip} className={clip?'active':''} onClick={()=>onScope('clip')}>Selected text</button><button aria-pressed={!clip} className={!clip?'active':''} onClick={()=>onScope('default')}>Project default</button>
    </div></section>
    {clip?<><section className="panel-sec study-current-style"><div className="study-current-thumb" style={{aspectRatio:`${project.width}/${project.height}`}}>{preview&&<img src={preview} alt="Selected text style preview"/>}</div><div className="study-current-meta"><span className="study-style-name">{ALL_LOOKS.find(l=>l.id===(project.look?.id||'default'))?.name}</span><button onClick={()=>onScope('default')}>Browse defaults</button></div></section>{children}</>:defaults}
  </div>;
}
