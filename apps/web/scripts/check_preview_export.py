"""Preview (studio canvas) vs export route (#/render) pixel diff for a look, at 3 frames. No data is written:
the studio's GET of the project is intercepted to add the look.
Usage: server/.venv/bin/python apps/web/scripts/check_preview_export.py <project-id> <look>"""
import asyncio, base64, io, json, os, sys, urllib.request
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright
BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174'); PID, LOOK = sys.argv[1], sys.argv[2]
FRAMES = [19, 20, 31]
def img(data): return np.asarray(Image.open(io.BytesIO(base64.b64decode(data.split(',')[1]))).convert('RGBA')).astype(int)
async def main():
    proj = json.load(urllib.request.urlopen(f'http://127.0.0.1:8787/api/projects/{PID}')); proj['look'] = {'id': LOOK}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ex = await b.new_page(); await ex.goto(f'{BASE}/#/render?project={PID}&layer=composite&server=http://127.0.0.1:8787&look={LOOK}')
        await ex.wait_for_function('window.__typeset !== undefined')
        exp = {f: img(await ex.evaluate('async f=>{await window.__typeset.ready;await window.__typeset.renderFrame(f);return document.querySelector("#stage").toDataURL("image/png")}', f)) for f in FRAMES}
        pv = await b.new_page(viewport={'width': 1500, 'height': 1000})
        await pv.route(f'**/api/projects/{PID}', lambda r: r.fulfill(json=proj) if r.request.method == 'GET' else r.continue_())
        await pv.goto(f'{BASE}/#/studio?project={PID}')
        await pv.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
        cur = 19; worst = 0
        for f in FRAMES:
            for _ in range(f - cur): await pv.keyboard.press('ArrowRight')
            cur = f; await pv.wait_for_timeout(2500)
            a = img(await pv.evaluate('document.querySelector("canvas#stage").toDataURL("image/png")'))
            d = (np.abs(a - exp[f]).max(axis=2) > 8).mean(); worst = max(worst, d)
            print(f'frame {f}: {d*100:.3f}% pixels differ (>8/255)')
        print('PASS' if worst < .02 else 'FAIL', f'preview vs export, {LOOK}, worst {worst*100:.3f}%')
        await b.close()
asyncio.run(main())
