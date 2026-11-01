// The perception/generation pipeline as the studio shows it: which analysis ran, on which engine, how long it took.
// Job records come from GET /api/jobs?projectId=… (kind, status, message, result.elapsedSeconds, createdAt).
import type {Project,Job} from '../types';
import {at} from '../base';

export type Engine = 'comfy'|'cpu'|'remote'|'browser';
export type StepId = 'words'|'matte'|'occupancy'|'surface'|'reframe'|'beats'|'flow'|'audio'|'voice'|'generate';
export type JobRecord = Job & {createdAt?:string|null;updatedAt?:string|null};
export type StepState = 'done'|'running'|'failed'|'fallback'|'idle'|'n/a';

export type StepDef = {
  id:StepId;title:string;model:string;engine:Engine;
  /** ComfyUI node chain (class_type) as it appears in the workflow JSON. */
  nodes:string[];
  /** Workflow JSON served by the editor (copies of repo workflows/ in public/workflows) + the repo path. */
  workflow?:{href:string;repo:string};
  jobKinds:string[];
  produces:string;
};

export const STEPS:StepDef[] = [
  {id:'words',title:'Words',model:'Lyric forced alignment: HDemucs vocals → MMS_FA CTC (Whisper without lyrics / on failure)',engine:'comfy',nodes:['LoadAudio','TypesetAlignLyrics','SaveTextFile','SaveImage'],
    workflow:{href:at('/workflows/align.api.json'),repo:'workflows/align.api.json'},jobKinds:['words'],produces:'analysis/words.json → editable words'},
  {id:'matte',title:'Subject matte',model:'BiRefNet general + hole fill + mask→tracks',engine:'comfy',nodes:['LoadVideo','GetVideoComponents','BiRefNetRMBG','TypesetMatteRefine','SaveImage','MaskToTracks','SaveTextFile'],
    workflow:{href:at('/workflows/matte.api.json'),repo:'workflows/matte.api.json'},jobKinds:['matte'],produces:'fg.webm alpha cutout + person tracks'},
  {id:'occupancy',title:'Occupancy',model:'matte → 32×18 coverage grid',engine:'comfy',nodes:['TypesetLoadImageSequence','TypesetOccupancyGrid','SaveTextFile'],
    workflow:{href:at('/workflows/occupancy.api.json'),repo:'workflows/occupancy.api.json'},jobKinds:['occupancy'],produces:'where the subject is not — drives auto-placement'},
  {id:'surface',title:'Planar track',model:'LK flow + RANSAC homography',engine:'comfy',nodes:['LoadVideo','GetVideoComponents','TypesetLoadImageSequence','TypesetPlanarTrack','SaveTextFile'],
    workflow:{href:at('/workflows/surface_track.api.json'),repo:'workflows/surface_track.api.json'},jobKinds:['surface'],produces:'wall quads that stay on the wall'},
  {id:'reframe',title:'Reframe 9:16',model:'subject-follow crop, damped spring',engine:'comfy',nodes:['TypesetReframeCrop','SaveTextFile'],
    workflow:{href:at('/workflows/reframe.api.json'),repo:'workflows/reframe.api.json'},jobKinds:['reframe'],produces:'vertical project + crop.json'},
  {id:'beats',title:'Beats',model:'librosa beat grid, bars + sections',engine:'comfy',nodes:['LoadAudio','TypesetBeatGrid','SaveTextFile','SaveImage'],
    workflow:{href:at('/workflows/beats.api.json'),repo:'workflows/beats.api.json'},jobKinds:['beats'],produces:'analysis/beats.json → timeline grid + snap'},
  {id:'flow',title:'Motion field',model:'DIS optical flow → coarse field (CPU, no weights)',engine:'comfy',nodes:['LoadVideo','GetVideoComponents','TypesetFlowField','SaveTextFile'],
    workflow:{href:at('/workflows/flow.api.json'),repo:'workflows/flow.api.json'},jobKinds:['flow'],produces:'analysis/flow.json → look · flow pushes the type'},
  {id:'audio',title:'Audio field',model:'mix STFT → 40–140 Hz energy (dB, percentile-normalised) → instant attack, 250 ms release',engine:'comfy',nodes:['LoadAudio','TypesetAudioField','SaveTextFile','SaveImage'],
    workflow:{href:at('/workflows/audio.api.json'),repo:'workflows/audio.api.json'},jobKinds:['audio'],produces:'analysis/audio_<job>.json → look · audio pulses the type'},
  {id:'voice',title:'Voice field',model:'HDemucs vocals → loudness, pYIN pitch, vibrato, onsets',engine:'comfy',nodes:['LoadAudio','TypesetVoiceField','SaveTextFile','SaveImage'],
    workflow:{href:at('/workflows/voice.api.json'),repo:'workflows/voice.api.json'},jobKinds:['voice'],produces:'analysis/voice.json → look · voice moves the type'},
  {id:'generate',title:'In-world shot',model:'Qwen edit writes the line into the frame (local) → MiniMax H3 I2V (remote 4090)',engine:'comfy',nodes:['LoadImage','TypesetTextPlate','LTXVImgToVideo','SamplerCustom','VAEDecode','VHS_VideoCombine'],
    workflow:{href:at('/workflows/ltx_i2v.api.json'),repo:'workflows/ltx_i2v.api.json'},jobKinds:['inworld'],produces:'generated shot with the word in the world'},
];

export type StepStatus = {state:StepState;path:string;engineNote:string;seconds?:number;message?:string;progress?:number;job?:JobRecord;count?:number};

const secs=(j?:JobRecord)=>{const r=j?.result as {elapsedSeconds?:number;timings?:{total?:number}}|undefined;if(r?.elapsedSeconds!=null)return r.elapsedSeconds;if(r?.timings?.total!=null)return r.timings.total;
  if(j?.createdAt&&j.updatedAt&&j.status!=='running'&&j.status!=='queued')return (Date.parse(j.updatedAt)-Date.parse(j.createdAt))/1000;return undefined;};

/** Latest job per kind (jobs list is newest first from the server, but sort anyway). */
export function latestJobs(jobs:JobRecord[]){
  const sorted=[...jobs].sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||''));
  const out=new Map<string,JobRecord>();for(const j of sorted)if(!out.has(j.kind))out.set(j.kind,j);return out;
}

/**
 * Derive each step's status from the project's analysis fields + job history. `occKind` comes from the renderer
 * (occupancy | tracks | none) and tells whether auto-placement uses the server grid or a fallback.
 */
export function stepStatus(step:StepDef,p:Project,jobs:Map<string,JobRecord>,ctx:{occKind?:string;hasBeats:boolean;beatsNote?:string;comparing:boolean}):StepStatus{
  const job=step.jobKinds.map(k=>jobs.get(k)).find(Boolean);
  const live=job&&(job.status==='running'||job.status==='queued');
  const base={job,seconds:secs(job),message:job?.message||undefined,progress:job?.progress??undefined};
  // Jobs report which path ran (result.engine: 'comfy' | 'fallback'). Runs from before the Comfy port report nothing.
  const ran=(job?.result as {engine?:string}|undefined)?.engine;
  const via=(ok:StepStatus):StepStatus=>ran==='fallback'?{...ok,state:'fallback',path:'OpenCV fallback',engineNote:job?.message?.replace(/^.*?—\s*/,'')||'ComfyUI unavailable'}:
    ran==='comfy'?{...ok,path:'ComfyUI'}:job&&step.id!=='words'&&step.id!=='matte'&&step.id!=='generate'?{...ok,path:'server',engineNote:`${ok.engineNote} · in-process run`}:ok;
  if(live)return {...base,state:'running',path:step.engine==='comfy'?'ComfyUI':'server',engineNote:job!.status};
  if(p.id==='sample')return {...base,state:'n/a',path:'bundled sample',engineNote:'offline sample — precomputed'};
  switch(step.id){
    case 'words':
      if(p.analysis.words){
        // Server result: engine 'align' (TypesetAlignLyrics) | 'whisper' (WhisperWords), plus note and lowConfidence.
        const r=(job?.result||{}) as {engine?:string;lowConfidence?:number;note?:string};const low=r.lowConfidence||0;
        const note=r.engine==='align'?`forced alignment (HDemucs → MMS_FA)${low?` · ${low} low-confidence to ear-check`:''}`:
          r.engine==='whisper'?(r.note?.includes('failed')?'Whisper (lyric alignment failed)':'Whisper word timings'):'word timings';
        return {...base,state:r.engine==='whisper'&&p.media.lyrics?'fallback':'done',path:'ComfyUI',engineNote:note,count:p.words.length};}
      if(job?.status==='failed')return {...base,state:'failed',path:'ComfyUI',engineNote:'failed'};
      return p.words.length?{...base,state:'fallback',path:'authored',engineNote:'words typed by hand',count:p.words.length}:{...base,state:'idle',path:'—',engineNote:'not run'};
    case 'matte':
      if(p.analysis.matte)return {...base,state:'done',path:'ComfyUI',engineNote:p.analysis.tracks?'cutout + person tracks':'cutout'};
      if(job?.status==='failed')return {...base,state:'failed',path:'ComfyUI',engineNote:'failed'};
      return {...base,state:'idle',path:'—',engineNote:'not run · behind needs it'};
    case 'occupancy':
      if(p.analysis.occupancy)return via({...base,state:'done',path:'ComfyUI',engineNote:'from the matte'});
      if(ctx.occKind==='occupancy')return {...base,state:'fallback',path:'fixture',engineNote:'local fixture grid'};
      if(ctx.occKind==='tracks')return {...base,state:'fallback',path:'browser',engineNote:'coarse grid from track boxes'};
      return {...base,state:'idle',path:'—',engineNote:'needs a matte'};
    case 'surface':{
      const s=p.surfaces||[];if(!s.length)return {...base,state:'idle',path:'—',engineNote:'draw a wall on the stage'};
      const tracked=s.filter(x=>x.status==='tracked').length;
      if(tracked)return via({...base,state:'done',path:'ComfyUI',engineNote:`${tracked}/${s.length} walls tracked`,count:s.length});
      return {...base,state:'fallback',path:'static',engineNote:`${s.length} drawn, untracked`,count:s.length};}
    case 'reframe':
      if(p.frame?.crop)return via({...base,state:'done',path:'ComfyUI',engineNote:`${p.frame.aspect} crop.json`});
      if(ctx.comparing)return {...base,state:'fallback',path:'browser',engineNote:'client 9:16 preview'};
      return {...base,state:'idle',path:'—',engineNote:'Make vertical to run'};
    case 'beats':
      if(ctx.hasBeats)return via({...base,state:'done',path:'ComfyUI',engineNote:ctx.beatsNote||'beat grid on the timeline'});
      return {...base,state:'idle',path:'—',engineNote:'no beats.json yet'};
    case 'flow':
      if(p.analysis.flow)return via({...base,state:'done',path:'ComfyUI',engineNote:'motion field · look → flow'});
      return {...base,state:'idle',path:'—',engineNote:job?.status==='failed'?'failed':'not run · optional'};
    case 'audio':
      if(p.analysis.audio)return via({...base,state:'done',path:'ComfyUI',engineNote:'low-band pulse · look → audio'});
      return {...base,state:job?.status==='failed'?'failed':'idle',path:'—',engineNote:job?.status==='failed'?'failed':'not run · optional'};
    case 'voice':
      if(p.analysis.voice)return {...base,state:'done',path:'ComfyUI',engineNote:'voice field · look → voice'};
      return {...base,state:job?.status==='failed'?'failed':'idle',path:job?.status==='failed'?'ComfyUI':'—',engineNote:job?.status==='failed'?'failed':'not run · optional'};
    case 'generate':{
      const shots=p.shots||[];const done=shots.filter(s=>s.status==='done');
      if(done.length)return {...base,state:'done',path:done.some(s=>/minimax/i.test(s.workflow))?'ComfyUI · remote':'ComfyUI',engineNote:`${done.length} shot${done.length>1?'s':''} · ${done[0].workflow}`,count:done.length};
      if(shots.some(s=>s.status==='failed'))return {...base,state:'failed',path:'ComfyUI',engineNote:'last shot failed'};
      return {...base,state:'idle',path:'—',engineNote:'optional · select In-world'};}
  }
}

/** beats.json is written by a ComfyUI AudioBeatMarkers job. Accept a bare list or {beats, bpm, downbeats, sections}. */
export type Beats = {beats:number[];bpm?:number;downbeats?:number[];sections?:{start:number;end:number;label?:string}[]};
export function parseBeats(raw:unknown):Beats|undefined{
  if(Array.isArray(raw)&&raw.every(n=>typeof n==='number'))return {beats:raw as number[]};
  if(raw&&typeof raw==='object'){const o=raw as Record<string,unknown>;const beats=Array.isArray(o.beats)?(o.beats as unknown[]).map(b=>typeof b==='number'?b:(b as {t?:number;time?:number})?.t??(b as {time?:number})?.time).filter((n):n is number=>typeof n==='number'):[];
    if(beats.length)return {beats,bpm:typeof o.bpm==='number'?o.bpm:undefined,downbeats:Array.isArray(o.downbeats)?o.downbeats as number[]:undefined,sections:Array.isArray(o.sections)?o.sections as Beats['sections']:undefined};}
  return undefined;
}
