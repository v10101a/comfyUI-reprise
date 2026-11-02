import {useEffect,useRef,useState} from 'react';
import type {Asset,MediaLayer,Project} from '../types';
import {assetUrl,request} from '../api';
import {assetOf,insertLayer,layersOf,mediaLayer} from '../layers';
import {Icon} from './icons';
import {listWorkflows,type Workflow} from './workflows';
import {mergeAssets,setGeneration,visualLayer} from './takes';
import {BOARD_ROLES,DEFAULT_VIEW,addCards,appendDirection,assignReference,boardPoint,cardId,cardsOf,fitBoard,groupMembers,moveCards,removeCard,updateCard,zoomAt,type BoardCard,type BoardRole,type BoardView} from './board';
import './reference-board.css';

type Props={project:Project;edit:(f:(p:Project)=>Project)=>void;checkpoint:()=>void;selectedLayer:string;onSelectLayer:(id:string)=>void;onClose:()=>void;onGenerate:()=>void;onUndo:(redo:boolean)=>void};
type Gesture={kind:'move'|'resize'|'pan';x:number;y:number;cards:BoardCard[];view:BoardView;dx:number;dy:number};
const label=(s:string)=>s[0].toUpperCase()+s.slice(1);
const safeLink=(url:string|undefined)=>{try{const u=new URL(url||'');return ['https:','http:'].includes(u.protocol)?u.href:undefined;}catch{return undefined;}};

/** A creative reference space backed by the same project assets and actual workflow inputs as Create. */
export function ReferenceBoard({project:p,edit,checkpoint,selectedLayer,onSelectLayer,onClose,onGenerate,onUndo}:Props){
  const [selected,setSelected]=useState(''),[workflows,setWorkflows]=useState<Workflow[]>([]),[port,setPort]=useState('');
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[uploading,setUploading]=useState(false),[over,setOver]=useState(false);
  const viewKey=`typeset.board.${p.id}`;
  const [view,setView]=useState<BoardView>(()=>{try{const v=JSON.parse(localStorage.getItem(viewKey)||'null');if(v&&[v.x,v.y,v.zoom].every(Number.isFinite)&&v.zoom>=.25&&v.zoom<=2)return v;}catch{}return p.board?.view||DEFAULT_VIEW;});
  const [drag,setDrag]=useState<Gesture|null>(null);
  const viewport=useRef<HTMLDivElement>(null),upload=useRef<HTMLInputElement>(null),viewRef=useRef(view),gesture=useRef<Gesture|null>(null),live=useRef(true);viewRef.current=view;
  const cards=cardsOf(p),card=cards.find(c=>c.id===selected),asset=card?.assetId?assetOf(p,card.assetId):undefined;
  const media=layersOf(p).filter((l):l is MediaLayer=>l.kind==='media'),layer=visualLayer(p,selectedLayer);
  const wid=layer?.generation?.workflowId||workflows[0]?.id||'',wf=workflows.find(w=>w.id===wid);
  const inputs=wf?Object.entries(wf.inputs):[],mediaInputs=inputs.filter(([,i])=>i.role==='media'&&
    (i.media==='video'?asset?.kind==='video':String(i.media)==='audio'?asset?.kind==='video'&&asset.hasAudio:true));
  const promptInputs=inputs.filter(([,i])=>i.role==='prompt');
  const ports=card?.kind==='note'?promptInputs:mediaInputs;
  const inputKey=ports.some(([k])=>k===port)?port:ports[0]?.[0]||'';
  const activeSource=layer?.generation?.workflows?.[wid]?.sources?.[inputKey];
  const selectCard=(c:BoardCard)=>{setSelected(c.id);if(c.layerId&&visualLayer(p,c.layerId))onSelectLayer(c.layerId);};
  useEffect(()=>{live.current=true;viewport.current?.focus();void listWorkflows().then(ws=>{if(live.current)setWorkflows(ws);}).catch(e=>{if(live.current)setError(String(e.message||e));});return()=>{live.current=false;};},[]);
  useEffect(()=>{try{localStorage.setItem(viewKey,JSON.stringify(view));}catch{}},[view,viewKey]);
  useEffect(()=>{setPort('');setNotice('');},[selected,selectedLayer,wid]);
  useEffect(()=>{const el=viewport.current;if(!el)return;const wheel=(e:WheelEvent)=>{
    if((e.target as Element).closest('textarea,video'))return;e.preventDefault();const v=viewRef.current;
    if(e.ctrlKey||e.metaKey){const r=el.getBoundingClientRect();setView(zoomAt(v,{x:e.clientX-r.left,y:e.clientY-r.top},Math.exp(-e.deltaY*.008)));}
    else setView({...v,x:v.x-e.deltaX,y:v.y-e.deltaY});
  };el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);},[]);
  const point=(x?:number,y?:number)=>{const r=viewport.current!.getBoundingClientRect();return boardPoint({x:x==null?r.width/2:x-r.left,y:y==null?r.height/2:y-r.top},viewRef.current);};
  const patch=(v:Partial<BoardCard>)=>{if(card)edit(q=>updateCard(q,card.id,v));};
  const fail=(e:unknown)=>{if(live.current)setError(e instanceof Error?e.message:String(e));};
  function add(kind:'note'|'group',at=point(),text=''){
    const c:BoardCard={id:cardId(),kind,x:Math.round(at.x-100),y:Math.round(at.y-70),w:kind==='group'?600:230,h:kind==='group'?460:190,title:kind==='group'?'New group':'New note',text,role:'reference'};
    checkpoint();edit(q=>addCards(q,[c]));setSelected(c.id);
  }
  function addAsset(a:Asset,at=point()){
    const c:BoardCard={id:cardId(),kind:'asset',assetId:a.id,title:a.name||'Reference',role:a.source?.kind==='workflow'?'asset':'reference',x:Math.round(at.x-110),y:Math.round(at.y-90),w:220,h:224};
    checkpoint();edit(q=>addCards(q,[c]));setSelected(c.id);
  }
  async function uploadFiles(files:File[],at=point()){
    if(p.id==='sample'){setError('Create a saved project to upload references.');return;}
    const supported=files.filter(f=>/^(image|video)\//.test(f.type));if(!supported.length){setError('Drop image or video files, or paste text for a note.');return;}
    const pid=p.id;setUploading(true);setError('');
    try{for(const [i,f] of supported.entries()){
      const form=new FormData();form.append('file',f);const a=await request<Asset>(`/api/projects/${pid}/assets`,{method:'POST',body:form});if(!live.current)return;
      const c:BoardCard={id:cardId(),kind:'asset',assetId:a.id,title:a.name||f.name,role:'reference',x:Math.round(at.x-110+i*32),y:Math.round(at.y-90+i*32),w:220,h:224};
      checkpoint();edit(q=>q.id===pid?addCards(mergeAssets(q,pid,[a]),[c]):q);setSelected(c.id);
    }}catch(e){fail(e);}finally{if(live.current)setUploading(false);}
  }
  function begin(e:React.PointerEvent,kind:Gesture['kind'],c?:BoardCard){
    if(e.button!==0&&e.button!==1)return;e.preventDefault();e.stopPropagation();
    viewport.current?.focus({preventScroll:true});
    if(c)selectCard(c);else setSelected('');const members=c?(c.kind==='group'&&kind==='move'?groupMembers(cards,c):[c]):[];
    const g:Gesture={kind,x:e.clientX,y:e.clientY,cards:members,view:viewRef.current,dx:0,dy:0};gesture.current=g;setDrag(g);
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }
  function move(e:React.PointerEvent){
    const g=gesture.current;if(!g)return;const dx=(e.clientX-g.x)/g.view.zoom,dy=(e.clientY-g.y)/g.view.zoom;
    const next={...g,dx,dy};gesture.current=next;setDrag(next);
    if(g.kind==='pan')setView({...g.view,x:g.view.x+e.clientX-g.x,y:g.view.y+e.clientY-g.y});
  }
  function finish(cancel=false){const g=gesture.current;gesture.current=null;setDrag(null);if(!g||cancel||g.kind==='pan'||Math.abs(g.dx)+Math.abs(g.dy)<2)return;
    checkpoint();if(g.kind==='move')edit(q=>moveCards(q,g.cards,g.dx,g.dy));
    else{const c=g.cards[0];edit(q=>updateCard(q,c.id,{w:Math.max(c.kind==='group'?300:160,Math.round(c.w+g.dx)),h:Math.max(c.kind==='group'?220:130,Math.round(c.h+g.dy))}));}
  }
  function useReference(){if(!layer||!wf||!inputKey||!card)return;checkpoint();
    if(card.kind==='note')edit(q=>appendDirection(q,layer.id,wf.id,inputKey,card.text||card.title,String(wf.inputs[inputKey].default||'')));
    else if(asset)edit(q=>assignReference(q,layer.id,wf.id,inputKey,asset.id));
    setNotice(card.kind==='note'?`Added to ${wf.inputs[inputKey].title}`:`Assigned to ${wf.inputs[inputKey].title}`);
  }
  function key(e:React.KeyboardEvent){
    if((e.target as Element).closest('input,textarea,select,video')){e.stopPropagation();return;}
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();onUndo(e.shiftKey);}
    else if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();if(card){checkpoint();edit(q=>removeCard(q,card.id));setSelected('');}}
    else if(e.key==='Escape'){if(drag)finish(true);else if(card)setSelected('');else onClose();}
    else if(e.key.startsWith('Arrow')&&card){e.preventDefault();const d=e.shiftKey?20:5;checkpoint();edit(q=>moveCards(q,card.kind==='group'?groupMembers(cards,card):[card],e.key==='ArrowLeft'?-d:e.key==='ArrowRight'?d:0,e.key==='ArrowUp'?-d:e.key==='ArrowDown'?d:0));}
    e.stopPropagation();
  }
  const bound=(assetId:string|undefined)=>!!assetId&&media.some(l=>Object.values(l.generation?.workflows||{}).some(w=>Object.values(w.sources||{}).includes(assetId)));

  return <section className="reference-board" aria-label="Reference board" tabIndex={0} onKeyDown={key} onPaste={e=>{
    if((e.target as Element).closest('input,textarea'))return;
    const files=[...e.clipboardData.files];if(files.length){e.preventDefault();void uploadFiles(files);}
    else{const text=e.clipboardData.getData('text/plain');if(text){e.preventDefault();add('note',point(),text);}}
  }}>
    <header className="rb-toolbar"><div><b>Reference board</b><span>Collect a world for your next shot</span></div>
      <button onClick={()=>upload.current?.click()} disabled={uploading}>{uploading?'Uploading…':'+ Images / video'}</button>
      <button onClick={()=>add('note')}>+ Note</button><button onClick={()=>add('group')}>+ Group</button>
      <div className="rb-zoom"><button aria-label="Zoom out board" onClick={()=>{const r=viewport.current!.getBoundingClientRect();setView(zoomAt(view,{x:r.width/2,y:r.height/2},.8));}}>−</button><span>{Math.round(view.zoom*100)}%</span>
        <button aria-label="Zoom in board" onClick={()=>{const r=viewport.current!.getBoundingClientRect();setView(zoomAt(view,{x:r.width/2,y:r.height/2},1.25));}}>+</button>
        <button onClick={()=>{const r=viewport.current!.getBoundingClientRect();setView(fitBoard(cards,r.width,r.height));}}>Fit board</button></div>
      <button onClick={onClose}>Back to edit ↗</button>
      <input ref={upload} type="file" accept="image/*,video/*" multiple hidden onChange={e=>{const fs=[...(e.target.files||[])];e.target.value='';if(fs.length)void uploadFiles(fs);}}/>
    </header>
    <div className="rb-body"><div className="rb-space">
      <div ref={viewport} className={`rb-viewport ${over?'drop':''} ${drag?.kind==='pan'?'panning':''}`} tabIndex={0} aria-label="Board canvas"
        style={{backgroundPosition:`${view.x}px ${view.y}px`,backgroundSize:`${24*view.zoom}px ${24*view.zoom}px`}}
        onPointerDown={e=>{if(!(e.target as Element).closest('[data-board-card]'))begin(e,'pan');}}
        onPointerMove={move} onPointerUp={()=>finish()} onPointerCancel={()=>finish(true)}
        onDoubleClick={e=>{if(!(e.target as Element).closest('[data-board-card]'))add('note',point(e.clientX,e.clientY));}}
        onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setOver(false);}}
        onDrop={e=>{e.preventDefault();setOver(false);const at=point(e.clientX,e.clientY),id=e.dataTransfer.getData('application/x-typeset-asset'),a=assetOf(p,id);
          if(a)addAsset(a,at);else if(e.dataTransfer.files.length)void uploadFiles([...e.dataTransfer.files],at);else{const t=e.dataTransfer.getData('text/plain');if(t)add('note',at,t);}}}>
        {!cards.length&&<div className="rb-empty"><span>✳</span><h2>Start with what you see.</h2><p>Drop a character, wardrobe, lighting reference, or a clip.<br/>Keep notes beside them. Try a few directions.</p><button onClick={()=>upload.current?.click()}>Add your first reference</button><small>Double-click anywhere for a note · scroll to pan · pinch to zoom</small></div>}
        <div className="rb-world" style={{transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`}}>
          {[...cards].sort((a,b)=>(a.kind==='group'?0:1)-(b.kind==='group'?0:1)).map(c=>{
            const moved=drag&&drag.cards.some(x=>x.id===c.id),resizing=moved&&drag.kind==='resize';const x=c.x+(moved&&drag.kind==='move'?drag.dx:0),y=c.y+(moved&&drag.kind==='move'?drag.dy:0);
            const w=resizing?Math.max(c.kind==='group'?300:160,c.w+drag.dx):c.w,h=resizing?Math.max(c.kind==='group'?220:130,c.h+drag.dy):c.h;
            const a=c.assetId?assetOf(p,c.assetId):undefined;
            return <article key={c.id} data-board-card={c.id} className={`rb-card ${c.kind} role-${c.role} ${selected===c.id?'selected':''}`} aria-label={c.title}
              style={{left:x,top:y,width:w,height:h}} tabIndex={0} onFocus={()=>selectCard(c)} onPointerDown={e=>{if(e.button===0)selectCard(c);}}>
              <div className="rb-card-head" onPointerDown={e=>begin(e,'move',c)}><span className="rb-role">{c.kind==='group'?'Group':label(c.role)}</span><span className="rb-grip">⠿</span></div>
              {c.kind==='asset'&&a&&<div className="rb-card-media">{a.kind==='image'?<img src={assetUrl(p,a.path)} alt={c.title} draggable={false}/>:<video src={assetUrl(p,a.path)} controls muted playsInline preload="metadata"/>}</div>}
              <b className="rb-card-title">{c.title}</b>
              {c.kind==='note'&&<p className="rb-card-note">{c.text||'Select to write a note…'}</p>}
              {c.kind==='asset'&&bound(c.assetId)&&<span className="rb-used">↗ Assigned reference</span>}
              <button className="rb-resize" aria-label={`Resize ${c.title}`} title="Drag to resize" onPointerDown={e=>begin(e,'resize',c)}/>
            </article>;
          })}
        </div>
        {cards.length>0&&<span className="rb-help">Drag card headers · scroll to pan · pinch to zoom</span>}
      </div>
      <div className="rb-assets"><div><b>Project assets</b><span>Drag onto the board · double-click to add</span></div>
        <div className="rb-asset-strip">{(p.assets||[]).map(a=><button key={a.id} draggable title={a.name||a.path} aria-label={`Add ${a.name||'asset'} to board`}
          onDragStart={e=>{e.dataTransfer.setData('application/x-typeset-asset',a.id);e.dataTransfer.effectAllowed='copy';}} onDoubleClick={()=>addAsset(a)}>
          {a.kind==='image'?<img src={assetUrl(p,a.path)} alt="" draggable={false}/>:<video src={assetUrl(p,a.path)} muted playsInline preload="metadata"/>}<span>{a.name||'Asset'}</span></button>)}
          <button className="rb-asset-add" onClick={()=>upload.current?.click()} disabled={uploading}>+ Upload</button></div>
      </div>
    </div>
    <aside className="rb-inspector">
      {error&&<div className="rb-error" role="alert">{error}<button aria-label="Dismiss board error" onClick={()=>setError('')}>×</button></div>}
      {card?<>
        <div className="rb-inspector-head"><b>{card.kind==='group'?'Group':card.kind==='note'?'Note':'Reference'}</b><button className="icon-sm" aria-label="Remove card from board" title="Remove card; keep the asset" onClick={()=>{checkpoint();edit(q=>removeCard(q,card.id));setSelected('');}}><Icon name="trash" size={15}/></button></div>
        <label>Title<input aria-label="Card title" value={card.title} onChange={e=>patch({title:e.target.value})}/></label>
        {card.kind!=='group'&&<label>Role<select aria-label="Reference role" value={card.role} onChange={e=>patch({role:e.target.value as BoardRole})}>{BOARD_ROLES.map(r=><option key={r} value={r}>{label(r)}</option>)}</select></label>}
        {card.kind==='note'&&<label>Note<textarea aria-label="Board note" rows={6} value={card.text||''} onChange={e=>patch({text:e.target.value})} placeholder="What matters here? Movement, texture, styling…"/></label>}
        {card.kind!=='group'&&<label>Source link<input aria-label="Reference source link" value={card.url||''} placeholder="https://…" onChange={e=>patch({url:e.target.value})}/>{safeLink(card.url)&&<a href={safeLink(card.url)} target="_blank" rel="noreferrer">Open source ↗</a>}</label>}
        {card.kind==='group'?<p className="rb-note">Drag the group header to move it with the cards fully inside. Resize from the bottom corner.</p>:<div className="rb-binding">
          <b>Use in generation</b>
          <label>Visual layer<select aria-label="Board target layer" value={layer?.id||''} onChange={e=>{patch({layerId:e.target.value||undefined});onSelectLayer(e.target.value);}}><option value="">Choose a layer</option>{media.map(l=><option key={l.id} value={l.id}>{l.name||'Layer'}</option>)}</select></label>
          {layer&&<label>Workflow<select aria-label="Board workflow" value={wid} onChange={e=>edit(q=>setGeneration(q,layer.id,e.target.value))}>{wid&&!wf&&<option value={wid}>Unavailable workflow</option>}{workflows.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}
          {layer&&wf&&ports.length>0&&<><label>{card.kind==='note'?'Prompt':'Reference input'}<select aria-label="Workflow input" value={inputKey} onChange={e=>setPort(e.target.value)}>{ports.map(([k,i])=><option key={k} value={k}>{i.title}</option>)}</select></label>
            <button onClick={useReference} disabled={card.kind==='asset'&&activeSource===card.assetId}>{card.kind==='note'?'Add note to prompt':activeSource===card.assetId?'Assigned to this input':activeSource?'Replace this reference':'Use as reference'}</button>
            {card.kind==='asset'&&mediaInputs.length===1&&<small>This workflow exposes one matching reference input. Assigning another image replaces that input.</small>}</>}
          {layer&&wf&&!ports.length&&<p className="rb-note">This workflow has no matching {card.kind==='note'?'prompt':'media'} input. You can expose inputs in Create or choose another workflow.</p>}
          {!layer&&<><p className="rb-note">Choose a visual layer to connect references, or start one from this asset.</p>
            {asset&&<button onClick={()=>{const l=mediaLayer(asset,p);checkpoint();edit(q=>insertLayer(q,l,'under-text'));onSelectLayer(l.id);}}>Create visual layer from this</button>}</>}
          <p className="rb-note">Roles help organize your ideas. Only assigned references go into generation.</p>
          {notice&&<p className="rb-success" role="status">{notice}</p>}
          <button className="primary" onClick={onGenerate}>Open generation & takes ↗</button>
        </div>}
      </>:<div className="rb-intro"><span>✳</span><h2>A place for the whole idea.</h2><p>Collect characters, wardrobe, atmosphere, movement, and finished assets together.</p><p>Group a direction. Select a card to connect it to a workflow, or keep it here as inspiration.</p><button onClick={()=>add('group')}>Make a group</button></div>}
    </aside></div>
  </section>;
}
