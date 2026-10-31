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
 *   v4 grade split: project.grade (GRADES, gradeOf, setGrade, setGradeAmount, migrateProject, legacyGrade) is the
 *   footage treatment; looks are text only. LOOK_PARAMS / lookParam / setLookParam: the editable param set.
 *
 *   Fonts: FONTS (family, file, license) — registered by the renderer's loadFonts(); the UI may list them in a
 *   font menu. All are bundled OFL/Apache faces in public/fonts with their license files.
 * ─────────────────────────────────────────────────────────────────────────────────────────────────
 */
import type {Project,Word,Look,LookId,LookRef,LineMeta,Grade,GradeId,GradeRef} from './types';
import PRESET_FILE from './look-presets.json';

export type LookInfo = {id:LookId;name:string;description:string;swatch:string[];fonts:string[]};
export type GradeInfo = {id:GradeId;name:string};

/** Bundled faces. `weight` is the CSS weight range of the file (variable fonts cover a range).
 *  Bracket-free file names (Inter-Variable.ttf etc. are byte-identical copies of the upstream [axes] files). */
export const FONTS:{family:string;file:string;weight:string;style?:string;license:string}[] = [
  {family:'Inter',file:'Inter-Variable.ttf',weight:'100 900',license:'OFL-Inter.txt'},
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
  {family:'IBM Plex Mono',file:'IBMPlexMono-Regular.ttf',weight:'400',license:'OFL-IBMPlexMono.txt'},
  {family:'IBM Plex Mono',file:'IBMPlexMono-Italic.ttf',weight:'400',style:'italic',license:'OFL-IBMPlexMono.txt'},
  {family:'IBM Plex Mono',file:'IBMPlexMono-Medium.ttf',weight:'500',license:'OFL-IBMPlexMono.txt'},
  {family:'IBM Plex Mono',file:'IBMPlexMono-MediumItalic.ttf',weight:'500',style:'italic',license:'OFL-IBMPlexMono.txt'},
  {family:'IBM Plex Mono',file:'IBMPlexMono-SemiBold.ttf',weight:'600 700',license:'OFL-IBMPlexMono.txt'},
  {family:'Newsreader',file:'Newsreader-Variable.ttf',weight:'200 800',license:'OFL-Newsreader.txt'},
  {family:'Newsreader',file:'Newsreader-Italic-Variable.ttf',weight:'200 800',style:'italic',license:'OFL-Newsreader.txt'},
  {family:'Sixtyfour',file:'Sixtyfour-Variable.ttf',weight:'400',license:'OFL-Sixtyfour.txt'},
];
/** One entry per family, for font menus. */
export const FONT_FAMILIES=[...new Set(FONTS.map(f=>f.family))];

/**
 * Presets live in look-presets.json (shared with the ComfyUI node pack's TypesetLook / TypesetGrade nodes; a node
 * test keeps the two copies equal). Tuning one restyles every project that references it. Names describe rules,
 * not artists. Looks are text only (type, colour, layout, motion, text optics); the footage treatment is a Grade.
 */
type PresetFile={looks:Record<string,LookInfo&{look:Look;hidden?:boolean}>;grades:Record<string,{name:string;grade:Grade}>};
const FILE=PRESET_FILE as unknown as PresetFile;
const PRESETS=Object.fromEntries(Object.entries(FILE.looks).map(([id,x])=>[id,x.look])) as Record<Exclude<LookId,'default'>,Look>;
export const GRADE_PRESETS=Object.fromEntries(Object.entries(FILE.grades).map(([id,x])=>[id,x.grade])) as Record<GradeId,Grade>;

/** Every look, including hidden ones kept only for older projects (red-glow). */
export const ALL_LOOKS:LookInfo[] = [
  {id:'default',name:'Default',description:'Your per-word styles, no art direction.',swatch:['#f4f1ea','#d8ff62'],fonts:['Inter']},
  ...Object.entries(FILE.looks).map(([id,{name,description,swatch,fonts}])=>({id:id as LookId,name,description,swatch,fonts})),
];
/** The picker's looks, in order. */
export const LOOKS:LookInfo[] = ALL_LOOKS.filter(l=>!FILE.looks[l.id]?.hidden);
export const GRADES:GradeInfo[] = Object.entries(FILE.grades).map(([id,{name}])=>({id:id as GradeId,name}));

export function lookOf(p:Pick<Project,'look'>):Look|undefined{
  const ref=p.look;if(!ref||ref.id==='default')return undefined;
  const base=PRESETS[ref.id as Exclude<LookId,'default'>];if(!base)return undefined;
  const o=ref.overrides||{};
  const font={...base.font,...(o.font||{})};
  // A swapped face drops the preset's weight for it (the preset weight may not exist in the new face).
  if(o.font?.hero&&o.font.hero!==base.font.hero&&o.font.heroWeight===undefined)delete font.heroWeight;
  if(o.font?.body&&o.font.body!==base.font.body&&o.font.bodyWeight===undefined)delete font.bodyWeight;
  return {...base,...o,id:base.id,font,palette:{...base.palette,...(o.palette||{})},optics:{...base.optics,...(o.optics||{})}};
}

// ---------- grade (footage) ----------
/** Pre-v4 footage treatment of each look (frozen copy of the old presets' grade / mono / flash / optics.grain). */
const LEGACY_FOOTAGE:Partial<Record<LookId,Grade>>={
  'red-glow':{tint:{color:'#0f6f7a',amount:.35},grain:.25},
  'lens-bound':{tint:{color:'#1b3a2a',amount:.18},grain:.18},
  'paper-cut':{tint:{color:'#c8243a',amount:.16},grain:.35},
  'ticker':{tint:{color:'#2a1a00',amount:.2},grain:.15},
  'grey-noise':{tint:{color:'#c7c7c7',amount:.45},grain:.4},
  'night-code':{tint:{color:'#1b1f11',amount:.35},grain:.2},
  'xerox':{mono:{contrast:1.75,crush:.06,keep:{hue:338,width:42,minSat:.38}},flash:{amount:.55,decay:.2,beat:.35},grain:.6},
};
const canon=(g:Grade)=>JSON.stringify({tint:g.tint||null,mono:g.mono||null,flash:g.flash||null,grain:g.grain||0,halation:g.halation||0});
/**
 * The grade a pre-v4 project's look implied (its old footage treatment, including old look overrides of grade /
 * mono / flash / optics.grain), as a GradeRef: a named grade when one matches exactly, else 'film' with explicit
 * overrides. Renders are unchanged by construction.
 */
export function legacyGrade(ref:LookRef|null|undefined):GradeRef|null{
  if(!ref||ref.id==='default')return null;
  const o=(ref.overrides||{}) as Partial<Look>;const g:Grade={...(LEGACY_FOOTAGE[ref.id]||{})};
  if(o.grade!==undefined)g.tint=o.grade?{color:o.grade.tint,amount:o.grade.amount}:null;
  if(o.mono!==undefined)g.mono=o.mono;if(o.flash!==undefined)g.flash=o.flash;if(o.optics?.grain!==undefined)g.grain=o.optics.grain;
  const key=canon(g);if(key===canon({}))return null;
  const named=(Object.keys(GRADE_PRESETS) as GradeId[]).find(id=>canon(GRADE_PRESETS[id])===key);
  if(named)return {id:named,amount:1};
  return {id:'film',amount:1,overrides:{tint:g.tint||null,mono:g.mono||null,flash:g.flash||null,grain:g.grain||0,halation:0}};
}
/** The project's grade ref: project.grade when present (null = none), else the legacy grade of its look. */
export function gradeRefOf(p:Pick<Project,'look'|'grade'>):GradeRef|null{return p.grade===undefined?legacyGrade(p.look):p.grade;}
/** Resolved footage grade with `amount` (0..1) applied: tint, grain, halation and flash scale; mono cross-fades
 *  (monoMix). undefined = ungraded footage. */
export function gradeOf(p:Pick<Project,'look'|'grade'>):(Grade&{monoMix:number})|undefined{
  const ref=gradeRefOf(p);if(!ref||ref.id==='none'&&!ref.overrides)return undefined;
  const base=GRADE_PRESETS[ref.id]||{};const g:Grade={...base,...(ref.overrides||{})};const a=Math.max(0,Math.min(1,ref.amount??1));
  if(a<=0)return undefined;
  if(a===1)return {...g,monoMix:1};
  return {tint:g.tint?{color:g.tint.color,amount:g.tint.amount*a}:null,mono:g.mono,flash:g.flash?{...g.flash,amount:g.flash.amount*a}:null,
    grain:(g.grain||0)*a,halation:(g.halation||0)*a,monoMix:a};
}
/** Load-time migration (v4 grade split): a project without a `grade` key gets the grade its look used to imply, so
 *  switching looks later keeps the footage as it was. Pure; returns the same object when nothing changes. */
export function migrateProject<T extends Project>(p:T):T{
  if(p.grade!==undefined)return p;
  return {...p,grade:legacyGrade(p.look)};
}
export function setGrade(p:Project,id:GradeId|null,amount?:number):Project{
  if(!id||id==='none')return {...p,grade:null};
  return {...p,grade:{id,amount:amount??p.grade?.amount??1,overrides:null}};
}
export function setGradeAmount(p:Project,amount:number):Project{
  const ref=gradeRefOf(p);if(!ref)return p;return {...p,grade:{...ref,amount}};
}

// ---------- editable look params (studio panel + TypesetLook node) ----------
/**
 * The shared, small parameter set a look exposes for editing. Each param reads from the resolved Look and writes
 * into project.look.overrides (deep-merged into palette / font / optics). Same keys as the TypesetLook node's widgets.
 */
export type LookParamKey='ink'|'accent'|'card'|'cards'|'font'|'body'|'case'|'layout'|'scale'|'motion'|'glow'|'flicker'|'drips'|'light'|'outline'|'halo'|'soft'|'tubes'|'scroll'|'hooks'|'flow'|'voice';
export type LookParam={key:LookParamKey;label:string;kind:'color'|'font'|'select'|'range'|'toggle';options?:string[];min?:number;max?:number;step?:number};
export const LOOK_PARAMS:LookParam[]=[
  {key:'ink',label:'Ink',kind:'color'},
  {key:'accent',label:'Accent',kind:'color'},
  {key:'card',label:'Card',kind:'color'},
  {key:'font',label:'Font',kind:'font'},
  {key:'body',label:'Body',kind:'font'},
  {key:'case',label:'Case',kind:'select',options:['upper','lower','as-is']},
  {key:'layout',label:'Layout',kind:'select',options:['line','hero','stack','constellation']},
  {key:'scale',label:'Size',kind:'range',min:.4,max:2,step:.05},
  {key:'motion',label:'Motion',kind:'range',min:0,max:2,step:.05},
  {key:'glow',label:'Glow',kind:'range',min:0,max:1,step:.05},
  {key:'flicker',label:'Flicker',kind:'range',min:0,max:1,step:.05},
  {key:'drips',label:'Drips',kind:'range',min:0,max:1,step:.05},
  {key:'light',label:'Light',kind:'range',min:0,max:1,step:.05},
  {key:'outline',label:'Outline',kind:'range',min:0,max:.15,step:.005},
  {key:'halo',label:'Halo',kind:'range',min:0,max:1,step:.05},
  {key:'soft',label:'Soft',kind:'range',min:0,max:1,step:.05},
  {key:'cards',label:'Cards',kind:'toggle'},
  {key:'tubes',label:'Tubes',kind:'toggle'},
  {key:'scroll',label:'Scroll',kind:'toggle'},
  {key:'hooks',label:'Hooks',kind:'toggle'},
  {key:'flow',label:'Flow',kind:'range',min:0,max:1,step:.05},
  {key:'voice',label:'Voice',kind:'range',min:0,max:1,step:.05},
];
export function lookParam(look:Look,key:LookParamKey):string|number|boolean{
  switch(key){
    case 'ink':return look.palette.text;case 'accent':return look.palette.accent;case 'card':return look.palette.card||'#2f6bff';
    case 'cards':return !!look.card;case 'font':return look.font.hero;case 'body':return look.font.body;
    case 'case':return look.font.heroCase||'as-is';case 'layout':return look.layout;case 'scale':return look.scale??1;
    case 'motion':return look.intensity??1;case 'glow':return look.optics.glow||0;case 'outline':return look.outlineWidth??0;
    case 'halo':return look.halo??0;case 'soft':return look.optics.blur||0;case 'scroll':return look.motion==='marquee';
    case 'hooks':return look.quiet==='hooks-only';case 'flicker':return look.flicker??0;case 'drips':return look.drips??.5;case 'light':return look.light??.8;case 'tubes':return look.finish==='neon';
    case 'flow':return look.fields?.motion??0;case 'voice':return look.fields?.voice??0;
  }
}
type Overrides=NonNullable<LookRef['overrides']>;
/** The overrides patch for one param (deep parts merged by setLookOverrides). */
export function lookParamPatch(look:Look,key:LookParamKey,v:string|number|boolean):Overrides{
  switch(key){
    case 'ink':return {palette:{text:String(v)} as Look['palette']};case 'accent':return {palette:{accent:String(v)} as Look['palette']};
    case 'card':return {palette:{card:String(v)} as Look['palette'],card:true};case 'cards':return v&&!look.palette.card?{card:true,palette:{card:'#2f6bff'} as Look['palette']}:{card:!!v};
    case 'font':return {font:{hero:String(v)} as Look['font']};case 'body':return {font:{body:String(v)} as Look['font']};
    case 'case':return {font:{heroCase:v,bodyCase:v} as Look['font']};case 'layout':return {layout:v as Look['layout']};
    case 'scale':return {scale:Number(v)};case 'motion':return {intensity:Number(v)};case 'glow':return {optics:{glow:Number(v)}};
    case 'outline':return {outlineWidth:Number(v)};case 'halo':return {halo:Number(v)};case 'soft':return {optics:{blur:Number(v)}};
    case 'scroll':return {motion:v?'marquee':'none'};case 'hooks':return {quiet:v?'hooks-only':'none'};
    case 'flicker':return {flicker:Number(v)};case 'drips':return {drips:Number(v)};case 'light':return {light:Number(v)};case 'tubes':return {finish:v?'neon':null};
    case 'flow':return {fields:{...look.fields,motion:Number(v)}};case 'voice':return {fields:{...look.fields,voice:Number(v)}};
  }
}
export function setLookParam(p:Project,key:LookParamKey,v:string|number|boolean):Project{
  const look=lookOf(p);if(!look)return p;return setLookOverrides(p,lookParamPatch(look,key,v));
}

// ---------- mutators (pure) ----------
export function setLook(p:Project,id:LookId|null,overrides?:LookRef['overrides']):Project{
  return {...p,look:!id||id==='default'?null:{id,overrides:overrides??null}};
}
/** Merge into project.look.overrides (palette / font / optics / verse merge one level deep). */
export function setLookOverrides(p:Project,partial:NonNullable<LookRef['overrides']>):Project{
  if(!p.look)return p;const cur=p.look.overrides||{};const out:Record<string,unknown>={...cur,...partial};
  for(const k of ['palette','font','optics','verse'] as const)if(partial[k]&&cur[k])out[k]={...cur[k],...partial[k]};
  return {...p,look:{...p.look,overrides:out as NonNullable<LookRef['overrides']>}};
}
export function clearLookOverrides(p:Project):Project{return p.look?{...p,look:{...p.look,overrides:null}}:p;}
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
