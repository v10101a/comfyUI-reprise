"""Browser checks for editor interactions and deterministic alpha/composite rendering.
Run from repo root with server/.venv/bin/python apps/web/scripts/check_browser.py.
Requires running Vite (:5173), Playwright Chromium, and generated sample assets.
"""
import asyncio
import base64
import os
import io
import json
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

BASE = os.environ.get('TYPESET_WEB_URL','http://127.0.0.1:5174')
OUT = Path('outputs/web-check')

async def pixels(page, frame):
    data = await page.evaluate('''async frame => {
      await window.__typeset.ready;
      await window.__typeset.renderFrame(frame);
      return document.querySelector('#stage').toDataURL('image/png').split(',')[1];
    }''', frame)
    return Image.open(io.BytesIO(base64.b64decode(data))).convert('RGBA')

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':950}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto(BASE+'/#/studio')
        await page.wait_for_selector('.line-words button')
        await page.wait_for_selector('.stage-loading', state='hidden', timeout=30000)
        assert await page.locator('.word-chip').count() == 25
        # Word-level fields live behind the "Word details" disclosure of the line inspector.
        await page.locator('.word-details summary').click()
        await page.locator('.word-input').fill('Motion')
        assert await page.locator('.line-words button.selected').inner_text() == 'Motion'
        await page.get_by_role('button',name='Forward one frame',exact=True).click()
        await page.get_by_role('button',name='Play',exact=True).click()
        await page.wait_for_timeout(300)
        await page.get_by_role('button',name='Pause',exact=True).click()
        await page.screenshot(path=str(OUT/'editor.png'))
        assert not errors, errors
        await page.goto(BASE+'/#/render?project=sample&layer=text')
        await page.wait_for_function('window.__typeset !== undefined')
        first=await pixels(page,24)
        await pixels(page,170)
        again=await pixels(page,24)
        assert first.tobytes()==again.tobytes(), 'Seeking changed text pixels'
        alpha=first.getchannel('A')
        assert alpha.getextrema()==(0,255), 'Text layer must include transparent and opaque pixels'
        first.save(OUT/'text.png')
        captured=await page.locator('#stage').screenshot(omit_background=True)
        screenshot=Image.open(io.BytesIO(captured)).convert('RGBA')
        assert screenshot.getchannel('A').getextrema()==(0,255), 'Screenshot must preserve text alpha through the html/body backgrounds'
        screenshot.save(OUT/'text-capture.png')
        # Verify exact hold/hide boundary directly against the sample detector gap.
        hold_hide=await page.evaluate('''async()=>{const {anchorAt}=await import('/src/renderer.ts');const tracks=await fetch('/sample/tracks.json').then(r=>r.json());return [Boolean(anchorAt(tracks,'person0',155)),Boolean(anchorAt(tracks,'person0',156))];}''')
        assert hold_hide==[True,False], 'Track gap hold/hide boundary is wrong'
        # HUD anchor is hidden after six missing track frames (gap 150..168).
        hidden=await pixels(page,156)
        assert hidden.getchannel('A').getextrema()==(0,0), 'Missing-track frame should not draw stale anchor'
        await page.goto(BASE+'/#/render?project=sample&layer=composite')
        await page.wait_for_function('window.__typeset !== undefined')
        composite=await pixels(page,82)
        await pixels(page,250)
        repeated=await pixels(page,82)
        assert composite.tobytes()==repeated.tobytes(), 'Composite seek is not deterministic'
        assert composite.getchannel('A').getextrema()==(255,255)
        composite.save(OUT/'composite.png')
        assert not errors, errors
        # API projects may have explicit null media entries before upload or
        # when only one kind of media is present. Opening Media must not crash.
        empty = json.loads(Path('apps/web/public/sample/project.json').read_text())
        empty.update(id='null-media', name='Empty media regression', words=[], shots=[], analysis={})
        empty['media'] = {'video': None, 'audio': None, 'lyrics': None}
        await page.route('**/api/projects', lambda route: route.fulfill(json=[empty]))
        await page.route('**/api/projects/null-media', lambda route: route.fulfill(json=empty))
        await page.goto(BASE+'/#/studio')
        await page.get_by_role('button', name='Media', exact=True).click()
        await page.locator('.project-list option[value="null-media"]').wait_for(state='attached')
        await page.locator('.project-list select').select_option('null-media')
        await page.wait_for_function('document.querySelector("[aria-label=\\"Project name\\"]")?.value === "Empty media regression"')
        assert await page.locator('.media-card').count() == 0
        assert not errors, errors
        print('PASS: editor edits/playback, deterministic random seeking, transparent text, opaque composite, missing-track behavior, null media project')
        print('Artifacts:',OUT)
        await browser.close()

if __name__=='__main__': asyncio.run(main())
