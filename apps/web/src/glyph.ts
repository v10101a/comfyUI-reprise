// v4.3 glyph fill: the lyric drawn with the footage's own light. A filled line is a fixed letter grid (the line's
// text tiled in reading order) whose cells take their brightness from the graded footage under them, masked to a
// region (the subject, the world around the subject, the whole frame) or warped onto the wall the line is placed on.
// Deterministic per frame and free of state: a cell keeps its letter for the whole line (the body moving over the
// grid reveals a stable page of text instead of reshuffling letters), sung words light up over RAMP frames, the word
// being sung takes the accent, brightness is continuous (no quantised glyph ramp, so nothing flickers at level edges).
import type {Look,Point,Word} from './types';
import {drawWarped,squareToQuad,applyH,quadSize} from './geometry';
import {applyCase,FILL_DEFAULTS} from './looks';

export type FillSpec=NonNullable<Look['fill']>;
export type FillLine={key:string;words:Word[];start:number;end:number;surfaceId?:string|null};
export type FillDraw={
  look:Look;fill:FillSpec;W:number;H:number;t:number;frame:number;fps:number;
  /** Graded footage of this frame at W×H (the fill reads its light). */
  env:HTMLCanvasElement;
  /** Draws the matte (subject cutout) of this frame scaled to w×h; absent = no matte. */
  matte?:(g:CanvasRenderingContext2D,w:number,h:number)=>void;
  lines:FillLine[];
  /** Output-space pixel quad of a surface at this frame (undefined = not on screen / not drawable). */
  quadOf:(surfaceId:string)=>Point[]|undefined;
  subset:'all'|'behind'|'front';
  /** Draft (scrub) quality: coarser cells. */
  draft?:boolean;
};

/** Cell height / width (terminal cells). */
const ASPECT=1.9;
/** Brightness steps in the atlas (per colour). */
const LEVELS=16;
/** Brightness of words not yet sung. */
const DIM=.22;
/** The darkest cell inside the region still shows its letter at this brightness. */
const FLOOR=.14;
/** Frames for a sung word to light up. */
const RAMP=3;
/** Seconds: fade in at the line's start, fade out after its end. */
const FADE_IN=.15,FADE_OUT=.25;
/** Luminance is read from the footage at 1/SAMPLE resolution. */
const SAMPLE=4;
const DEFAULT_WEIGHT:Record<string,number>={Inter:800,'Archivo Narrow':500,'Big Shoulders Display':900,'Space Mono':700};

type Atlas={canvas:HTMLCanvasElement;index:Map<string,number>;cw:number;ch:number};
type Program={chars:string[];word:number[];len:number;words:Word[]};

function fadeOf(line:FillLine,t:number){
  if(t<line.start||t>=line.end+FADE_OUT)return 0;
  const i=Math.min(1,(t-line.start)/FADE_IN);const o=t<line.end?1:1-(t-line.end)/FADE_OUT;return Math.max(0,Math.min(i,o));
}
/** The line's text as one tiled string: words in time order, one space between words, two after the line. */
function program(line:FillLine,look:Look):Program{
  const words=[...line.words].sort((a,b)=>a.start-b.start||a.end-b.end);const chars:string[]=[],word:number[]=[];
  words.forEach((w,i)=>{for(const ch of applyCase(w.text,look.font.heroCase)){chars.push(ch);word.push(i);}chars.push(' ');word.push(i);});
  chars.push(' ');word.push(Math.max(0,words.length-1));
  return {chars,word,len:chars.length,words};
}
const currentWord=(words:Word[],t:number)=>{let cur=-1;for(let i=0;i<words.length;i++)if(words[i].start<=t)cur=i;return cur;};

export class GlyphFill{
  private atlases=new Map<string,Atlas>();
  private mid=document.createElement('canvas');private midData?:Uint8ClampedArray;private midStamp='';
  private small=document.createElement('canvas');private smallMatte=document.createElement('canvas');
  private grid=document.createElement('canvas');private plane=document.createElement('canvas');

  draw(ctx:CanvasRenderingContext2D,d:FillDraw){
    const {fill,t}=d;
    const cw=Math.max(4,Math.round((fill.cell??FILL_DEFAULTS.cell)*Math.min(d.W,d.H)*(d.draft?1.5:1)));const ch=Math.round(cw*ASPECT);
    this.midStamp='';
    for(const line of d.lines){
      const a=fadeOf(line,t);if(a<=0)continue;
      // Wall lines fill their wall; a subject fill without a matte falls back to the whole frame.
      const region=line.surfaceId?'surface':fill.region==='subject'&&!d.matte?'frame':fill.region;
      const behind=region==='world'||region==='surface';
      if(d.subset==='behind'&&!behind||d.subset==='front'&&behind)continue;
      if(region==='surface'){const quad=d.quadOf(line.surfaceId!);if(quad)this.drawWall(ctx,d,line,quad,a,cw,ch);}
      else this.drawScreen(ctx,d,line,region,a,cw,ch);
    }
  }

  /** Glyph atlas for one look + cell size: every character of the line at LEVELS brightness steps, ink rows then accent rows. */
  private atlas(look:Look,chars:Iterable<string>,cw:number,ch:number):Atlas{
    const family=look.font.hero,weight=look.font.heroWeight??DEFAULT_WEIGHT[family]??700;
    const list=[...new Set(chars)].filter(c=>c.trim()).sort();
    const key=`${family}|${weight}|${cw}|${ch}|${look.palette.text}|${look.palette.accent}|${list.join('')}`;
    const hit=this.atlases.get(key);if(hit)return hit;
    if(this.atlases.size>16)this.atlases.clear();
    const c=document.createElement('canvas');c.width=Math.max(1,list.length*cw);c.height=2*LEVELS*ch;const g=c.getContext('2d')!;
    // Type size: the em in 78% of the cell height, shrunk until the widest glyph fits 92% of the cell width.
    let px=ch*.78;g.font=`${weight} ${px}px "${family}"`;const widest=Math.max(1,...list.map(x=>g.measureText(x).width));
    if(widest>cw*.92)px*=cw*.92/widest;
    g.font=`${weight} ${px}px "${family}"`;g.textAlign='center';g.textBaseline='middle';
    const index=new Map<string,number>();
    list.forEach((x,i)=>{index.set(x,i);for(let k=0;k<2;k++){g.fillStyle=k?look.palette.accent:look.palette.text;
      for(let l=1;l<LEVELS;l++){g.globalAlpha=l/(LEVELS-1);g.fillText(x,i*cw+cw/2,(k*LEVELS+l)*ch+ch/2);}}});
    const atlas={canvas:c,index,cw,ch};this.atlases.set(key,atlas);return atlas;
  }
  /** The graded footage at 1/SAMPLE resolution (drawn once per draw call). */
  private midFrame(d:FillDraw){
    const mw=Math.max(1,Math.round(d.W/SAMPLE)),mh=Math.max(1,Math.round(d.H/SAMPLE));const stamp=`${mw}x${mh}`;
    const mid=this.mid;if(this.midStamp===stamp)return mid;
    if(mid.width!==mw||mid.height!==mh){mid.width=mw;mid.height=mh;}
    const g=mid.getContext('2d',{willReadFrequently:true})!;g.imageSmoothingEnabled=true;g.imageSmoothingQuality='high';g.clearRect(0,0,mw,mh);g.drawImage(d.env,0,0,mw,mh);
    this.midStamp=stamp;this.midData=undefined;return mid;
  }
  /** Per-cell luminance (0..1) of the screen grid and, when asked, the matte's coverage per cell. */
  private sample(d:FillDraw,cols:number,rows:number,wantMatte:boolean){
    const mid=this.midFrame(d);
    const s=this.small;s.width=cols;s.height=rows;const sg=s.getContext('2d',{willReadFrequently:true})!;sg.imageSmoothingEnabled=true;sg.imageSmoothingQuality='high';sg.drawImage(mid,0,0,cols,rows);
    const px=sg.getImageData(0,0,cols,rows).data;const lum=new Float32Array(cols*rows);
    for(let i=0;i<lum.length;i++)lum[i]=(.2126*px[i*4]+.7152*px[i*4+1]+.0722*px[i*4+2])/255;
    let cover:Float32Array|undefined;
    if(wantMatte&&d.matte){const m=this.smallMatte;m.width=cols;m.height=rows;const g=m.getContext('2d',{willReadFrequently:true})!;g.imageSmoothingEnabled=true;g.imageSmoothingQuality='high';g.clearRect(0,0,cols,rows);d.matte(g,cols,rows);
      const a=g.getImageData(0,0,cols,rows).data;cover=new Float32Array(cols*rows);for(let i=0;i<cover.length;i++)cover[i]=a[i*4+3]/255;}
    return {lum,cover};
  }
  /** Brightness level (0..LEVELS-1) of a cell from its luminance and its word's reveal. */
  private level(lum:number,gain:number,on:number){
    const v=Math.min(1,Math.max(0,(lum*gain-.02)/.9));const bright=(FLOOR+(1-FLOOR)*v)*(DIM+(1-DIM)*on);
    return Math.round(bright*(LEVELS-1));
  }
  private drawScreen(ctx:CanvasRenderingContext2D,d:FillDraw,line:FillLine,region:'subject'|'world'|'frame',a:number,cw:number,ch:number){
    const cols=Math.ceil(d.W/cw),rows=Math.ceil(d.H/ch);
    const {lum,cover}=this.sample(d,cols,rows,region==='subject');
    const prog=program(line,d.look);const atlas=this.atlas(d.look,prog.chars,cw,ch);
    const G=this.grid;if(G.width!==d.W||G.height!==d.H){G.width=d.W;G.height=d.H;}const g=G.getContext('2d')!;g.setTransform(1,0,0,1,0,0);g.globalAlpha=1;g.globalCompositeOperation='source-over';g.clearRect(0,0,d.W,d.H);
    const backing=d.fill.backing??FILL_DEFAULTS.backing;
    if(backing>0){g.globalAlpha=backing;g.fillStyle=d.look.palette.card||'#000000';g.fillRect(0,0,d.W,d.H);g.globalAlpha=1;}
    const cur=currentWord(prog.words,d.t);const gain=d.fill.gain??FILL_DEFAULTS.gain;
    for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
      const i=r*cols+c;if(cover&&cover[i]<.04)continue;
      const idx=(r*(cols+4)+c)%prog.len;const gi=atlas.index.get(prog.chars[idx]);if(gi===undefined)continue;
      const wi=prog.word[idx];const on=Math.min(1,Math.max(0,(d.t-prog.words[wi].start)*d.fps/RAMP));
      const level=this.level(lum[i],gain,on);if(level<1)continue;
      g.drawImage(atlas.canvas,gi*cw,((wi===cur?LEVELS:0)+level)*ch,cw,ch,c*cw,r*ch,cw,ch);
    }
    if(d.matte&&region==='subject'){g.globalCompositeOperation='destination-in';d.matte(g,d.W,d.H);g.globalCompositeOperation='source-over';}
    // Text-only renders of everything: the world fill keeps a hole where the subject is (the composite paints the cutout over it).
    else if(d.matte&&region==='world'&&d.subset==='all'){g.globalCompositeOperation='destination-out';d.matte(g,d.W,d.H);g.globalCompositeOperation='source-over';}
    ctx.save();ctx.globalAlpha*=a;ctx.drawImage(G,0,0);ctx.restore();
  }
  /** A wall line: the grid lives in the wall's plane (perspective-correct cells), lit by the footage under each cell. */
  private drawWall(ctx:CanvasRenderingContext2D,d:FillDraw,line:FillLine,quad:Point[],a:number,cw:number,ch:number){
    const [uw,uh]=quadSize(quad);if(uw<cw||uh<ch)return;
    const pcols=Math.min(480,Math.ceil(uw/cw)),prows=Math.min(240,Math.ceil(uh/ch));
    const mid=this.midFrame(d);const mw=mid.width,mh=mid.height;
    if(!this.midData)this.midData=mid.getContext('2d',{willReadFrequently:true})!.getImageData(0,0,mw,mh).data;const px=this.midData;
    const Hm=squareToQuad(quad);
    const prog=program(line,d.look);const atlas=this.atlas(d.look,prog.chars,cw,ch);
    const P=this.plane;const pw=pcols*cw,ph=prows*ch;if(P.width!==pw||P.height!==ph){P.width=pw;P.height=ph;}const g=P.getContext('2d')!;g.setTransform(1,0,0,1,0,0);g.globalAlpha=1;g.globalCompositeOperation='source-over';g.clearRect(0,0,pw,ph);
    const backing=d.fill.backing??FILL_DEFAULTS.backing;
    if(backing>0){g.globalAlpha=backing;g.fillStyle=d.look.palette.card||'#000000';g.fillRect(0,0,pw,ph);g.globalAlpha=1;}
    const cur=currentWord(prog.words,d.t);const gain=d.fill.gain??FILL_DEFAULTS.gain;
    for(let r=0;r<prows;r++)for(let c=0;c<pcols;c++){
      const [x,y]=applyH(Hm,(c+.5)/pcols,(r+.5)/prows);const mx=Math.min(mw-1,Math.max(0,Math.round(x/SAMPLE))),my=Math.min(mh-1,Math.max(0,Math.round(y/SAMPLE)));
      const k=(my*mw+mx)*4;const lum=(.2126*px[k]+.7152*px[k+1]+.0722*px[k+2])/255;
      const idx=(r*(pcols+4)+c)%prog.len;const gi=atlas.index.get(prog.chars[idx]);if(gi===undefined)continue;
      const wi=prog.word[idx];const on=Math.min(1,Math.max(0,(d.t-prog.words[wi].start)*d.fps/RAMP));
      const level=this.level(lum,gain,on);if(level<1)continue;
      g.drawImage(atlas.canvas,gi*cw,((wi===cur?LEVELS:0)+level)*ch,cw,ch,c*cw,r*ch,cw,ch);
    }
    if(d.matte&&d.subset==='all'){
      // Text-only render of everything: keep a hole where the subject is.
      const G=this.grid;if(G.width!==d.W||G.height!==d.H){G.width=d.W;G.height=d.H;}const gg=G.getContext('2d')!;gg.setTransform(1,0,0,1,0,0);gg.globalAlpha=1;gg.globalCompositeOperation='source-over';gg.clearRect(0,0,d.W,d.H);
      drawWarped(gg,P,quad);gg.globalCompositeOperation='destination-out';d.matte(gg,d.W,d.H);gg.globalCompositeOperation='source-over';
      ctx.save();ctx.globalAlpha*=a;ctx.drawImage(G,0,0);ctx.restore();return;
    }
    ctx.save();ctx.globalAlpha*=a;drawWarped(ctx,P,quad);ctx.restore();
  }
}
