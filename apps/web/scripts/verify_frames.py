"""Render composite frames of a project through #/render and save PNGs.
Usage: server/.venv/bin/python apps/web/scripts/verify_frames.py <project-id> <prefix> <frame> [<frame>...] [--src=/fixtures/x.project.json] [--layer=composite]
Writes apps/web/.verify/<prefix>_f<frame>.png. Extra hash params (e.g. --param=key=value) are appended to the route.
"""
import asyncio, base64, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
OUT = Path(__file__).resolve().parents[1] / '.verify'

async def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opts = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--'))
    project, prefix, frames = args[0], args[1], [int(f) for f in args[2:]]
    layer = opts.pop('layer', 'composite')
    server = opts.pop('server', os.environ.get('TYPESET_API', ''))  # '' = same origin via the Vite proxy
    extra = ''.join(f'&{k}={v}' for k, v in opts.items())
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        await page.goto(f'{BASE}/#/render?project={project}&layer={layer}&server={server}{extra}')
        await page.wait_for_function('window.__typeset !== undefined')
        for f in frames:
            data = await page.evaluate('''async f => {await window.__typeset.ready;await window.__typeset.renderFrame(f);return document.querySelector('#stage').toDataURL('image/png').split(',')[1];}''', f)
            path = OUT / f'{prefix}_f{f:03d}.png'
            path.write_bytes(base64.b64decode(data))
            print(path)
        if errors: print('ERRORS', errors)
        await browser.close()

asyncio.run(main())
