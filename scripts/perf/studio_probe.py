"""Read-only studio performance probe (parameterized copy of the 2026-10-31 audit script).

Two modes against a running Vite dev server:
  renderer (default): import StageRenderer directly, time composite/text renders, seeks and every look.
  --ui: drive the real Studio (scrub the ruler, drag a line), record renders, long tasks and pointer timing.
All non-GET requests are aborted, so autosave never writes. --fast is the diagnostic-only variant from the
audit (heavy optics off, detached-canvas renders skipped); never treat it as a production patch.

  python3 scripts/perf/studio_probe.py --label baseline
  python3 scripts/perf/studio_probe.py --ui --label baseline
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_PROJECTS = [
    '54da2790-92c6-4737-bc43-81a207e47ab5',  # Neon Rain (hero), flat-card
    '4b960dd8-1ef5-465e-b698-44784b8f873e',  # LOUDER fields demo, red-glow + fields
]

PATCH = '''
const auditLoad=StageRenderer.prototype.load,auditRender=StageRenderer.prototype.render;
StageRenderer.prototype.load=async function(...args){this.auditId=(window.auditSerial=(window.auditSerial||0)+1);const start=performance.now();try{return await auditLoad.apply(this,args);}finally{window.perfAudit.loads.push({id:this.auditId,start,ms:performance.now()-start});}};
StageRenderer.prototype.render=async function(...args){
  if(window.auditFast){this.heavyOptics=false;if(!args[0].isConnected)return;}
  const start=performance.now(),look=this.project.look?.id||'default',stage=!!args[0].isConnected;try{return await auditRender.apply(this,args);}finally{const o=args[3]||{};window.perfAudit.renders.push({id:this.auditId,look,stage,frame:args[1],q:o.full?'full':o.proxy?(o.heavyOptics===false?'draft':'proxy'):'orig',start,ms:performance.now()-start});}};
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--origin', default='http://127.0.0.1:5174')
    ap.add_argument('--projects', nargs='*', default=DEFAULT_PROJECTS)
    ap.add_argument('--out-dir', default='outputs/perf')
    ap.add_argument('--label', default='run')
    ap.add_argument('--ui', action='store_true')
    ap.add_argument('--fast', action='store_true', help='diagnostic only')
    ap.add_argument('--steps', type=int, default=30)
    ap.add_argument('--settle-ms', type=int, default=2000)
    ap.add_argument('--play-ms', type=int, default=4000, help='UI mode: also press space and record playback for this long (0 = skip)')
    a = ap.parse_args()
    origin = a.origin.rstrip('/')
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    suffix = ('-ui' if a.ui else '-renderer') + ('-fast' if a.fast else '')
    out = out_dir / f'{a.label}{suffix}-{stamp}.json'

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 950})

        def readonly(route):
            req = route.request
            if req.method not in ('GET', 'HEAD', 'OPTIONS'):
                route.abort()
            elif req.url.split('#')[0] == origin + '/__typeset_perf__':
                route.fulfill(status=200, content_type='text/html', body='<html><body><div id="root"></div></body></html>')
            elif a.ui and '/src/renderer.ts' in req.url:
                response = route.fetch()
                route.fulfill(response=response, body=response.text() + PATCH)
            else:
                route.continue_()
        context.route('**/*', readonly)
        page = context.new_page()

        if a.ui:
            page.goto(origin + '/__typeset_perf__#/studio?project=' + a.projects[0])
            page.evaluate('''async()=>{
              const refresh=await import('/@react-refresh');refresh.default.injectIntoGlobalHook(window);
              window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;
              window.perfAudit={renders:[],loads:[],longTasks:[],pointers:[]};
              new PerformanceObserver(l=>{for(const e of l.getEntries())window.perfAudit.longTasks.push({start:e.startTime,ms:e.duration});}).observe({type:'longtask',buffered:true});
              for(const name of ['pointerdown','pointermove','pointerup'])document.addEventListener(name,e=>window.perfAudit.pointers.push({name,t:performance.now(),x:e.clientX}),true);
            }''')
            page.evaluate('(fast)=>window.auditFast=fast', a.fast)
            page.evaluate('async()=>{await import("/src/main.tsx");}')
            page.wait_for_selector('.tl-ruler', timeout=30000)
            page.wait_for_timeout(6000)
            start_data = page.evaluate('window.perfAudit')
            steps = []
            for kind, selector in [('scrub', '.tl-ruler'), ('line_drag', '.tl-region')]:
                box = page.locator(selector).first.bounding_box()
                if not box:
                    steps.append({'kind': kind, 'error': 'element unavailable'})
                    continue
                page.evaluate('window.perfAudit={renders:[],loads:[],longTasks:[],pointers:[]}')
                x = box['x'] + min(box['width'] / 2, 30)
                y = box['y'] + box['height'] / 2
                page.mouse.move(x, y)
                t0 = time.monotonic()
                page.mouse.down()
                for i in range(1, a.steps + 1):
                    page.mouse.move(x + i * 3, y)
                    page.wait_for_timeout(16)
                page.mouse.up()
                drag_ms = (time.monotonic() - t0) * 1000
                page.wait_for_timeout(a.settle_ms)
                d = page.evaluate('window.perfAudit')
                d.update(kind=kind, dispatch_elapsed_ms=round(drag_ms, 1), nominal_wait_ms=16 * a.steps)
                steps.append(d)
            if a.play_ms > 0:
                page.evaluate('window.perfAudit={renders:[],loads:[],longTasks:[],pointers:[]}')
                page.keyboard.press('Space')
                page.wait_for_timeout(a.play_ms)
                page.keyboard.press('Space')
                page.wait_for_timeout(500)
                d = page.evaluate('window.perfAudit')
                d.update(kind='play', play_ms=a.play_ms)
                steps.append(d)
            result = {'kind': 'read-only isolated Chromium studio; all non-GET requests blocked', 'label': a.label,
                      'fast_experiment': a.fast, 'project': a.projects[0], 'startup': start_data, 'steps': steps}
            out.write_text(json.dumps(result, indent=2))
            for label, d in [('startup', start_data)] + [(d['kind'], d) for d in steps]:
                r = d.get('renders', [])
                stage = [x for x in r if x.get('stage')]
                thumbs = [x for x in r if not x.get('stage')]
                lt = [round(t['ms']) for t in d.get('longTasks', [])]
                print(json.dumps({'phase': label, 'stage_renders': len(stage), 'stage_ms_med': round(sorted([x['ms'] for x in stage])[len(stage)//2]) if stage else 0, 'stage_ms_max': round(max([x['ms'] for x in stage], default=0)),
                                  'thumb_renders': len(thumbs), 'thumb_ms_total': round(sum(x['ms'] for x in thumbs)),
                                  'long_tasks_ms': lt, 'dispatch_elapsed_ms': d.get('dispatch_elapsed_ms')}), flush=True)
            print(str(out), flush=True)
            browser.close()
            return

        page.goto(origin + '/__typeset_perf__')
        report = {'origin': origin, 'label': a.label, 'kind': 'headless Chromium read-only component timings', 'projects': []}
        for pid in a.projects:
            data = page.evaluate('''async pid => {
              const {StageRenderer,seek}=await import('/src/renderer.ts');
              const {setLook,LOOKS}=await import('/src/looks.ts');
              const p=await fetch('/api/projects/'+pid).then(r=>r.json());
              const r=new StageRenderer(p);const canvas=document.createElement('canvas');
              const loadStart=performance.now();await r.load();const loadMs=performance.now()-loadStart;
              const measure=async(fn)=>{const a=performance.now();await fn();return +(performance.now()-a).toFixed(2);};
              const frames=[24,48,72,96,120];
              const result={id:pid,name:p.name,width:p.width,height:p.height,look:p.look,loadMs:+loadMs.toFixed(2),passes:[]};
              for(const layer of ['composite','text']){
                for(const heavy of [true,false]){
                  r.heavyOptics=heavy;
                  const samples=[];for(const f of frames)samples.push(await measure(()=>r.render(canvas,f,layer)));
                  result.passes.push({layer,heavy,samples});
                }
              }
              const repeated=[];r.heavyOptics=true;await r.render(canvas,48);
              for(let i=0;i<5;i++)repeated.push(await measure(()=>r.render(canvas,48)));
              result.sameFrameMs=repeated;
              result.seeks={};
              for(const [key,v] of [['video',r.bg],['matte',r.matte]])if(v){
                result.seeks[key]=[];for(const f of frames)result.seeks[key].push(await measure(()=>seek(v,(f+.5)/p.fps)));
              }
              result.looks=[];
              for(const look of LOOKS){r.project=setLook(p,look.id==='default'?null:look.id);
                result.looks.push({id:look.id,ms:await measure(()=>r.render(canvas,48))});}
              r.dispose();return result;
            }''', pid)
            report['projects'].append(data)
            out.write_text(json.dumps(report, indent=2))
            med = lambda xs: sorted(xs)[len(xs) // 2]
            print(json.dumps({'project': data['name'], 'loadMs': data['loadMs'],
                              'median_ms': {f"{p['layer']}/{'heavy' if p['heavy'] else 'light'}": med(p['samples']) for p in data['passes']},
                              'sameFrame': med(data['sameFrameMs']), 'seeks': {k: [round(x) for x in v] for k, v in data['seeks'].items()},
                              'looks': {l['id']: round(l['ms']) for l in data['looks']}}), flush=True)
        browser.close()
    print(str(out), flush=True)


if __name__ == '__main__':
    main()
