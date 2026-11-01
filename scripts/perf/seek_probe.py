"""Time the renderer's seek() (which waits for the frame to be presented) per media URL in headless Chromium.

  server/.venv/bin/python scripts/perf/seek_probe.py \
    orig=/files/projects/<pid>/media/clip.mp4 half=/files/projects/<pid>/media/proxy_cand/half_intra.mp4

Reports, per URL: median of jumps to spaced frames, median of consecutive-frame steps (a scrub), and the max.
Read-only: all non-GET requests are aborted.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('urls', nargs='+', help='label=url (url relative to origin or absolute)')
    ap.add_argument('--origin', default='http://127.0.0.1:5174')
    ap.add_argument('--fps', type=float, default=24)
    ap.add_argument('--jumps', default='24,96,300,48,480,150,400,72')
    ap.add_argument('--scrub-start', type=int, default=200)
    ap.add_argument('--scrub-len', type=int, default=24)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    origin = a.origin.rstrip('/')
    items = [u.split('=', 1) for u in a.urls]
    jumps = [int(x) for x in a.jumps.split(',')]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()

        def readonly(route):
            req = route.request
            if req.method not in ('GET', 'HEAD', 'OPTIONS'):
                route.abort()
            elif req.url.split('#')[0] == origin + '/__typeset_perf__':
                route.fulfill(status=200, content_type='text/html', body='<html><body></body></html>')
            else:
                route.continue_()
        context.route('**/*', readonly)
        page = context.new_page()
        page.goto(origin + '/__typeset_perf__')
        results = []
        for label, url in items:
            data = page.evaluate('''async ({url,fps,jumps,s0,sl}) => {
              const {seek}=await import('/src/renderer.ts');
              const v=document.createElement('video');v.crossOrigin='anonymous';v.preload='auto';v.muted=true;v.playsInline=true;
              const t0=performance.now();
              await new Promise((res,rej)=>{v.onloadeddata=()=>res();v.onerror=()=>rej(new Error('load '+url));v.src=url;v.load();});
              const loadMs=performance.now()-t0;
              const m=async(f)=>{const a=performance.now();await seek(v,(f+.5)/fps);return performance.now()-a;};
              const jump=[];for(const f of jumps)jump.push(await m(f));
              const scrub=[];for(let f=s0;f<s0+sl;f++)scrub.push(await m(f));
              const back=[];for(let f=s0+sl;f>s0;f--)back.push(await m(f));
              v.removeAttribute('src');v.load();
              return {loadMs,w:v.videoWidth,h:v.videoHeight,jump,scrub,back};
            }''', {'url': url, 'fps': a.fps, 'jumps': jumps, 's0': a.scrub_start, 'sl': a.scrub_len})
            med = lambda xs: round(sorted(xs)[len(xs) // 2], 1)
            row = {'label': label, 'size': f"{data['w']}x{data['h']}", 'load_ms': round(data['loadMs']),
                   'jump_med': med(data['jump']), 'jump_max': round(max(data['jump'])),
                   'scrub_fwd_med': med(data['scrub']), 'scrub_back_med': med(data['back']), 'scrub_max': round(max(data['scrub'] + data['back']))}
            results.append({**row, 'raw': data})
            print(json.dumps(row), flush=True)
        browser.close()
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=2))
        print(a.out)


if __name__ == '__main__':
    main()
