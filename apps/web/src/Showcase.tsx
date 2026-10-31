// Demo page: one stage, a shelf of pieces. Paper-grey, names only; detail lives in tooltips.
// Media are plain files in public/showcase/ (see README there): swapping a piece is a file copy.
import {useEffect, useRef, useState} from 'react';
import {request} from './api';
import {at} from './base';
import type {Project} from './types';
import {ThemeToggle} from './studio/ThemeToggle';
import {LooksSection} from './LooksSection';
import './showcase.css';

type Piece = {
  id: string; name: string; src: string; kind: 'video' | 'image'; aspect: string;
  /** Tooltip only. */
  note: string;
  /** Studio project that made it (opened by "studio →" when the API knows it). */
  project?: string;
  /** Alternate takes on the same stage, e.g. the source plate. */
  alts?: {label: string; src: string; aspect?: string}[];
  /** Hidden until its file exists (pieces still being made). */
  optional?: boolean;
};

const S = (f: string) => at(`/showcase/${f}`);
const pieces: Piece[] = [
  {id: 'hero', name: 'Neon Rain', src: S('hero-16x9.mp4'), kind: 'video', aspect: '1344/768', project: '54da2790-92c6-4737-bc43-81a207e47ab5',
    note: 'lyric video · lens-bound look · 22 s · 1344×768', alts: [{label: '9:16', src: S('hero-9x16.mp4'), aspect: '720/1280'}, {label: 'Source', src: S('hero-source.mp4')}]},
  {id: 'hero-dark', name: 'Neon Rain · Night', src: S('hero-dark.mp4'), kind: 'video', aspect: '1344/768', optional: true, project: '54da2790-92c6-4737-bc43-81a207e47ab5',
    note: 'dark restyle'},
  {id: 'vertical', name: 'Neon Rain · 9:16', src: S('hero-9x16.mp4'), kind: 'video', aspect: '720/1280', project: 'cb4de765-9043-4540-953b-8f017fc28a87',
    note: 'auto-reframed to 9:16, subject-follow crop · 720×1280'},
  {id: 'ffm', name: 'Fall For Me', src: S('ffm.mp4'), kind: 'video', aspect: '1080/1280', project: '14ef9e95-1d22-4bc1-8e42-5a1db01368ee',
    note: 'lyric video · 26 s'},
  {id: 'ffm-angel', name: 'Fall For Me · Angel', src: S('ffm-angel.mp4'), kind: 'video', aspect: '1080/1280', optional: true, project: '86c2492e-db7a-4d3e-9cc4-837bcff147c8',
    note: 'lyric video · generated angel shots'},
];
const clock = (n: number) => `${Math.floor(n / 60)}:${Math.floor(n % 60).toString().padStart(2, '0')}`;
const isImage = (src: string) => /\.(png|jpe?g|webp)$/i.test(src);

export default function Showcase() {
  const [missing, setMissing] = useState<Set<string>>(new Set());
  const shown = pieces.filter(p => !missing.has(p.id));
  const [id, setId] = useState(pieces[0].id);
  const [alt, setAlt] = useState<number>(-1);
  const [still, setStill] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [projects, setProjects] = useState<Set<string>>(new Set());
  const video = useRef<HTMLVideoElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const piece = shown.find(p => p.id === id) || shown[0];
  const view = alt >= 0 && piece.alts?.[alt] ? piece.alts[alt] : null;
  const src = still || view?.src || piece.src;
  const aspect = still ? 'auto' : view?.aspect || piece.aspect;
  const image = still != null || isImage(src);
  const studio = `#/studio${piece.project && projects.has(piece.project) ? `?project=${piece.project}` : ''}`;

  useEffect(() => {
    let live = true;
    void request<Project[]>('/api/projects').then(p => {if (live) setProjects(new Set(p.map(x => x.id)));}).catch(() => {});
    return () => {live = false;};
  }, []);
  useEffect(() => {setTime(0); setDuration(0); setPlaying(false);}, [src]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches('input,select,textarea')) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        const i = shown.findIndex(p => p.id === piece.id);
        choose(shown[(i + (e.key === 'ArrowRight' ? 1 : shown.length - 1)) % shown.length].id);
      }
      if (e.key === ' ' && !image) {e.preventDefault(); toggle();}
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  });

  function choose(next: string) {setId(next); setAlt(-1); setStill(null); stage.current?.scrollIntoView({block: 'nearest', behavior: 'smooth'});}
  function toggle() {const v = video.current; if (!v) return; if (v.paused) void v.play().catch(() => {}); else v.pause();}
  const hide = (pid: string) => setMissing(m => new Set(m).add(pid));

  return <div className="showcase">
    <header className="sc-top">
      <a className="sc-brand" href="#/showcase">typeset</a>
      <nav><a className="sc-open" href={studio}>Open studio</a><ThemeToggle/></nav>
    </header>

    <main>
      <section className="sc-stage-wrap" ref={stage}>
        <div className={`sc-stage ${image ? 'is-image' : ''}`} style={{aspectRatio: aspect}}>
          {image
            ? <img src={src} alt={piece.name}/>
            : <video key={src} ref={video} src={src} autoPlay={!window.matchMedia('(prefers-reduced-motion: reduce)').matches} loop muted={muted} playsInline preload="auto"
                aria-label={piece.name} onClick={toggle} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
                onTimeUpdate={e => setTime(e.currentTarget.currentTime)} onLoadedMetadata={e => setDuration(e.currentTarget.duration)}/>}
        </div>
        <div className="sc-bar">
          <h1 title={still ? undefined : piece.note}>{still ? still.split('/').pop()!.replace(/\.png$/, '').replace('-', ' ') : piece.name}</h1>
          {(piece.alts?.length || 0) > 0 && !still && <div className="sc-alts" role="group" aria-label="view">
            <button aria-pressed={alt < 0} onClick={() => setAlt(-1)}>Typeset</button>
            {piece.alts!.map((a, i) => <button key={a.label} aria-pressed={alt === i} onClick={() => setAlt(i)}>{a.label}</button>)}
          </div>}
          {!image && <div className="sc-controls">
            <button onClick={toggle} aria-label={playing ? 'pause' : 'play'}>{playing ? 'Ⅱ' : '▶'}</button>
            <input aria-label="seek" type="range" min={0} max={duration || 1} step={0.01} value={time}
              onChange={e => {if (video.current) {video.current.currentTime = Number(e.target.value); setTime(Number(e.target.value));}}}/>
            <span className="sc-time">{clock(time)}</span>
            <button onClick={() => setMuted(m => !m)} aria-label={muted ? 'unmute' : 'mute'} title={muted ? 'sound off' : 'sound on'} className={muted ? 'sc-muted' : ''}>♪</button>
            <button onClick={() => void stage.current?.querySelector('.sc-stage')?.requestFullscreen?.().catch(() => {})} aria-label="fullscreen">⤢</button>
          </div>}
          <a className="sc-dl" href={src} download title="download" aria-label="download">↓</a>
        </div>
      </section>

      <section className="sc-shelf" aria-label="pieces">
        {pieces.map(p => missing.has(p.id) ? null : <button key={p.id} className={`sc-piece ${p.id === piece.id && !still ? 'on' : ''}`} onClick={() => choose(p.id)} title={p.note} aria-pressed={p.id === piece.id && !still}>
          <span className="sc-thumb" style={{aspectRatio: p.aspect}}>
            {p.kind === 'image'
              ? <img src={p.src} alt="" loading="lazy" onError={() => hide(p.id)}/>
              : <video src={`${p.src}#t=1`} muted playsInline preload="metadata" onError={() => p.optional && hide(p.id)}
                  onMouseEnter={e => void e.currentTarget.play().catch(() => {})} onMouseLeave={e => e.currentTarget.pause()}/>}
          </span>
          <span className="sc-name">{p.name}</span>
        </button>)}
      </section>

      <LooksSection/>
    </main>
  </div>;
}
