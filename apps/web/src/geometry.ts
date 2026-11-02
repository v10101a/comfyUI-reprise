// Pure geometry: homographies for surface text, per-frame crop windows for reframing.
import type {Point,CropData,CropFrame,Tracks,Aspect} from './types';

/** 3×3 projective map (row-major, h[8] = 1) taking the unit square (u,v) to a quad TL,TR,BR,BL. */
export type Homography = number[];

export function squareToQuad(q:Point[]):Homography{
  const [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]=q;
  const dx1=x1-x2,dx2=x3-x2,dx3=x0-x1+x2-x3,dy1=y1-y2,dy2=y3-y2,dy3=y0-y1+y2-y3;
  if(Math.abs(dx3)<1e-12&&Math.abs(dy3)<1e-12)return [x1-x0,x3-x0,x0,y1-y0,y3-y0,y0,0,0,1];
  const den=dx1*dy2-dx2*dy1||1e-12;
  const g=(dx3*dy2-dx2*dy3)/den,h=(dx1*dy3-dx3*dy1)/den;
  return [x1-x0+g*x1,x3-x0+h*x3,x0,y1-y0+g*y1,y3-y0+h*y3,y0,g,h,1];
}
export function applyH(m:Homography,u:number,v:number):Point{
  const w=m[6]*u+m[7]*v+m[8];
  return [(m[0]*u+m[1]*v+m[2])/w,(m[3]*u+m[4]*v+m[5])/w];
}
/** Monotone cubic (Fritsch–Carlson) through (xs, ys) at x, held outside the ends: smooth, and never swings past a key
 *  however unevenly the keys are spaced. */
export function monotone(xs:number[],ys:number[],x:number):number{
  const n=xs.length;if(n===1||x<=xs[0])return ys[0];if(x>=xs[n-1])return ys[n-1];
  let i=0;while(xs[i+1]<x)i++;
  const d=(j:number)=>(ys[j+1]-ys[j])/(xs[j+1]-xs[j]);
  const m=(j:number)=>{if(j===0)return d(0);if(j===n-1)return d(n-2);const a=d(j-1),b=d(j);return a*b<=0?0:2/(1/a+1/b);};
  const h=xs[i+1]-xs[i],s=(x-xs[i])/h;
  return (2*s**3-3*s**2+1)*ys[i]+(s**3-2*s**2+s)*h*m(i)+(-2*s**3+3*s**2)*ys[i+1]+(s**3-s**2)*h*m(i+1);
}
/** Corner offsets at `frame` from per-key offsets (monotone per coordinate). */
export function keyedOffset(fs:number[],offs:Point[][],frame:number):Point[]{
  return offs[0].map((_,c)=>[0,1].map(d=>monotone(fs,offs.map(o=>o[c][d]),frame)) as Point);
}
/** Inverse projective map (quad → unit square). */
export function invertH(m:Homography):Homography{
  const [a,b,c,d,e,f,g,h,i]=m;
  const A=e*i-f*h,B=c*h-b*i,C=b*f-c*e,D=f*g-d*i,E=a*i-c*g,F=c*d-a*f,G=d*h-e*g,Hh=b*g-a*h,I=a*e-b*d;
  const k=I||1e-12;return [A/k,B/k,C/k,D/k,E/k,F/k,G/k,Hh/k,1];
}
/** A quad is drawable when it is convex and non-degenerate (otherwise the warp folds). */
export function quadIsConvex(q:Point[]){
  let sign=0;
  for(let i=0;i<4;i++){
    const [ax,ay]=q[i],[bx,by]=q[(i+1)%4],[cx,cy]=q[(i+2)%4];
    const z=(bx-ax)*(cy-by)-(by-ay)*(cx-bx);
    if(Math.abs(z)<1e-9)return false;
    if(sign===0)sign=Math.sign(z);else if(Math.sign(z)!==sign)return false;
  }
  return true;
}
/** Average edge lengths (pixel space): [width, height] of the quad's plane rectangle. */
export function quadSize(q:Point[]):[number,number]{
  const d=(a:Point,b:Point)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  return [(d(q[0],q[1])+d(q[3],q[2]))/2,(d(q[0],q[3])+d(q[1],q[2]))/2];
}

/**
 * Draw `src` (whole image = unit square) into the quad `dst` (pixels) on ctx with a piecewise-affine
 * approximation of the homography: an n×n mesh of triangles, each clipped and affinely mapped.
 * Deterministic and exact at mesh vertices; n=12 is visually indistinguishable from a true projective warp.
 */
export function drawWarped(ctx:CanvasRenderingContext2D,src:HTMLCanvasElement|OffscreenCanvas,dst:Point[],n=12){
  const H=squareToQuad(dst);drawMapped(ctx,src,(u,v)=>applyH(H,u,v),n);
}
/** Draw `src` through an arbitrary map (u,v ∈ [0,1] of the source → destination pixels) as an n×n affine triangle mesh. */
export function drawMapped(ctx:CanvasRenderingContext2D,src:HTMLCanvasElement|OffscreenCanvas,map:(u:number,v:number)=>Point,n=12){
  const W=src.width,Hs=src.height;
  const grid:Point[][]=[];
  for(let j=0;j<=n;j++){grid.push([]);for(let i=0;i<=n;i++)grid[j].push(map(i/n,j/n));}
  const tri=(s:Point[],d:Point[])=>{
    const [[sx0,sy0],[sx1,sy1],[sx2,sy2]]=s,[[dx0,dy0],[dx1,dy1],[dx2,dy2]]=d;
    const den=(sx1-sx0)*(sy2-sy0)-(sx2-sx0)*(sy1-sy0);if(Math.abs(den)<1e-9)return;
    const a=((dx1-dx0)*(sy2-sy0)-(dx2-dx0)*(sy1-sy0))/den,c=((dx2-dx0)*(sx1-sx0)-(dx1-dx0)*(sx2-sx0))/den;
    const b=((dy1-dy0)*(sy2-sy0)-(dy2-dy0)*(sy1-sy0))/den,dd=((dy2-dy0)*(sx1-sx0)-(dy1-dy0)*(sx2-sx0))/den;
    const e=dx0-a*sx0-c*sy0,f=dy0-b*sx0-dd*sy0;
    // Expand the clip triangle ~0.6px about its centroid so neighbouring triangles overlap (no hairline seams).
    const mx=(dx0+dx1+dx2)/3,my=(dy0+dy1+dy2)/3;
    const grow=(x:number,y:number):Point=>{const l=Math.hypot(x-mx,y-my)||1;return [x+(x-mx)/l*.6,y+(y-my)/l*.6];};
    ctx.save();ctx.beginPath();
    const p0=grow(dx0,dy0),p1=grow(dx1,dy1),p2=grow(dx2,dy2);
    ctx.moveTo(p0[0],p0[1]);ctx.lineTo(p1[0],p1[1]);ctx.lineTo(p2[0],p2[1]);ctx.closePath();ctx.clip();
    ctx.transform(a,b,c,dd,e,f);ctx.drawImage(src as CanvasImageSource,0,0);ctx.restore();
  };
  for(let j=0;j<n;j++)for(let i=0;i<n;i++){
    const s00:Point=[i/n*W,j/n*Hs],s10:Point=[(i+1)/n*W,j/n*Hs],s01:Point=[i/n*W,(j+1)/n*Hs],s11:Point=[(i+1)/n*W,(j+1)/n*Hs];
    tri([s00,s10,s11],[grid[j][i],grid[j][i+1],grid[j+1][i+1]]);
    tri([s00,s11,s01],[grid[j][i],grid[j+1][i+1],grid[j+1][i]]);
  }
}

// ---------- reframe ----------
export const aspectRatio=(a:Aspect)=>{const [w,h]=a.split(':').map(Number);return w/h;};
export function cropAt(crop:CropData|undefined,frame:number):CropFrame|undefined{
  const fr=crop?.frames;if(!fr?.length)return undefined;
  let lo=0,hi=fr.length-1,found=0;
  while(lo<=hi){const mid=(lo+hi)>>1;if(fr[mid].f<=frame){found=mid;lo=mid+1;}else hi=mid-1;}
  return fr[found];
}
/** Source-normalized point → output-normalized point through a crop window. */
export const toOut=(c:CropFrame|undefined,x:number,y:number):Point=>c?[(x-c.x)/c.w,(y-c.y)/c.h]:[x,y];
export const toSource=(c:CropFrame|undefined,x:number,y:number):Point=>c?[c.x+x*c.w,c.y+y*c.h]:[x,y];

/** Largest look lens warp (lens-bound: 0.5 × 0.35). Reframed layouts assume it: the look can change later. */
export const LOOK_WARP_MAX=.5*.35;
/**
 * Pre-warp safe margins [x, y] (fractions of width/height) so that text kept inside them is still ≥ `base` from
 * every edge after the looks' barrel warp r' = r(1 + k r²) (r normalized by the half-diagonal). k = 0 → [base, base].
 * Mirrored in server/app/analysis_v2.py:_warp_safe_margins.
 */
export function warpSafeMargins(W:number,H:number,k:number,base=.06):[number,number]{
  const R=Math.hypot(W,H)/2;
  const solve=(D:number)=>{let o=.5-base;for(let i=0;i<30;i++){const r=o*D/R;o=(.5-base)/(1+k*r*r);}return .5-o;};
  return [solve(W),solve(H)];
}
/** Output pixel size for a reframe of a srcW×srcH source (keeps the source's short-side resolution, even dims). */
export function reframeSize(srcW:number,srcH:number,aspect:Aspect):[number,number]{
  const ar=aspectRatio(aspect);const even=(n:number)=>Math.max(2,Math.round(n/2)*2);
  return srcW/srcH>ar?[even(srcH*ar),even(srcH)]:[even(srcW),even(srcW/ar)];
}
/**
 * Client-side virtual camera (used when the server has not written analysis/crop.json yet):
 * follow person0's bbox centre, zero-phase smoothed (forward+backward exponential), then a dead zone,
 * clamped inside the source. Pure function of the tracks.
 */
export function cropFromTracks(tracks:Tracks|undefined,frames:number,srcW:number,srcH:number,aspect:Aspect,fps:number):CropData{
  const ar=aspectRatio(aspect);
  const w=srcW/srcH>ar?srcH*ar/srcW:1,h=srcW/srcH>ar?1:srcW/ar/srcH;
  const pts=tracks?.tracks.find(t=>t.id==='person0')?.frames||tracks?.tracks[0]?.frames||[];
  const byF=new Map(pts.map(p=>[p.f,p]));
  const tx:number[]=[],ty:number[]=[];let lx=.5,ly=.45;
  for(let f=0;f<frames;f++){const p=byF.get(f);if(p){lx=.55*(p.bbox[0]+p.bbox[2]/2)+.45*p.cx;ly=p.bbox[1]+p.bbox[3]*.42;}tx.push(lx);ty.push(ly);}
  const smooth=(a:number[])=>{const k=.12;const f=[...a];for(let i=1;i<f.length;i++)f[i]=f[i-1]+(f[i]-f[i-1])*k;for(let i=f.length-2;i>=0;i--)f[i]=f[i+1]+(f[i]-f[i+1])*k;return f;};
  const deadZone=(a:number[],dz:number)=>{const out=[...a];for(let i=1;i<out.length;i++){const d=a[i]-out[i-1];out[i]=Math.abs(d)<dz?out[i-1]:a[i]-Math.sign(d)*dz;}return smooth(out);};
  const sx=deadZone(smooth(tx),w*.06),sy=deadZone(smooth(ty),h*.06);
  const clamp=(v:number,lo:number,hi:number)=>Math.min(hi,Math.max(lo,v));
  return {fps,aspect,frames:sx.map((cx,f)=>({f,x:clamp(cx-w/2,0,1-w),y:clamp(sy[f]-h/2,0,1-h),w,h}))};
}
