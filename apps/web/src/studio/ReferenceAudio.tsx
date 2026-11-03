import {useEffect,useRef,useState} from 'react';
import {Icon} from './icons';

/** Compact transport for the exact vocal window used by generation. */
export function ReferenceAudio({src,name,start=0,end}:{src:string;name:string;start?:number;end?:number}){
  const ref=useRef<HTMLAudioElement>(null),[playing,setPlaying]=useState(false),[at,setAt]=useState(start),[duration,setDuration]=useState(0),[failed,setFailed]=useState(false);
  const stop=end===undefined?duration:duration?Math.min(end,duration):end,length=Math.max(0,stop-start);
  useEffect(()=>{const a=ref.current;setPlaying(false);setAt(start);setFailed(false);if(a){a.pause();a.currentTime=start;}},[src,start,end]);
  const tick=()=>{const a=ref.current;if(!a)return;if(stop&&a.currentTime>=stop){a.pause();a.currentTime=start;}setAt(a.currentTime);};
  return <div className="wf-audio-transport" onKeyDown={e=>e.stopPropagation()}>
    <audio ref={ref} src={src} preload="metadata" onLoadedMetadata={e=>{setDuration(e.currentTarget.duration);e.currentTarget.currentTime=start;}} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onEnded={()=>{setPlaying(false);setAt(start);}} onTimeUpdate={tick} onError={()=>setFailed(true)}/>
    <button className="icon-sm" aria-label={`${playing?'Pause':'Play'} ${name}`} title={failed?'Audio unavailable':`${playing?'Pause':'Play'} ${name}`} disabled={failed} onClick={()=>{const a=ref.current;if(!a)return;if(playing)a.pause();else{if(a.currentTime<start||a.currentTime>=stop)a.currentTime=start;void a.play().catch(()=>setPlaying(false));}}}><Icon name={failed?'mute':playing?'pause':'play'} size={14}/></button>
    <input type="range" aria-label={`Seek ${name}`} min={start} max={stop||start+1} step="0.01" value={Math.max(start,Math.min(at,stop||start))} disabled={failed||!length} onChange={e=>{const t=Number(e.target.value);if(ref.current)ref.current.currentTime=t;setAt(t);}}/>
    <span className="mono" title={name}>{length?`${length.toFixed(1)}s`:'—'}</span>
  </div>;
}
