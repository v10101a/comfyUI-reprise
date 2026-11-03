// Demo page: one stage with the studio's transport, a shelf of pieces, the looks grid, a look inside the studio.
// Paper-grey, names only; detail lives in tooltips. Media are plain files in public/showcase/ (see README there).
import {useEffect, useRef, useState} from 'react';
import {request} from './api';
import {at} from './base';
import type {Project} from './types';
import {ThemeToggle} from './studio/ThemeToggle';
import {Icon} from './studio/icons';
import {LooksSection} from './LooksSection';
import {ShowcaseCredits} from './ShowcaseCredits';
import PIECES from './showcase-pieces.json';
import './showcase.css';

type Credits = {image?: string; music?: string};
type Piece = {
  id: string; name: string; src: string; kind: 'video' | 'image'; aspect: string;
  /** Tooltip only. */
  note: string;
  /** Under the title: where the footage and the music came from. */
  credits?: Credits;
  /** Studio project that made it (opened by "Open studio" when the API knows it). */
  project?: string;
  /** Alternate takes on the same stage, e.g. the source plate. */
  alts?: {label: string; src: string; aspect?: string}[];
  /** Hidden until its file exists (pieces still being made). */
  optional?: boolean;
};

const S = (f: string) => at(`/showcase/${f}`);
/** Pieces live in showcase-pieces.json (shared with the server's save→demo refresh). */
type PieceFile = {id: string; name: string; file: string; kind: string; aspect: string; note: string; project?: string; optional?: boolean;
  credits?: Credits; alts?: {label: string; file: string; aspect?: string}[]};
const pieces: Piece[] = (PIECES.pieces as PieceFile[]).map(p => ({...p, kind: p.kind === 'image' ? 'image' : 'video', src: S(p.file),
  alts: p.alts?.map(a => ({label: a.label, src: S(a.file), aspect: a.aspect}))}));
const clock = (n: number) => `${Math.floor(n / 60)}:${Math.floor(n % 60).toString().padStart(2, '0')}`;
const isImage = (src: string) => /\.(png|jpe?g|webp)$/i.test(src);

/** Inside the studio: the README's captures (public/showcase/studio/). */
const INSIDE = [
  {file: 'studio-walkthrough.mp4', text: 'Compare takes, browse the board, preview text styles.'},
  {file: 'board.png', text: 'Scenes keep their references and takes together.'},
  {file: 'takes.png', text: 'Try a take in the edit before committing.'},
];

export default function Showcase() {
  const [missing, setMissing] = useState<Set<string>>(new Set());
  const shown = pieces.filter(p => !missing.has(p.id));
  const [id, setId] = useState(pieces[0].id);
  const [alt, setAlt] = useState<number>(-1);
  const [still, setStill] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [projects, setProjects] = useState<Set<string>>(new Set());
  /** File mtimes from the API: a clip re-rendered after a studio save gets a fresh URL. */
  const [ver, setVer] = useState<Record<string, number>>({});
  const vsrc = (p: Piece) => ver[p.id] ? `${p.src}?v=${ver[p.id]}` : p.src;
  /** The Reprise video is the clock and the only sound; alt views are muted layers kept in sync under it. */
  const video = useRef<HTMLVideoElement>(null);
  const layers = useRef<(HTMLVideoElement | null)[]>([]);
  const stage = useRef<HTMLDivElement>(null);
  const piece = shown.find(p => p.id === id) || shown[0];
  const view = alt >= 0 && piece.alts?.[alt] ? piece.alts[alt] : null;
  const src = still || view?.src || vsrc(piece);
  const aspect = still ? 'auto' : piece.aspect;
  const image = still != null || isImage(piece.src);
  const studio = `#/studio${piece.project && projects.has(piece.project) ? `?project=${piece.project}` : ''}`;

  useEffect(() => {
    let live = true;
    void request<Project[]>('/api/projects').then(p => {if (live) setProjects(new Set(p.map(x => x.id)));}).catch(() => {});
    void request<Record<string, number>>('/api/showcase').then(v => {if (live) setVer(v);}).catch(() => {});
    return () => {live = false;};
  }, []);
  useEffect(() => {setTime(0); setDuration(0); setPlaying(false);}, [piece.src, still]);
  // Sound on by default; if the browser blocks unmuted autoplay, play muted and unmute on the first gesture
  // (outside the Looks section, which has its own sound).
  const blocked = useRef(false);
  useEffect(() => {
    if (!muted || !blocked.current) return;
    const unmute = (e: Event) => {
      if ((e.target as Element | null)?.closest?.('.sc-looks, button')) return;   // buttons handle sound themselves
      blocked.current = false; setMuted(false); if (video.current) video.current.muted = false;
    };
    window.addEventListener('pointerdown', unmute);
    window.addEventListener('keydown', unmute);
    return () => {window.removeEventListener('pointerdown', unmute); window.removeEventListener('keydown', unmute);};
  }, [muted]);
  // One sound at a time on the page: the stage and the Looks section mute each other.
  useEffect(() => {if (!muted) window.dispatchEvent(new CustomEvent('sc-sound', {detail: 'stage'}));}, [muted]);
  useEffect(() => {
    const other = (e: Event) => {if ((e as CustomEvent).detail !== 'stage') setMuted(true);};
    window.addEventListener('sc-sound', other);
    return () => window.removeEventListener('sc-sound', other);
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches('input,select,textarea')) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') step(e.key === 'ArrowRight' ? 1 : -1);
      if (e.key === ' ' && !image) {e.preventDefault(); toggle();}
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  });

  function choose(next: string) {layers.current = []; setId(next); setAlt(-1); setStill(null); stage.current?.scrollIntoView({block: 'nearest', behavior: 'smooth'});}
  function step(by: number) {const i = shown.findIndex(p => p.id === piece.id); choose(shown[(i + by + shown.length) % shown.length].id);}
  function sync(force = false) {
    const m = video.current; if (!m) return;
    for (const l of layers.current) {
      if (!l || l.readyState < 1) continue;
      if (force || Math.abs(l.currentTime - m.currentTime) > .08) l.currentTime = m.currentTime;
      if (m.paused && !l.paused) l.pause(); else if (!m.paused && l.paused) void l.play().catch(() => {});
    }
  }
  function showView(i: number) {setAlt(i); sync(true);}
  function start(v: HTMLVideoElement) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    v.play().catch(() => {v.muted = true; blocked.current = true; setMuted(true); void v.play().catch(() => {});});
  }
  function toggle() {const v = video.current; if (!v) return; if (v.paused) void v.play().catch(() => {}); else v.pause();}
  function seek(t: number) {if (video.current) video.current.currentTime = t; setTime(t);}
  const hide = (pid: string) => setMissing(m => new Set(m).add(pid));
  const credits = still ? undefined : piece.credits;

  return <div className="showcase">
    <header className="sc-top">
      <div className="sc-left"><a className="sc-brand" href="#/showcase" aria-label="Reprise home">reprise</a><span className="sc-tag">A ComfyUI studio for music video and motion graphics.</span></div>
      <nav><a className="sc-open" href={studio}>Open studio</a><ThemeToggle/></nav>
    </header>

    <main>
      <p className="sc-tag-m">A ComfyUI studio for music video and motion graphics.</p>
      <section className="sc-stage-wrap" ref={stage} style={{'--ar': image ? '1' : aspect} as React.CSSProperties}>
        <div className={`sc-stage ${image ? 'is-image' : ''}`} style={{aspectRatio: aspect}}>
          {image
            ? <img src={src} alt={piece.name}/>
            : <>
              <video key={piece.src} ref={video} src={vsrc(piece)} loop muted={muted} playsInline preload="auto"
                aria-label={piece.name} onClick={toggle} onPlay={() => {setPlaying(true); sync();}} onPause={() => {setPlaying(false); sync();}} onSeeked={() => sync(true)}
                onTimeUpdate={e => {setTime(e.currentTarget.currentTime); sync();}} onLoadedMetadata={e => {setDuration(e.currentTarget.duration); start(e.currentTarget);}}/>
              {piece.alts?.map((a, i) => <video key={`${piece.id}:${a.src}`} ref={el => {layers.current[i] = el;}} src={a.src} loop muted playsInline preload="auto"
                className={`sc-layer ${alt === i ? 'on' : ''}`} aria-hidden={alt !== i} onClick={toggle} onLoadedMetadata={() => sync(true)}/>)}
            </>}
        </div>

        {/* the studio's transport: time on the left, play in the middle, sound and view on the right */}
        {!image && <div className="sc-transport">
          <input className="sc-seek" aria-label="Seek" type="range" min={0} max={duration || 1} step={0.01} value={time}
            style={{'--p': `${duration ? time / duration * 100 : 0}%`} as React.CSSProperties} onChange={e => seek(Number(e.target.value))}/>
          <span className="sc-clock"><b>{clock(time)}</b> / {clock(duration)}</span>
          <div className="sc-tc">
            <button className="sc-ib" aria-label="Previous piece" title="Previous (←)" onClick={() => step(-1)}><Icon name="prev" size={14}/></button>
            <button className="sc-play" aria-label={playing ? 'Pause' : 'Play'} title="Space" onClick={toggle}><Icon name={playing ? 'pause' : 'play'} size={16}/></button>
            <button className="sc-ib" aria-label="Next piece" title="Next (→)" onClick={() => step(1)}><Icon name="next" size={14}/></button>
          </div>
          <div className="sc-tr">
            <button className={`sc-ib ${muted ? 'sc-muted' : ''}`} aria-label={muted ? 'Unmute' : 'Mute'} onClick={() => {blocked.current = false; setMuted(m => !m);}}><Icon name={muted ? 'mute' : 'sound'} size={16}/></button>
            <button className="sc-ib" aria-label="Fullscreen" onClick={() => void stage.current?.querySelector('.sc-stage')?.requestFullscreen?.().catch(() => {})}><Icon name="expand" size={14}/></button>
            <a className="sc-ib" href={src} download aria-label="Download" title="Download">↓</a>
          </div>
        </div>}

        <div className="sc-bar">
          <p className="sc-credit" title={still ? undefined : piece.note}>
            {credits?.image && <span><i>image</i>{credits.image}</span>}
            {credits?.music && <span><i>music</i>{credits.music}</span>}
          </p>
          {(piece.alts?.length || 0) > 0 && !still && <div className="sc-alts" role="group" aria-label="view">
            <button aria-pressed={alt < 0} onClick={() => showView(-1)}>Reprise</button>
            {piece.alts!.map((a, i) => <button key={a.label} aria-pressed={alt === i} onClick={() => showView(i)}>{a.label}</button>)}
          </div>}
          {image && <a className="sc-ib sc-dl" href={src} download aria-label="Download" title="Download">↓</a>}
        </div>
      </section>

      <section className="sc-shelf" aria-label="pieces">
        {pieces.map(p => missing.has(p.id) ? null : <button key={p.id} className={`sc-piece ${p.id === piece.id && !still ? 'on' : ''}`} onClick={() => choose(p.id)} title={p.note} aria-pressed={p.id === piece.id && !still}>
          <span className="sc-thumb" style={{aspectRatio: p.aspect}}>
            {p.kind === 'image'
              ? <img src={p.src} alt="" loading="lazy" onError={() => hide(p.id)}/>
              : <video src={`${vsrc(p)}#t=1`} muted playsInline preload="metadata" onError={() => p.optional && hide(p.id)}
                  onMouseEnter={e => void e.currentTarget.play().catch(() => {})} onMouseLeave={e => e.currentTarget.pause()}/>}
          </span>
          <span className="sc-name">{p.name}</span>
        </button>)}
      </section>

      <LooksSection/>

      <section className="sc-inside" aria-label="Inside the studio">
        <h2>Inside the studio</h2>
        <div className="sc-inside-grid">
          {INSIDE.map(x => <figure key={x.file}>
            {x.file.endsWith('.mp4')
              ? <video src={S(`studio/${x.file}`)} muted loop playsInline autoPlay preload="metadata" aria-label={x.text}/>
              : <img src={S(`studio/${x.file}`)} alt={x.text} loading="lazy"/>}
            <figcaption>{x.text}</figcaption>
          </figure>)}
        </div>
      </section>

      <ShowcaseCredits/>
    </main>
  </div>;
}
