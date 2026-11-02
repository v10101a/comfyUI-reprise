import {useRef,useState} from 'react';

/** Rename commits once on Enter/blur; Escape restores the name without an undo entry. */
export function SceneName({name,label,className,onSelect,onRename,onFinish}:{name:string;label:string;className?:string;
  onSelect?:()=>void;onRename:(name:string)=>void;onFinish?:()=>void}){
  const [draft,setDraft]=useState(name),[editing,setEditing]=useState(false),cancel=useRef(false);
  return <input className={`study-scene-name-input ${className||''}`} aria-label={label} title="Rename scene" value={editing?draft:name}
    onPointerDown={e=>e.stopPropagation()} onClick={e=>e.stopPropagation()}
    onFocus={e=>{cancel.current=false;setDraft(name);setEditing(true);onSelect?.();e.currentTarget.select();}}
    onChange={e=>setDraft(e.target.value)}
    onBlur={()=>{const next=draft.trim();if(!cancel.current&&next&&next!==name)onRename(next);else setDraft(name);setEditing(false);cancel.current=false;}}
    onKeyDown={e=>{e.stopPropagation();if(e.nativeEvent.isComposing)return;
      if(e.key==='Enter'){e.preventDefault();e.currentTarget.blur();onFinish?.();}
      else if(e.key==='Escape'){e.preventDefault();cancel.current=true;setDraft(name);e.currentTarget.blur();onFinish?.();}
    }} onKeyUp={e=>e.stopPropagation()}/>
}
