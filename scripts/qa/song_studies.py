"""Check imported real song studies in the browser, intercepting every write/generation."""
import copy,json,math
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
OUT=Path('outputs/songs/studios');state=json.loads((OUT/'manifest.json').read_text())
api=httpx.Client(base_url='http://127.0.0.1:8787',timeout=60)
report={};errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    for slug,info in state['projects'].items():
        p=api.get('/api/projects/'+info['id']).json();saved=copy.deepcopy(p);runs=[]
        layers=[l for l in p['layers'] if l['kind']=='media'];assets={a['id']:a for a in p['assets']}
        for i,l in enumerate(layers):
            assert (Path('data/projects')/p['id']/assets[l['assetId']]['path']).is_file()
            assert abs(l['start']-(layers[i-1]['start']+layers[i-1]['out']-layers[i-1]['in'] if i else 0))<1e-5
            assert l['out']<=assets[l['assetId']]['duration']+1/p['fps'],(slug,l,assets[l['assetId']]['duration'])
        assert abs(layers[-1]['start']+layers[-1]['out']-layers[-1]['in']-p['duration'])<1e-5
        original=api.get('/api/projects/'+info['originalId']).json();snapshot=json.loads((OUT/f'{slug}-original.json').read_text())
        for key in ('words','layers','media','style','look'):assert original.get(key)==snapshot.get(key),(slug,key,'original changed')
        shift=original['media']['audioClip']['in']-original['media']['audioClip'].get('offset',0)-p['media']['audioClip']['in']
        assert len(p['words'])==len(original['words'])
        for a,b in zip(p['words'],original['words']):assert abs(a['start']-b['start']-shift)<1e-5
        page=browser.new_page(viewport=dict(width=1600,height=1050));page.on('pageerror',lambda e:errors.append(str(e)))
        def guard(r):
            global saved
            req=r.request;path=req.url.split('/api/',1)[-1].split('?',1)[0]
            if path=='projects/'+p['id']:
                if req.method=='PUT':saved=req.post_data_json
                r.fulfill(json=saved)
            elif path=='session':r.fulfill(json=dict(projectId=p['id']))
            elif path=='jobs':r.fulfill(json=[])
            elif req.method not in ('GET','HEAD'):
                if path.endswith('/run'):
                    runs.append(req.post_data_json);r.fulfill(json=dict(id='qa-run',kind='workflow',status='done',projectId=p['id'],result={'assets':[]}))
                else:r.fulfill(status=409,json={'detail':'Writes disabled in song study QA'})
            else:r.continue_()
        page.route('**/api/**',guard);page.goto(info['url']);page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
        page.get_by_role('button',name='Board',exact=True).click()
        expect(page.locator('[data-board-card]')).to_have_count(len(p['board']['cards']))
        page.wait_for_function("[...document.querySelectorAll('.rb-card video')].every(v=>v.readyState>=2)",timeout=30000)
        page.screenshot(path=str(OUT/f'{slug}-board.png'))
        # Select a singing shot beyond the opening, then enter Create; no timeline selection required.
        l=next(l for l in layers[1:] if l.get('generation',{}).get('workflowId')=='ed3fbc575706')
        c=next(c for c in p['board']['cards'] if c.get('layerId')==l['id'] and c['kind']=='asset')
        page.locator(f'[data-board-card="{c["id"]}"] .rb-card-title').click()
        expect(page.get_by_label('Board target layer')).to_have_value(l['id'])
        page.get_by_role('button',name='Open generation & takes ↗').click()
        panel=page.locator('.wf-panel');expect(panel.get_by_label('Reference clip')).to_have_value(l['id'])
        expect(panel.get_by_label('Workflow',exact=True)).to_have_value('ed3fbc575706')
        expect(page.locator('.time-display')).to_have_attribute('title',f'frame {round(l["start"]*p["fps"])} / {round(p["duration"]*p["fps"])}')
        vocal=panel.locator('#ref-audio');expect(vocal).to_have_value('@prepared')
        run=panel.get_by_role('button',name='Generate take',exact=True);expect(run).to_be_enabled(timeout=20000)
        page.wait_for_function("""()=>{const c=document.querySelector('.stage-wrap canvas');if(!c)return false;
          const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;
          for(let i=0;i<d.length;i+=16)if(d[i]+d[i+1]+d[i+2]>60)n++;return n>c.width*c.height/20;}""",timeout=30000)
        page.screenshot(path=str(OUT/f'{slug}-create.png'))
        run.click();expect(run).to_be_enabled(timeout=10000)
        draft=l['generation']['workflows']['ed3fbc575706'];body=runs[-1]
        assert body['sources']['audio']==dict(path=draft['mediaFiles']['audio']['path'],start=0,end=draft['mediaFiles']['audio']['duration'])
        assert body['postprocess']==draft['postprocess'] and body['layerId']==l['id'] and body['remote']
        vocal.select_option('@song');run.click();expect(run).to_be_enabled(timeout=10000)
        assert runs[-1]['sources']['audio']==dict(start=l['start'],end=l['start']+l['out']-l['in'])
        assert 'postprocess' not in runs[-1]
        if slug=='playboi':
            made=next((a for a in p['assets'] if a.get('source',{}).get('workflowId')=='ed3fbc575706' and a.get('source',{}).get('seed')==29),None)
            if made:
                lid=made['source']['layerId'];authored=next(l for l in p['layers'] if l['id']==lid)
                panel.get_by_label('Reference clip').select_option(lid)
                panel.get_by_role('option',name='Preview '+made['name'],exact=True).click()
                expect(panel.get_by_role('button',name='Candidate',exact=True)).to_have_attribute('aria-pressed','true')
                # The generated candidate can be auditioned without modifying the accepted source.
                assert next(l for l in saved['layers'] if l['id']==lid)['assetId']==authored['assetId']
                page.wait_for_timeout(1200);page.screenshot(path=str(OUT/'playboi-new-take.png'))
                panel.get_by_role('button',name='Replace selected clip',exact=True).click();page.wait_for_timeout(1500)
                accepted=next(l for l in saved['layers'] if l['id']==lid)
                assert accepted['assetId']==made['id']
                for k in ('start','in','out','transform','keys','opacity','mask'):assert accepted.get(k)==authored.get(k),k
        assert not errors,errors
        report[slug]=dict(shots=len(layers),cards=len(p['board']['cards']),assets=len(p['assets']),duration=p['duration'],words=len(p['words']),originalUnchanged=True,requests=runs,browserErrors=errors.copy())
        page.close()
    browser.close()
(OUT/'qa.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:{x:v for x,v in r.items() if x!='requests'} for k,r in report.items()},indent=2))
