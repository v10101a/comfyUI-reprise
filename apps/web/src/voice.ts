/** analysis/voice.json (TypesetVoiceField): per video frame, vocal loudness 0..1, pitch (MIDI, null = unvoiced),
 *  vibrato 0..1 and onset strength 0..1. */
export type VoiceDoc = {fps:number;frames:number;loud:(number|null)[];pitch:(number|null)[];vibrato:(number|null)[];onset:(number|null)[];
  /** Song second of frame 0 (the audioClip's in; absent = 0). */
  t0?:number};
/** analysis/audio_<job>.json (TypesetAudioField): the mix's low band (kick/bass), instant attack / slow release, 0..1 per
 *  video frame; level[f] is the peak over song seconds [t0 + f/fps, t0 + (f+1)/fps), already led by leadFrames. */
export type AudioDoc = {kind:'bass';fps:number;frames:number;band:[number,number];level:number[];t0?:number};

/** What the voice does to one word at time t (all deterministic in t). */
export type VoiceMods = {
  /** Added to the font weight (variable fonts move smoothly; static faces snap to the nearest weight). */
  weight:number;
  /** Horizontal / vertical scale: belted notes widen, onsets kick. */
  sx:number;sy:number;
  /** Baseline shift in units of the word's size (negative = up); 0 today: the voice drives size only. */
  dy:number;
};

const SMOOTH=4;

export const NO_VOICE:VoiceMods={weight:0,sx:1,sy:1,dy:0};

/** The voice as a field: the type swells with the singer. */
export class VoiceField {
  constructor(readonly doc:VoiceDoc){}
  private val(a:(number|null)[],t:number):number|null{
    const x=(this.doc.t0?t-this.doc.t0:t)*this.doc.fps,i=Math.floor(x),k=x-i;const a0=a[i]??null,a1=a[i+1]??null;
    if(a0===null)return a1===null||k<.5?null:a1;if(a1===null)return a0;return a0+(a1-a0)*k;
  }
  /** Gaussian-smoothed over ±SMOOTH frames: the letters breathe with the phrase instead of twitching per frame. */
  private smooth(a:(number|null)[],t:number):number|null{
    let s=0,w=0;for(let k=-SMOOTH;k<=SMOOTH;k++){const v=this.val(a,t+k/this.doc.fps);if(v===null)continue;const g=Math.exp(-k*k/(2*(SMOOTH/2)**2));s+=v*g;w+=g;}
    return w>0?s/w:null;
  }
  loud(t:number){return this.smooth(this.doc.loud,t)??0;}
  pitch(t:number){return this.smooth(this.doc.pitch,t);}
  /** Onset envelope: each attack decays over ~0.15 s, so the kick reads as a pulse, not a one-frame flash. */
  private kick(t:number){let m=0;for(let i=0;i<8;i++){const v=this.val(this.doc.onset,t-i/this.doc.fps)??0;m=Math.max(m,v*Math.exp(-i/(.15*this.doc.fps)));}return m;}
  /** Median voiced pitch over [t0, t1): the line's reference, so the melody moves around the authored position. */
  refPitch(t0:number,t1:number):number|null{
    const o=this.doc.t0||0;const f0=Math.max(0,Math.floor((t0-o)*this.doc.fps)),f1=Math.min(this.doc.frames,Math.ceil((t1-o)*this.doc.fps));
    const ps=this.doc.pitch.slice(f0,f1).filter((p):p is number=>p!==null).sort((a,b)=>a-b);return ps.length?ps[ps.length>>1]:null;
  }
  /** Modifiers for a word sung over [start, end) on a line whose reference pitch is ref, at time t; amount 0..1. */
  mods(t:number,start:number,end:number,ref:number|null,amount:number):VoiceMods{
    if(amount<=0||t<start)return NO_VOICE;
    // A word keeps the voice it ended with (no snap back while the line stays up), easing out over 0.4 s.
    const tt=Math.min(t,end),hold=t>end?Math.exp(-(t-end)/.4):1;
    const loud=this.loud(tt)*hold,p=this.pitch(tt),vib=(this.smooth(this.doc.vibrato,tt)??0)*hold,on=this.kick(tt)*hold;
    // Size only: the word swells with loudness (weight + scale) and pulses on attacks; it never moves off its line
    // (pitch/vibrato baseline motion read as jitter). Pitch and vibrato stay in the field for future use.
    void p;void vib;void ref;
    const grow=.14*(loud-.45)+.07*on;
    return {weight:amount*500*(loud-.45),sx:1+amount*grow,sy:1+amount*grow,dy:0};
  }
}

/** The mix's low band as a field: each word's size pulses with the kick and bass (size only, no weight change). */
export class AudioField {
  constructor(readonly doc:AudioDoc){}
  /** Frame value, held for the whole frame (no interpolation: a hit never starts rising before its frame). */
  private val(t:number){const a=this.doc.level,i=Math.floor((t-(this.doc.t0||0))*this.doc.fps+1e-6);return i>=0&&i<a.length?a[i]:0;}
  /** Release-only smoothing: rises at once, falls no faster than a 0.25 s exponential (over the last 3 frames). */
  level(t:number){const d=1/this.doc.fps,r=Math.exp(-d/.25);let m=this.val(t);for(let k=1;k<=3;k++)m=Math.max(m,this.val(t-k*d)*r**k);return m;}
  refPitch(){return null;}
  mods(t:number,start:number,end:number,_ref:number|null,amount:number):VoiceMods{
    if(amount<=0||t<start)return NO_VOICE;
    // Same hold as the voice: after the word ends it keeps its last size, easing out over 0.4 s.
    const tt=Math.min(t,end),hold=t>end?Math.exp(-(t-end)/.4):1;
    const s=1+amount*.24*this.level(tt)*hold;
    return {weight:0,sx:s,sy:s,dy:0};
  }
}

export type SongField = VoiceField|AudioField;
/** voice.json / audio.json → the matching field (a TypesetAudioField doc may also arrive as voice.json, e.g. from TypesetRender). */
export function songField(doc:VoiceDoc|AudioDoc):SongField{return (doc as AudioDoc).kind==='bass'?new AudioField(doc as AudioDoc):new VoiceField(doc as VoiceDoc);}
