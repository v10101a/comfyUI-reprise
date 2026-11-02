// SCHEMA v2 §B — occupancy grids and deterministic auto-placement of caption lines.
import type {Occupancy,Tracks,CropData} from './types';
import {cropAt} from './geometry';

/** One frame of occupancy in OUTPUT space: cols×rows, row-major, values 0..1 (fraction covered by the subject). */
export type Grid = {cols:number;rows:number;data:Float32Array};
export type SourceMapping={frame:(f:number)=>number|undefined;point:(f:number,x:number,y:number)=>[number,number]};

function decode(b64:string){const s=atob(b64);const out=new Uint8Array(s.length);for(let i=0;i<s.length;i++)out[i]=s.charCodeAt(i);return out;}

/**
 * Supplies per-frame occupancy in output space. Source priority: analysis/occupancy.json (server or fixture),
 * else a coarse grid rasterised from tracks.json bboxes. With a crop, source grids are resampled through the window.
 */
export class OccupancySource {
  private cache=new Map<number,Grid|undefined>();private raw=new Map<number,Uint8Array>();
  readonly kind:'occupancy'|'tracks'|'none';
  constructor(private occ:Occupancy|undefined,private tracks:Tracks|undefined,private fps:number,private crop?:CropData,private outPortrait=false,private mapping?:SourceMapping){
    this.kind=occ?.frames.length?'occupancy':tracks?.tracks.length?'tracks':'none';
  }
  private sourceAt(frame:number):((x:number,y:number)=>number)|undefined{
    if(this.kind==='occupancy'){
      const o=this.occ!;const i=Math.max(0,Math.min(o.frames.length-1,Math.floor(Math.round(frame*o.fps/this.fps)/Math.max(1,o.step))));
      let bytes=this.raw.get(i);if(!bytes){bytes=decode(o.frames[i]);this.raw.set(i,bytes);}
      const b=bytes;return (x,y)=>{const c=Math.min(o.cols-1,Math.max(0,Math.floor(x*o.cols))),r=Math.min(o.rows-1,Math.max(0,Math.floor(y*o.rows)));return b[r*o.cols+c]/255;};
    }
    if(this.kind==='tracks'){
      const tf=Math.round(frame*this.tracks!.fps/this.fps);
      const boxes=this.tracks!.tracks.map(t=>{let best;for(const p of t.frames){if(p.f<=tf&&tf-p.f<=6)best=p;if(p.f>tf)break;}return best?.bbox;}).filter(Boolean) as number[][];
      // A person's bbox is not solid: approximate the silhouette as ~70% coverage, heavier at the torso.
      return (x,y)=>{let v=0;for(const [bx,by,bw,bh] of boxes)if(x>=bx&&x<=bx+bw&&y>=by&&y<=by+bh)v=Math.max(v,.7);return v;};
    }
    return undefined;
  }
  at(frame:number):Grid|undefined{
    if(this.cache.has(frame))return this.cache.get(frame);
    const sourceFrame=this.mapping?this.mapping.frame(frame):frame;
    const src=sourceFrame==null?undefined:this.sourceAt(sourceFrame);let grid:Grid|undefined;
    if(src){
      const cols=this.outPortrait?18:32,rows=this.outPortrait?32:18;const data=new Float32Array(cols*rows);const c=cropAt(this.crop,frame);
      // 3×3 supersample per output cell.
      for(let r=0;r<rows;r++)for(let k=0;k<cols;k++){let s=0;for(let a=0;a<3;a++)for(let b=0;b<3;b++){const ox=(k+(b+.5)/3)/cols,oy=(r+(a+.5)/3)/rows;
        const [x,y]=this.mapping?this.mapping.point(frame,ox,oy):c?[c.x+ox*c.w,c.y+oy*c.h]:[ox,oy];
        s+=this.mapping&&(x<0||x>1||y<0||y>1)?0:src(x,y);}data[r*cols+k]=s/9;}
      grid={cols,rows,data};
    }
    if(this.cache.size>400)this.cache.clear();
    this.cache.set(frame,grid);return grid;
  }
}

/** Summed-area table with an extra zero row/col; continuous coverage integral by bilinear interpolation (exact for piecewise-constant cells). */
class SAT {
  private s:Float64Array;private W:number;
  constructor(private g:Grid){const W=g.cols+1;this.W=W;this.s=new Float64Array(W*(g.rows+1));
    for(let r=0;r<g.rows;r++)for(let c=0;c<g.cols;c++)this.s[(r+1)*W+c+1]=g.data[r*g.cols+c]+this.s[r*W+c+1]+this.s[(r+1)*W+c]-this.s[r*W+c];}
  private F(x:number,y:number){const gx=Math.min(this.g.cols,Math.max(0,x*this.g.cols)),gy=Math.min(this.g.rows,Math.max(0,y*this.g.rows));
    const c0=Math.min(this.g.cols-1,Math.floor(gx)),r0=Math.min(this.g.rows-1,Math.floor(gy));const fx=gx-c0,fy=gy-r0;const W=this.W,s=this.s;
    const a=s[r0*W+c0],b=s[r0*W+c0+1],c=s[(r0+1)*W+c0],d=s[(r0+1)*W+c0+1];
    return a*(1-fx)*(1-fy)+b*fx*(1-fy)+c*(1-fx)*fy+d*fx*fy;}
  /** Mean occupancy over a normalized rectangle. */
  mean(x0:number,y0:number,x1:number,y1:number){const area=(x1-x0)*(y1-y0)*this.g.cols*this.g.rows;if(area<=0)return 0;return (this.F(x1,y1)-this.F(x0,y1)-this.F(x1,y0)+this.F(x0,y0))/area;}
}

export type LineRequest = {key:string;w:number;h:number;f0:number;f1:number;hint?:{x:number;y:number};tolerance:number;canPromote?:boolean;
  /** v3: keep the box centre ≥ avoidR (fraction of frame height) from an already-placed line (the hero). */
  avoidKey?:string;avoidR?:number;
  /** v3: prefer the four corners (stack layout); never shrink (hero bleeds instead). */
  corner?:boolean;noShrink?:boolean;
  /** v3: satellites — any subject coverage counts (blocked from 2%, fully at 12%). */
  strict?:boolean};
/** front: a behind line that could not be read anywhere is drawn in front of the subject instead (keep visible). */
export type LinePlacement = {cx:number;cy:number;scale:number;coverage:number;front?:boolean};
/** A box already on screen for frames [f0,f1] (normalized x0,y0,x1,y1). */
export type Placed = {box:[number,number,number,number];f0:number;f1:number};

const SAFE_X0=.045,SAFE_Y0=.055;const SCALES=[1,.86,.74,.62,.52];
// Coverage depends on footage, dimensions and time, not on other text. Keep bounded
// candidate grids across edits so dragging one line does not rescan every other line.
const coverageCache=new WeakMap<OccupancySource,Map<string,Float64Array>>();

/**
 * Choose one stable position (box centre, normalized) and scale for each line over its whole span.
 * Lines are placed in request order; boxes of earlier lines that overlap in time repel later ones.
 * Pure: same requests + same occupancy → same answer.
 */
export function autoPlace(reqs:LineRequest[],occ:OccupancySource,aspect:number,obstacles:Placed[]=[],safe:[number,number]=[.06,.06]):Map<string,LinePlacement>{
  let coverage=coverageCache.get(occ);if(!coverage){coverage=new Map();coverageCache.set(occ,coverage);}
  // Title-safe margins on every edge (≥6%, more under a lens warp: see geometry.ts:warpSafeMargins).
  const SAFE_X=Math.max(SAFE_X0,safe[0]),SAFE_Y=Math.max(SAFE_Y0,safe[1]);
  // obstacles: fixed-position text (HUD meta, subtitles, ensembles) that auto-placed lines must also avoid.
  const out=new Map<string,LinePlacement>();const placed:Placed[]=[...obstacles];
  const satCache=new Map<number,SAT|null>();
  const sat=(f:number)=>{if(!satCache.has(f)){const g=occ.at(f);satCache.set(f,g?new SAT(g):null);}return satCache.get(f)!;};
  for(const req0 of reqs){let req=req0;
    // Sample at most 24 frames evenly across the line span.
    const n=Math.max(1,Math.min(24,req.f1-req.f0+1));const frames:SAT[]=[];
    for(let i=0;i<n;i++){const s=sat(Math.round(req.f0+(req.f1-req.f0)*(n===1?0:i/(n-1))));if(s)frames.push(s);}
    // Readability loss = fraction of the line's length that is hidden: the box is cut into 8 vertical slices
    // (each a few glyphs); a slice counts as blocked from 10% coverage, fully blocked at 40%. Mean blends with the
    // worst frame so a line that is clean on average but swallowed for a moment still loses.
    const lo=req.strict?.02:.1,span=req.strict?.1:.3;
    const cov=(x0:number,y0:number,x1:number,y1:number)=>{if(!frames.length)return 0;let sum=0,max=0;const sw=(x1-x0)/8;
      for(const s of frames){let lost=0;for(let k=0;k<8;k++){const m=s.mean(x0+k*sw,y0,x0+(k+1)*sw,y1);lost+=Math.min(1,Math.max(0,(m-lo)/span));}lost/=8;sum+=lost;if(lost>max)max=lost;}
      return .5*sum/frames.length+.5*max;};
    const placeOne=(req:LineRequest,scales:number[])=>{
    let best:{score:number;p:LinePlacement}|undefined;
    for(const scale of scales){
      const w=Math.min(req.w*scale,1-2*SAFE_X),h=req.h*scale;let bestAtScale:{score:number;p:LinePlacement}|undefined;
      const ck=JSON.stringify([req0.f0,req0.f1,w,h,!!req0.strict,SAFE_X,SAFE_Y]);
      let grid=coverage!.get(ck);
      if(grid){coverage!.delete(ck);coverage!.set(ck,grid);}
      else{grid=new Float64Array(33*33).fill(NaN);coverage!.set(ck,grid);if(coverage!.size>128)coverage!.delete(coverage!.keys().next().value!);}
      for(let j=0;j<=32;j++){const cy=SAFE_Y+h/2+(1-2*SAFE_Y-h)*(j/32);if(h>1-2*SAFE_Y&&j>0)break;
        for(let i=0;i<=32;i++){const cx=SAFE_X+w/2+(1-2*SAFE_X-w)*(i/32);if(w>=1-2*SAFE_X-1e-6&&i>0)break;
          // Coverage of the whole box plus its core (the middle 60%, where glyphs are dense).
          const k=j*33+i;
          const c=Number.isNaN(grid[k])?(grid[k]=cov(cx-w/2,cy-h*.38,cx+w/2,cy+h*.38)):grid[k];
          let score=8*Math.max(0,c-req.tolerance)+.6*c;
          if(req.hint)score+=.9*Math.hypot((cx-req.hint.x)*aspect,cy-req.hint.y)/Math.max(1,aspect);
          else score+=.35*Math.min(Math.abs(cy-.80),Math.abs(cy-.2)+.03)+.08*Math.abs(cx-.5);
          for(const o of placed){if(o.f1<req.f0||o.f0>req.f1)continue;const m=.015,ix=Math.min(cx+w/2+m,o.box[2])-Math.max(cx-w/2-m,o.box[0]),iy=Math.min(cy+h/2+m,o.box[3])-Math.max(cy-h/2-m,o.box[1]);if(ix>0&&iy>0)score+=3*ix*iy/(w*h)+.5;}
          score+=.5*(1-scale);
          if(req.avoidKey){const o=out.get(req.avoidKey);if(o){const d=Math.hypot((cx-o.cx)*aspect,cy-o.cy);const r=req.avoidR??.3;if(d<r)score+=4*(1-d/r)+1;}}
          if(req.corner)score+=.6*Math.min(...[[0,0],[1,0],[0,1],[1,1]].map(([x,y])=>Math.hypot(cx-x,cy-y)));
          if(!bestAtScale||score<bestAtScale.score-1e-9)bestAtScale={score,p:{cx,cy,scale,coverage:c}};
        }}
      if(bestAtScale&&(!best||bestAtScale.score<best.score-1e-9))best=bestAtScale;
      // Stop shrinking once the line reads cleanly at this size.
      if(best&&best.p.coverage<=req.tolerance)break;
    }
    return best?.p;};
    let p:LinePlacement=placeOne(req,req.noShrink?[1]:SCALES)||{cx:req.hint?.x??.5,cy:req.hint?.y??.8,scale:1,coverage:0};
    if(req.canPromote&&p.coverage>req.tolerance+.12){
      // Nowhere readable behind the subject: keep the line visible in front, at full size, in the least intrusive spot.
      req={...req,canPromote:false,tolerance:1};const front=placeOne(req,[1]);if(front)p={...front,front:true};
    }
    const w=req.w*p.scale,h=req.h*p.scale;placed.push({box:[p.cx-w/2,p.cy-h/2,p.cx+w/2,p.cy+h/2],f0:req.f0,f1:req.f1});
    out.set(req.key,p);
  }
  return out;
}
