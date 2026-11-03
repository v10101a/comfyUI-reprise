import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {sceneHeight as height,type Scene} from './scenes';
import type {BoardView} from './board';
import {boardPoint} from './board';
import {Icon} from './icons';
import {SceneName} from './SceneName';

type Point={x:number;y:number};
type Props={scenes:Scene[];active:string;selection:string[];onSelection:(ids:string[])=>void;view:BoardView|null;onView:(v:BoardView)=>void;
  onSelect:(s:Scene)=>void;onMove:(positions:{id:string;x:number;y:number}[])=>void;onBlank:()=>void;onKeyDown:(e:React.KeyboardEvent)=>void;
  onRename:(id:string,name:string)=>void;onCombine:(target:string,ids:string[],name:string)=>void;
  onCollapse:(s:Scene)=>void;dropTarget:string;dropProps:(s:Scene)=>React.HTMLAttributes<HTMLElement>;
  onTakeMove:(id:string,target:string,point?:Point)=>void;references:(s:Scene)=>ReactNode;takes:(s:Scene)=>ReactNode};
type Gesture={kind:'pan'|'move'|'box';px:number;py:number;view:BoardView;dx:number;dy:number;moved:boolean;
  before:{id:string;x:number;y:number}[];selected:string[];start:Point;point:Point;merge?:string};
const W=270,TAKE_MIME='application/x-typeset-scene-take';
const zoomAt=(v:BoardView,x:number,y:number,factor:number)=>{
  const zoom=Math.max(.1,Math.min(4,v.zoom*factor)),pt=boardPoint({x,y},v);return {zoom,x:x-pt.x*zoom,y:y-pt.y*zoom};
};

/** Scene frames are directly selectable, movable and combinable; blank drags marquee-select. */
export function SceneCanvas(props:Props){
  const port=useRef<HTMLDivElement>(null),gesture=useRef<Gesture|null>(null),space=useRef(false),nativeDragging=useRef(false);
  const [drag,setDrag]=useState<Gesture|null>(null),[hand,setHand]=useState(false),[editing,setEditing]=useState(''),[newAt,setNewAt]=useState<Point|null>(null);
  const live=useRef(props);live.current=props;
  const view=props.view||{x:16,y:32,zoom:.8},viewRef=useRef(view);viewRef.current=view;
  const fit=(all:boolean)=>{
    const el=port.current;if(!el)return;const ss=all?live.current.scenes:live.current.scenes.filter(s=>s.id===live.current.active);if(!ss.length)return;
    const x=Math.min(...ss.map(s=>s.x)),y=Math.min(...ss.map(s=>s.y))-32,w=Math.max(...ss.map(s=>s.x+W))-x,h=Math.max(...ss.map(s=>s.y+height(s)))-y;
    const zoom=Math.max(.1,Math.min(all?1:1.2,(el.clientWidth-40)/w,(el.clientHeight-72)/h));live.current.onView({x:(el.clientWidth-w*zoom)/2-x*zoom,y:24-y*zoom,zoom});
  };
  useLayoutEffect(()=>{if(!props.view)fit(false);},[]);
  useEffect(()=>{if(gesture.current||nativeDragging.current)return;const s=props.scenes.find(s=>s.id===props.active),el=port.current;if(!s||!el)return;const v=viewRef.current;
    if(s.x*v.zoom+v.x<0||(s.x+W)*v.zoom+v.x>el.clientWidth||s.y*v.zoom+v.y<24||s.y*v.zoom+v.y>el.clientHeight-80)fit(false);
  },[props.active]);
  useEffect(()=>{const el=port.current;if(!el)return;
    const wheel=(e:WheelEvent)=>{e.preventDefault();e.stopPropagation();if(gesture.current)return;const v=viewRef.current,r=el.getBoundingClientRect(),unit=e.deltaMode===1?16:e.deltaMode===2?el.clientHeight:1;
      live.current.onView(e.ctrlKey||e.metaKey?zoomAt(v,e.clientX-r.left,e.clientY-r.top,Math.exp(-e.deltaY*unit*.008)):{...v,x:v.x-e.deltaX*unit,y:v.y-e.deltaY*unit});};
    el.addEventListener('wheel',wheel,{passive:false});
    const release=(e:KeyboardEvent)=>{if(e.code==='Space'){space.current=false;setHand(false);}};
    const blur=()=>{space.current=false;setHand(false);gesture.current=null;setDrag(null);};
    window.addEventListener('blur',blur);window.addEventListener('keyup',release);
    return()=>{el.removeEventListener('wheel',wheel);window.removeEventListener('blur',blur);window.removeEventListener('keyup',release);};
  },[]);
  const point=(x:number,y:number,v=viewRef.current)=>{const r=port.current!.getBoundingClientRect();return boardPoint({x:x-r.left,y:y-r.top},v);};
  const begin=(e:React.PointerEvent,s?:Scene)=>{
    if(e.button!==0&&e.button!==1)return;e.preventDefault();e.stopPropagation();port.current?.focus({preventScroll:true});
    const pan=space.current||e.button===1,v=viewRef.current,start=point(e.clientX,e.clientY,v);
    let selected=props.selection;
    if(!pan&&s){
      if(e.shiftKey||e.metaKey||e.ctrlKey){props.onSelection(selected.includes(s.id)?selected.filter(id=>id!==s.id):[...selected,s.id]);props.onBlank();return;}
      if(!selected.includes(s.id))selected=[s.id];props.onSelection(selected);props.onSelect(s);
    }
    const g:Gesture={kind:pan?'pan':s?'move':'box',px:e.clientX,py:e.clientY,view:v,dx:0,dy:0,moved:false,start,point:start,
      selected:e.shiftKey?selected:[],before:props.scenes.filter(s=>selected.includes(s.id)).map(s=>({id:s.id,x:s.x,y:s.y}))};
    gesture.current=g;setDrag(g);e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move=(e:React.PointerEvent)=>{const g=gesture.current;if(!g)return;
    const dx=e.clientX-g.px,dy=e.clientY-g.py,pt=point(e.clientX,e.clientY,g.view);
    const n:Gesture={...g,dx:dx/g.view.zoom,dy:dy/g.view.zoom,point:pt,moved:g.moved||Math.hypot(dx,dy)>4,merge:undefined};
    if(g.kind==='pan')props.onView({...g.view,x:g.view.x+dx,y:g.view.y+dy});
    else if(g.kind==='box'&&n.moved){const x=Math.min(g.start.x,pt.x),y=Math.min(g.start.y,pt.y),right=Math.max(g.start.x,pt.x),bottom=Math.max(g.start.y,pt.y);
      props.onSelection([...new Set([...g.selected,...props.scenes.filter(s=>s.x<right&&s.x+W>x&&s.y-32<bottom&&s.y+height(s)>y).map(s=>s.id)])]);
    }else if(g.kind==='move'&&n.moved){
      n.merge=props.scenes.find(s=>!g.before.some(b=>b.id===s.id)&&pt.x>s.x+20&&pt.x<s.x+W-20&&pt.y>s.y+12&&pt.y<s.y+height(s)-12)?.id;
    }
    gesture.current=n;setDrag(n);
  };
  const end=(cancel=false)=>{const g=gesture.current;if(!g)return;gesture.current=null;setDrag(null);
    if(cancel){if(g.kind==='pan')props.onView(g.view);if(g.kind==='box')props.onSelection(g.selected);return;}
    if(g.kind==='move'&&g.moved){const target=props.scenes.find(s=>s.id===g.merge);
      if(target){props.onCombine(target.id,g.before.map(s=>s.id),target.name);props.onSelection([target.id]);}
      else props.onMove(g.before.map(s=>({...s,x:s.x+g.dx,y:s.y+g.dy})));
    }else if(g.kind==='box'&&!g.moved){props.onSelection([]);props.onBlank();}
  };
  const zoom=(factor:number)=>{const r=port.current!.getBoundingClientRect();props.onView(zoomAt(viewRef.current,r.width/2,r.height/2,factor));};
  const finishName=()=>{setEditing('');port.current?.focus({preventScroll:true});};
  return <div ref={port} className={`study-canvas ${hand?'hand':''} ${drag?'dragging':''}`} role="region" aria-label="Scene board canvas" tabIndex={0}
    data-x={view.x} data-y={view.y} data-zoom={view.zoom} title="Drag to select · Shift-click to add · Space-drag to pan · drop a scene onto another to combine"
    onPointerDownCapture={e=>{if(e.button===1||space.current)begin(e);}}
    onPointerDown={e=>{if(!(e.target as Element).closest('.study-board-card,.study-canvas-tools'))begin(e);}}
    onPointerMove={move} onPointerUp={()=>end()} onPointerCancel={()=>end(true)}
    onDragStartCapture={()=>{nativeDragging.current=true;}}
    onDragOver={e=>{if(!e.dataTransfer.types.includes(TAKE_MIME)||(e.target as Element).closest('.study-board-card'))return;e.preventDefault();e.dataTransfer.dropEffect='move';setNewAt(point(e.clientX,e.clientY));}}
    onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node|null))setNewAt(null);}}
    onDrop={e=>{const id=e.dataTransfer.getData(TAKE_MIME);if(id&&!(e.target as Element).closest('.study-board-card')){e.preventDefault();e.stopPropagation();props.onTakeMove(id,'@new',point(e.clientX,e.clientY));}setNewAt(null);}}
    onDragEnd={()=>{nativeDragging.current=false;setNewAt(null);}}
    onKeyDown={e=>{if((e.target as Element).closest('input,textarea,select'))return;
      props.onKeyDown(e);if(e.defaultPrevented)return;
      if(e.code==='Space'){e.preventDefault();e.stopPropagation();space.current=true;setHand(true);}
      else if(['=','+','-','0','1','2'].includes(e.key)){e.preventDefault();e.stopPropagation();if(e.key==='1')fit(true);else if(e.key==='2')fit(false);else zoom(e.key==='0'?1/view.zoom:e.key==='-'?.8:1.25);}
      else if(e.key==='Enter'&&props.selection.length===1){e.preventDefault();e.stopPropagation();setEditing(props.selection[0]);}
      else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();end(true);props.onSelection([]);props.onBlank();}
    }} onKeyUp={e=>{if(e.code==='Space'){space.current=false;setHand(false);e.stopPropagation();}}}>
    <div className="study-canvas-world" style={{transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`}}>
      {props.scenes.map(s=>{const moved=drag?.kind==='move'&&drag.before.some(b=>b.id===s.id),merge=drag?.merge===s.id;return <section key={s.id} data-scene-id={s.id} role="group" aria-label={`Scene ${s.name}`} tabIndex={0}
        {...props.dropProps(s)} className={`study-board-card ${props.selection.includes(s.id)?'selected':''} ${s.collapsed?'collapsed':''} ${props.dropTarget===s.id||merge?'scene-drop-take':''} ${moved?'scene-moving':''}`}
        style={{left:s.x+(moved?drag.dx:0),top:s.y+(moved?drag.dy:0)}}
        onFocus={e=>{if(e.target===e.currentTarget){props.onSelection([s.id]);props.onSelect(s);}}}
        onPointerDown={e=>{if(!(e.target as Element).closest('button,input,textarea,select,label'))begin(e,s);}}>
        {editing===s.id?<SceneName name={s.name} label={`Scene name on board: ${s.name}`} className="study-board-title" autoFocus onRename={name=>props.onRename(s.id,name)} onFinish={finishName}/>:
          <button className="study-board-title scene-title" aria-label={`Select scene ${s.name}`} title="Drag scene · double-click to rename" onPointerDown={e=>begin(e,s)} onDoubleClick={()=>setEditing(s.id)}
            onClick={e=>{if(e.detail===0){props.onSelection([s.id]);props.onSelect(s);}}}>{s.name}</button>}
        <button className="scene-collapse icon-sm" aria-label={`${s.collapsed?'Expand':'Collapse'} scene ${s.name}`} title={s.collapsed?'Expand scene':'Collapse scene'} aria-expanded={!s.collapsed} onClick={()=>{props.onCollapse(s);port.current?.focus({preventScroll:true});}}>{s.collapsed?'›':'⌄'}</button>
        {merge&&<span className="scene-drop-label">Release to combine</span>}
        {s.collapsed?<div className="scene-collapsed-summary">{s.takes.length} takes <span>· {s.refs.length} references</span></div>:<>{props.references(s)}{props.takes(s)}{!s.refs.length&&!s.takes.length&&<div className="scene-empty-card">Drop takes here</div>}</>}
      </section>;})}
      {drag?.kind==='box'&&drag.moved&&<div className="scene-marquee" style={{left:Math.min(drag.start.x,drag.point.x),top:Math.min(drag.start.y,drag.point.y),width:Math.abs(drag.point.x-drag.start.x),height:Math.abs(drag.point.y-drag.start.y)}}/>}
      {newAt&&<div className="scene-new-drop" style={{left:newAt.x,top:newAt.y}}>New scene</div>}
    </div>
    <div className="study-canvas-tools" onPointerDown={e=>e.stopPropagation()}><button aria-label="Zoom out board" title="Zoom out" onClick={()=>zoom(.8)}>−</button><button className="mono" aria-label="Reset board zoom" title="100%" onClick={()=>zoom(1/view.zoom)}>{Math.round(view.zoom*100)}%</button><button aria-label="Zoom in board" title="Zoom in" onClick={()=>zoom(1.25)}>+</button><button aria-label="Fit board" title="Fit all scenes (1)" disabled={!props.scenes.length} onClick={()=>fit(true)}><Icon name="fit" size={14}/></button><button aria-label="Focus selected scene" title="Focus selected scene (2)" disabled={!props.active} onClick={()=>fit(false)}><Icon name="guides" size={14}/></button></div>
  </div>;
}
