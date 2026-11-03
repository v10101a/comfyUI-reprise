/** Where the studio is mounted: '' at a site root (vite dev, FastAPI :8787), '/typeset' inside ComfyUI.
 *  Built with a relative Vite base, so only root-absolute paths written in code need `at()`. */
// A nested entry (studio/index.html) names the site root with <html data-root="../"> so shared files stay at the root.
export const BASE = new URL(document.documentElement.dataset.root || '.', document.baseURI).pathname.replace(/\/$/, '');
export const at = (path: string) => BASE && path.startsWith('/') && !path.startsWith('//') && !path.startsWith(`${BASE}/`) ? `${BASE}${path}` : path;
