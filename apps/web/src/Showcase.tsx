import {useEffect, useRef, useState} from 'react';
import {request} from './api';
import type {Project} from './types';
import './showcase.css';

type View = 'result' | 'source' | 'overlay';
type Film = {
  id: string; title: string; label: string; description: string; detail: string;
  file: string; poster: string; source: string; sourceType: 'image' | 'video';
  spec: string; project?: string; overlay?: string;
};
const films: Film[] = [
  {
    id: 'neon', title: 'A word. A world.', label: 'Generative lettering',
    description: 'A still image becomes a neon-lit scene. Let the camera move; let the word hold its place.',
    detail: 'Recorded output · Krea2 image → MiniMax H3 video. About 3½ minutes for both stages on the 4090. The word remained readable in sampled frames; generated spelling still needs review.',
    file: '/showcase/neon.mp4', poster: '/showcase/neon-poster.jpg', source: '/showcase/neon-source.png', sourceType: 'image',
    spec: '5.17 SEC / 1344 × 768', project: 'Typeset — GPU neon demo',
  },
  {
    id: 'kinetic', title: 'Give words a place.', label: 'Editable motion type',
    description: 'Time each word. Put it behind a subject. Follow an anchor. Change your mind and keep editing.',
    detail: 'Recorded editor export · A synthetic scene demonstrates pop, karaoke, typewriter and HUD motion, subject occlusion and mask-based anchors. Exact lettering comes from fonts. The transparent overlay is unoccluded; behind-subject compositing also needs a foreground layer.',
    file: '/showcase/kinetic.mp4', poster: '/showcase/kinetic-poster.jpg', source: '/sample/sample.mp4', sourceType: 'video',
    overlay: '/showcase/overlay.webm', spec: '12 SEC / 1280 × 720', project: 'Typeset — typography demo',
  },
  {
    id: 'morph', title: 'Same word. New material.', label: 'First-to-last-frame study',
    description: 'Guide a word from neon into chrome with two lettering plates. A material experiment in motion.',
    detail: 'Recorded output · LTX-Video with first/last-frame guidance. The change reaches chrome early in this run; transition timing is still experimental. The plates use rendered fonts.',
    file: '/showcase/morph.mp4', poster: '/showcase/morph-poster.jpg', source: '/showcase/morph-source.png', sourceType: 'image',
    spec: '2.04 SEC / 768 × 448',
  },
];
const studies = [
  {word: 'NEON', material: 'Light, bent into letters', file: 'neon-type.png', model: 'FLUX.2 Klein 4B'},
  {word: 'LOUDER', material: 'Volume you can see', file: 'louder.png', model: 'FLUX.2 Klein 4B'},
  {word: 'stay', material: 'A softer kind of type', file: 'stay.png', model: 'FLUX.2 Klein 4B'},
  {word: 'HOLD ON', material: 'Words with weight', file: 'holdon.png', model: 'Z-Image Turbo'},
  {word: 'forever', material: 'Stitched into the surface', file: 'forever.png', model: 'FLUX.2 Klein 4B'},
  {word: 'ECHO', material: 'An experiment in glass', file: 'echo.png', model: 'Z-Image Turbo'},
];
const clock = (n: number) => `${Math.floor(n / 60)}:${Math.floor(n % 60).toString().padStart(2, '0')}`;

export default function Showcase() {
  const [selected, setSelected] = useState(0);
  const [view, setView] = useState<View>('result');
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState('');
  const [presenting, setPresenting] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [study, setStudy] = useState<(typeof studies)[number] | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const player = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const presentButton = useRef<HTMLButtonElement>(null);
  const exitButton = useRef<HTMLButtonElement>(null);
  const film = films[selected];
  const isImage = view === 'source' && film.sourceType === 'image';
  const src = view === 'source' ? film.source : view === 'overlay' ? film.overlay! : film.file;
  const linkedProject = projects.find(p => p.name === film.project);
  const editorHref = `#/studio${linkedProject ? `?project=${encodeURIComponent(linkedProject.id)}` : ''}`;

  useEffect(() => {
    let live = true;
    void request<Project[]>('/api/projects').then(p => {if (live) setProjects(p);}).catch(() => {});
    return () => {live = false;};
  }, []);
  useEffect(() => {setTime(0); setDuration(0); setPlaying(false); setError('');}, [selected, view]);
  useEffect(() => {
    if (!presenting) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    exitButton.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {event.preventDefault(); setPresenting(false);}
      if ((event.target as HTMLElement).matches('input,select,textarea')) return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault(); setView('result');
        setSelected(i => (i + (event.key === 'ArrowRight' ? 1 : films.length - 1)) % films.length);
      }
    };
    window.addEventListener('keydown', key);
    return () => {document.body.style.overflow = overflow; window.removeEventListener('keydown', key); presentButton.current?.focus();};
  }, [presenting]);
  useEffect(() => {if (study) dialog.current?.showModal();}, [study]);

  function choose(index: number) {setSelected(index); setView('result');}
  async function togglePlayback() {
    if (!video.current) return;
    if (video.current.paused) {
      try {await video.current.play();} catch {setError('Playback could not start. Try downloading the clip below.');}
    } else video.current.pause();
  }

  return <div className={`showcase${presenting ? ' is-presenting' : ''}`}>
    <header className="show-header">
      <a className="show-brand" href="#/showcase" aria-label="Typeset showcase"><span>T↗</span>typeset<span className="show-edition">EXPERIMENT 001</span></a>
      <nav aria-label="Main navigation"><span className="show-nav-current">Showcase</span><a href="#/studio">Open studio <span aria-hidden="true">↗</span></a></nav>
    </header>

    <main>
      <section className="show-intro">
        <div><p className="show-eyebrow"><span/> A MOTION STUDIO FOR WORDS</p><h1>Words belong<br/>in the <em>scene.</em></h1></div>
        <div className="show-intro-aside"><p>From a line of text to a moment<br/> you can feel.</p><p className="show-muted">Animate it. Place it. Make it part of the world.</p><a className="show-text-link" href="#/studio">Make something move <span>↗</span></a></div>
      </section>

      <section className="show-work" aria-label="Video showcase">
        <div className="show-section-top"><p className="show-eyebrow">01 — THE WORK IN MOTION</p><button ref={presentButton} className="show-present-button" onClick={() => {setView('result'); setPresenting(true);}}>⛶ Presentation mode</button></div>
        <div className="show-present-top"><a className="show-brand" href="#/showcase" onClick={() => setPresenting(false)}><span>T↗</span>typeset</a><span>{film.label}</span><button ref={exitButton} onClick={() => setPresenting(false)}>Exit presentation <kbd>Esc</kbd></button></div>
        <div className="show-work-grid">
          <div className="show-feature">
            <div className="show-view-tabs" role="group" aria-label="Preview layer">
              <button aria-pressed={view === 'result'} onClick={() => setView('result')}>Final result</button>
              <button aria-pressed={view === 'source'} onClick={() => setView('source')}>{film.sourceType === 'image' ? 'Starting image' : 'Source footage'}</button>
              {film.overlay && <button aria-pressed={view === 'overlay'} onClick={() => setView('overlay')}>Text overlay</button>}
              <span className="show-recorded"><i/> RECORDED OUTPUT</span>
            </div>
            <div ref={player} className={`show-player${view === 'overlay' ? ' has-alpha' : ''}`}>
              {isImage ? <img src={src} alt={`Starting image for ${film.title}`} onError={() => setError('This image could not load.')} /> :
                <video key={`${film.id}-${view}`} ref={video} src={src} poster={view === 'result' ? film.poster : undefined}
                  autoPlay={!window.matchMedia('(prefers-reduced-motion: reduce)').matches} loop muted={muted} playsInline preload="metadata"
                  aria-label={`${film.title} — ${view}`} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
                  onTimeUpdate={e => setTime(e.currentTarget.currentTime)} onLoadedMetadata={e => setDuration(e.currentTarget.duration)}
                  onError={() => setError('This video could not load. Download it below or try Chrome.')} />}
              {error && <div className="show-media-error" role="alert">{error}<a href={src} download>Download file ↗</a></div>}
              {!isImage && <div className="show-player-controls">
                <button onClick={() => void togglePlayback()} aria-label={playing ? 'Pause preview' : 'Play preview'}>{playing ? 'Ⅱ' : '▶'}</button>
                <span className="show-time">{clock(time)} <span>/ {clock(duration)}</span></span>
                <input aria-label="Seek preview" type="range" min={0} max={duration || 1} step={0.01} value={time} onChange={e => {if (video.current) {video.current.currentTime = Number(e.target.value); setTime(Number(e.target.value));}}}/>
                <button className="show-sound" aria-label={muted ? 'Unmute preview' : 'Mute preview'} onClick={() => setMuted(m => !m)}>{muted ? 'Sound off' : 'Sound on'}</button>
                <button aria-label="Fullscreen preview" onClick={() => {void player.current?.requestFullscreen?.().catch(() => setError('Fullscreen is unavailable in this browser. Presentation mode is available above.'));}}>⛶</button>
              </div>}
              {isImage && <div className="show-still-label">THE STARTING FRAME</div>}
            </div>
            <div className="show-caption"><div><h2>{film.title}</h2><p>{film.description}</p></div><a href={film.file} download className="show-download" aria-label={`Download ${film.title}`}>↓ <span>MP4</span></a></div>
            <details className="show-render-notes"><summary>About this render <span>+</span></summary><p>{film.detail}</p></details>
          </div>

          <aside className="show-playlist" aria-label="Choose a demo">
            <div className="show-playlist-heading"><span>THREE WAYS TO PLAY</span><span>↙</span></div>
            {films.map((item, index) => <button key={item.id} className={`show-film${selected === index ? ' selected' : ''}`} aria-pressed={selected === index} onClick={() => choose(index)}>
              <div className="show-film-image"><img src={item.poster} alt=""/><span>{String(index + 1).padStart(2, '0')}</span></div>
              <div><span className="show-film-label">{item.label}</span><strong>{item.title}</strong><small>{item.spec}</small></div><span className="show-film-arrow" aria-hidden="true">↗</span>
            </button>)}
            <div className="show-try"><p>Now make it yours.</p><span>Open a clip, select a word,<br/>and give it some direction.</span><a href={editorHref}>{linkedProject ? 'Open this clip in studio' : 'Try the live editor'} <span>↗</span></a></div>
          </aside>
        </div>
        <div className="show-present-footer"><span>{String(selected + 1).padStart(2, '0')} / 03 <span>Use ← → to switch scenes</span></span><div>{films.map((item, i) => <button key={item.id} aria-label={`Present ${item.label}`} aria-pressed={selected === i} onClick={() => choose(i)}>{item.label}</button>)}</div></div>
      </section>

      <section className="show-studies" aria-labelledby="studies-title">
        <div className="show-studies-heading"><div><p className="show-eyebrow">02 — MATERIAL STUDIES</p><h2 id="studies-title">Type, with texture.</h2></div><p>Six words. A few different worlds.<br/><span>Actual image-model outputs. Open one for a closer look.</span></p></div>
        <div className="show-study-grid">{studies.map(item => <button key={item.word} className="show-study" onClick={() => setStudy(item)} aria-label={`View ${item.word} material study`}><div><img src={`/showcase/${item.file}`} alt={`${item.word} generated as physical lettering`} loading="lazy"/><span>↗</span></div><footer><strong>{item.word}</strong><span>{item.material}</span></footer></button>)}</div>
        <p className="show-study-note">Explorations, not a spelling guarantee. For exact captions, the editor uses real fonts.</p>
      </section>

      <section className="show-process" aria-labelledby="process-title"><div><p className="show-eyebrow">03 — FROM VIEWING TO MAKING</p><h2 id="process-title">Keep the words.<br/>Change everything else.</h2><a href="#/studio">Open the studio <span>↗</span></a></div><ol><li><span>01</span><div><h3>Start with a moment.</h3><p>Bring your footage, or open the editable demo.</p></div></li><li><span>02</span><div><h3>Give every word direction.</h3><p>Adjust timing, motion and placement. Preview changes as you make them.</p></div></li><li><span>03</span><div><h3>Take it into your edit.</h3><p>Export a finished video or a transparent text layer.</p></div></li></ol></section>

      <details className="show-demo-guide"><summary><span>Presenting at the hackathon?</span><span>A 90-second walkthrough ↗</span></summary><ol><li><strong>0–20s · Show the result.</strong> Play the neon clip. Switch to its starting image to show what changed.</li><li><strong>20–40s · Show control.</strong> Choose “Editable motion type.” Compare source footage, final result and the transparent text layer.</li><li><strong>40–70s · Make a live edit.</strong> Open the studio, select a word, change its text or motion preset, and press play.</li><li><strong>70–90s · Show the handoff.</strong> Explain the finished-video and alpha-overlay exports. Saved previews play without a GPU connection; generating a new shot takes time.</li></ol></details>
    </main>
    <footer className="show-footer"><a className="show-brand" href="#/showcase"><span>T↗</span>typeset</a><p>A working prototype. Your words, in motion.</p><a href="#/studio">Let's make a scene ↗</a></footer>

    <dialog ref={dialog} className="show-lightbox" onClose={() => setStudy(null)} onClick={event => {if (event.target === event.currentTarget) dialog.current?.close();}} aria-label={study ? `${study.word} material study` : 'Material study'}>
      {study && <><div><span>{study.word} / MATERIAL STUDY</span><button autoFocus onClick={() => dialog.current?.close()} aria-label="Close image preview">Close ×</button></div><img src={`/showcase/${study.file}`} alt={`${study.word} — ${study.material}`}/><footer><span>{study.model} · recorded output</span><a href={`/showcase/${study.file}`} download>Download image ↓</a></footer></>}
    </dialog>
  </div>;
}
