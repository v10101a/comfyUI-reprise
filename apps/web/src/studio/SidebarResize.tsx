import {useLayoutEffect,useRef,useState} from 'react';

const KEY='typeset.leftWidth',MIN=224,MAX=600;
const clamp=(width:number,max:number)=>Math.round(Math.max(MIN,Math.min(max,width)));

/** A remembered panel width, bounded to leave room for the stage and inspector. */
export function SidebarResize(){
  const handle=useRef<HTMLDivElement>(null);
  const [preferred,setPreferred]=useState<number|null>(()=>{try{
    const raw=localStorage.getItem(KEY),width=Number(raw);
    return raw&&Number.isFinite(width)&&width>=MIN?Math.min(MAX,width):null;
  }catch{return null;}});
  const [size,setSize]=useState({width:280,max:MAX});
  const [dragging,setDragging]=useState(false);
  const drag=useRef<{x:number;width:number;current:number}|null>(null);
  useLayoutEffect(()=>{
    const main=handle.current?.parentElement;if(!main)return;
    const fit=()=>{
      const right=main.querySelector('.s-right')?.getBoundingClientRect().width||320;
      const max=Math.max(MIN,Math.min(MAX,main.clientWidth-right-320));
      const fallback=window.innerWidth>=1700?296:window.innerWidth<=1180?224:280;
      const width=clamp(preferred??fallback,max);
      main.style.setProperty('--left-width',`${width}px`);
      setSize(old=>old.width===width&&old.max===max?old:{width,max});
    };
    fit();const observer=new ResizeObserver(fit);observer.observe(main);
    return()=>observer.disconnect();
  },[preferred]);
  const remember=(width:number|null)=>{setPreferred(width);try{
    if(width===null)localStorage.removeItem(KEY);else localStorage.setItem(KEY,String(width));
  }catch{/* Layout remains usable without storage. */}};
  const finish=()=>{if(!drag.current)return;remember(drag.current.current);drag.current=null;setDragging(false);};
  return <div ref={handle} className={`s-left-resize${dragging?' dragging':''}`} role="separator" tabIndex={0}
    aria-label="Resize left sidebar" aria-orientation="vertical" aria-controls="studio-left-panel"
    aria-valuemin={MIN} aria-valuemax={size.max} aria-valuenow={size.width} aria-valuetext={`${size.width} pixels`}
    title="Drag to resize · double-click to reset" style={{left:size.width}}
    onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);
      drag.current={x:e.clientX,width:size.width,current:size.width};setDragging(true);}}
    onPointerMove={e=>{const start=drag.current;if(!start)return;
      start.current=clamp(start.width+e.clientX-start.x,size.max);setPreferred(start.current);}}
    onPointerUp={e=>{finish();if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
    onPointerCancel={finish} onLostPointerCapture={finish}
    onDoubleClick={()=>remember(null)}
    onKeyDown={e=>{e.stopPropagation();const step=e.shiftKey?40:16;
      const next=e.key==='ArrowRight'?size.width+step:e.key==='ArrowLeft'?size.width-step:e.key==='Home'?MIN:e.key==='End'?size.max:null;
      if(next!==null){e.preventDefault();remember(clamp(next,size.max));}
      else if(e.key==='Enter'){e.preventDefault();remember(null);}}}/>
}
