import type {Project,RendererAPI} from './types';
import {request} from './api';
import {at} from './base';

/** Browser capture: when the host asks for it (Reprise inside ComfyUI has no Playwright), the studio renders the
 *  export frames itself, through the same #/render route Playwright would load, and uploads them as PNG.
 *  Returns extra ExportBody fields ({frames: session}) or {} when the server captures. */
export async function prepareExport(project:Project,layer:'text'|'composite',formats:string[],progress:(message:string)=>void,scale=1):Promise<{frames?:string}>{
  const health=await request<{capture?:string}>('/api/health').catch(()=>({capture:undefined}));
  if(health.capture!=='browser')return {};
  const layers=[...new Set([...(formats.includes('mp4')?[layer]:[]),...(formats.some(f=>f==='mov'||f==='webm')?['text' as const]:[])])];
  const {session}=await request<{session:string}>(`/api/projects/${encodeURIComponent(project.id)}/export/frames`,{method:'POST'});
  for(const l of layers)await renderLayer(project,l,session,(i,n)=>progress(`rendering ${l} ${i}/${n}`),scale);
  return {frames:session};
}

async function renderLayer(project:Project,layer:string,session:string,tick:(i:number,n:number)=>void,scale=1){
  const frame=document.createElement('iframe');
  // Off-screen, full size: the render page sizes its canvas from the project (× scale), not the viewport.
  Object.assign(frame.style,{position:'fixed',left:'-20000px',top:'0',width:`${project.width*scale}px`,height:`${project.height*scale}px`,border:'0'});
  frame.src=`${at('/')}#/render?project=${encodeURIComponent(project.id)}&layer=${layer}${scale!==1?`&scale=${scale}`:''}`;
  document.body.append(frame);
  try{
    const win=frame.contentWindow as (Window&{__typeset?:RendererAPI})|null;
    const api=await new Promise<RendererAPI>((resolve,reject)=>{const t0=Date.now();const poll=()=>{const a=win?.__typeset;if(a)resolve(a);else if(Date.now()-t0>30000)reject(new Error('Renderer did not load'));else setTimeout(poll,100);};poll();});
    await api.ready;
    const canvas=frame.contentDocument!.getElementById('stage') as HTMLCanvasElement;
    const pending=new Set<Promise<unknown>>();
    for(let i=0;i<api.frames;i++){
      await api.renderFrame(i);
      const png=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error(`Frame ${i} did not encode`)),'image/png'));
      const put=fetch(`/api/projects/${encodeURIComponent(project.id)}/export/frames/${session}/${layer}/${i}`,{method:'PUT',body:png})
        .then(r=>{if(!r.ok)throw new Error(`Frame ${i} upload failed (${r.status})`);});
      pending.add(put);void put.finally(()=>pending.delete(put)).catch(()=>{});
      if(pending.size>=6)await Promise.race(pending);
      if(i%8===0||i===api.frames-1)tick(i+1,api.frames);
    }
    await Promise.all(pending);
  }finally{frame.remove();}
}
