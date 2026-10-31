import {useState,useEffect,useRef,lazy,Suspense} from 'react';
import type {Project,Layer,RendererAPI,Aspect,CropData,LookId,GradeId} from './types';
import {request,getProject,assetUrl} from './api';
import {StageRenderer,loadFonts} from './renderer';
import {reframeProject} from './reframe';
import {migrateProject,setGrade} from './looks';
import Showcase from './Showcase';
// Lazy: the #/render export route must never import studio code (a studio edit/syntax error must not break exports).
const Studio=lazy(()=>import('./studio/Studio'));

function RenderPage(){
  const canvas=useRef<HTMLCanvasElement>(null);const [error,setError]=useState('');
  useEffect(()=>{const query=new URLSearchParams(location.hash.split('?')[1]);const id=query.get('project')||'sample';const server=query.get('server')||'';const layer=(query.get('layer')||'text') as Layer;let renderer:StageRenderer|undefined;let alive=true;
    // Optional: src=<url of a project JSON> (fixtures), autoplace=0 (authored positions), reframe=9:16 (client-side reframe).
    const src=query.get('src');const aspect=query.get('reframe') as Aspect|null;
    const api:RendererAPI={frames:0,ready:Promise.resolve(),renderFrame:async(_frame:number)=>{throw new Error('Renderer is not ready');}};
    api.ready=(async()=>{let p:Project=src?await request<Project>(src):id==='sample'?await request<Project>('/sample/project.json'):await getProject(id,server);if(!alive)return;
      // look=<id> previews a look without saving it (verification / contact sheets).
      // grade=<id>[:amount] and overrides=<json> (look params) likewise; the grade is migrated before the look swap.
      p=migrateProject(p);const lookId=query.get('look');if(lookId)p={...p,look:lookId==='default'?null:{id:lookId as LookId}};
      const gradeQ=query.get('grade');if(gradeQ){const [gid,amt]=gradeQ.split(':');p=setGrade(p,gid as GradeId,amt?Number(amt):1);}
      const ovQ=query.get('overrides');if(ovQ&&p.look)p={...p,look:{...p.look,overrides:JSON.parse(ovQ)}};
      let crop:CropData|undefined;
      if(aspect){await loadFonts();const tracks=p.analysis.tracks?await fetch(assetUrl(p,p.analysis.tracks,server)).then(r=>r.json()):undefined;({project:p,crop}=reframeProject(p,aspect,tracks));}
      renderer=new StageRenderer(p,server);renderer.crop=crop;renderer.autoPlace=query.get('autoplace')!=='0';await renderer.load(layer);api.frames=Math.round(p.duration*p.fps);api.renderFrame=async frame=>{await renderer!.render(canvas.current!,frame,layer);};document.documentElement.classList.add('render-mode');document.body.classList.add('render-mode');await api.renderFrame(0);})();
    window.__typeset=api;void api.ready.catch(e=>setError(String(e)));
    return()=>{alive=false;renderer?.dispose();delete window.__typeset;document.documentElement.classList.remove('render-mode');document.body.classList.remove('render-mode');};
  },[]);
  return <>{error&&<pre className="render-error">{error}</pre>}<canvas id="stage" ref={canvas}/></>;
}

export default function App(){const [hash,setHash]=useState(location.hash);useEffect(()=>{const update=()=>setHash(location.hash);window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);if(hash.startsWith('#/render'))return <RenderPage key={hash}/>;if(hash.startsWith('#/studio')){const id=new URLSearchParams(hash.split('?')[1]).get('project')||'sample';return <Suspense fallback={<div className="boot"><p>Opening the studio…</p></div>}><Studio key={id} initialProjectId={id}/></Suspense>;}return <Showcase/>;}
