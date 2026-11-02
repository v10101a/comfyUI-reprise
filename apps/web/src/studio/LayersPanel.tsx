// Layers: the asset bin (import / drop, sharp thumbnails), the stack (top first: drag to reorder, eye, select), the
// selected media layer's inspector and its timeline lanes. Stack model and edits: ../layers.ts (docs/SCHEMA.md §1 layers).
import {useRef,useState} from 'react';
import type {Project,Asset,SceneLayer,MediaLayer,LayerBlend} from '../types';
import {assetUrl,request} from '../api';
import {layersOf,assetOf,mapLayer,editMedia,insertLayer,mediaLayer,replaceAsset,dragLayer,propAt,setLayerProp,keyAll,unkey,keyNear,layerLength} from '../layers';
import {Icon} from './icons';
import {ScrubNum,SizeSlider} from './LineInspector';
import {DurationInput} from './DurationInput';
import {ASSET_MIME,fitLayerEnd,setMediaLength} from './duration';
import {reorderMedia,stepMediaOrder,type MediaTrack} from './mediaTracks';
import './layers.css';

const LAYER_MIME='application/x-typeset-layer';
const MARKER:Record<string,{icon:string;name:string;tip:string}>={plate:{icon:'media',name:'Footage',tip:'The project video, graded'},subject:{icon:'matte',name:'Person',tip:'The subject cut out of the footage'},
  behind:{icon:'behind',name:'Behind text',tip:'Lyrics placed behind the person'},front:{icon:'caption',name:'Front text',tip:'Captions, HUD and walls in front'}};
const markerOf=(l:SceneLayer)=>l.kind==='plate'?MARKER.plate:l.kind==='subject'?MARKER.subject:l.kind==='text'?MARKER[l.which]:undefined;
const BLENDS:LayerBlend[]=['normal','screen','multiply','add','overlay'];
const cap=(s:string)=>s[0].toUpperCase()+s.slice(1);

export function AssetThumb({project,asset}:{project:Project;asset:Asset}){
  const url=assetUrl(project,asset.path);
  return asset.kind==='image'?<img className="as-thumb" src={url} alt="" draggable={false}/>:<video className="as-thumb" src={`${url}#t=0.5`} muted playsInline preload="metadata"/>;
}

/** Upload files into the bin; returns the stored assets (server appends them to project.assets). */
export async function uploadAssets(pid:string,files:File[]):Promise<Asset[]>{
  const out:Asset[]=[];for(const f of files){const form=new FormData();form.append('file',f);out.push(await request<Asset>(`/api/projects/${encodeURIComponent(pid)}/assets`,{method:'POST',body:form}));}return out;
}

export function LayersPanel({project:p,edit,checkpoint,selected,onSelect,run,onAdded}:{project:Project;edit:(u:(p:Project)=>Project)=>void;checkpoint:()=>void;
  selected:string;onSelect:(id:string)=>void;run:(a:()=>Promise<void>)=>void;onAdded?:(id:string,assetId:string)=>void}){
  const input=useRef<HTMLInputElement>(null);const [over,setOver]=useState<string|null>(null);const [dropping,setDropping]=useState(false);
  const stack=layersOf(p);const shown=[...stack].reverse();const assets=p.assets||[];const disabled=p.id==='sample';
  const take=(as:Asset[])=>edit(q=>({...q,assets:[...(q.assets||[]).filter(a=>!as.some(x=>x.id===a.id)),...as]}));
  const importFiles=(files:File[])=>{files=files.filter(f=>/^(video|image)\//.test(f.type));if(!files.length||disabled)return;run(async()=>take(await uploadAssets(p.id,files)));};
  const place=(a:Asset,where:'under-text'|'top')=>{checkpoint();const l=mediaLayer(a,p);edit(q=>insertLayer(q,l,where));onAdded?.(l.id,a.id);onSelect(l.id);};
  // Drop on a row (display order, top first): the dragged layer / new asset goes just above that row.
  const dropOn=(e:React.DragEvent,target:SceneLayer)=>{e.preventDefault();setOver(null);const lid=e.dataTransfer.getData(LAYER_MIME),aid=e.dataTransfer.getData(ASSET_MIME);
    const moving=lid?stack.find(l=>l.id===lid):(()=>{const a=assetOf(p,aid);return a?mediaLayer(a,p):undefined;})();
    if(!moving||moving.id===target.id)return;checkpoint();edit(q=>insertLayer(q,moving,{above:target.id}));if(moving.kind==='media'){if(!lid)onAdded?.(moving.id,moving.assetId);onSelect(moving.id);}};
  return <div className={`layers-panel ${dropping?'dropping':''}`} onDragOver={e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();setDropping(true);}}} onDragLeave={e=>{if(e.currentTarget===e.target)setDropping(false);}}
    onDrop={e=>{if(!e.dataTransfer.files.length)return;e.preventDefault();setDropping(false);importFiles([...e.dataTransfer.files]);}}>
    <div className="as-bin" role="list" aria-label="Assets">
      {assets.map(a=><div key={a.id} role="listitem" className="as-item" draggable onDragStart={e=>{e.dataTransfer.setData(ASSET_MIME,a.id);e.dataTransfer.effectAllowed='copy';}}
        title={`${a.name||a.path.split('/').pop()}${a.duration?` · ${a.duration.toFixed(1)} s`:''}${a.source&&a.source.kind!=='upload'?` · ${a.source.kind}`:''} · double-click adds behind the text`} onDoubleClick={()=>place(a,'under-text')}>
        <AssetThumb project={p} asset={a}/>
        <div className="as-acts"><button className="icon-sm" aria-label="Add behind text" title="Add behind the text" onClick={()=>place(a,'under-text')}><Icon name="behind" size={13}/></button>
          <button className="icon-sm" aria-label="Add on top" title="Add on top" onClick={()=>place(a,'top')}><Icon name="plus" size={13}/></button></div>
        {a.kind==='video'&&<span className="as-dur mono">{a.duration?.toFixed(1)}</span>}
      </div>)}
      <button className="as-add" onClick={()=>input.current?.click()} disabled={disabled} aria-label="Import" title={disabled?'Open a saved project first':'Import video or images · or drop files here'}><Icon name="plus" size={18}/></button>
    </div>
    <div className="ly-stack" role="list" aria-label="Layers">
      {shown.map(l=>{const m=markerOf(l);const a=l.kind==='media'?assetOf(p,l.assetId):undefined;
        return <div key={l.id} role="listitem" className={`ly-row ${l.kind} ${selected===l.id?'sel':''} ${l.hidden?'off':''} ${over===l.id?'over':''}`} draggable
          onDragStart={e=>{e.dataTransfer.setData(LAYER_MIME,l.id);e.dataTransfer.effectAllowed='move';}} onDragOver={e=>{if(e.dataTransfer.types.includes(LAYER_MIME)||e.dataTransfer.types.includes(ASSET_MIME)){e.preventDefault();setOver(l.id);}}}
          onDragLeave={()=>setOver(o=>o===l.id?null:o)} onDrop={e=>dropOn(e,l)} onClick={()=>l.kind==='media'&&onSelect(l.id)} title={m?.tip}>
          <button className="icon-sm ly-eye" aria-label={l.hidden?'Show':'Hide'} title={l.hidden?'Show':'Hide'} onClick={e=>{e.stopPropagation();checkpoint();edit(q=>mapLayer(q,l.id,x=>({...x,hidden:x.hidden?null:true})));}}><Icon name={l.hidden?'eyeOff':'eye'} size={14}/></button>
          {m?<span className="ly-icon"><Icon name={m.icon} size={15}/></span>:a?<AssetThumb project={p} asset={a}/>:<span className="ly-icon"/>}
          <span className="ly-name">{m?m.name:l.kind==='media'?l.name||a?.name||'Layer':''}</span>
          {l.kind==='media'&&(l.mask||l.blend&&l.blend!=='normal')&&<span className="ly-tag mono" title={[l.mask&&`mask: ${l.mask==='subject'?'person':'background'}`,l.blend&&l.blend!=='normal'&&l.blend].filter(Boolean).join(' · ')}>{l.mask?'◐':''}{l.blend&&l.blend!=='normal'?l.blend.slice(0,3):''}</span>}
        </div>;})}
    </div>
    <input ref={input} type="file" accept="video/*,image/*" multiple hidden onChange={e=>{importFiles([...(e.target.files||[])]);e.target.value='';}}/>
  </div>;
}

/** Selected media layer: Replace (a new take keeps placement, timing, keys and effects), mask, blend, opacity, transform, keys. */
export function LayerInspector({project:p,id,time,edit,checkpoint,onClose,onSeek,onCreate}:{project:Project;id:string;time:number;edit:(u:(p:Project)=>Project)=>void;checkpoint:()=>void;onClose:()=>void;onSeek:(t:number)=>void;onCreate?:()=>void}){
  const l=layersOf(p).find(x=>x.id===id);if(!l||l.kind!=='media')return null;const a=assetOf(p,l.assetId);
  const lt=time-l.start;const on=lt>=0&&lt<layerLength(l);const set=(f:(l:MediaLayer)=>MediaLayer)=>edit(q=>editMedia(q,id,f));
  const prop=(k:'x'|'y'|'scale'|'rotate'|'opacity')=>propAt(l,k,lt);const put=(k:'x'|'y'|'scale'|'rotate'|'opacity',v:number)=>set(x=>setLayerProp(x,k,v,lt));
  const eps=.5/p.fps;const key=keyNear(l,lt,eps);const keys=[...(l.keys||[])].sort((x,y)=>x.t-y.t);
  const prevKey=[...keys].reverse().find(k=>k.t<lt-eps),nextKey=keys.find(k=>k.t>lt+eps);
  return <section className="panel-sec ly-insp">
    <div className="sec-head"><button className="icon-sm" onClick={onClose} aria-label="Back" title="Back"><Icon name="keyPrev" size={14}/></button><b title={a?.path}>{l.name||a?.name||'Layer'}</b>
      <span className="insp-flags"><button className="icon-sm" aria-label="Delete layer" title="Delete layer (⌫)" onClick={()=>{checkpoint();edit(q=>mapLayer(q,id,()=>null));onClose();}}><Icon name="trash" size={14}/></button></span></div>
    {onCreate&&<button className="ly-explore" onClick={onCreate}>Explore references & takes <span>↗</span></button>}
    <div className="fld"><label title="Swap the source; timing, placement, keys and effects stay">Replace</label>
      <select aria-label="Replace source" value={l.assetId} onChange={e=>{const n=assetOf(p,e.target.value);if(n){checkpoint();edit(q=>replaceAsset(q,id,n));}}}>
        {(p.assets||[]).map(x=><option key={x.id} value={x.id}>{x.name||x.path.split('/').pop()}{x.kind==='video'&&x.duration?` · ${x.duration.toFixed(1)} s`:''}</option>)}</select></div>
    <div className="fld"><label>Length</label><div className="ly-duration">
      <DurationInput value={layerLength(l)} label="Layer length in seconds" onChange={seconds=>{checkpoint();edit(q=>setMediaLength(q,id,seconds));}}/><span>s</span>
      <button onClick={()=>{checkpoint();edit(q=>setMediaLength(q,id,Math.max(1/q.fps,q.duration-l.start)));}} title="Extend this layer to the end of the timeline">To end</button>
    </div></div>
    {a?.kind==='video'&&<p className="ly-duration-note">Source: {(a.duration||0).toFixed(2)} s. Drag more footage onto the timeline to continue the edit.</p>}
    <div className="fld"><label title="Show it only on the person, or only around them (the footage's subject matte)">Mask</label>
      <div className="seg" role="radiogroup" aria-label="Mask">{([[null,'All','Whole layer'],['subject','Person','Only over the person'],['world','Background','Everywhere but the person']] as const).map(([v,label,tip])=>
        <button key={label} role="radio" aria-checked={(l.mask??null)===v} className={(l.mask??null)===v?'active':''} title={tip} onClick={()=>{checkpoint();set(x=>({...x,mask:v}));}}>{label}</button>)}</div></div>
    <div className="fld"><label>Blend</label><div className="row2">
      <select aria-label="Blend" value={l.blend||'normal'} onChange={e=>{checkpoint();const v=e.target.value as LayerBlend;set(x=>({...x,blend:v==='normal'?null:v}));}}>{BLENDS.map(b=><option key={b} value={b}>{cap(b)}</option>)}</select>
      <label className="check" title="Apply the footage grade to this layer"><input type="checkbox" checked={l.graded!==false} onChange={e=>{checkpoint();const v=e.target.checked;set(x=>({...x,graded:v?null:false}));}}/>Grade</label></div></div>
    <SizeSlider label="Opacity" value={prop('opacity')*100} min={0} max={100} step={1} fmt={v=>`${Math.round(v)}%`} onStart={checkpoint} onChange={v=>put('opacity',v/100)}/>
    <div className="fld"><label title="Offset from centre, % of the frame (X right, Y down); scale × cover; rotation in degrees">Transform</label>
      <div className="row2"><ScrubNum label="X" value={prop('x')*100} onStart={checkpoint} onChange={v=>put('x',v/100)}/><ScrubNum label="Y" value={prop('y')*100} onStart={checkpoint} onChange={v=>put('y',v/100)}/></div>
      <div className="row2"><ScrubNum label="S" title="Scale %" value={prop('scale')*100} onStart={checkpoint} onChange={v=>put('scale',Math.max(1,v)/100)}/><ScrubNum label="R" title="Rotate °" value={prop('rotate')} onStart={checkpoint} onChange={v=>put('rotate',v)}/></div></div>
    <div className="fld ly-keys"><label title="Keyframes: with a key on a property, edits at the playhead set keys; values ease between them">Keys</label>
      <div className="row-keys"><button className="icon-sm" disabled={!prevKey} aria-label="Previous key" title="Previous key" onClick={()=>prevKey&&onSeek(l.start+prevKey.t)}><Icon name="keyPrev" size={14}/></button>
        <button className={`icon-sm ${key?'on':''}`} disabled={!on} aria-pressed={!!key} aria-label={key?'Remove key':'Add key'} title={key?'Remove the key at the playhead':'Key every property at the playhead'} onClick={()=>{checkpoint();set(x=>key?unkey(x,key.t):keyAll(x,lt));}}><Icon name="key" size={14}/></button>
        <button className="icon-sm" disabled={!nextKey} aria-label="Next key" title="Next key" onClick={()=>nextKey&&onSeek(l.start+nextKey.t)}><Icon name="keyNext" size={14}/></button>
        {keys.length>0&&<span className="mono ly-keycount" title="Keys on this layer">{keys.length}</span>}</div></div>
  </section>;
}

/** Packed visual rows; each clip retains its layer, source trims, keys and Create settings. */
export function LayerLanes({project:p,X,bodyW,pps,time,tracks,onHolding,selected,onSelect,edit,checkpoint,scrub,linked,candidate}:{project:Project;X:(t:number)=>number;bodyW:number;pps:number;time:number;tracks:MediaTrack[];onHolding:(holding:boolean)=>void;selected:string;onSelect:(id:string)=>void;linked?:string[];candidate?:{layerId:string;name:string};
  edit:(u:(p:Project)=>Project)=>void;checkpoint:()=>void;scrub:Record<'onPointerDown'|'onPointerMove'|'onPointerUp',(e:React.PointerEvent)=>void>}){
  type Order={row:number;where:'above'|'below'};
  type Drag={id:string;kind:'move'|'head'|'tail';x0:number;y0:number;center:number;rowHeight:number;rows:{row:number;center:number;ids:string[]}[];
    l0:MediaLayer;next:MediaLayer;layers:SceneLayer[];pps:number;scroll:Element|null;capture:Element;moved:boolean;order:Order|null};
  const drag=useRef<Drag|null>(null),[moving,setMoving]=useState<{id:string;dy:number;order:Order|null}|null>(null);
  const begin=(e:React.PointerEvent,l:MediaLayer,kind:'move'|'head'|'tail')=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();onSelect(l.id);checkpoint();onHolding(true);
    const scroll=e.currentTarget.closest('.tl-scroll'),lane=e.currentTarget.closest('.ly-lane')!,rect=lane.getBoundingClientRect();
    // A clip may move within its packed row as its time changes. Capture on the stable row,
    // so React reordering keyed clip elements cannot interrupt the pointer gesture.
    lane.setPointerCapture(e.pointerId);
    const sy=scroll?.scrollTop||0,rows=[...(scroll?.querySelectorAll<HTMLElement>('.ly-lane')||[])].map(el=>{const r=el.getBoundingClientRect(),row=Number(el.dataset.mediaRow);return {row,center:r.top+r.height/2+sy,ids:tracks.find(t=>t.row===row)?.clips.map(c=>c.id)||[]};});
    drag.current={id:l.id,kind,x0:e.clientX+(scroll?.scrollLeft||0),y0:e.clientY+sy,center:rect.top+rect.height/2+sy,rowHeight:rect.height,rows,
      l0:l,next:l,layers:p.layers||[],pps,scroll,capture:lane,moved:false,order:null};
  };
  const move=(e:React.PointerEvent)=>{const d=drag.current;if(!d)return;
    const dx=e.clientX+(d.scroll?.scrollLeft||0)-d.x0,dy=e.clientY+(d.scroll?.scrollTop||0)-d.y0;
    if(!d.moved&&(d.kind==='move'?Math.hypot(dx,dy):Math.abs(dx))<3)return;d.moved=true;
    // Tiny horizontal hand movement during a vertical reorder should not shift a cut by a frame.
    const dt=d.kind==='move'&&Math.abs(dx)<6?0:dx/d.pps;
    d.next=d.kind==='move'&&dt===0?d.l0:dragLayer(d.l0,assetOf(p,d.l0.assetId),d.kind,dt,p.fps);
    d.order=null;
    if(d.kind==='move'&&Math.abs(dy)>d.rowHeight/2){
      const row=d.rows.reduce((a,b)=>Math.abs(a.center-(d.center+dy))<Math.abs(b.center-(d.center+dy))?a:b);
      d.order={row:row.row,where:dy<0?'above':'below'};
    }
    const next=d.next,order=d.order,targets=order?d.rows.find(r=>r.row===order.row)!.ids:[];
    edit(q=>{let n=editMedia({...q,layers:d.layers},d.id,()=>next);if(order)n=reorderMedia(n,d.id,targets,order.where);return n;});
    setMoving(d.kind==='move'?{id:d.id,dy,order}:null);
  };
  const end=(e:React.PointerEvent,cancel=false)=>{const d=drag.current;drag.current=null;if(!d)return;e.stopPropagation();setMoving(null);
    if(d.moved)edit(q=>cancel?{...q,layers:d.layers}:d.next===d.l0?q:fitLayerEnd(q,d.next));onHolding(false);if(d.capture.hasPointerCapture(e.pointerId))d.capture.releasePointerCapture(e.pointerId);
  };
  return <>{tracks.map(track=>{const off=track.clips.every(l=>l.hidden),number=track.row+1;
    const current=track.clips.find(l=>l.id===selected)||track.clips.find(l=>time>=l.start&&time<l.start+layerLength(l))||track.clips[0];
    return <div key={track.row} className={`tl-row tl-track ly-lane ${track.clips.some(l=>l.id===selected)?'sel':''} ${off?'off':''}`} data-media-row={track.row} style={{['--rows' as string]:1}}
      onPointerMove={move} onPointerUp={e=>end(e)} onPointerCancel={e=>end(e,true)} onLostPointerCapture={e=>end(e,true)}>
      <div className="tl-head" title="Display order · front to back · drag clips up/down to reorder; rows compact automatically" onClick={()=>current&&onSelect(current.id)}>
        <button className={`tl-swatch ${off?'off':''}`} aria-pressed={!off} aria-label={`${off?'Show':'Hide'} visual row ${number}`} title={`${off?'Show':'Hide'} all clips in this row`}
          onClick={e=>{e.stopPropagation();checkpoint();edit(q=>track.clips.reduce((next,l)=>mapLayer(next,l.id,x=>({...x,hidden:off?null:true})),q));}}/>
        <span className="ly-row-number">{tracks.length>1?number:<Icon name="layers" size={12}/>}</span>
      </div>
      <div className="tl-body" style={{width:bodyW}} {...scrub}>
        {moving?.order?.row===track.row&&<div className={`ly-order-drop ${moving.order.where}`} role="status">{moving.order.where==='above'?'In front':'Behind'}</div>}
        {track.clips.map(l=>{const a=assetOf(p,l.assetId),name=l.name||a?.name||'Layer',x0=X(l.start),w=Math.max(4,X(l.start+layerLength(l))-x0);
          return <div key={l.id} data-layer-id={l.id} role="group" aria-label={`Visual clip: ${name}`} tabIndex={0}
          className={`ly-clip ${linked?.includes(l.id)?'scene-linked':''} ${candidate?.layerId===l.id?'candidate-target':''} ${selected===l.id?'sel':''} ${moving?.id===l.id?'reordering':''} ${l.hidden?'off':''} ${w<76?'short':''}`} style={{left:x0,width:w,transform:moving?.id===l.id?`translateY(${moving.dy}px)`:undefined}} title={`${name} · ${l.start.toFixed(2)} s · source ${l.in.toFixed(2)}–${l.out.toFixed(2)} s · drag horizontally for time, vertically for display order · edges trim · ⌥↑/↓ reorders`}
          onFocus={e=>{if(e.target===e.currentTarget)onSelect(l.id);}}
          onPointerDown={e=>begin(e,l,'move')}
          onKeyDown={e=>{if(e.altKey&&(e.key==='ArrowUp'||e.key==='ArrowDown')){e.preventDefault();e.stopPropagation();checkpoint();edit(q=>stepMediaOrder(q,l.id,e.key==='ArrowUp'?'above':'below'));}}}>
          {a&&<span className="ly-clipthumb"><AssetThumb project={p} asset={a}/></span>}<span className="ly-cliplabel">{name}</span>
          {candidate?.layerId===l.id&&<span className="scene-candidate-box" role="status">Preview · {candidate.name}</span>}
          {(l.keys||[]).map((k,i)=><i key={i} className="ly-key" style={{left:k.t*pps}}/>)}
          <span className="ly-clip-actions">
            <button className="icon-sm ly-clip-eye" aria-label={`${l.hidden?'Show':'Hide'} layer: ${name}`} title={l.hidden?'Show clip':'Hide clip'}
              onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();checkpoint();edit(q=>mapLayer(q,l.id,x=>({...x,hidden:x.hidden?null:true})));}}><Icon name={l.hidden?'eyeOff':'eye'} size={13}/></button>
            <button className="icon-sm ly-delete" aria-label={`Delete layer: ${name}`} title="Delete clip · ⌘Z to undo"
              onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();checkpoint();edit(q=>mapLayer(q,l.id,()=>null));if(selected===l.id)onSelect('');}}><Icon name="trash" size={13}/></button>
          </span>
          <i className="tl-clip-edge in tl-trim-start" aria-label={`Trim start: ${l.name||a?.name||'Layer'}`} title="Trim start" onPointerDown={e=>begin(e,l,'head')}/>
          <i className="tl-clip-edge out tl-trim-end" aria-label={`Trim end: ${l.name||a?.name||'Layer'}`} title="Extend or trim within the source footage" onPointerDown={e=>begin(e,l,'tail')}/>
        </div>;})}
      </div>
    </div>;})}</>;
}
