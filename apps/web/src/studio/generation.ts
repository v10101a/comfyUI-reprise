import type {GenerationDraft,Project,Word} from '../types';

export const LETTERING_STARTERS=[
  {name:'Paint',text:'Large painted letters on the wall behind the person. Let the surface texture and existing light show through the paint.'},
  {name:'Neon',text:'A practical neon sign mounted on the wall behind the person. Coloured glass tubes, a restrained glow and reflected light that fits the scene.'},
  {name:'Chrome',text:'Solid chrome letters standing in the open space behind the person. Believable weight, contact shadows and reflections of the existing scene.'},
  {name:'Poster',text:'A paper poster pasted onto the wall behind the person. Bold printed lettering, slightly uneven paper edges and shadows that match the scene.'},
] as const;
export const CAMERAS={
  locked:{label:'Locked',text:'The camera holds a static shot. Keep the framing and lens unchanged.'},
  push:{label:'Slow push in',text:'The camera pushes in slowly with small amplitude. Keep the lettering fully inside the frame.'},
  pull:{label:'Slow pull out',text:'The camera pulls out slowly with small amplitude, revealing a little more of the existing scene.'},
  follow:{label:'Gentle follow',text:'The camera follows the subject gently with small amplitude. Keep the lettering readable and in frame.'},
  custom:{label:'Describe below',text:''},
} as const;
export const DEFAULT_LETTERING=LETTERING_STARTERS[0].text;
export const DEFAULT_MOTION='Small natural movement in the scene. A light breeze moves hair and loose clothing. The person stays in the same pose, with lips gently closed.';

export function directionFor(p:Project,lineId:string):GenerationDraft{
  const saved=p.lineMeta?.[lineId]?.generation;
  if(saved)return saved;
  const ids=new Set(p.words.filter(w=>w.lineId===lineId).map(w=>w.id));
  const previous=[...p.shots].reverse().find(s=>s.wordIds.some(id=>ids.has(id)));
  return previous?.prompt?{lettering:previous.prompt}:{};
}

export function setDirection(p:Project,lineId:string,patch:Partial<GenerationDraft>):Project{
  const generation={...directionFor(p,lineId),...patch};
  for(const key of Object.keys(generation) as (keyof GenerationDraft)[])if(generation[key]===undefined)delete generation[key];
  return {...p,lineMeta:{...p.lineMeta,[lineId]:{...p.lineMeta?.[lineId],generation}}};
}

export function generationPlan(p:Project,selected:Word){
  const draft=directionFor(p,selected.lineId);
  const words=draft.scope==='word'?[selected]:p.words.filter(w=>w.lineId===selected.lineId).sort((a,b)=>a.start-b.start);
  const first=Math.min(...words.map(w=>w.start)),last=Math.max(...words.map(w=>w.end));
  const start=Number.isFinite(draft.start)?draft.start!:first;
  const duration=Number.isFinite(draft.duration)?draft.duration!:Math.max(2,Math.min(10,last-first));
  const end=Math.min(p.duration,start+duration);
  const lettering=draft.lettering??DEFAULT_LETTERING;
  const motion=draft.motion??DEFAULT_MOTION;
  const camera=CAMERAS[draft.camera||'locked']??CAMERAS.locked;
  const motionPrompt=[camera.text,motion.trim()].filter(Boolean).join(' ');
  const text=words.map(w=>w.text).join(' ');
  const reason=!p.media.video?'Add footage first.':!text.trim()?'Choose words for the lettering.':
    !Number.isFinite(start)||start<0||start>=p.duration?'Choose a start inside the video.':
    !Number.isFinite(duration)||duration<1.2||duration>10?'Choose a length from 1.2 to 10 seconds.':
    end-start<1.2-1e-6?'Move the start earlier to leave at least 1.2 seconds.':
    !lettering.trim()?'Describe the lettering or choose a starting point.':
    draft.camera==='custom'&&!motion.trim()?'Describe the camera and movement.':
    draft.seed!=null&&(!Number.isInteger(draft.seed)||draft.seed<0||draft.seed>2147483647)?'Seed must be a whole number from 0 to 2147483647.':'';
  return {draft,text,start,end,duration,reason,body:{wordIds:words.map(w=>w.id),text,prompt:lettering.trim(),
    motionPrompt,start,end,engine:'remote-minimax' as const,longEdge:draft.longEdge??1344,
    ...(draft.referenceImage?{referenceImage:draft.referenceImage,guideFirstFrame:true}:{}),
    ...(draft.seed!=null?{seed:draft.seed}:{})}};
}
