"""Review the separate Angel study with real media; never edits the original Angel project."""
import json,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
OUT=Path('outputs/progress/takes');demo=json.loads((OUT/'demo.json').read_text())
c=httpx.Client(base_url='http://127.0.0.1:8787',timeout=120)
original=c.get(f"/api/projects/{demo['originalProject']}").content
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    context=browser.new_context(viewport=dict(width=1440,height=1050),record_video_dir=str(OUT/'recording'),record_video_size=dict(width=1440,height=1050))
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(demo['url']);page.wait_for_selector('.stage-loading',state='hidden',timeout=60000)
    panel=page.locator('.wf-panel')
    expect(panel.get_by_label('Reference clip')).to_have_value('angel-motion')
    expect(panel.get_by_role('listbox',name='Takes')).to_be_visible()
    expect(panel.get_by_role('option',name='Preview Forest · take 01',exact=True)).to_be_visible()
    expect(panel.get_by_role('button',name='Generate 2 takes',exact=True)).to_be_disabled()
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT/'angel-current.png'))
    panel.get_by_role('option',name='Preview Forest · take 02',exact=True).click()
    expect(page.get_by_text('Candidate preview',exact=True)).to_be_visible()
    page.get_by_role('button',name='Loop',exact=True).click()
    page.keyboard.press('Space');page.wait_for_timeout(2200);page.keyboard.press('Space')
    page.screenshot(path=str(OUT/'angel-candidate.png'))
    # Accept on the stage; source choice is the only edit to the media layer.
    page.locator('.take-preview-status').get_by_role('button',name='Replace selected clip',exact=True).click()
    with page.expect_response(lambda r:r.request.method=='PUT' and demo['projectId'] in r.url):page.locator('.s-save').click()
    p=c.get(f"/api/projects/{demo['projectId']}").json()
    assert p['layers'][0]['assetId']==demo['takes'][1]
    assert p['layers'][0]['out']==3 and len(p['layers'][0]['keys'])==2
    panel.get_by_role('option',name='Preview Portrait · take 03',exact=True).click()
    page.keyboard.press('Space');page.wait_for_timeout(2200);page.keyboard.press('Space')
    page.locator('.take-preview-status').get_by_role('button',name='Return to current',exact=True).click()
    # Leave the study on its initial take; all three remain available.
    panel.get_by_role('option',name='Preview Forest · take 01',exact=True).click()
    page.locator('.take-preview-status').get_by_role('button',name='Replace selected clip',exact=True).click()
    with page.expect_response(lambda r:r.request.method=='PUT' and demo['projectId'] in r.url):page.locator('.s-save').click()
    page.locator('.s-left').evaluate('(e)=>e.scrollTop=0')
    page.screenshot(path=str(OUT/'angel-study.png'))
    assert not errors,errors
    video=page.video;context.close();video.save_as(str(OUT/'angel-iteration.webm'));browser.close()
assert c.get(f"/api/projects/{demo['originalProject']}").content==original,'Original project changed'
# Exercise the regular export path with media layers, music and existing text/effects.
r=c.post(f"/api/projects/{demo['projectId']}/export",json=dict(layer='composite',formats=['mp4'],scale=1));r.raise_for_status();job=r.json()
deadline=time.monotonic()+180
while job['status'] in ('queued','running') and time.monotonic()<deadline:
    time.sleep(2);job=c.get(f"/api/jobs/{job['id']}").json()
assert job['status']=='done',job
report=dict(projectId=demo['projectId'],browserErrors=errors,originalUnchanged=True,export=job['result'])
(OUT/'demo-review.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
