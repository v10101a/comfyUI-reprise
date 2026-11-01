// Song clip (media.audioClip): trim the song to [in,out) and play it from project time `offset`.
// Words live in project time; beats.json / voice.json stay in song time and map through shift = offset − in.
import type {AudioClip,Project} from './types';

export type Clip = AudioClip;
const clamp=(v:number,a:number,b:number)=>Math.max(a,Math.min(b,v));
/** The media the song comes from (the studio plays audio, else the video's own track). */
export const songRef=(p:Project)=>p.media.audio||p.media.video||null;
export const songDuration=(p:Project)=>songRef(p)?.duration||p.duration;
/** Resolved clip: absent → whole song at 0. */
export function clipOf(p:Project,dur=songDuration(p)):Clip{
  const c=p.media.audioClip;if(!c)return {in:0,out:dur,offset:0};
  const i=clamp(c.in||0,0,Math.max(0,dur-.05));return {in:i,out:clamp(c.out??dur,i+.05,dur),offset:c.offset||0};
}
export const shiftOf=(c:Clip)=>c.offset-c.in;
/** Project seconds → song seconds (no clip: identity). */
export const toSong=(p:Project,t:number)=>p.media.audioClip?t-shiftOf(clipOf(p)):t;
/** Is the song audible at project time t? */
export const audibleAt=(p:Project,t:number)=>{if(!p.media.audioClip)return true;const c=clipOf(p);const s=t-shiftOf(c);return s>=c.in&&s<c.out;};
const r3=(v:number)=>+v.toFixed(3);
/** Set (or clear, when it equals the whole song at 0) the clip. */
export function setClip(p:Project,c:Clip|null,dur=songDuration(p)):Project{
  const whole=!c||(c.in<=.001&&c.out>=dur-.001&&Math.abs(c.offset)<.001);
  const media={...p.media};if(whole)delete media.audioClip;else media.audioClip={in:r3(c!.in),out:r3(c!.out),offset:r3(c!.offset)};
  return {...p,media};
}
/** Song-time beat grid → project time, keeping only beats inside the clip. */
export function mapBeats<B extends {beats:number[];downbeats?:number[];sections?:{start:number;end:number;label?:string}[]}>(b:B|undefined,c:Clip|null):B|undefined{
  if(!b||!c)return b;const sh=shiftOf(c);const keep=(x:number)=>x>=c.in-1e-3&&x<=c.out+1e-3;
  return {...b,beats:b.beats.filter(keep).map(x=>x+sh),downbeats:b.downbeats?.filter(keep).map(x=>x+sh),
    sections:b.sections?.filter(s=>s.end>c.in&&s.start<c.out).map(s=>({...s,start:Math.max(s.start,c.in)+sh,end:Math.min(s.end,c.out)+sh}))};
}

/** Move: the clip slides along the project timeline (offset changes, same song section). Keeps ≥ .1 s audible. */
export function moveClip(c0:Clip,offset:number,dur:number):Clip{const len=c0.out-c0.in;return {...c0,offset:+Math.max(.1-len,Math.min(dur-.1,offset)).toFixed(3)};}
/** Slip: the clip stays put; which part of the song plays under it changes (in/out move together). */
export function slipClip(c0:Clip,ds:number,songDur:number):Clip{
  const d=Math.max(-c0.in,Math.min(songDur-.1-c0.in,ds));return {in:+(c0.in+d).toFixed(3),out:+Math.min(songDur,c0.out+d).toFixed(3),offset:c0.offset};
}
/** Song-time shift change between two clips (what linked words move by). */
export const shiftDelta=(a:Clip,b:Clip)=>shiftOf(b)-shiftOf(a);
/** Linked words: every word moves rigidly by dt from its position when the gesture began; durations never change
 *  (a word pushed off the project range keeps its length and is simply not on screen). */
export function shiftWords(p:Project,words0:Map<string,[number,number]>,dt:number):Project{
  if(Math.abs(dt)<1e-6)return {...p,words:p.words.map(w=>{const o=words0.get(w.id);return o?{...w,start:o[0],end:o[1]}:w;})};
  return {...p,words:p.words.map(w=>{const o=words0.get(w.id);return o?{...w,start:+(o[0]+dt).toFixed(4),end:+(o[1]+dt).toFixed(4)}:w;})};
}
