// Day / night toggle (viola.city's sun/moon). Sets data-theme on <html>; remembered per browser. Light by default.
import {useState} from 'react';

type Theme = 'light'|'dark';
const KEY='typeset-theme';
const read=():Theme=>{try{return localStorage.getItem(KEY)==='dark'?'dark':'light';}catch{return 'light';}};
const apply=(t:Theme)=>{document.documentElement.dataset.theme=t;};
if(typeof document!=='undefined')apply(read());

export function ThemeToggle(){
  const [theme,setTheme]=useState<Theme>(read);
  const flip=()=>{const t:Theme=theme==='dark'?'light':'dark';setTheme(t);apply(t);try{localStorage.setItem(KEY,t);}catch{/* private mode */}};
  return <button className="theme-toggle" onClick={flip} aria-label={theme==='dark'?'Switch to day':'Switch to night'} title={theme==='dark'?'day':'night'}>{theme==='dark'?'☾':'☀'}</button>;
}
