import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {at} from './base';
import {request} from './api';
import {GENERATION_PRESETS,SETUP_EVENT,type SetupTab} from './setup';
import {Icon} from './studio/icons';
import './setup.css';

const REPO='https://github.com/v10101a/comfyUI-reprise';
function Command({children}:{children:string}){
  const [copied,setCopied]=useState(false);
  return <div className="setup-command"><code>{children}</code><button onClick={()=>{void navigator.clipboard.writeText(children).then(()=>setCopied(true)).catch(()=>setCopied(false));}}>{copied?'Copied':'Copy'}</button></div>;
}

/** Public-site handoff to an existing installation; never stores an API key in the browser. */
export function SetupGuide(){
  const dialog=useRef<HTMLDialogElement>(null);
  const [tab,setTab]=useState<SetupTab>('demo');
  const [open,setOpen]=useState(false),[status,setStatus]=useState<'checking'|'demo'|'connected'>('checking');
  const [comfyUrl,setComfyUrl]=useState('http://127.0.0.1:8188');
  let studioUrl='';try{const u=new URL(comfyUrl);if(['http:','https:'].includes(u.protocol)&&!u.username&&!u.password){u.search='';u.hash='';u.pathname=u.pathname.replace(/\/$/,'').replace(/\/typeset$/,'')+'/typeset/';studioUrl=u.href;}}catch{/* keep the invalid address editable */}
  useEffect(()=>{
    const show=(e:Event)=>{setTab((e as CustomEvent<SetupTab>).detail||'demo');setOpen(true);};
    window.addEventListener(SETUP_EVENT,show);return()=>window.removeEventListener(SETUP_EVENT,show);
  },[]);
  useEffect(()=>{
    if(!open)return;
    const node=dialog.current!;node.showModal();setStatus('checking');
    const controller=new AbortController(),timer=setTimeout(()=>{setStatus('demo');controller.abort();},12000);
    void request<{status?:string}>('/api/health',{signal:controller.signal}).then(h=>{if(!controller.signal.aborted)setStatus(h.status==='ok'?'connected':'demo');}).catch(()=>{if(!controller.signal.aborted)setStatus('demo');}).finally(()=>clearTimeout(timer));
    return()=>{controller.abort();clearTimeout(timer);node.close();};
  },[open]);
  if(!open)return null;
  const close=()=>setOpen(false);
  return createPortal(<dialog ref={dialog} className="setup-dialog" aria-labelledby="setup-title" onCancel={close} onKeyDown={e=>e.stopPropagation()} onClick={e=>{if(e.target===e.currentTarget)close();}}>
    <div className="setup-content">
      <header><Icon name="pipeline"/><h2 id="setup-title">Generation setup</h2><button className="setup-close" aria-label="Close setup" title="Close (Esc)" onClick={close}><Icon name="close"/></button></header>
      <nav className="setup-tabs" aria-label="Setup options">{([['demo','Demo'],['local','My ComfyUI'],['cloud','Comfy Cloud'],['models','Models']] as const).map(([id,label])=><button key={id} className={tab===id?'active':''} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</nav>
      {tab==='demo'&&<section key={tab}>
        <p>Edit the sample’s words, typography and timeline. Changes save in this browser; no account or credits needed.</p>
        <a className="setup-primary" href="#/studio?project=sample" onClick={close}>Open editable demo</a>
        <p className="setup-status">{status==='checking'?'Checking connection…':status==='connected'?'Reprise connected · ready for your own projects':'Your own media and exports need a Reprise installation.'}</p>
      </section>}
      {tab==='local'&&<section key={tab}>
        <label className="setup-address">Your ComfyUI address<input type="url" value={comfyUrl} onChange={e=>setComfyUrl(e.target.value)} placeholder="http://127.0.0.1:8188"/></label>
        {studioUrl?<a className="setup-primary" href={studioUrl} target="_blank" rel="noreferrer">Open Reprise in my ComfyUI ↗</a>:<p className="setup-error">Enter an http:// or https:// ComfyUI address.</p>}
        <p className="setup-detail">Uses your existing installation and model folders.</p>
        <details className="setup-help"><summary>Install Reprise in ComfyUI</summary>
        <ol>
          <li><a href={`${REPO}/archive/refs/heads/main.zip`}>Download Reprise</a> and follow the <a href={`${REPO}#run-locally`} target="_blank" rel="noreferrer">installation steps</a> to build the editor and link its nodes into your existing ComfyUI. Keep the full Reprise folder.</li>
          <li>Restart ComfyUI and open its <b>Reprise</b> sidebar, or use the button above.</li>
          <li>Import your ComfyUI API workflow, then choose installed files in <b>Models</b>.</li>
        </ol>
        <p className="setup-detail">Local model workflows need no Cloud credits. Paid API nodes still use their provider’s credits.</p>
        </details>
        <a className="setup-secondary" href="http://127.0.0.1:8787/studio/" target="_blank" rel="noreferrer">Open standalone Reprise ↗</a>
      </section>}
      {tab==='cloud'&&<section key={tab}>
        <p>Generate with your own Cloud account. Requires a paid subscription and credits.</p>
        <a className="setup-primary" href="https://platform.comfy.org/" target="_blank" rel="noreferrer">Create a Cloud API key ↗</a>
        <details className="setup-help"><summary>Connect your key to Reprise</summary>
        <ol>
          <li>Complete <a href={`${REPO}#run-locally`} target="_blank" rel="noreferrer">Reprise’s local setup</a> for editing and export.</li>
          <li>Create <code>.env.comfy</code> in your Reprise folder and add <code>TYPESET_CLOUD_API_KEY=your-key</code>. Keep this file private; this website does not collect your key.</li>
          <li>Restart the app, then choose <b>Comfy Cloud</b> from <b>Run on</b>.</li>
        </ol>
        <Command>scripts/dev.sh</Command>
        <p className="setup-detail">This command is for macOS/Linux. Other installations can set the same environment variable before starting Reprise. Cloud workflows must use its available nodes and models. Local lyric/matte analysis still needs the Reprise nodes.</p>
        </details>
        <a className="setup-secondary" href="https://docs.comfy.org/development/deploy/cloud" target="_blank" rel="noreferrer">Cloud requirements ↗</a>
      </section>}
      {tab==='models'&&<section key={tab}>
        <p>Import your own workflow, or start with a preset.</p>
        <div className="setup-models">{GENERATION_PRESETS.map(p=><article key={p.id}>
          <div className="setup-model-name" title={p.description}><h3>{p.name}</h3><span>{p.task}</span><small>{p.requirements}</small></div>
          <div className="setup-model-actions"><a href={at(`/workflows/${p.file}`)} download aria-label={`Download ${p.name} workflow`} title="Download workflow JSON"><Icon name="download" size={14}/>Workflow</a><a href={p.models} target="_blank" rel="noreferrer" aria-label={`${p.name} model files`}>Model files ↗</a></div>
        </article>)}</div>
        <details className="setup-help"><summary>Model compatibility &amp; downloads</summary>
        <p>Choose installed files in a scene’s <b>Models</b> dropdowns. Keep to the workflow’s model family; a different architecture needs a matching workflow.</p>
        <p>For missing files, open a matching ComfyUI template. Desktop can download supported models into the right folders; other installations may need manual placement. Then click <b>Refresh models</b> in Reprise. Workflow JSON files do not install model weights.</p>
        <a href="https://docs.comfy.org/interface/features/template" target="_blank" rel="noreferrer">How model downloads work ↗</a>
        </details>
      </section>}
    </div>
  </dialog>,document.querySelector('.studio')||document.querySelector('.showcase')||document.body);
}
