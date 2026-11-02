"""Read-only review of the populated local Angel reference board and live workflow readiness."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
OUT=Path('outputs/progress/reference-board');pid='2011807a-4665-4f2f-a7e8-a410a24a9834'
c=httpx.Client(base_url='http://127.0.0.1:8787',timeout=30)
p=c.get(f'/api/projects/{pid}').json();assert len(p['board']['cards'])>=10
errors=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050));page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:5174/#/studio?project={pid}');page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
 expect(page.locator('.wf-panel').get_by_role('button',name='Generate 2 takes',exact=True)).to_be_enabled(timeout=30000)
 page.get_by_role('button',name='Board',exact=True).click();expect(page.get_by_role('region',name='Reference board')).to_be_visible()
 page.get_by_role('button',name='Fit board',exact=True).click()
 page.wait_for_function("Array.from(document.querySelectorAll('.rb-card-media img')).every(i=>i.complete&&i.naturalWidth>0)")
 page.wait_for_timeout(600);page.screenshot(path=str(OUT/'angel-board.png'))
 page.locator('[data-board-card="wardrobe"] .rb-card-title').click()
 expect(page.get_by_label('Reference role',exact=True)).to_have_value('wardrobe')
 expect(page.get_by_text('This workflow exposes one matching reference input. Assigning another image replaces that input.',exact=True)).to_be_visible()
 page.screenshot(path=str(OUT/'angel-wardrobe.png'))
 page.get_by_role('button',name='Open generation & takes ↗',exact=True).click()
 expect(page.locator('.wf-panel').get_by_label('Reference clip',exact=True)).to_have_value('angel-motion')
 expect(page.locator('.wf-panel').get_by_role('button',name='Generate 2 takes',exact=True)).to_be_enabled()
 assert not errors,errors
 browser.close()
ws=c.get('/api/workflows').json();w=next(w for w in ws if w['id']==p['layers'][0]['generation']['workflowId'])
report=dict(projectId=pid,cards=len(p['board']['cards']),generationEnabled=True,target=w.get('target'),missingModels=w.get('missingModels'),browserErrors=errors)
(OUT/'demo-review.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
