"""Built-site and model-selection QA. Isolated static server, intercepted APIs, no Comfy jobs."""
import copy
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'apps/web/dist'
OUT = ROOT / 'outputs/progress/compute-setup'
OUT.mkdir(parents=True, exist_ok=True)


class Static(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Simulate a GitHub Pages project site, including /studio/index.html.
        return str(DIST / urlsplit(path).path.removeprefix('/reprise/'))

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), Static)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}/reprise'
project = dict(version=1, id='compute-qa', name='Compute QA', width=640, height=360, fps=24, duration=5,
               media={}, analysis={}, shots=[], surfaces=[], grade=None, words=[], assets=[], layers=[],
               style=dict(fontFamily='Inter', fontWeight=700, fontSize=.1, fill='#ffffff', align='center'),
               board=dict(cards=[], scenes=[dict(id='scene', name='New scene', x=0, y=0, clips=[], takes=[], refs=[],
                  generation=dict(workflowId='qa', workflows={}))]))
key = 'model.1.unet_name'


def workflow(remote=False):
    return dict(id='qa', name='Bring your own model', nodes=3, source='file', missing=[],
        missingModels=['author.safetensors'], target='remote' if remote else 'local',
        targets=[dict(id='local', label='My ComfyUI'), dict(id='remote', label='Comfy Cloud')],
        output=dict(node='3', type='image'), candidates=dict(inputs=[], outputs=[]),
        inputs={key: dict(node='1', field='unet_name', title='Image model', role='model', kind='string',
                         default='author.safetensors', choices=['cloud.safetensors' if remote else 'mine.safetensors']),
                'prompt': dict(node='2', field='text', title='Prompt', role='prompt', kind='string', default='A portrait')})


checks, errors, runs, requests = [], [], [], []
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1500, height=980))
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '/studio/')
        expect(page.get_by_role('textbox', name='Project name', exact=True)).to_be_visible()
        page.get_by_role('button', name='Demo · setup', exact=True).click()
        expect(page.get_by_role('dialog', name='Generation setup')).to_be_visible()
        page.get_by_role('button', name='My ComfyUI', exact=True).click()
        page.get_by_role('textbox', name='Your ComfyUI address').fill('http://localhost:9000')
        expect(page.get_by_role('link', name='Open Reprise in my ComfyUI')).to_have_attribute('href', 'http://localhost:9000/typeset/')
        page.get_by_role('textbox', name='Your ComfyUI address').fill('javascript:alert(1)')
        expect(page.get_by_text('Enter an http:// or https:// ComfyUI address.')).to_be_visible()
        page.get_by_role('button', name='Models', exact=True).click()
        for file in ['starter_zimage.api.json', 'starter_s2v.api.json', 'minimax_remote_i2v.api.json']:
            response = page.request.get(base + '/workflows/' + file)
            assert response.ok and all('class_type' in n for n in response.json().values()), file
        for theme in ['light', 'dark']:
            page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
            page.screenshot(path=str(OUT / f'setup-models-{theme}.png'), animations='disabled')
            page.get_by_role('button', name='My ComfyUI', exact=True).click()
            page.get_by_role('textbox', name='Your ComfyUI address').fill('http://127.0.0.1:8188')
            page.screenshot(path=str(OUT / f'setup-local-{theme}.png'), animations='disabled')
            page.get_by_role('button', name='Models', exact=True).click()
        page.set_viewport_size(dict(width=390, height=844))
        page.screenshot(path=str(OUT / 'setup-mobile.png'), animations='disabled')
        page.set_viewport_size(dict(width=1500, height=980))
        page.evaluate("document.documentElement.dataset.theme = 'light'")
        page.keyboard.press('Escape')
        name = page.get_by_role('textbox', name='Project name', exact=True)
        name.fill('My browser demo')
        page.locator('.s-save').click()
        page.reload()
        expect(page.get_by_role('textbox', name='Project name', exact=True)).to_have_value('My browser demo')
        page.get_by_role('combobox', name='Switch project', exact=True).select_option('+new')
        expect(page.get_by_role('dialog', name='Generation setup')).to_be_visible()
        page.keyboard.press('Escape')
        checks.append('Static subpath demo loads, edits persist, setup opens, new project gives setup, preset downloads exist')

        def api(route):
            global project
            req = route.request
            path = urlsplit(req.url).path.split('/api/', 1)[1]
            requests.append(req.url)
            if path == 'workflows':
                remote = parse_qs(urlsplit(req.url).query).get('remote') == ['true']
                route.fulfill(json=[workflow(remote)])
            elif path == 'projects':
                route.fulfill(json=[project])
            elif path == 'projects/compute-qa':
                if req.method == 'PUT': project = copy.deepcopy(req.post_data_json)
                route.fulfill(json=project)
            elif path.endswith('/run'):
                runs.append(req.post_data_json)
                route.fulfill(json=dict(id='fake', kind='workflow', status='succeeded', result={}))
            elif path == 'session':
                route.fulfill(json=dict(projectId=project['id']))
            elif path == 'health':
                route.fulfill(json=dict(status='ok', comfyui=True))
            else:
                route.fulfill(json=[])

        page.route('**/api/**', api)
        page.goto(base + '/studio/#/studio?project=compute-qa')
        picker = page.get_by_role('combobox', name='Model: Image model · unet_name', exact=True)
        expect(picker).to_be_visible()
        generate = page.get_by_role('button', name='Generate take', exact=True)
        expect(generate).to_be_disabled()
        picker.select_option('mine.safetensors')
        expect(generate).to_be_enabled()
        generate.click()
        page.wait_for_function('() => !document.querySelector(".s-save.dirty")')
        assert runs[-1]['remote'] is False and runs[-1]['inputs'][key] == 'mine.safetensors'
        assert project['board']['scenes'][0]['generation']['workflows']['qa']['inputs'][key] == 'mine.safetensors'
        checks.append('Installed local model replaces missing default and is saved in the scene/run')

        page.get_by_role('combobox', name='Run on', exact=True).select_option('remote')
        expect(picker.locator('option[value="cloud.safetensors"]')).to_have_count(1)
        expect(picker.locator('option[value="mine.safetensors"]')).to_contain_text('unavailable')
        expect(generate).to_be_disabled()
        picker.select_option('cloud.safetensors')
        expect(generate).to_be_enabled()
        generate.click()
        expect(generate).to_be_enabled()
        assert runs[-1]['remote'] is True and runs[-1]['inputs'][key] == 'cloud.safetensors'
        page.locator('.wf-models summary').click()
        page.get_by_role('button', name='Refresh models', exact=True).click()
        expect(page.get_by_role('button', name='Refresh models', exact=True)).to_be_enabled()
        assert any('refresh=true&remote=true' in r for r in requests)
        for theme in ['light', 'dark']:
            page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
            page.screenshot(path=str(OUT / f'models-{theme}.png'), animations='disabled')
        checks.append('Switching hosts refreshes available files, blocks stale choices, pins the selected host, supports rescan')
        page.goto(base + '/')
        page.get_by_role('button', name='Use my ComfyUI', exact=True).click()
        expect(page.get_by_role('dialog', name='Generation setup')).to_be_visible()
        page.screenshot(path=str(OUT / 'setup-showcase.png'), animations='disabled')
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
print(json.dumps(dict(checks=checks, browserErrors=errors, realGenerations=0), indent=2))
