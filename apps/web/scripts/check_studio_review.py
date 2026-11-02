"""Read-only checks for look depth, visual tuning, and timeline copy/paste/split.

Project saves are fulfilled in memory; this never modifies stored user projects.
"""
import argparse
import base64
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

PROJECT = 'f5db48db-b4d4-42c8-b54e-00ce40116255'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5174')
    parser.add_argument('--out', type=Path, default=Path('outputs/studio_review'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Instrument whichever Vite module URL Studio imports (HMR may add a timestamp query).
        def instrument_renderer(route):
            response = route.fetch()
            route.fulfill(response=response, body=response.text() + '''
                const auditRender=StageRenderer.prototype.render;
                StageRenderer.prototype.render=function(...args){
                    if(args[0].isConnected)(window.previewOptions??=[]).push(args[3]||{});
                    return auditRender.apply(this,args);
                };
            ''')
        page.route('**/src/renderer.ts*', instrument_renderer)
        page.goto(f'{args.base}/#/render?project={PROJECT}&layer=composite&look=flat-card&subs=0')
        page.wait_for_function('window.__typeset!==undefined')
        page.evaluate('()=>window.__typeset.ready')
        visual = page.evaluate('''async pid=>{
            const {StageRenderer}=await import('/src/renderer.ts');
            const {setLook}=await import('/src/looks.ts');
            const {lookPreviewFrame}=await import('/src/studio/LookPicker.tsx');
            const p=await fetch('/api/projects/'+pid).then(r=>r.json());
            const r=new StageRenderer(p);await r.load();const c=document.createElement('canvas');
            const pictures={};
            for(const id of ['flat-card','paper-cut','xerox','neon']){
                r.project={...setLook(p,id),grade:null,words:p.words.filter(w=>w.placement==='surface')};
                await r.render(c,130,'composite');pictures[id]=c.toDataURL('image/png');
            }
            const q={...p,surfaces:[],lineMeta:null,grade:null,words:[{id:'test',lineId:'one',text:'DANCING',
                start:0,end:p.duration,placement:'behind',preset:'none',autoPlace:false,position:{x:.5,y:.5}}]};
            const counts={};
            const count=()=>{const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i])n++;return n;};
            for(const placement of ['behind','overlay']){
                r.project=setLook({...q,words:q.words.map(w=>({...w,placement}))},'ticker');
                for(const layer of ['text-behind','text-front']){await r.render(c,24,layer);counts[placement+':'+layer]=count();}
                await r.render(c,24,'composite');pictures['marquee-'+placement]=c.toDataURL('image/png');
            }
            // A lone line otherwise becomes an inferred hook. Ordinary titles get the new minimum;
            // authored hooks keep their size so existing count-ins and hero edits do not change.
            r.project=setLook({...q,lineMeta:{one:{hook:false}},words:q.words.map(w=>({...w,autoPlace:true,position:null,style:{fontSize:.04}}))},'flat-card');
            await r.render(c,24,'composite');pictures['flat-card-title']=c.toDataURL('image/png');
            const unit=r.units(c.getContext('2d'))[0];const title={size:unit.size/p.height,position:unit.words[0].position,placement:unit.placement};
            r.project=setLook({...q,lineMeta:{one:{hook:true}},words:q.words.map(w=>({...w,style:{fontSize:.04}}))},'flat-card');
            const hookUnit=r.units(c.getContext('2d'))[0];const hook={size:hookUnit.size/p.height,position:hookUnit.words[0].position};
            const preview=lookPreviewFrame({...q,words:q.words.map(w=>({...w,start:2,end:4}))},0);
            r.dispose();return {pictures,counts,title,hook,preview};
        }''', PROJECT)
        for name, data in visual.pop('pictures').items():
            (args.out / f'{name}.png').write_bytes(base64.b64decode(data.split(',')[1]))
        report['renderer'] = visual
        assert visual['counts']['behind:text-behind'] > 0 and visual['counts']['behind:text-front'] == 0, visual
        assert visual['counts']['overlay:text-front'] > 0 and visual['counts']['overlay:text-behind'] == 0, visual
        assert visual['title']['size'] >= .15 and visual['title']['position'] == {'x': .5, 'y': .5}, visual
        assert abs(visual['hook']['size'] - .04) < 1e-6 and visual['hook']['position'] == {'x': .5, 'y': .5}, visual
        assert 48 < visual['preview'] < 96, visual

        project = page.request.get(f'{args.base}/api/projects/{PROJECT}').json()
        project.update(name='Read-only Studio check', duration=8, surfaces=[], lineMeta=None,
                       look={'id': 'flat-card'}, grade=None,
                       words=[{'id': 'first', 'lineId': 'first-line', 'text': 'DANCING', 'start': 1, 'end': 3,
                               'placement': 'behind', 'preset': 'none'},
                              {'id': 'second', 'lineId': 'second-line', 'text': 'NIGHT', 'start': 4, 'end': 6,
                               'placement': 'behind', 'preset': 'none'}])
        saved = []

        def api(route):
            path = urlsplit(route.request.url).path
            if path == f'/api/projects/{PROJECT}':
                if route.request.method == 'PUT':
                    saved.append(route.request.post_data_json)
                route.fulfill(json=saved[-1] if saved else project)
            elif path == '/api/projects':
                route.fulfill(json=[project])
            elif path == '/api/jobs':
                route.fulfill(json=[])
            elif route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
                route.abort()
            else:
                route.continue_()

        page.route('**/api/**', api)
        page.goto(f'{args.base}/#/studio?project={PROJECT}')
        page.wait_for_selector('.tl-region')
        page.locator('.word-chip').first.click()
        expect(page.get_by_role('textbox', name='Word text', exact=True)).to_be_visible()
        expect(page.get_by_role('textbox', name='Word text', exact=True)).to_have_value('DANCING')
        expect(page.locator('.s-right summary').filter(has_text='More')).to_have_count(0)
        page.locator('.s-right summary').filter(has_text='Position & motion').click()
        page.get_by_role('button', name='Align center', exact=True).click()
        expect(page.get_by_role('button', name='Align center', exact=True)).to_have_attribute('aria-pressed', 'true')
        page.get_by_role('button', name='Copy text clips', exact=True).click()

        def seek(t):
            box = page.locator('.tl-ruler').bounding_box()
            page.mouse.click(box['x'] + box['width'] * t / 8, box['y'] + box['height'] * .7)

        seek(5)
        page.keyboard.press('Meta+v')
        expect(page.locator('.tl-region')).to_have_count(3)
        page.keyboard.press('Meta+z')
        expect(page.locator('.tl-region')).to_have_count(2)
        page.keyboard.press('Meta+Shift+z')
        expect(page.locator('.tl-region')).to_have_count(3)
        page.locator('.word-chip').first.click()
        seek(2)
        expect(page.get_by_role('button', name='Split selected clip', exact=True)).to_be_enabled()
        page.keyboard.press('Meta+b')
        expect(page.locator('.tl-region')).to_have_count(4)
        page.keyboard.press('Meta+z')
        expect(page.locator('.tl-region')).to_have_count(3)
        deadline = time.monotonic() + 30
        while (not saved or len(saved[-1]['words']) != 3) and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        assert saved and len(saved[-1]['words']) == 3, saved
        assert sorted((w['start'], w['end']) for w in saved[-1]['words']) == [(1, 3), (4, 6), (5, 7)], saved[-1]['words']
        # Inspector drags use the same light preview path as timeline/stage drags, then restore settled quality.
        page.locator('.word-chip').first.click()
        page.evaluate('window.previewOptions=[]')
        slider = page.locator('.s-right .size-row input[type=range]').first
        slider.scroll_into_view_if_needed()
        slider.hover()
        box = slider.bounding_box()
        page.mouse.move(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] * .6, box['y'] + box['height'] * .5, steps=4)
        try:
            page.wait_for_function('window.previewOptions.some(o=>o.proxy && o.heavyOptics===false && o.cacheMedia)')
        except Exception:
            page.screenshot(path=str(args.out / 'inspector-failure.png'))
            print(json.dumps({'slider': box, 'renders': page.evaluate('window.previewOptions')}), flush=True)
            raise
        page.evaluate('window.previewOptions=[]')
        page.mouse.up()
        page.wait_for_function('window.previewOptions.some(o=>o.full && o.cacheMedia && o.heavyOptics!==false)')
        page.screenshot(path=str(args.out / 'studio.png'))
        report['timeline'] = {'copyPaste': True, 'split': True, 'undoRedo': True, 'inspectorDraftThenFull': True, 'savedInMemory': len(saved)}
        assert not errors, errors
        report['passed'] = True
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        browser.close()
    print(json.dumps(report))


if __name__ == '__main__':
    main()
