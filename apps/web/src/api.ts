import type {Project, Job} from './types';
export async function request<T>(path:string, options:RequestInit = {}, server=''):Promise<T>{
  const response = await fetch(`${server}${path}`, { ...options, headers: options.body instanceof FormData ? options.headers : {'Content-Type':'application/json',...options.headers}});
  if(!response.ok){let message=await response.text();try{message=JSON.parse(message).detail ?? message;}catch{/* non-JSON errors */}throw new Error(typeof message==='string'?message:JSON.stringify(message));}
  return response.json() as Promise<T>;
}
export const getProject=(id:string,server='')=>request<Project>(`/api/projects/${encodeURIComponent(id)}`,{},server);
export function assetUrl(project:Project,path:string,server=''){
  if(path.startsWith('blob:') || path.startsWith('data:') || path.startsWith('/'))return path; // '/…' = web-origin fixture
  if(project.id==='sample')return `/sample/${path.replace(/^media\//,'').replace(/^analysis\//,'')}`;
  return `${server}/files/projects/${encodeURIComponent(project.id)}/${path.split('/').map(encodeURIComponent).join('/')}`;
}
export async function pollJob(job:Job,update:(job:Job)=>void,server=''){
  let current=job;
  while(current.status==='queued'||current.status==='running'){
    update(current);await new Promise(resolve=>setTimeout(resolve,900));
    current=await request<Job>(`/api/jobs/${current.id}`,{},server);
  }
  update(current);if(current.status==='failed')throw new Error(current.message||'Job failed');return current;
}
