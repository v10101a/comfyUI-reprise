// Demo page "Looks": one shot (the plaza drop, HOLD | ON, 11.50–13.92 s of the hero) rendered in every look and a few
// footage grades. Switching keeps the playback time, so the look changes on the same frame.
// Clips: public/showcase/looks/<look>[--<grade>].mp4 (+ .jpg still); made by the #/render route with ?look=&grade=.
import {useRef, useState} from 'react';
import {at} from './base';
import {LOOKS, GRADES} from './looks';

const LOOK_IDS = ['flat-card', 'paper-cut', 'graffiti', 'neon', 'xerox', 'ticker', 'lens-bound', 'scatter'];
const GRADE_IDS = ['none', 'mono', 'xerox', 'film'];
const file = (look: string, grade: string) => at(`/showcase/looks/${look === 'source' || grade === 'none' ? look : `${look}--${grade}`}`);
const nameOf = (id: string) => id === 'source' ? 'Source' : LOOKS.find(l => l.id === id)?.name || id;
const gradeName = (id: string) => id === 'none' ? 'None' : GRADES.find(g => g.id === id)?.name || id;

type Layer = {key: number; src: string; ready: boolean};

export function LooksSection() {
  const [look, setLook] = useState('lens-bound');
  const [grade, setGrade] = useState('none');
  const [muted, setMuted] = useState(true);
  const t = useRef(0);
  const playing = useRef(true);
  const n = useRef(0);
  const [layers, setLayers] = useState<Layer[]>([{key: 0, src: file('lens-bound', 'none'), ready: true}]);
  const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(nextLook: string, nextGrade: string) {
    setLook(nextLook); setGrade(nextGrade);
    const src = file(nextLook, nextGrade);
    // New clip loads under the current one, seeks to the same time, then takes over.
    setLayers(ls => ls[ls.length - 1].src === src ? ls : [...ls.filter(l => l.ready).slice(-1), {key: ++n.current, src, ready: false}]);
  }
  const current = layers[layers.length - 1];

  return <section className="sc-looks" aria-label="Looks">
    <h2>Looks</h2>
    <div className="sc-looks-stage">
      {layers.map(l => <video key={l.key} src={`${l.src}.mp4`} poster={`${l.src}.jpg`} muted={muted || l !== current} loop playsInline preload="auto"
        autoPlay={!reduce} className={l.ready ? 'ready' : ''}
        onLoadedMetadata={e => {if (l.ready) return; const v = e.currentTarget; v.currentTime = Math.min(t.current, Math.max(0, v.duration - .05));}}
        onSeeked={e => {if (l.ready) return; const v = e.currentTarget; if (playing.current && !reduce) void v.play().catch(() => {});
          setLayers(ls => ls.map(x => x.key === l.key ? {...x, ready: true} : x).filter(x => x.key >= l.key));}}
        onTimeUpdate={e => {if (l === current && l.ready) t.current = e.currentTarget.currentTime;}}
        onPlay={() => {if (l === current) playing.current = true;}} onPause={e => {if (l === current && !e.currentTarget.seeking) playing.current = false;}}
        onClick={e => {const v = e.currentTarget; if (v.paused) void v.play().catch(() => {}); else v.pause();}}/>)}
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
