import {useState} from 'react';
import type {GenerationDraft,Project,Word} from '../types';
import {assetUrl,request} from '../api';
import {CAMERAS,DEFAULT_LETTERING,DEFAULT_MOTION,LETTERING_STARTERS,generationPlan,setDirection} from './generation';
import './generation.css';

export function GenerationPanel({project,word,edit,busy,blocker,generate}:{
  project:Project;word:Word;edit:(f:(p:Project)=>Project)=>void;busy:boolean;blocker:string;generate:()=>void;
}){
  const plan=generationPlan(project,word),d=plan.draft;
  const [uploading,setUploading]=useState(false),[error,setError]=useState('');
  const change=(patch:Partial<GenerationDraft>)=>edit(p=>p.id===project.id?setDirection(p,word.lineId,patch):p);
  async function reference(file:File){
    if(file.size>50*1024*1024){setError('Choose an image smaller than 50 MB.');return;}
    setUploading(true);setError('');
    try{const form=new FormData();form.append('kind','reference');form.append('file',file);
      const result=await request<{path:string}>(`/api/projects/${project.id}/media`,{method:'POST',body:form});
      change({referenceImage:result.path,referenceName:file.name});
    }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setUploading(false);}
  }
  const why=blocker||plan.reason;
  return <section className="generation-panel" aria-label="Shot direction">
    <div className="gen-heading"><b>Shot direction</b><span>Saved with this line</span></div>
    <fieldset className="gen-fields" disabled={busy||uploading}>
    <div className="seg mini" role="radiogroup" aria-label="Lettering scope">
      {(['line','word'] as const).map(scope=><button key={scope} role="radio" aria-checked={(d.scope||'line')===scope}
        className={(d.scope||'line')===scope?'active':''} onClick={()=>change({scope})}>{scope==='line'?'Whole line':'Selected word'}</button>)}
    </div>
    <blockquote className="gen-words" aria-label="Exact lettering">{plan.text}</blockquote>
    <label className="gen-field"><span>Lettering &amp; setting</span><textarea rows={4} aria-label="Lettering and setting"
      value={d.lettering??DEFAULT_LETTERING} onChange={e=>change({lettering:e.target.value})}/></label>
    <div className="gen-starters" role="group" aria-label="Lettering starting points">{LETTERING_STARTERS.map(s=><button key={s.name}
      title={`Use this starting point: ${s.text}`} onClick={()=>change({lettering:s.text})}>{s.name}</button>)}</div>
    <div className="gen-row">
      <label className="gen-field"><span>Camera</span><select aria-label="Shot camera" value={d.camera||'locked'}
        onChange={e=>change({camera:e.target.value as GenerationDraft['camera']})}>{Object.entries(CAMERAS).map(([key,c])=><option key={key} value={key}>{c.label}</option>)}</select></label>
      <label className="gen-field"><span>Detail</span><select aria-label="Shot detail" value={d.longEdge??1344}
        onChange={e=>change({longEdge:Number(e.target.value) as 736|1344})}><option value={1344}>High · 1344 px</option><option value={736}>Draft · 736 px</option></select></label>
    </div>
    <label className="gen-field"><span>Movement</span><textarea rows={3} aria-label="Shot movement" value={d.motion??DEFAULT_MOTION}
      placeholder="Describe one clear action and how it unfolds." onChange={e=>change({motion:e.target.value})}/></label>
    <details className="gen-more"><summary>Timing &amp; reference</summary>
      <div className="gen-row">
        <label className="gen-field"><span>Start · seconds</span><input type="number" aria-label="Shot start" min={0} max={project.duration} step={1/project.fps}
          value={d.start??+plan.start.toFixed(3)} onChange={e=>change({start:e.target.value===''?undefined:Number(e.target.value)})}/></label>
        <label className="gen-field"><span>Length · seconds</span><input type="number" aria-label="Shot length" min={1.2} max={10} step={.1}
          value={d.duration??+plan.duration.toFixed(3)} onChange={e=>change({duration:e.target.value===''?undefined:Number(e.target.value)})}/></label>
      </div>
      <div className="gen-reference">
        {d.referenceImage&&<><img src={assetUrl(project,d.referenceImage)} alt={d.referenceName||'Identity reference'}/><span>{d.referenceName||'Identity reference'}</span>
          <button className="icon-sm" aria-label="Remove identity reference" onClick={()=>change({referenceImage:undefined,referenceName:undefined})}>×</button></>}
        <label className="gen-upload">{uploading?'Adding reference…':d.referenceImage?'Change face reference':'Add face reference'}
          <input type="file" accept="image/*" aria-label="Face reference" disabled={busy||uploading} onChange={e=>{const file=e.target.files?.[0];if(file)void reference(file);e.target.value='';}}/>
        </label>
      </div>
      <label className="gen-field"><span>Seed · optional</span><input type="number" aria-label="Shot seed" min={0} max={2147483647} step={1} placeholder="Random"
        value={d.seed??''} onChange={e=>change({seed:e.target.value===''?undefined:Number(e.target.value)})}/></label>
    </details>
    <details className="gen-more"><summary>Review direction</summary><div className="gen-review"><p>{plan.text}</p><p>{plan.body.prompt}</p><p>{plan.body.motionPrompt}</p></div></details>
    </fieldset>
    <p className="gen-note">{plan.start.toFixed(2)}–{plan.end.toFixed(2)} s · Original song stays unchanged.</p>
    {(error||why)&&<p className="gen-note gen-error" role="status">{error||why}</p>}
    <button className="wide primary" disabled={busy||uploading||!!why} onClick={generate}>Generate shot</button>
  </section>;
}
