// SCHEMA v2 §C — client-side reframe: preview a 9:16 (etc.) version of a project before/without the server job.
import type {Project,Aspect,CropData,Tracks} from './types';
import {cropFromTracks,reframeSize,cropAt,toOut,warpSafeMargins,LOOK_WARP_MAX} from './geometry';
import {lines} from './renderer';
import {isSubtitleLine} from './looks';

/**
 * Re-layout rules (schema): copy words; clear explicit positions and auto-place; shrink each line so it fits
 * ~86% of the new width; anchor offsets are re-expressed in output fractions; surface words keep their surface
 * (mapped through the crop by the renderer). Media and analysis stay pointed at the source project's files.
 */
export function reframeProject(src:Project,aspect:Aspect,tracks:Tracks|undefined,crop?:CropData):{project:Project;crop:CropData}{
  const [W,H]=reframeSize(src.width,src.height,aspect);const frames=Math.round(src.duration*src.fps);
  const c=crop||cropFromTracks(tracks,frames,src.width,src.height,aspect,src.fps);
  const cw=c.frames[0]?.w||1,ch=c.frames[0]?.h||1;
  src=surfacesToTitles(src,c);
  const ctx=document.createElement('canvas').getContext('2d')!;
  // Width of each line in output pixels if font fractions were kept (font sizes are fractions of height).
  const scaleByLine=new Map<string,number>();
  // Lines wrap into stacked rows in the renderer, so only the longest single word has to fit.
  // Width of each line in units of its own font size (for the ensemble layout).
  const lineUnits=new Map<string,number>();
  for(const l of lines(ctx,src)){const fs=(l.words[0].style?.fontSize??src.style.fontSize)*src.height;if(fs>0)lineUnits.set(l.lineId,Math.max(lineUnits.get(l.lineId)||0,l.total/fs));const widest=l.placement==='surface'?l.total:Math.max(...l.metrics.map(m=>m.width));scaleByLine.set(l.key,Math.min(1,.86*W/Math.max(1,widest*H/src.height)));
    // Fixed subtitle: the whole line must fit between its x and the right margin; measured at least as wide as
    // Space Mono (0.6 em/char) because looks set the subtitle register in mono.
    const pos=l.words[0].position;
    if(pos&&isSubtitleLine(src,l.lineId)){const fs=(l.words[0].style?.fontSize??src.style.fontSize)*src.height;const chars=l.words.map(w=>w.text).join(' ').length;
      const width=Math.max(l.total,chars*.6*fs)*H/src.height;scaleByLine.set(l.key,Math.min(1,(.95-Math.min(Math.max(pos.x,.05),.95))*W/Math.max(1,width)));}}

  // Head band (output y) over a time span: person bbox top → head anchor (cy) + the same again, through the crop.
  const person=tracks?.tracks.find(t=>t.id==='person0')||tracks?.tracks[0];const tf=tracks?.fps||src.fps;
  const head=(t0:number,t1:number):[number,number]|undefined=>{if(!person)return undefined;let top=1,bot=0;
    for(const fr of person.frames){const t=fr.f/tf;if(t<t0||t>t1)continue;const [,by,,bh]=fr.bbox;const hb=Math.min(fr.cy+Math.max(fr.cy-by,.06),by+.35*bh);
      const cf=cropAt(c,Math.round(t*src.fps));top=Math.min(top,toOut(cf,fr.cx,by)[1]);bot=Math.max(bot,toOut(cf,fr.cx,hb)[1]);}
    return bot>top?[Math.max(0,top),Math.min(1,bot)]:undefined;};
  const ensemble=layoutEnsembles(src,W,H,(l)=>{const u=lineUnits.get(l);return u??1;},warpSafeMargins(W,H,LOOK_WARP_MAX),head);
  const words=src.words.map(w=>{
    const fixed=ensemble.get(w.lineId);
    if(fixed)return {...w,position:fixed.position,autoPlace:false,placement:fixed.front&&w.placement==='behind'?'overlay' as const:w.placement,style:{...(w.style||{}),fontSize:fixed.fontSize}};
    const k=scaleByLine.get(`${w.lineId}:${w.placement}`)??1;
    const style={...(w.style||{})};const base=style.fontSize??src.style.fontSize;
    if(k<1)style.fontSize=base*k;
    const out={...w,style};
    // Subtitle/karaoke lines keep their fixed spot (x clamped into the new frame's margin); others re-place.
    if(isSubtitleLine(src,w.lineId)&&w.position)out.position={x:Math.min(Math.max(w.position.x,.05),.95),y:w.position.y};
    else if(w.placement==='behind'||w.placement==='overlay'){out.position=null;out.autoPlace=true;}
    if(w.anchor)out.anchor={...w.anchor,dx:w.anchor.dx/cw,dy:w.anchor.dy/ch};
    return out;
  });
  return {crop:c,project:{...src,width:W,height:H,words,name:`${src.name} · ${aspect}`,frame:{aspect,source:{projectId:src.id},crop:null}}};
}

type Fixed={position:{x:number;y:number};fontSize:number;front:boolean};
/**
 * Multi-line endings ("EVERY WORD / I KNOW" as four one-word lines in a grid) must keep reading order when
 * re-laid out: independent auto-placement scrambles them. An ensemble = overlay/behind lines with explicit
 * positions, the same font size (±10%) and overlapping lifetimes. Its rows are the authored rows (lines at the
 * same y) in start order; if they don't fit the new frame, one line per row. The layout giving the larger type
 * wins; positions are written explicitly (no autoPlace). Rows narrower than 75% of the frame, or centred
 * below 30% of its height (body level), go to the front (behind → overlay) so words can't vanish behind the subject. `units(lineId)` = line width in units of its font size.
 * Mirrored by server/app/analysis_v2.py:_ensemble_layout.
 */
export function layoutEnsembles(src:Project,W:number,H:number,units:(lineId:string)=>number,margins:[number,number]=[.06,.06],head?:(t0:number,t1:number)=>[number,number]|undefined):Map<string,Fixed>{
  type L={id:string;start:number;end:number;x:number;y:number;fs:number};
  const byLine=new Map<string,L>();
  for(const w of src.words){
    if(w.placement!=='overlay'&&w.placement!=='behind'||!w.position||w.autoPlace)continue;
    const fs=w.style?.fontSize??src.style.fontSize;const l=byLine.get(w.lineId);
    if(!l)byLine.set(w.lineId,{id:w.lineId,start:w.start,end:w.end,x:w.position.x,y:w.position.y,fs});
    else{l.start=Math.min(l.start,w.start);l.end=Math.max(l.end,w.end);}
  }
  const ls=[...byLine.values()].sort((a,b)=>a.start-b.start||a.y-b.y||a.x-b.x);
  const parent=ls.map((_,i)=>i);const find=(i:number):number=>parent[i]===i?i:(parent[i]=find(parent[i]));
  for(let i=0;i<ls.length;i++)for(let j=i+1;j<ls.length;j++){const a=ls[i],b=ls[j];
    const overlap=Math.min(a.end,b.end)-Math.max(a.start,b.start)>.05;const same=Math.abs(a.fs-b.fs)<=.1*Math.max(a.fs,b.fs);
    const apart=Math.hypot(a.x-b.x,a.y-b.y)>.02;if(overlap&&same&&apart)parent[find(j)]=find(i);}
  const groups=new Map<number,L[]>();ls.forEach((l,i)=>{const r=find(i);groups.set(r,[...(groups.get(r)||[]),l]);});
  const out=new Map<string,Fixed>();
  for(const g of groups.values()){
    if(g.length<2)continue;const fs0=g[0].fs;
    // Authored rows: cluster by y (within half a line height), rows top→bottom, each row in start order.
    const rows:L[][]=[];
    for(const l of [...g].sort((a,b)=>a.y-b.y)){const r=rows.find(r=>Math.abs(r[0].y-l.y)<fs0*.5);if(r)r.push(l);else rows.push([l]);}
    rows.forEach(r=>r.sort((a,b)=>a.start-b.start));rows.sort((a,b)=>a[0].start-b[0].start);
    const single=g.map(l=>[l]);const GAP=.28,LEAD=1.02;
    // Safe area: margins (warp-aware) on every edge; rows stay above 0.86 so the subtitle band stays free.
    const [mx,my]=margins,BOT=.86,GLY=.5;
    const sizeFor=(rs:L[][])=>{const widest=Math.max(...rs.map(r=>r.reduce((s,l)=>s+units(l.id),0)+GAP*(r.length-1)));
      return Math.min(fs0,(1-2*mx)*W/Math.max(.01,widest)/H,(BOT-my)/(rs.length*LEAD));};
    const a=sizeFor(rows),b=sizeFor(single);let [rs,size]=a>=b*.9?[rows,a]:[single,b];const n=rs.length;
    // Never over the face: with a person track, the first k rows go above the head band (keeping their placement),
    // the rest below the chin in front; k and the size maximize the type, but a layout with at least one row
    // above the head wins if its type is ≥60% of the best (a title over the head reads as a title, not a caption). Otherwise split around the subject.
    const band=head?.(Math.min(...g.map(l=>l.start)),Math.max(...g.map(l=>l.end)));
    let rowY:(ri:number)=>number,frontAt:(ri:number,wsum:number)=>boolean;
    let pick:{k:number;size:number}|undefined;
    if(band){const hT=band[0]-.01,hB=band[1]+.015;const opts:{k:number;size:number}[]=[];
      for(let k=0;k<=n;k++){let s=size;if(k>0)s=Math.min(s,(hT-my)/(k*LEAD));if(n-k>0)s=Math.min(s,(BOT-hB)/((n-k)*LEAD));if(s>0)opts.push({k,size:s});}
      const bestAll=Math.max(0,...opts.map(o=>o.size));const above=opts.filter(o=>o.k>0&&o.size>=.6*bestAll).sort((x,y)=>y.size-x.size)[0];
      pick=above||opts.sort((x,y)=>y.size-x.size)[0];
      if(pick&&pick.size<.5*size)pick=undefined;
      if(pick){const k=pick.k;size=pick.size;const sp=size*LEAD;
        rowY=ri=>ri<k?my+size*GLY+ri*sp:hB+size*GLY+(ri-k)*sp;frontAt=ri=>ri>=k;}}
    if(!pick){const sp=size*LEAD;const top=my+size*GLY;const split=n>=2&&n*sp<=.45?Math.ceil(n/2):n;
      rowY=ri=>ri<split?top+ri*sp:Math.max(top+ri*sp,.55+size/2)+(ri-split)*sp;
      // A narrow row ("I") placed behind would vanish behind a centred subject in portrait: bring it to the front.
      frontAt=(ri,wsum)=>wsum*size*H/W<.75||rowY(ri)>.3;}
    rs.forEach((r,ri)=>{const wsum=r.reduce((s,l)=>s+units(l.id),0)+GAP*(r.length-1);let x=.5-wsum*size*H/W/2;
      const front=frontAt(ri,wsum);
      for(const l of r){const w=units(l.id)*size*H/W;out.set(l.id,{position:{x:+(x+w/2).toFixed(4),y:+rowY(ri).toFixed(4)},fontSize:+size.toFixed(4),front});x+=w+GAP*size*H/W;}});
  }
  return out;
}

/**
 * A static (untracked) surface that is mostly outside the crop is a screen-space title in disguise (a flat wall
 * drawn for 16:9). Its lines become behind lines at the quad centre with an explicit position, so the ensemble
 * layout stacks them in reading order and the front rule brings body-level rows in front of the subject.
 * Tracked surfaces stay surfaces (the renderer fits them to the visible plane). Mirrored in analysis_v2.py.
 */
export function surfacesToTitles(src:Project,c:CropData):Project{
  const conv=new Map<string,{x:number;y:number}>();
  for(const s of src.surfaces||[]){
    if(s.track&&!(s as {noTrack?:boolean}).noTrack)continue;  // noTrack: extra field on hand-drawn static walls
    const [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]=s.corners;
    const at=(u:number,v:number)=>[(1-v)*((1-u)*x0+u*x1)+v*((1-u)*x3+u*x2),(1-v)*((1-u)*y0+u*y1)+v*((1-u)*y3+u*y2)];
    const byLine=new Map<string,{start:number;end:number}>();
    for(const w of src.words)if(w.placement==='surface'&&w.surfaceId===s.id){const l=byLine.get(w.lineId);byLine.set(w.lineId,{start:Math.min(l?.start??w.start,w.start),end:Math.max(l?.end??w.end,w.end)});}
    for(const [lineId,l] of byLine){
      const cf=cropAt(c,Math.round((l.start+l.end)/2*src.fps));let inside=0;
      for(let j=0;j<=10;j++)for(let i=0;i<=10;i++){const [x,y]=at(i/10,j/10);const [ox,oy]=toOut(cf,x,y);if(ox>=0&&ox<=1&&oy>=0&&oy<=1)inside++;}
      if(inside/121<.5){const [x,y]=at(.5,.5);conv.set(lineId,{x,y});}
    }
  }
  if(!conv.size)return src;
  return {...src,words:src.words.map(w=>{const pos=conv.get(w.lineId);return pos&&w.placement==='surface'?{...w,placement:'behind' as const,surfaceId:null,position:pos,autoPlace:false}:w;})};
}
