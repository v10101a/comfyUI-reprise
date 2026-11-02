import {useEffect,useRef,useState} from 'react';
import type {Asset,Project} from '../types';
import {assetUrl} from '../api';

const posters=new Map<string,string>();
/** Board frames outside the viewport should not open dozens of video decoders. */
export function SceneThumb({project,asset}:{project:Project;asset:Asset}){
  const url=assetUrl(project,asset.path),host=useRef<HTMLSpanElement>(null);
  const [visible,setVisible]=useState(false),[poster,setPoster]=useState(()=>posters.get(url));
  useEffect(()=>{setPoster(posters.get(url));const el=host.current;if(!el)return;
    const observer=new IntersectionObserver(entries=>setVisible(entries.some(e=>e.isIntersecting)),{rootMargin:'80px'});observer.observe(el);return()=>observer.disconnect();
  },[url]);
  const capture=(v:HTMLVideoElement)=>{if(!v.videoWidth||v.readyState<2)return;
    try{const c=document.createElement('canvas');c.width=240;c.height=Math.max(1,Math.round(240*v.videoHeight/v.videoWidth));c.getContext('2d')!.drawImage(v,0,0,c.width,c.height);
      const image=c.toDataURL('image/jpeg',.8);if(posters.size>=256)posters.delete(posters.keys().next().value!);posters.set(url,image);setPoster(image);
    }catch{/* Cross-origin references can still display as video. */}
  };
  return <span className="as-thumb scene-thumb" ref={host}>
    {asset.kind==='image'?<img src={url} alt="" draggable={false} loading="lazy"/>:poster?<img src={poster} alt="" draggable={false}/>:
      visible?<video src={url} muted playsInline preload="auto" onLoadedMetadata={e=>{e.currentTarget.currentTime=Math.min(.5,(e.currentTarget.duration||1)/2);}} onSeeked={e=>capture(e.currentTarget)}/>:null}
  </span>;
}
