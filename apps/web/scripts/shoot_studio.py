"""Studio screenshots without writing to projects (every PUT/POST/DELETE to /api is intercepted).
Run from repo root: server/.venv/bin/python apps/web/scripts/shoot_studio.py <name> [project-id] [--w=1440 --h=900] [--do=looks|timeline|pipeline|surface|output|overview]
Output: apps/web/.verify/studio/<name>.png
"""
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
OUT = Path(__file__).resolve().parents[1] / '.verify' / 'studio'
args = [a for a in sys.argv[1:] if not a.startswith('--')]
opts = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
NAME = args[0] if args else 'shot'
PID = args[1] if len(args) > 1 else 'beeba9e1-9178-4f24-b9ce-9fb119bb33f6'
W, H = int(opts.get('w', 1440)), int(opts.get('h', 900))
DO = opts.get('do', 'overview')

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: m.type == 'error' and errors.append('console: ' + m.text))
        writes = []
        async def guard(route):
            r = route.request
            if r.method in ('PUT', 'POST', 'DELETE'):
                writes.append(f'{r.method} {r.url}')
                body = json.loads(r.post_data) if r.method == 'PUT' and r.post_data else {}
                if r.method == 'PUT': await route.fulfill(json=body)
                else: await route.fulfill(status=404, json={'detail': 'Not Found'})
            else: await route.continue_()
        await page.route('**/api/**', guard)
        await page.goto(f'{BASE}/#/studio?project={PID}')
        await page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
        frame = int(opts.get('frame', 40))
        for _ in range(frame - 19): await page.keyboard.press('ArrowRight')
        await page.wait_for_timeout(2500)
        if 'look' in opts:
            await page.keyboard.press(f"Digit{opts['look']}"); await page.wait_for_timeout(2500)
        if DO == 'looks':
            await page.keyboard.press('KeyG'); await page.wait_for_timeout(4500)
        elif DO == 'pipeline':
            await page.locator('.step-actions .link').nth(int(opts.get('wf', 0))).click(); await page.wait_for_timeout(1200)
        elif DO == 'surface':
            await page.locator('.word-chip', has_text='the neon rain').click()
            await page.get_by_role('button', name='▱ Place on surface').click()
            box = await page.locator('.surface-overlay').bounding_box()
            for x, y in [(.36, .05), (.66, .17), (.66, .62), (.36, .70)]:
                await page.mouse.click(box['x'] + x * box['width'], box['y'] + y * box['height'])
            await page.wait_for_timeout(500)
        elif DO == 'output':
            await page.get_by_role('button', name='Output').click(); await page.wait_for_timeout(600)
        elif DO == 'timeline':
            lane = int(opts.get('lane', 2))
            await page.locator('.tl-lane').nth(lane).locator('.word-chip').first.click()
            await page.keyboard.press('KeyL')
            for _ in range(int(opts.get('zoom', 0))): await page.get_by_role('button', name='Zoom in').click()
            await page.wait_for_timeout(1200)
        elif DO == 'occupancy':
            await page.keyboard.press('KeyO'); await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT / f'{NAME}.png'))
        print('saved', OUT / f'{NAME}.png'); print('intercepted writes:', writes)
        if errors: print('ERRORS:', errors)
        await b.close()
asyncio.run(main())
