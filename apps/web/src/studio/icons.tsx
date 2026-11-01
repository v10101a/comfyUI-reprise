// Studio icons: 24-unit strokes, currentColor. Every icon-only button that uses one carries an aria-label and a title.
const P:Record<string,React.ReactNode>={
  play:<path d="m8 5 11 7-11 7Z"/>,pause:<path d="M8 5v14M16 5v14"/>,upload:<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>,download:<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>,
  sound:<path d="M4 10v4h4l5 4V6l-5 4Zm13-3a8 8 0 0 1 0 10"/>,mute:<path d="M4 10v4h4l5 4V6l-5 4Zm13-1 5 6m0-6-5 6"/>,
  loop:<path d="M17 2l3 3-3 3M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3m13-3v2a4 4 0 0 1-4 4H4"/>,prev:<path d="M6 5v14M18 5 9 12l9 7Z"/>,next:<path d="M18 5v14M6 5l9 7-9 7Z"/>,
  close:<path d="M6 6l12 12M18 6 6 18"/>,expand:<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>,
  eye:<><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
  eyeOff:<path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7a9.6 9.6 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2"/>,
  bolt:<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z"/>,
  // roles
  caption:<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h10M9 12h6"/></>,
  behind:<><rect x="3" y="5" width="18" height="6" rx="1"/><circle cx="12" cy="10" r="2.6"/><path d="M6.5 20c.7-3.6 2.8-5.6 5.5-5.6s4.8 2 5.5 5.6"/></>,
  hud:<><path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><circle cx="12" cy="12" r="2"/></>,
  wall:<><path d="M3 6.5 20 3v18L3 17.5Z"/><path d="M7 11.2 16 10"/></>,
  inworld:<><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/></>,
  // tools
  copy:<><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/></>,
  paste:<><path d="M8 5H5v16h14V5h-3"/><rect x="8" y="3" width="8" height="4" rx="1"/></>,
  split:<><path d="M12 3v18M8 7H3v10h5M16 7h5v10h-5"/><path d="m9 10 3 2-3 2m6-4-3 2 3 2"/></>,
  guides:<><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9" strokeDasharray="2 2"/></>,
  compare:<><rect x="2.5" y="6" width="12" height="12" rx="1.5"/><rect x="16.5" y="4" width="5" height="16" rx="1"/></>,
  magnet:<path d="M6 3v8a6 6 0 0 0 12 0V3h-4v8a2 2 0 0 1-4 0V3ZM6 7h4M14 7h4"/>,
  fit:<path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4M8 12h8"/>,
  plus:<path d="M12 5v14M5 12h14"/>,keys:<><rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/></>,
  link:<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>,
  unlink:<path d="M15.5 13.5 18.7 11a4 4 0 0 0-5.7-5.7l-1.6 1.6M8.5 10.5 5.3 13a4 4 0 0 0 5.7 5.7l1.6-1.6M4 4l16 16"/>,
  rail:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></>,
  pipeline:<><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="12" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8.5 6.5 15.5 11M8.5 17.5l7-4.5"/></>,
  media:<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M8 5v4M16 5v4M10 12.5v4l3.5-2Z"/></>,
  wallNew:<><path d="M3 6.5 14 4.3v15.4L3 17.5Z"/><path d="M19 8v6M16 11h6"/></>,
  redraw:<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>,track:<><circle cx="12" cy="12" r="7"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></>,
  trash:<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>,
  // missing inputs: person with a slash (no person track), a cut-out silhouette with a slash (no subject matte)
  noPerson:<><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.8 3.6-6 7-6s6.2 2.2 7 6M3 3l18 18"/></>,
  noMatte:<><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="10" r="2.6"/><path d="M7.5 20c.6-3 2.4-4.6 4.5-4.6s3.9 1.6 4.5 4.6M3 3l18 18"/></>,
  matte:<><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="10" r="2.6"/><path d="M7.5 20c.6-3 2.4-4.6 4.5-4.6s3.9 1.6 4.5 4.6"/></>,
};

export function Icon({name,size=16}:{name:string;size?:number}){
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{P[name]}</svg>;
}
