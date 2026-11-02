import type {Project,Word,LineMeta} from '../types';

/** Nudge whole lines and/or single words by n frames (Premiere ⌥←/→), rigidly, clamped to the project. */
export function nudgeText(p:Project,lineIds:string[],wordIds:string[],frames:number):TextEdit|null{
  const lines=new Set(lineIds),ids=new Set(wordIds);const hit=p.words.filter(w=>lines.has(w.lineId)||ids.has(w.id));if(!hit.length||!frames)return null;
  const start=Math.min(...hit.map(w=>w.start));const moved=new Map(dragTextTiming(hit,'move',start+frames/p.fps,p.duration,p.fps).map(w=>[w.id,w]));
  return {project:{...p,words:p.words.map(w=>moved.get(w.id)??w)},lineIds:[...lines],wordId:wordIds[0]??''};
}
/** A copied text selection is a snapshot, independent of subsequent edits. */
export type TextClipboard={projectId:string;words:Word[];meta:Record<string,LineMeta>;start:number;end:number};
export type TextEdit={project:Project;lineIds:string[];wordId:string};
const clone=<T,>(value:T):T=>structuredClone(value);
const stamp=(t:number)=>+t.toFixed(6);

/** Move a text clip rigidly, or trim one boundary. Trimming keeps every word and at least one frame per word
 * (already shorter words keep their minimum span); it never stretches the other boundary or retimes the interior. */
export function dragTextTiming(words:Word[],kind:'move'|'start'|'end',at:number,duration:number,fps:number):Word[]{
  if(!words.length||!Number.isFinite(at))return words;
  const start=Math.min(...words.map(w=>w.start)),end=Math.max(...words.map(w=>w.end));
  const minSpan=(w:Word)=>Math.min(1/fps,w.end-w.start);
  if(kind==='move'){
    const delta=Math.max(-start,Math.min(duration-end,at-start));
    return words.map(w=>({...w,start:stamp(w.start+delta),end:stamp(w.end+delta)}));
  }
  if(kind==='start'){
    const next=Math.max(0,Math.min(at,...words.map(w=>w.end-minSpan(w))));
    return words.map(w=>({...w,start:stamp(w.start===start||w.start<next?next:w.start)}));
  }
  const next=Math.min(duration,Math.max(at,...words.map(w=>w.start+minSpan(w))));
  return words.map(w=>({...w,end:stamp(w.end===end||w.end>next?next:w.end)}));
}

export function copyText(p:Project,lineIds:string[]):TextClipboard|null{
  const ids=new Set(lineIds);const words=p.words.filter(w=>ids.has(w.lineId));if(!words.length)return null;
  return {projectId:p.id,words:clone(words),meta:clone(Object.fromEntries(lineIds.filter(id=>p.lineMeta?.[id]).map(id=>[id,p.lineMeta![id]]))),
    start:Math.min(...words.map(w=>w.start)),end:Math.max(...words.map(w=>w.end))};
}

/** Paste complete clips at the playhead; clamp the group together at the end of the project. */
export function pasteText(p:Project,clip:TextClipboard,time:number,id:()=>string=()=>crypto.randomUUID()):TextEdit|null{
  const span=clip.end-clip.start;if(clip.projectId!==p.id||span>p.duration||!Number.isFinite(time))return null;
  const delta=Math.max(0,Math.min(p.duration-span,time))-clip.start;
  const lines=new Map([...new Set(clip.words.map(w=>w.lineId))].map(old=>[old,id()]));
  const words=new Map(clip.words.map(w=>[w.id,id()]));
  const added=clip.words.map(w=>({...clone(w),id:words.get(w.id)!,lineId:lines.get(w.lineId)!,start:stamp(w.start+delta),end:stamp(w.end+delta)}));
  const meta={...p.lineMeta};
  for(const [old,next] of lines){const m=clip.meta[old];if(m)meta[next]={...clone(m),heroWordId:m.heroWordId?words.get(m.heroWordId)??null:m.heroWordId};}
  // Generated shots refer to word IDs and time spans; retain their asset reference for a pasted in-world clip.
  const shots=p.shots.filter(s=>s.wordIds.some(w=>words.has(w))).map(s=>({...clone(s),id:id(),wordIds:s.wordIds.filter(w=>words.has(w)).map(w=>words.get(w)!),
    start:stamp(s.start+delta),end:stamp(s.end+delta)}));
  for(const shot of shots)for(const w of added)if(shot.wordIds.includes(w.id))w.shotId=shot.id;
  return {project:{...p,words:[...p.words,...added].sort((a,b)=>a.start-b.start),lineMeta:meta,shots:[...p.shots,...shots]},lineIds:[...lines.values()],wordId:added[0].id};
}

/** Split each selected text clip on the frame grid. A word crossing the cut exists in both halves. */
export function splitText(p:Project,lineIds:string[],time:number,id:()=>string=()=>crypto.randomUUID()):TextEdit|null{
  const at=stamp(Math.round(time*p.fps)/p.fps);const selected=new Set(lineIds);
  const groups=new Map<string,Word[]>();for(const w of p.words)if(selected.has(w.lineId)){const ws=groups.get(w.lineId)||[];ws.push(w);groups.set(w.lineId,ws);}
  const cuts=new Map([...groups].filter(([,ws])=>!ws.some(w=>w.placement==='inworld')&&at>Math.min(...ws.map(w=>w.start))+1e-6&&at<Math.max(...ws.map(w=>w.end))-1e-6).map(([old])=>[old,id()]));
  if(!cuts.size)return null;
  const rightIds=new Map<string,string>();const words:Word[]=[];
  for(const w of p.words){const next=cuts.get(w.lineId);if(!next){words.push(w);continue;}
    if(w.start<at)words.push({...w,end:Math.min(w.end,at)});
    if(w.end>at){const right=w.start>=at?w.id:id();rightIds.set(w.id,right);words.push({...clone(w),id:right,lineId:next,start:Math.max(w.start,at)});}}
  const meta={...p.lineMeta};for(const [old,next] of cuts){const m=p.lineMeta?.[old];if(!m)continue;
    meta[next]={...clone(m),heroWordId:m.heroWordId?rightIds.get(m.heroWordId)??null:m.heroWordId};
    if(m.heroWordId&&!words.some(w=>w.lineId===old&&w.id===m.heroWordId))meta[old]={...m,heroWordId:null};}
  const ids=[...cuts.values()];return {project:{...p,words,lineMeta:meta},lineIds:ids,wordId:words.find(w=>ids.includes(w.lineId))!.id};
}

/** Delete whole lines and/or single words (a line whose last word goes is gone too); drops their line meta. */
export function deleteText(p:Project,lineIds:string[],wordIds:string[]=[]):TextEdit|null{
  const lines=new Set(lineIds),words=new Set(wordIds);const kept=p.words.filter(w=>!lines.has(w.lineId)&&!words.has(w.id));
  if(kept.length===p.words.length)return null;
  const live=new Set(kept.map(w=>w.lineId));const meta={...(p.lineMeta||{})};
  for(const id of Object.keys(meta)){if(!live.has(id))delete meta[id];else if(meta[id].heroWordId&&words.has(meta[id].heroWordId!))meta[id]={...meta[id],heroWordId:null};}
  // Next selection: the next word in the same line, else nothing.
  const gone=p.words.find(w=>lines.has(w.lineId)||words.has(w.id));const next=gone&&kept.find(w=>w.lineId===gone.lineId&&w.start>=gone.start);
  return {project:{...p,words:kept,lineMeta:meta},lineIds:[],wordId:next?.id||''};
}

/** What a new text clip is, per timeline track (group). */
export type NewTextKind = 'captions'|'hooks'|'behind'|'wall'|'hud'|'inworld';
/** A one-word line at `time` on a track; the studio opens it for inline typing. */
export function addText(p:Project,time:number,kind:NewTextKind,text='text',id:()=>string=()=>crypto.randomUUID()):TextEdit|null{
  if(p.duration<=0)return null;const start=stamp(Math.max(0,Math.min(time,p.duration-.1)));const end=stamp(Math.min(p.duration,start+.8));
  const wall=p.surfaces?.[0]?.id;
  const placement:Word['placement']=kind==='behind'?'behind':kind==='hud'?'anchor':kind==='wall'&&wall?'surface':'overlay';
  const word:Word={id:id(),text,start,end,lineId:id(),placement,preset:kind==='hud'?'hud':'pop',
    ...(placement==='surface'?{surfaceId:wall}:{}),...(placement==='anchor'?{anchor:{trackId:'person0',dx:0,dy:-.1}}:{})};
  const meta=kind==='hooks'?{...(p.lineMeta||{}),[word.lineId]:{hook:true}}:p.lineMeta;
  return {project:{...p,words:[...p.words,word].sort((a,b)=>a.start-b.start),lineMeta:meta},lineIds:[word.lineId],wordId:word.id};
}

/** Typed text for one word: several words share its time span evenly; empty deletes it. */
export function setWordText(p:Project,wordId:string,text:string,id:()=>string=()=>crypto.randomUUID()):TextEdit|null{
  const w=p.words.find(x=>x.id===wordId);if(!w)return null;const parts=text.trim().split(/\s+/).filter(Boolean);
  if(!parts.length)return deleteText(p,[],[wordId]);
  if(parts.length===1)return {project:{...p,words:p.words.map(x=>x.id===wordId?{...x,text:parts[0]}:x)},lineIds:[w.lineId],wordId};
  const span=(w.end-w.start)/parts.length;
  const made=parts.map((t,i)=>({...clone(w),id:i?id():w.id,text:t,start:stamp(w.start+span*i),end:stamp(i===parts.length-1?w.end:w.start+span*(i+1))}));
  return {project:{...p,words:p.words.flatMap(x=>x.id===wordId?made:[x])},lineIds:[w.lineId],wordId};
}
