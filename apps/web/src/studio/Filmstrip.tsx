// Timeline filmstrip: thumbnails of the project's source video, aligned to the arrangement's time axis.
// Client-side only: one offscreen <video> seeks per thumbnail, frames go to a small canvas cache (keyed by frame),
// and only the slots in view are requested. Under a reframe crop each thumb shows the cropped window.
import {useEffect,useRef} from 'react';
import type {CropData} from '../types';
import {cropAt} from '../geometry';
import {proxyPath} from '../renderer';

const CACHE_MAX=900;
type Thumb={f:number;c:HTMLCanvasElement};

export function Filmstrip({src,fps,aspect,crop,pps,bodyW,height,viewLeft,viewWidth,duration,offset=0,cropOffset=0}:{
  src?:string;fps:number;aspect:number;crop?:CropData;pps:number;bodyW:number;height:number;viewLeft:number;viewWidth:number;duration?:number;offset?:number;cropOffset?:number;
}){
  const canvas=useRef<HTMLCanvasElement>(null);
  const cache=useRef(new Map<number,Thumb>());const video=useRef<HTMLVideoElement|null>(null);const ready=useRef<Promise<boolean>>();
  const gen=useRef(0);
  const tw=Math.max(12,Math.round(height*aspect));

  // One offscreen video per source: the half-size preview proxy when the server has made one (seeks ~17 ms instead of
  // ~100 ms; 46 px thumbs never need more), else the original.
  useEffect(()=>{cache.current.clear();if(!src){video.current=null;ready.current=undefined;return;}
    const v=document.createElement('video');v.muted=true;v.playsInline=true;v.preload='auto';v.crossOrigin='anonymous';
    const proxy=proxyPath(src);let fallback=proxy!==src;
    ready.current=new Promise(res=>{v.onloadeddata=()=>res(true);v.onerror=()=>{if(fallback){fallback=false;v.src=src;v.load();}else res(false);};});v.src=proxy;v.load();video.current=v;
    return()=>{v.removeAttribute('src');v.load();video.current=null;};
  },[src]);
  useEffect(()=>{cache.current.clear();},[crop]);

  // Visible slots → paint what is cached (nearest frame as a stand-in), then fetch the missing ones left to right.
  useEffect(()=>{const c=canvas.current;if(!c)return;const my=++gen.current;
    const dpr=Math.min(2,window.devicePixelRatio||1);const w=Math.max(1,Math.min(viewWidth,bodyW-viewLeft,4096));
    const sourceX=offset*pps,first=Math.max(0,Math.floor((viewLeft-sourceX)/tw)),last=Math.ceil((viewLeft+w-sourceX)/tw);
    const sourceW=Math.min(bodyW,sourceX+(duration??Infinity)*pps);
    const slots:{x:number;f:number}[]=[];for(let i=first;i<=last;i++){const x=sourceX+i*tw;if(x>=sourceW)break;slots.push({x,f:Math.round((i*tw+tw/2)/pps*fps)});}
    const paint=()=>{if(gen.current!==my)return;if(c.width!==Math.round(w*dpr)||c.height!==Math.round(height*dpr)){c.width=Math.round(w*dpr);c.height=Math.round(height*dpr);}
      c.style.width=`${w}px`;c.style.height=`${height}px`;c.style.left=`${viewLeft}px`;
      const g=c.getContext('2d')!;g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,w,height);
      const all=[...cache.current.values()];
      for(const s of slots){let t=cache.current.get(s.f);if(!t&&all.length){let bd=Infinity;for(const a of all){const d=Math.abs(a.f-s.f);if(d<bd){bd=d;t=a;}}}
        if(t)g.drawImage(t.c,s.x-viewLeft,0,Math.min(tw,sourceW-s.x),height);}
    };
    paint();
    const missing=slots.filter(s=>!cache.current.has(s.f));if(!missing.length||!ready.current)return;
    let live=true;
    (async()=>{if(!(await ready.current))return;const v=video.current;if(!v)return;
      for(const s of missing){if(!live||gen.current!==my)return;
        const t=Math.min(Math.max(0,s.f/fps),Math.max(0,v.duration-.05));
        try{await new Promise<void>((res,rej)=>{const to=setTimeout(()=>rej(new Error('seek')),4000);v.onseeked=()=>{clearTimeout(to);res();};v.currentTime=t;});}catch{continue;}
        const th=document.createElement('canvas');th.width=Math.round(tw*dpr);th.height=Math.round(height*dpr);const g=th.getContext('2d')!;
        const vw=v.videoWidth,vh=v.videoHeight;const cr=cropAt(crop,s.f+Math.round(cropOffset*fps));
        let sx=0,sy=0,sw=vw,sh=vh;if(cr){sx=cr.x*vw;sy=cr.y*vh;sw=cr.w*vw;sh=cr.h*vh;}
        // Cover-fit the (cropped) frame into the thumb.
        const want=th.width/th.height;if(sw/sh>want){const nw=sh*want;sx+=(sw-nw)/2;sw=nw;}else{const nh=sw/want;sy+=(sh-nh)/2;sh=nh;}
        try{g.drawImage(v,sx,sy,sw,sh,0,0,th.width,th.height);}catch{continue;}
        cache.current.set(s.f,{f:s.f,c:th});if(cache.current.size>CACHE_MAX){const k=cache.current.keys().next().value;if(k!==undefined)cache.current.delete(k);}
        paint();}
    })();
    return()=>{live=false;};
  },[src,fps,tw,pps,bodyW,height,viewLeft,viewWidth,crop,duration,offset,cropOffset]);// eslint-disable-line react-hooks/exhaustive-deps

  return <canvas ref={canvas} className="tl-filmcanvas" aria-hidden="true"/>;
}
