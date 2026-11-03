import {useEffect,useRef,useState} from 'react';
import type {Project} from '../types';
import {assetOf} from '../layers';
import {uploadAssets} from './LayersPanel';
import {SceneThumb as AssetThumb} from './SceneThumb';
import {mergeAssets} from './takes';
import {BOARD_ROLES} from './board';
import {patchScene,scenesOf,sceneForId,type Scene} from './scenes';
import {Icon} from './icons';

export function SceneReferences({project,scene,edit,onPreview,onError}:{project:Project;scene:Scene;edit:(f:(p:Project)=>Project)=>void;onPreview:(id:string)=>void;onError:(message:string)=>void}){
  const [open,setOpen]=useState(false),[uploading,setUploading]=useState(false),file=useRef<HTMLInputElement>(null);
  const [expanded,setExpanded]=useState(false);
  useEffect(()=>{setExpanded(false);setOpen(false);},[scene.id]);
  const add=(id:string)=>{edit(p=>{const s=scenesOf(p).find(s=>s.id===scene.id);return s?patchScene(p,s.id,{refs:[...new Set([...s.refs,id])]}):p;});setOpen(false);};
  const upload=async(files:File[])=>{const pid=project.id,sid=scene.id;setUploading(true);
    try{const assets=await uploadAssets(pid,files);edit(p=>{if(p.id!==pid)return p;const q=mergeAssets(p,pid,assets),s=sceneForId(q,sid);return s?patchScene(q,s.id,{refs:[...new Set([...s.refs,...assets.map(a=>a.id)])]}):q;});}
    catch(e){onError(String(e));}finally{setUploading(false);setOpen(false);}
  };
  return <div className="scene-references">
    <div className="study-refs">{(expanded?scene.refs:scene.refs.slice(0,3)).map(id=>{const a=assetOf(project,id);return a&&<div className="scene-ref" key={id}>
      <button aria-label={`Preview reference ${a.name||id}`} title={a.name} onClick={()=>onPreview(id)}><AssetThumb project={project} asset={a}/></button>
      <select aria-label={`Role for ${a.name||id}`} value={scene.roles?.[id]||'reference'} onChange={e=>{const role=e.target.value as typeof BOARD_ROLES[number];edit(p=>{const s=scenesOf(p).find(s=>s.id===scene.id);return s?patchScene(p,s.id,{roles:{...s.roles,[id]:role}}):p;});}}>{BOARD_ROLES.map(r=><option key={r} value={r}>{r}</option>)}</select>
      <button className="scene-ref-remove" aria-label={`Remove reference ${a.name||id}`} title="Remove from scene" onClick={()=>edit(p=>{const s=scenesOf(p).find(s=>s.id===scene.id);if(!s)return p;
        // Clearing an attached reference also clears explicit workflow assignments to it.
        const generation=s.generation?{...s.generation,workflows:Object.fromEntries(Object.entries(s.generation.workflows||{}).map(([wid,d])=>[wid,{...d,sources:Object.fromEntries(Object.entries(d.sources||{}).filter(([,v])=>v!==id))}]))}:undefined;
        return patchScene(p,s.id,{refs:s.refs.filter(x=>x!==id),generation});})}>×</button>
    </div>;})}<button className="scene-ref-add" aria-label="Add scene reference" title="Add reference" onClick={()=>setOpen(v=>!v)}><Icon name="plus" size={16}/></button></div>
    {scene.refs.length>3&&<button className="scene-all-refs" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>{expanded?'Fewer references':`All ${scene.refs.length} references`}</button>}
    {open&&<div className="scene-reference-picker"><button disabled={uploading||project.id==='sample'} onClick={()=>file.current?.click()}>{uploading?'Uploading…':'Upload reference'}</button><div className="scene-asset-grid">{(project.assets||[]).filter(a=>!scene.refs.includes(a.id)).map(a=><button key={a.id} title={a.name} aria-label={`Attach ${a.name||a.id}`} onClick={()=>add(a.id)}><AssetThumb project={project} asset={a}/></button>)}</div></div>}
    <input ref={file} type="file" accept="image/*,video/*" multiple hidden onChange={e=>{const files=Array.from(e.target.files||[]);e.target.value='';if(files.length)void upload(files);}}/>
    {scene.notes&&<details className="scene-notes"><summary>Notes</summary><textarea aria-label="Scene notes" rows={5} value={scene.notes} onChange={e=>{const notes=e.target.value;edit(p=>patchScene(p,scene.id,{notes}));}}/></details>}
  </div>;
}
