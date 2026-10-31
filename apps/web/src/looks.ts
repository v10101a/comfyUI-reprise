/*
 * ─── Look system API (for U / the studio UI) ─────────────────────────────────────────────────────
 * TODO(U): build the look picker against exactly these exports; everything else in here is internal.
 *
 *   LOOKS: LookInfo[]
 *       { id, name, description, swatch: string[] (2–4 CSS colours), fonts: string[] (display names) }
 *       Ordered for the picker. 'default' = no look (v2 rendering).
 *   lookOf(project): Look | undefined
 *       Resolved preset + project.look.overrides. undefined when no look / 'default'.
 *
 *   Pure project mutators (return a new Project; never mutate; the renderer picks changes up on the next frame,
 *   so switching looks is instant — no reload, no re-analysis):
 *   setLook(project, id: LookId | null, overrides?)      → project.look = {id, overrides} (null/'default' clears)
 *   setLookOverrides(project, partial)                     → merge into project.look.overrides
 *   setLineMeta(project, lineId, {hook?, heroWordId?, hidden?})  (null value = clear that key)
 *   setWordHero(project, wordId, hero: boolean)            → Word.hero; clears hero on the line's other words
 *   setWordHidden(project, wordId, hidden: boolean)        → Word.hidden
 *
 *   Read helpers for the transcript/timeline (to grey out quiet words, badge hooks/heroes):
 *   lineIsHook(project, lineId): boolean                   (lineMeta.hook, else repeated-lyric heuristic, see below)
 *   heroWordId(project, lineId): string | undefined        (Word.hero, lineMeta.heroWordId, else longest non-stopword)
 *   wordIsShown(project, word): boolean                    (false if hidden by Word.hidden, lineMeta.hidden or look.quiet)
 *
 *   Fonts: FONTS (family, file, license) — registered by the renderer's loadFonts(); the UI may list them in a
 *   font menu. All are bundled OFL/Apache faces in public/fonts with their license files.
 * ─────────────────────────────────────────────────────────────────────────────────────────────────
 */
import type {Project,Word,Look,LookId,LookRef,LineMeta} from './types';

export type LookInfo = {id:LookId;name:string;description:string;swatch:string[];fonts:string[]};

/** Bundled faces. `weight` is the CSS weight range of the file (variable fonts cover a range). */
export const FONTS:{family:string;file:string;weight:string;style?:string;license:string}[] = [
  {family:'Inter',file:'Inter[opsz,wght].ttf',weight:'100 900',license:'OFL-Inter.txt'},
  {family:'Space Mono',file:'SpaceMono-Regular.ttf',weight:'400',license:'OFL-SpaceMono.txt'},
  {family:'Space Mono',file:'SpaceMono-Bold.ttf',weight:'700',license:'OFL-SpaceMono.txt'},
  {family:'Anton',file:'Anton-Regular.ttf',weight:'400',license:'OFL-Anton.txt'},
  {family:'Bebas Neue',file:'BebasNeue-Regular.ttf',weight:'400',license:'OFL-BebasNeue.txt'},
  {family:'Big Shoulders Display',file:'BigShouldersDisplay[wght].ttf',weight:'100 900',license:'OFL-BigShouldersDisplay.txt'},
  {family:'Permanent Marker',file:'PermanentMarker-Regular.ttf',weight:'400',license:'LICENSE-PermanentMarker.txt'},
  {family:'Instrument Serif',file:'InstrumentSerif-Regular.ttf',weight:'400',license:'OFL-InstrumentSerif.txt'},
  {family:'Instrument Serif',file:'InstrumentSerif-Italic.ttf',weight:'400',style:'italic',license:'OFL-InstrumentSerif.txt'},
  {family:'Rubik Wet Paint',file:'RubikWetPaint-Regular.ttf',weight:'400',license:'OFL-RubikWetPaint.txt'},
  {family:'Archivo Narrow',file:'ArchivoNarrow[wght].ttf',weight:'400 700',license:'OFL-ArchivoNarrow.txt'},
  {family:'Silkscreen',file:'Silkscreen-Regular.ttf',weight:'400',license:'OFL-Silkscreen.txt'},
];

/** Presets live in code: tuning one restyles every project that references it. Names describe rules, not artists. */
const PRESETS:Record<Exclude<LookId,'default'>,Look> = {
  'red-glow':{id:'red-glow',
    font:{hero:'Anton',body:'Anton',heroCase:'upper',bodyCase:'upper'},
    palette:{text:'#ff1a1a',accent:'#ff4a3d',shadow:'#1a0000'},
    texture:'grain',optics:{glow:.8,grain:.25},grade:{tint:'#0f6f7a',amount:.35},layout:'hero',quiet:'none',heroFill:'text'},
  'lens-bound':{id:'lens-bound',
    font:{hero:'Inter',body:'Inter',heroWeight:900,bodyWeight:600,heroCase:'upper',bodyCase:'lower'},
    palette:{text:'#ffffff',accent:'#7dff4a',shadow:'#000000'},
    texture:'grain',optics:{motionBlur:.7,chroma:.4,lensWarp:.5,grain:.18,glow:.25,extrude:1},grade:{tint:'#1b3a2a',amount:.18},layout:'line',quiet:'none',heroFill:'text'},
  'paper-cut':{id:'paper-cut',
    font:{hero:'Big Shoulders Display',body:'Big Shoulders Display',heroWeight:900,bodyWeight:800,heroCase:'upper',bodyCase:'upper'},
    palette:{text:'#efe6d2',accent:'#c8243a',shadow:'#000000',card:'#c8243a'},
    texture:'paper',optics:{grain:.35},grade:{tint:'#c8243a',amount:.16},layout:'hero',quiet:'none',heroFill:'accent'},
  'ticker':{id:'ticker',
    font:{hero:'Silkscreen',body:'Silkscreen',heroCase:'upper',bodyCase:'upper'},
    palette:{text:'#ffb000',accent:'#ff6a00',shadow:'#140a00'},
    texture:'grain',optics:{glow:.6,grain:.15},grade:{tint:'#2a1a00',amount:.2},layout:'line',quiet:'none',heroFill:'text',motion:'marquee'},
  'flat-card':{id:'flat-card',
    font:{hero:'Archivo Narrow',body:'Archivo Narrow',heroWeight:500,bodyWeight:500,heroCase:'lower',bodyCase:'lower'},
    palette:{text:'#101010',accent:'#101010',card:'#2f6bff'},
    texture:'none',optics:{blur:.3},grade:null,layout:'line',quiet:'none',heroFill:'text'},
  // Pastel synth-pop over light footage: white type outlined in pink (like a sticker / the cartoon stars), a soft
  // periwinkle halo for legibility on pale skies, pixel hooks, lowercase italic serif verses that can ride MIDI note
  // blocks (Word.note), sparkles on hook words. Footage ungraded.
  'dreamy':{id:'dreamy',
    font:{hero:'Silkscreen',body:'Instrument Serif',heroCase:'upper',bodyCase:'lower',bodyStyle:'italic'},
    palette:{text:'#ffffff',accent:'#ffffff',shadow:'#5a5fd6',outline:'#f0a3dc',note:'#8d93f2'},outlineWidth:.07,halo:.55,
    texture:'none',optics:{glow:.3,sparkle:.8},grade:null,layout:'line',quiet:'none',heroFill:'text',verse:{max:.075,keepPosition:true}},
};

export const LOOKS:LookInfo[] = [
  {id:'default',name:'Default',description:'Your per-word styles, no art direction.',swatch:['#f4f1ea','#d8ff62'],fonts:['Inter']},
  {id:'red-glow',name:'Red glow',description:'One condensed red face with bloom over cyan-graded footage; one huge word per line behind the subject.',swatch:['#ff1a1a','#0f6f7a','#1a0000'],fonts:['Anton']},
  {id:'lens-bound',name:'Lens-bound',description:'White heavy grotesk hooks, lowercase green verses; text takes the camera’s blur, fringing and lens bend.',swatch:['#ffffff','#7dff4a','#000000'],fonts:['Inter Black']},
  {id:'paper-cut',name:'Paper cut',description:'Rough condensed cut-paper type in cream, black and red with paper grain; hero words bleed off the frame.',swatch:['#efe6d2','#c8243a','#000000'],fonts:['Big Shoulders Display']},
  {id:'ticker',name:'Ticker',description:'Amber LED dot type that scrolls through its box and glows like a sign.',swatch:['#ffb000','#ff6a00','#140a00'],fonts:['Silkscreen']},
  {id:'flat-card',name:'Flat card',description:'Lowercase narrow sans on one flat colour card, slightly soft.',swatch:['#2f6bff','#101010','#ffffff'],fonts:['Archivo Narrow']},
  {id:'dreamy',name:'Dreamy',description:'Pastel synth-pop: white pixel hooks outlined in pink with sparkles, lowercase italic serif verses on periwinkle note blocks.',swatch:['#ffffff','#f0a3dc','#8d93f2','#5a5fd6'],fonts:['Silkscreen','Instrument Serif Italic']},
];

export function lookOf(p:Pick<Project,'look'>):Look|undefined{
  const ref=p.look;if(!ref||ref.id==='default')return undefined;
  const base=PRESETS[ref.id as Exclude<LookId,'default'>];if(!base)return undefined;
  const o=ref.overrides||{};
  return {...base,...o,id:base.id,font:{...base.font,...(o.font||{})},palette:{...base.palette,...(o.palette||{})},optics:{...base.optics,...(o.optics||{})},
    grade:o.grade===undefined?base.grade:o.grade};
}

// ---------- mutators (pure) ----------
export function setLook(p:Project,id:LookId|null,overrides?:LookRef['overrides']):Project{
  return {...p,look:!id||id==='default'?null:{id,overrides:overrides??null}};
}
export function setLookOverrides(p:Project,partial:NonNullable<LookRef['overrides']>):Project{
  if(!p.look)return p;return {...p,look:{...p.look,overrides:{...(p.look.overrides||{}),...partial}}};
}
export function setLineMeta(p:Project,lineId:string,patch:{[K in keyof LineMeta]?:LineMeta[K]|null}):Project{
  const cur={...(p.lineMeta?.[lineId]||{})} as Record<string,unknown>;
  for(const [k,v] of Object.entries(patch)){if(v===null||v===undefined)delete cur[k];else cur[k]=v;}
  const all={...(p.lineMeta||{})};if(Object.keys(cur).length)all[lineId]=cur as LineMeta;else delete all[lineId];
  return {...p,lineMeta:all};
}
export function setWordHero(p:Project,wordId:string,hero:boolean):Project{
  const w=p.words.find(x=>x.id===wordId);if(!w)return p;
  return {...p,words:p.words.map(x=>x.id===wordId?{...x,hero}:hero&&x.lineId===w.lineId&&x.hero?{...x,hero:false}:x)};
}
export function setWordHidden(p:Project,wordId:string,hidden:boolean):Project{
  return {...p,words:p.words.map(x=>x.id===wordId?{...x,hidden}:x)};
}

// ---------- line semantics (shared by renderer and UI) ----------
const STOP=new Set('a an the and or but if of to in on at by for with from up down out over under as is am are was were be been being do does did have has had i me my mine you your yours he him his she her hers it its we us our they them their this that these those so not no yes oh ooh yeah la na just can will would should could all any some every what when where who how why than then there here into onto off too very'.split(' '));
const norm=(s:string)=>s.toLowerCase().replace(/[^\p{L}\p{N}' ]+/gu,'').replace(/\s+/g,' ').trim();
function lineGroups(p:Project){const m=new Map<string,Word[]>();for(const w of p.words){const g=m.get(w.lineId);if(g)g.push(w);else m.set(w.lineId,[w]);}return m;}
const hookCache=new WeakMap<Word[],Set<string>>();
/** Hooks: lineMeta.hook; else lines whose normalized text occurs 2+ times. If neither marks anything, the lines set
 *  in the project's largest type (the authored "titles") count as hooks, so hooks-only never blanks a project. */
function hookSet(p:Project):Set<string>{
  const hit=hookCache.get(p.words);if(hit&&!p.lineMeta)return hit;
  const groups=lineGroups(p);const text=new Map<string,string>();const counts=new Map<string,number>();
  for(const [id,ws] of groups){const t=norm(ws.map(w=>w.text).join(' '));text.set(id,t);counts.set(t,(counts.get(t)||0)+1);}
  const out=new Set<string>();
  for(const [id] of groups){const m=p.lineMeta?.[id]?.hook;if(m===true||(m==null&&(counts.get(text.get(id)!)||0)>=2))out.add(id);}
  if(!out.size){
    const size=(ws:Word[])=>Math.max(...ws.map(w=>w.style?.fontSize??p.style.fontSize));
    const max=Math.max(0,...[...groups.values()].map(size));
    for(const [id,ws] of groups)if(p.lineMeta?.[id]?.hook!==false&&size(ws)>=max*.8&&ws.some(w=>w.placement!=='anchor'))out.add(id);
  }
  if(!p.lineMeta)hookCache.set(p.words,out);
  return out;
}
export function lineIsHook(p:Project,lineId:string){return hookSet(p).has(lineId);}
export function heroWordId(p:Project,lineId:string):string|undefined{
  const ws=p.words.filter(w=>w.lineId===lineId&&!w.hidden);if(!ws.length)return undefined;
  const manual=ws.find(w=>w.hero);if(manual)return manual.id;
  const meta=p.lineMeta?.[lineId]?.heroWordId;if(meta&&ws.some(w=>w.id===meta))return meta;
  const score=(w:Word)=>{const t=norm(w.text);const content=t.split(' ').filter(x=>x&&!STOP.has(x));return (content.length?1000:0)+Math.max(0,...(content.length?content:[t]).map(x=>x.length));};
  return [...ws].sort((a,b)=>score(b)-score(a)||b.start-a.start)[0].id;
}
/**
 * Subtitle / karaoke register: an overlay line whose words are all 'karaoke', or that has an explicit position,
 * autoPlace off and small type (≤0.045 of height). Looks keep its authored position (no auto-placement, no
 * verse restyle, never silenced by quiet); reframe keeps its position too. Mirrored in server/app/analysis_v2.py.
 */
export function isSubtitleLine(p:Project,lineId:string){
  const ws=p.words.filter(w=>w.lineId===lineId);if(!ws.length||ws.some(w=>w.placement!=='overlay'))return false;
  if(ws.every(w=>w.preset==='karaoke'))return true;
  return ws.every(w=>w.position&&w.autoPlace===false&&(w.style?.fontSize??p.style.fontSize)<=.045);
}
export function wordIsShown(p:Project,w:Word){
  if(w.hidden||p.lineMeta?.[w.lineId]?.hidden)return false;
  const look=lookOf(p);
  if(look?.quiet==='hooks-only'&&w.placement!=='surface'&&!lineIsHook(p,w.lineId)&&!isSubtitleLine(p,w.lineId))return false;
  return true;
}
export function applyCase(text:string,c?:'upper'|'lower'|'as-is'){return c==='upper'?text.toUpperCase():c==='lower'?text.toLowerCase():text;}
