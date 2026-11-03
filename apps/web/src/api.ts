import type {Project, Job} from './types';
import {at, BASE} from './base';
import {migrateProject} from './looks';
export async function request<T>(path:string, options:RequestInit = {}, server=''):Promise<T>{
  const response = await fetch(`${server}${path}`, { ...options, headers: options.body instanceof FormData ? options.headers : {'Content-Type':'application/json',...options.headers}});
  if(!response.ok){let message=await response.text();try{message=JSON.parse(message).detail ?? message;}catch{/* non-JSON errors */}
    // A static host (GitHub Pages, a plain file server) answers /api with an HTML 404: say so instead of printing the page.
    if(/text\/html/i.test(response.headers.get('content-type')||''))message=`No Reprise server here (HTTP ${response.status}). Run it locally to use your own footage.`;
    throw new Error(typeof message==='string'?message:JSON.stringify(message));}
  return response.json() as Promise<T>;
}
/** Projects come back migrated (v4: `grade` split out of the look; see looks.ts migrateProject). */
export const getProject=(id:string,server='')=>request<Project>(`/api/projects/${encodeURIComponent(id)}`,{},server).then(migrateProject);
export function assetUrl(project:Project,path:string,server=''){
  if(path.startsWith('blob:') || path.startsWith('data:'))return path;
  if(path.startsWith('/'))return at(path); // '/…' = web-origin fixture
  if(project.id==='sample')return at(`/sample/${path.replace(/^media\//,'').replace(/^analysis\//,'')}`);
  return `${server||BASE}/files/projects/${encodeURIComponent(project.id)}/${path.split('/').map(encodeURIComponent).join('/')}`;
}
export async function pollJob(job:Job,update:(job:Job)=>void,server=''){
  let current=job;
  while(current.status==='queued'||current.status==='running'){
    update(current);await new Promise(resolve=>setTimeout(resolve,900));
    current=await request<Job>(`/api/jobs/${current.id}`,{},server);
  }
  update(current);if(current.status==='failed')throw new Error(current.message||'Job failed');return current;
}
