"""Editor checks for v2 tools on a real project, without writing to it (PUT and v2 POSTs are intercepted).
Run from repo root: server/.venv/bin/python apps/web/scripts/check_v2_editor.py [project-id]
Covers: Place on surface (4 clicks, drag a handle, apply → 'tracking unavailable' when the endpoint 404s),
Find readable space toggle, Preview 9:16 side-by-side, Make vertical fallback. Screenshots → apps/web/.verify/editor_*.png
"""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
PID = sys.argv[1] if len(sys.argv) > 1 else 'beeba9e1-9178-4f24-b9ce-9fb119bb33f6'
OUT = Path(__file__).resolve().parents[1] / '.verify'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); page = await b.new_page(viewport={'width': 1500, 'height': 1000})
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
        saved = {}
        async def put(route):
            if route.request.method == 'PUT':
                saved['p'] = json.loads(route.request.post_data); await route.fulfill(json=saved['p'])
            else: await route.continue_()
        await page.route(f'**/api/projects/{PID}', put)
        await page.route('**/surfaces/*/track', lambda r: r.fulfill(status=404, json={'detail': 'Not Found'}))
        await page.route('**/reframe', lambda r: r.fulfill(status=404, json={'detail': 'Not Found'}))
        await page.goto(f'{BASE}/#/studio?project={PID}')
        await page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
        await page.locator('.word-chip', has_text='the neon rain').click()  # arrangement clip selects the line
        assert await page.locator('.auto-place input[type=checkbox]').is_checked()
        for _ in range(40): await page.keyboard.press('ArrowRight')
        await page.get_by_role('button', name='▱ Place on surface').click()
        box = await page.locator('.surface-overlay').bounding_box()
        for x, y in [(.36, .05), (.66, .17), (.66, .62), (.36, .70)]:
            await page.mouse.click(box['x'] + x * box['width'], box['y'] + y * box['height'])
        h = page.locator('.surface-overlay .handle circle').nth(1); hb = await h.bounding_box()
        await page.mouse.move(hb['x'] + hb['width'] / 2, hb['y'] + hb['height'] / 2); await page.mouse.down()
        await page.mouse.move(hb['x'] + 12, hb['y'] + 6, steps=4); await page.mouse.up()
        assert await page.locator('.surface-overlay line.grid').count() == 10
        await page.screenshot(path=str(OUT / 'editor_surface_draw.png'))
        await page.locator('.surface-bar button.primary').click()
        await page.wait_for_function('document.querySelector(".statusbar").innerText.includes("Tracking unavailable")', timeout=15000)
        s = saved['p']['surfaces'][-1]
        assert len(s['corners']) == 4 and s['status'] == 'drawn', s
        assert all(w['placement'] == 'surface' for w in saved['p']['words'] if w['text'] == 'the neon rain')
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(OUT / 'editor_surface_placed.png'))
        await page.get_by_role('button', name='Preview 9:16').click()
        await page.wait_for_selector('.stage-border.compare canvas'); await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT / 'editor_compare.png'))
        await page.get_by_role('button', name='Output').click()  # Make vertical lives in the Output panel
        await page.get_by_role('button', name='▯ Make vertical').click()
        await page.wait_for_function('document.querySelector(".statusbar").innerText.includes("reframe")', timeout=15000)
        # Determinism: surface (tracked fixture) and client reframe must not depend on render order.
        for q in ['src=/fixtures/walk-surface-paint.project.json', 'reframe=9:16', 'src=/fixtures/walk-surface-neon.project.json&reframe=9:16']:
            pg = await b.new_page()
            await pg.goto(f'{BASE}/#/render?project={PID}&layer=composite&server=http://127.0.0.1:8787&{q}')
            await pg.wait_for_function('window.__typeset !== undefined')
            grab = '''async f=>{await window.__typeset.ready;await window.__typeset.renderFrame(f);return document.querySelector('#stage').toDataURL('image/png');}'''
            a1 = await pg.evaluate(grab, 100); await pg.evaluate(grab, 20); a2 = await pg.evaluate(grab, 100)
            assert a1 == a2, f'non-deterministic render for {q}'
            await pg.close()
        assert not errors, errors
        print('PASS v2 determinism (surface paint/neon, reframe 9:16)')
        print('PASS v2 editor: surface draw/apply/untracked fallback, auto-place toggle, 9:16 preview, reframe fallback')
        await b.close()
asyncio.run(main())
