import {useEffect,useState} from 'react';

/** Commit once on blur/Enter, so typing a new duration is one undo step. */
export function DurationInput({value,label,onChange}:{value:number;label:string;onChange:(seconds:number)=>void}){
  const [text,setText]=useState(value.toFixed(2));
  useEffect(()=>setText(value.toFixed(2)),[value]);
  return <input className="duration-input mono" type="number" min="0.01" step="0.1" aria-label={label}
    value={text} onChange={e=>setText(e.target.value)}
    onBlur={()=>{const next=Number(text);if(Number.isFinite(next)&&next>0&&Math.abs(next-Number(value.toFixed(2)))>.0001)onChange(next);setText(value.toFixed(2));}}
    onKeyDown={e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();e.currentTarget.blur();}
      if(e.key==='Escape'){e.preventDefault();e.currentTarget.value=value.toFixed(2);setText(value.toFixed(2));}}}/>;
}
