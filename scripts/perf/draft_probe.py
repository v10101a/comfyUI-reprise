"""Composite render cost on the real StageRenderer: final (originals, heavy optics) vs draft (preview proxies, light
optics), as jumps and as a scrub. Also checks the text layer is byte-identical with proxies on (proxies only change
what the footage decodes from).

  server/.venv/bin/python scripts/perf/draft_probe.py --project <pid> [--out outputs/perf/draft-<label>.json]
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERO = '54da2790-92c6-4737-bc43-81a207e47ab5'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--origin', default='http://127.0.0.1:5174')
    ap.add_argument('--project', default=HERO)
    ap.add_argument('--jumps', default='24,96,300,48,480,150,400,72')
    ap.add_argument('--scrub-start', type=int, default=200)
    ap.add_argument('--scrub-len', type=int, default=24)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    origin = a.origin.rstrip('/')
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
        data = page.evaluate('''async ({pid,jumps,s0,sl}) => {
          const {StageRenderer}=await import('/src/renderer.ts');
          const p=await fetch('/api/projects/'+pid).then(r=>r.json());
          const r=new StageRenderer(p);r.draftMedia=true;await r.load();
          const canvas=document.createElement('canvas');
          const info={name:p.name,size:`${p.width}x${p.height}`,bgProxy:r.bgProxy?`${r.bgProxy.videoWidth}x${r.bgProxy.videoHeight}`:null,
            matteProxy:r.matteProxy?`${r.matteProxy.videoWidth}x${r.matteProxy.videoHeight}`:null};
          const m=async(fn)=>{const a=performance.now();await fn();return performance.now()-a;};
          const modes={final:{},settled_full_copies:{full:true},draft:{proxy:true,heavyOptics:false},proxy_only:{proxy:true},light_only:{heavyOptics:false}};
          info.seekCopies=!!(r.bgSeek||r.matteSeek);
          const out={};
          for(const [name,opts] of Object.entries(modes)){
            const jump=[];for(const f of jumps)jump.push(await m(()=>r.render(canvas,f,'composite',opts)));
            const scrub=[];for(let f=s0;f<s0+sl;f++)scrub.push(await m(()=>r.render(canvas,f,'composite',opts)));
            out[name]={jump,scrub};
          }
          // Paused frames on the full-size copies vs the originals: mean absolute RGB difference (0-255) and worst pixel.
          const px=async(opts)=>{await r.render(canvas,jumps[2],'composite',opts);return canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;};
          const A=await px({}),B=await px({full:true});let sum=0,mx=0;for(let i=0;i<A.length;i+=4)for(let k=0;k<3;k++){const d=Math.abs(A[i+k]-B[i+k]);sum+=d;if(d>mx)mx=d;}
          info.fullCopyDiff={meanAbs:+(sum/(A.length/4*3)).toFixed(3),max:mx};
          // Text layer must not depend on the proxy flag.
          await r.render(canvas,48,'text',{});const a1=canvas.toDataURL();
          await r.render(canvas,48,'text',{proxy:true});const a2=canvas.toDataURL();
          r.dispose();
          return {info,out,textIdentical:a1===a2};
        }''', {'pid': a.project, 'jumps': [int(x) for x in a.jumps.split(',')], 's0': a.scrub_start, 'sl': a.scrub_len})
        browser.close()
    med = lambda xs: round(sorted(xs)[len(xs) // 2], 1)
    print(json.dumps(data['info']))
    for name, d in data['out'].items():
        print(json.dumps({'mode': name, 'jump_med': med(d['jump']), 'jump_max': round(max(d['jump'])), 'scrub_med': med(d['scrub']), 'scrub_max': round(max(d['scrub']))}))
    print(json.dumps({'text_layer_identical_with_proxy': data['textIdentical']}))
    if a.out:
        Path(a.out).write_text(json.dumps(data, indent=2))
        print(a.out)


if __name__ == '__main__':
    main()
