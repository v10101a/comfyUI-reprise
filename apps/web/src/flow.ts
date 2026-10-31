import type {CropFrame,Point} from './types';
import {drawMapped} from './geometry';

/** analysis/flow.json (TypesetFlowField): per frame f the motion f-1→f on a cols×rows grid, normalized to the
 *  frame (dx/W, dy/H), int8-quantized against `scale`, base64 per frame. */
export type FlowDoc = {fps:number;cols:number;rows:number;scale:number;frames:string[]};

/**
 * Motion field, split in two:
 *  - camera: the median motion of the frame. The type drifts with the shot and settles back (inertia), so it
 *    feels like it floats in the space instead of being stuck to the glass.
 *  - local: what moves against the camera (a dancer's arm, a spin). It pushes the type like liquid around the
 *    body and leaves a short trail. Both are smoothed over neighbouring frames so the type glides, never twitches.
 * Deterministic per frame (sums over nearby frames, no simulation state), so seeks, exports and previews agree.
 */
export class FlowField {
  readonly cols:number;readonly rows:number;readonly fps:number;private doc:FlowDoc;
  private raw=new Map<number,{grid:Float32Array;cam:Point}>();private local=new Map<number,Float32Array>();private smoothed=new Map<number,Float32Array>();
  constructor(doc:FlowDoc){this.doc=doc;this.cols=doc.cols;this.rows=doc.rows;this.fps=doc.fps;}
  get frames(){return this.doc.frames.length;}
  private decode(f:number){
    if(f<0||f>=this.doc.frames.length)return undefined;let r=this.raw.get(f);
    if(!r){const bin=atob(this.doc.frames[f]);const k=this.doc.scale/127;const g=new Float32Array(bin.length);
      for(let i=0;i<bin.length;i++){const b=bin.charCodeAt(i);g[i]=(b>127?b-256:b)*k;}
      const med=(c:number)=>{const v:number[]=[];for(let i=c;i<g.length;i+=2)v.push(g[i]);v.sort((a,b)=>a-b);return v[v.length>>1]||0;};
      r={grid:g,cam:[med(0),med(1)]};cap(this.raw,f,r);}
    return r;
  }
  /** Camera motion of frame f, averaged over ±2 frames (normalized units per frame). */
  camera(f:number):Point{let x=0,y=0,n=0;for(let k=-2;k<=2;k++){const r=this.decode(f+k);if(!r)continue;x+=r.cam[0];y+=r.cam[1];n++;}return n?[x/n,y/n]:[0,0];}
  /** Decayed camera motion: how far the shot has carried the type and not yet let go. */
  drift(f:number,span=16,decay=.86):Point{let x=0,y=0,w=1;for(let i=0;i<span;i++){const [a,b]=this.camera(f-i);x+=a*w;y+=b*w;w*=decay;}return [x,y];}
  /** Motion against the camera, blurred in space. */
  private localGrid(f:number){
    let g=this.local.get(f);if(g)return g;const r=this.decode(f);if(!r)return undefined;
    g=new Float32Array(r.grid.length);for(let i=0;i<g.length;i+=2){g[i]=r.grid[i]-r.cam[0];g[i+1]=r.grid[i+1]-r.cam[1];}
    blur2(g,this.cols,this.rows,BLUR);cap(this.local,f,g);return g;
  }
  /** Local motion averaged over ±2 frames (gaussian weights): the field the type reacts to. */
  grid(f:number):Float32Array|undefined{
    let g=this.smoothed.get(f);if(g)return g;let w=0;
    for(let k=-2;k<=2;k++){const l=this.localGrid(f+k);if(!l)continue;const gk=Math.exp(-k*k/2);if(!g)g=new Float32Array(l.length);for(let i=0;i<l.length;i++)g[i]+=l[i]*gk;w+=gk;}
    if(!g)return undefined;for(let i=0;i<g.length;i++)g[i]/=w;cap(this.smoothed,f,g);return g;
  }
  /** Bilinear sample of the smoothed local field at source-normalized (x, y). */
  at(f:number,x:number,y:number):Point{
    const g=this.grid(f);if(!g)return [0,0];const C=this.cols,R=this.rows;
    const gx=Math.min(C-1,Math.max(0,x*C-.5)),gy=Math.min(R-1,Math.max(0,y*R-.5));
    const x0=Math.floor(gx),y0=Math.floor(gy),x1=Math.min(C-1,x0+1),y1=Math.min(R-1,y0+1),fx=gx-x0,fy=gy-y0;
    const v=(i:number,j:number,c:number)=>g[(j*C+i)*2+c];
    const s=(c:number)=>(v(x0,y0,c)*(1-fx)+v(x1,y0,c)*fx)*(1-fy)+(v(x0,y1,c)*(1-fx)+v(x1,y1,c)*fx)*fy;
    return [s(0),s(1)];
  }
  /** Decayed local motion: how far movement through (x, y) has pushed whatever sits there. */
  push(f:number,x:number,y:number,span=14,decay=.84):Point{
    let dx=0,dy=0,w=1;for(let i=0;i<span;i++){const [a,b]=this.at(f-i,x,y);dx+=a*w;dy+=b*w;w*=decay;}return [dx,dy];
  }
}
/** Cells of spatial smoothing: the type flows like liquid around a body instead of tearing at its edge. */
const BLUR=3;
function cap<K,V>(m:Map<K,V>,k:K,v:V){if(m.size>128)m.delete(m.keys().next().value!);m.set(k,v);}
/** Separable box blur, two passes (≈ gaussian), of an interleaved 2-channel grid in place; edges clamped. */
function blur2(g:Float32Array,C:number,R:number,r:number){
  const t=new Float32Array(g.length);
  for(let pass=0;pass<2;pass++){
    for(let y=0;y<R;y++)for(let x=0;x<C;x++)for(let c=0;c<2;c++){let s=0;for(let k=-r;k<=r;k++)s+=g[(y*C+Math.min(C-1,Math.max(0,x+k)))*2+c];t[(y*C+x)*2+c]=s/(2*r+1);}
    for(let y=0;y<R;y++)for(let x=0;x<C;x++)for(let c=0;c<2;c++){let s=0;for(let k=-r;k<=r;k++)s+=t[(Math.min(R-1,Math.max(0,y+k))*C+x)*2+c];g[(y*C+x)*2+c]=s/(2*r+1);}
  }
}

export type MotionOpts = {
  /** 0..1 look-level amount; 0 = off. */
  amount:number;
  /** Output size in px and the field frame for this output frame. */
  width:number;height:number;frame:number;
  /** Reframed projects: the source crop for this frame (output uv → source uv). */
  crop?:CropFrame;
  /** Mesh resolution (cells per side) and trail copies; lower for scrubbing. */
  mesh?:number;trail?:number;
};

/** Draw `src` (the text layer) into `ctx`: carried by the camera with inertia, pushed like liquid by what moves
 *  through it, with a short soft trail along the current motion. */
export function drawMotion(ctx:CanvasRenderingContext2D,src:HTMLCanvasElement,field:FlowField,o:MotionOpts){
  const {amount,width:W,height:H,frame:f,crop:c}=o;const n=o.mesh??20,K=o.trail??4;
  const toSrc=(u:number,v:number):Point=>c?[c.x+u*c.w,c.y+v*c.h]:[u,v];
  const sx=c?1/c.w:1,sy=c?1/c.h:1;
  const capD=.06*Math.min(W,H),soft=(d:number)=>capD*Math.tanh(d/capD);
  const [cx,cy]=field.drift(f);const ddx=soft(cx*sx*W*1.5*amount),ddy=soft(cy*sy*H*1.5*amount);
  // Push ~2.2× the decayed local motion, trail ~3 frames of it; both soft-capped so fast moves bend, never tear.
  const pushGain=2.2*amount,trailGain=3*amount,capP=.05*H*Math.max(.3,amount),softP=(d:number)=>capP*Math.tanh(d/capP);
  const disp:Point[][]=[],vel:Point[][]=[];
  for(let j=0;j<=n;j++){disp.push([]);vel.push([]);for(let i=0;i<=n;i++){
    const [x,y]=toSrc(i/n,j/n);const [px,py]=field.push(f,x,y);const [vx,vy]=field.at(f,x,y);
    disp[j].push([ddx+softP(px*sx*W*pushGain),ddy+softP(py*sy*H*pushGain)]);vel[j].push([softP(vx*sx*W*trailGain),softP(vy*sy*H*trailGain)]);}}
  const map=(k:number)=>(u:number,v:number):Point=>{const i=Math.round(u*n),j=Math.round(v*n);const [dx,dy]=disp[j][i],[tx,ty]=vel[j][i];
    return [u*W+dx-tx*k,v*H+dy-ty*k];};
  ctx.save();
  for(let k=K;k>=1;k--){ctx.globalAlpha=.3*(1-k/(K+1))*Math.min(1,amount*1.5);drawMapped(ctx,src,map(k/K),n);}
  ctx.globalAlpha=1;drawMapped(ctx,src,map(0),n);
  ctx.restore();
}
