import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import type {Scene} from './SceneStudy';
import type {BoardView} from '../src/studio/board';
import {boardPoint} from '../src/studio/board';
import {Icon} from '../src/studio/icons';
import {SceneName} from './SceneName';

type Props={scenes:Scene[];active:string;view:BoardView|null;onView:(v:BoardView)=>void;
  onSelect:(s:Scene)=>void;onMove:(id:string,x:number,y:number)=>void;onBlank:()=>void;onUndo:()=>void;
  onRename:(id:string,name:string)=>void;onDelete:(id:string)=>void;
  references:(s:Scene)=>ReactNode;takes:(s:Scene)=>ReactNode};
type Gesture={kind:'pan'|'move';id?:string;px:number;py:number;x:number;y:number;view:BoardView;dx:number;dy:number;moved:boolean};
const W=270;
const height=(s:Scene)=>Math.max(160,32+(s.refs.length?64:0)+Math.ceil(s.takes.length/2)*104+16);
const zoomAt=(v:BoardView,x:number,y:number,factor:number)=>{
  const zoom=Math.max(.1,Math.min(4,v.zoom*factor)),pt=boardPoint({x,y},v);
  return {zoom,x:x-pt.x*zoom,y:y-pt.y*zoom};
};

/** Unbounded scene coordinates, with viewport transforms independent of timeline selection. */
export function SceneCanvas(props:Props){
  const port=useRef<HTMLDivElement>(null),gesture=useRef<Gesture|null>(null),space=useRef(false);
  const [drag,setDrag]=useState<Gesture|null>(null),[hand,setHand]=useState(false);
  const live=useRef(props);live.current=props;
  const view=props.view||{x:16,y:32,zoom:.8},viewRef=useRef(view);viewRef.current=view;
  const fit=(all:boolean)=>{
    const el=port.current;if(!el)return;const ss=all?live.current.scenes:live.current.scenes.filter(s=>s.id===live.current.active);if(!ss.length)return;
    const x=Math.min(...ss.map(s=>s.x)),y=Math.min(...ss.map(s=>s.y))-28;
    const w=Math.max(...ss.map(s=>s.x+W))-x,h=Math.max(...ss.map(s=>s.y+height(s)))-y;
    const zoom=Math.max(.1,Math.min(all?1:1.2,(el.clientWidth-40)/w,(el.clientHeight-72)/h));
    live.current.onView({x:(el.clientWidth-w*zoom)/2-x*zoom,y:24-y*zoom,zoom});
  };
  useLayoutEffect(()=>{if(!props.view)fit(false);},[]);
  useEffect(()=>{const s=props.scenes.find(s=>s.id===props.active),el=port.current;if(!s||!el)return;const v=viewRef.current;
    if(s.x*v.zoom+v.x<0||(s.x+W)*v.zoom+v.x>el.clientWidth||s.y*v.zoom+v.y<24||s.y*v.zoom+v.y>el.clientHeight-80)fit(false);
  },[props.active]);
  useEffect(()=>{const el=port.current;if(!el)return;
    const wheel=(e:WheelEvent)=>{e.preventDefault();e.stopPropagation();const v=viewRef.current,r=el.getBoundingClientRect();
      const unit=e.deltaMode===1?16:e.deltaMode===2?el.clientHeight:1;
      live.current.onView(e.ctrlKey||e.metaKey?zoomAt(v,e.clientX-r.left,e.clientY-r.top,Math.exp(-e.deltaY*unit*.008)):{...v,x:v.x-e.deltaX*unit,y:v.y-e.deltaY*unit});};
    el.addEventListener('wheel',wheel,{passive:false});
    const release=()=>{space.current=false;setHand(false);};window.addEventListener('blur',release);window.addEventListener('keyup',release);
    return()=>{el.removeEventListener('wheel',wheel);window.removeEventListener('blur',release);window.removeEventListener('keyup',release);};
  },[]);
  const begin=(e:React.PointerEvent,s?:Scene)=>{
    if(e.button!==0&&e.button!==1)return;e.preventDefault();e.stopPropagation();port.current?.focus({preventScroll:true});
    const pan=!s||space.current||e.button===1;const v=viewRef.current;
    if(!pan&&s)props.onSelect(s);
    const g:Gesture={kind:pan?'pan':'move',id:s?.id,px:e.clientX,py:e.clientY,x:s?.x||0,y:s?.y||0,view:v,dx:0,dy:0,moved:false};
    gesture.current=g;setDrag(g);e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move=(e:React.PointerEvent)=>{const g=gesture.current;if(!g)return;
    const dx=e.clientX-g.px,dy=e.clientY-g.py;const n={...g,dx:dx/g.view.zoom,dy:dy/g.view.zoom,moved:g.moved||Math.hypot(dx,dy)>3};gesture.current=n;setDrag(n);
    if(g.kind==='pan')props.onView({...g.view,x:g.view.x+dx,y:g.view.y+dy});
  };
  const end=(cancel=false)=>{const g=gesture.current;if(!g)return;gesture.current=null;setDrag(null);
    if(cancel){if(g.kind==='pan')props.onView(g.view);return;}
    if(g.kind==='move'&&g.id&&g.moved)props.onMove(g.id,g.x+g.dx,g.y+g.dy);
    else if(g.kind==='pan'&&!g.moved)props.onBlank();
  };
  const zoom=(factor:number)=>{const r=port.current!.getBoundingClientRect();props.onView(zoomAt(viewRef.current,r.width/2,r.height/2,factor));};
  return <div ref={port} className={`study-canvas ${hand?'hand':''} ${drag?'dragging':''}`} role="region" aria-label="Scene board canvas" tabIndex={0}
    data-x={view.x} data-y={view.y} data-zoom={view.zoom} title="Scroll to pan · pinch to zoom · Space-drag to pan · drag scene frames to arrange"
    onPointerDownCapture={e=>{if(e.button===1||space.current)begin(e);}}
    onPointerDown={e=>{if(!(e.target as Element).closest('.study-board-card,.study-canvas-tools'))begin(e);}}
    onPointerMove={move} onPointerUp={()=>end()} onPointerCancel={()=>end(true)}
    onKeyDown={e=>{if((e.target as Element).closest('input,textarea,select'))return;
      if((e.metaKey||e.ctrlKey)&&e.key==='z'){e.preventDefault();e.stopPropagation();props.onUndo();}
      else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();e.stopPropagation();end(true);port.current?.focus({preventScroll:true});props.onDelete(props.active);}
      else if(e.code==='Space'){e.preventDefault();e.stopPropagation();space.current=true;setHand(true);}
      else if(['=','+','-','0','1','2'].includes(e.key)){e.preventDefault();e.stopPropagation();if(e.key==='1')fit(true);else if(e.key==='2')fit(false);else zoom(e.key==='0'?1/view.zoom:e.key==='-'?.8:1.25);}
      else if(e.key==='Escape'){end(true);props.onBlank();e.stopPropagation();}
    }} onKeyUp={e=>{if(e.code==='Space'){space.current=false;setHand(false);e.stopPropagation();}}}>
    <div className="study-canvas-world" style={{transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`}}>
      {props.scenes.map(s=>{const g=drag?.kind==='move'&&drag.id===s.id?drag:null;return <section key={s.id} data-scene-id={s.id} role="group" aria-label={`Scene ${s.name}`} tabIndex={0}
        className={`study-board-card ${props.active===s.id?'selected':''}`} style={{left:s.x+(g?.dx||0),top:s.y+(g?.dy||0)}}
        onFocus={e=>{if(e.target===e.currentTarget)props.onSelect(s);}}
        onPointerDown={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label'))begin(e,s);}}
        onDoubleClick={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label'))fit(false);}}>
        <SceneName name={s.name} label={`Scene name on board: ${s.name}`} className="study-board-title" onSelect={()=>props.onSelect(s)} onRename={name=>props.onRename(s.id,name)} onFinish={()=>port.current?.focus({preventScroll:true})}/>
        {props.references(s)}{props.takes(s)}
      </section>;})}
    </div>
    <div className="study-canvas-tools" onPointerDown={e=>e.stopPropagation()}><button aria-label="Zoom out board" title="Zoom out" onClick={()=>zoom(.8)}>−</button><button className="mono" aria-label="Reset board zoom" title="100%" onClick={()=>zoom(1/view.zoom)}>{Math.round(view.zoom*100)}%</button><button aria-label="Zoom in board" title="Zoom in" onClick={()=>zoom(1.25)}>+</button><button aria-label="Fit board" title="Fit all scenes (1)" disabled={!props.scenes.length} onClick={()=>fit(true)}><Icon name="fit" size={14}/></button><button aria-label="Focus selected scene" title="Focus selected scene (2)" disabled={!props.active} onClick={()=>fit(false)}><Icon name="guides" size={14}/></button></div>
  </div>;
}
