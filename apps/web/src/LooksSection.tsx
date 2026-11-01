// Demo page "Looks": one 4.0 s shot (the hero's S2 wall, 0.5 s longer each side than the hero's 3 s cut: she walks
// left→right in profile past the long pale wall, hero-time 3.83–7.83 s; big wall text EVERY SIGN / REPEATS / YOUR NAME
// on tracked wall rows, project a1aab922) rendered in every look and a few footage grades, captions off. Switching keeps the playback time, so the look changes on the same frame.
// One <audio> (looks/song.m4a, the clips' shared song) is the clock and the only sound; the clips are muted layers that follow it.
// Clips: public/showcase/looks/<look>[--<grade>].mp4 (+ .jpg still); made by the #/render route with ?look=&grade=.
import {useEffect, useRef, useState} from 'react';
import {at} from './base';
import {LOOKS, GRADES} from './looks';

const LOOK_IDS = ['flat-card', 'paper-cut', 'graffiti', 'neon', 'hud', 'xerox', 'ticker', 'scatter'];
const GRADE_IDS = ['none', 'mono', 'xerox', 'film'];
const file = (look: string, grade: string) => at(`/showcase/looks/${look === 'source' || grade === 'none' ? look : `${look}--${grade}`}`);
const nameOf = (id: string) => id === 'source' ? 'Source' : LOOKS.find(l => l.id === id)?.name || id;
const gradeName = (id: string) => id === 'none' ? 'None' : GRADES.find(g => g.id === id)?.name || id;

type Layer = {key: number; src: string; ready: boolean};

export function LooksSection() {
  const [look, setLook] = useState('flat-card');
  const [grade, setGrade] = useState('none');
  const [muted, setMuted] = useState(true);
  const audio = useRef<HTMLAudioElement>(null);
  // One sound at a time on the page: unmuting here mutes the stage, and the stage's sound mutes this.
  useEffect(() => {if (!muted) window.dispatchEvent(new CustomEvent('sc-sound', {detail: 'looks'}));}, [muted]);
  useEffect(() => {
    const other = (e: Event) => {if ((e as CustomEvent).detail !== 'looks') setMuted(true);};
    window.addEventListener('sc-sound', other);
    return () => window.removeEventListener('sc-sound', other);
  }, []);
  const n = useRef(0);
  const [layers, setLayers] = useState<Layer[]>([{key: 0, src: file('flat-card', 'none'), ready: true}]);
  const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(nextLook: string, nextGrade: string) {
    setLook(nextLook); setGrade(nextGrade);
    const src = file(nextLook, nextGrade);
    // New clip loads under the current one, seeks to the same time, then takes over.
    setLayers(ls => ls[ls.length - 1].src === src ? ls : [...ls.filter(l => l.ready).slice(-1), {key: ++n.current, src, ready: false}]);
  }
  const now = () => audio.current?.currentTime || 0;
  /** Keep a clip on the song's clock (clips and song are the same length and loop together). */
  function follow(v: HTMLVideoElement) {
    const a = audio.current; if (!a) return;
    if (Math.abs(v.currentTime - a.currentTime) > .08) v.currentTime = Math.min(a.currentTime, Math.max(0, v.duration - .05));
    if (a.paused && !v.paused) v.pause(); else if (!a.paused && v.paused) void v.play().catch(() => {});
  }
  function toggle() {const a = audio.current; if (!a) return; if (a.paused) void a.play().catch(() => {}); else a.pause();}

  return <section className="sc-looks" aria-label="Looks">
    <h2>Looks</h2>
    <div className="sc-looks-stage">
      <audio ref={audio} src={at('/showcase/looks/song.m4a')} loop muted={muted} autoPlay={!reduce} preload="auto"
        onPlay={() => document.querySelectorAll<HTMLVideoElement>('.sc-looks-stage video').forEach(follow)}
        onPause={() => document.querySelectorAll<HTMLVideoElement>('.sc-looks-stage video').forEach(v => v.pause())}/>
      {layers.map(l => <video key={l.key} src={`${l.src}.mp4`} poster={`${l.src}.jpg`} muted loop playsInline preload="auto"
        className={l.ready ? 'ready' : ''}
        onLoadedMetadata={e => {if (l.ready) return; const v = e.currentTarget; v.currentTime = Math.min(now() + .05, Math.max(0, v.duration - .05));}}
        onSeeked={e => {if (l.ready) return; follow(e.currentTarget);
          setLayers(ls => ls.map(x => x.key === l.key ? {...x, ready: true} : x).filter(x => x.key >= l.key));}}
        onTimeUpdate={e => {if (l.ready) follow(e.currentTarget);}}
        onClick={toggle}/>)}
      <button className={`sc-looks-sound ${muted ? 'sc-muted' : ''}`} onClick={() => setMuted(m => !m)} aria-label={muted ? 'unmute' : 'mute'}>♪</button>
    </div>
    <div className="sc-looks-bar">
      <div className="sc-alts" role="group" aria-label="grade">
        {GRADE_IDS.map(g => <button key={g} aria-pressed={grade === g && look !== 'source'} disabled={look === 'source'} onClick={() => show(look, g)}>{gradeName(g)}</button>)}
      </div>
    </div>
    <div className="sc-looks-row" role="group" aria-label="look">
      {['source', ...LOOK_IDS].map(id => <button key={id} className={`sc-look ${look === id ? 'on' : ''}`} aria-pressed={look === id} onClick={() => show(id, grade)}>
        <img src={`${file(id, id === 'source' ? 'none' : grade)}.jpg`} alt="" loading="lazy"/>
        <span>{nameOf(id)}</span>
      </button>)}
    </div>
  </section>;
}
