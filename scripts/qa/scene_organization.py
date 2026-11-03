"""Scene merge/move/layout regression using an isolated API fixture, never saved user projects."""
import base64
import copy
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('TYPESET_UI_URL', 'http://127.0.0.1:5174')
OUT = Path('outputs/progress/scene-organization')
PID = 'scene-organization-qa'


def asset(aid, name, color, scene):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="{color}"/></svg>'
    return dict(id=aid, kind='image', name=name, width=640, height=360,
                path='data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode(),
                source=dict(kind='workflow', workflowId='sing', sceneId=scene))


def scene(sid, name, take, clip, prompt, x):
    return dict(id=sid, name=name, x=x, y=0, takes=[take] if take else [], clips=[clip] if clip else [], refs=['ref'],
                generation=dict(workflowId='sing', workflows=dict(sing=dict(inputs=dict(prompt=prompt), sources=dict(image='ref'),
                    mediaFiles=dict(audio=dict(path=f'{sid}-vocal.wav', name='Prepared phrase', duration=4)),
                    postprocess=dict(timeScale=1.2, trimStart=.3, fps=24)))))


saved = dict(version=1, id=PID, name='Imported singing variations', width=640, height=360, fps=24, duration=6,
    media={}, analysis={}, shots=[], surfaces=[], words=[], grade=None, look=dict(id='default'),
    style=dict(fontFamily='Inter', fontWeight=700, fontSize=.1, fill='#ffffff', align='center'),
    assets=[asset('a', 'Singing A', '#bb4455', 'a-scene'), asset('b', 'Singing B', '#4455bb', 'b-scene'), asset('ref', 'Face', '#667766', 'ref')],
    layers=[dict(id='clip-a', name='First phrase', kind='media', assetId='a', start=0, **{'in': .5}, out=3.5),
            dict(id='clip-b', name='Second phrase', kind='media', assetId='b', start=3, **{'in': 1}, out=4, transform=dict(scale=1.1))],
    board=dict(cards=[], scenes=[scene('a-scene', 'Phrase A', 'a', 'clip-a', 'Quiet laugh', 0),
                                scene('b-scene', 'Phrase B', 'b', 'clip-b', 'Held myself', 450),
                                scene('arrival', 'Arrival', None, None, 'Walk along the platform', 900)]))
original = copy.deepcopy(saved)
workflow = dict(id='sing', name='Singing performance', source='file', nodes=4, missing=[], output=dict(node='4', type='image'),
    candidates=dict(inputs=[], outputs=[]), inputs=dict(
        image=dict(node='1', field='image', role='media', kind='comfy_input_path', media='image', title='Identity'),
        prompt=dict(node='2', field='text', role='prompt', kind='string', title='Direction', default=''),
        seed=dict(node='3', field='seed', role='seed', kind='int', title='Sampler', default=12)))
jobs, runs, errors, checks = [], [], [], []
release_job = False


def check(label, condition=True):
    assert condition, label
    checks.append(label)
    print(f'PASS {label}', flush=True)


def current(sid):
    return next(s for s in saved['board']['scenes'] if s['id'] == sid)


with sync_playwright() as pw:
    OUT.mkdir(parents=True, exist_ok=True)
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport=dict(width=1440, height=1000))
    page.on('pageerror', lambda e: errors.append(str(e)))

    def api(route):
        global saved
        req = route.request
        path = req.url.split('/api/', 1)[-1].split('?', 1)[0]
        if path == f'projects/{PID}':
            if req.method == 'PUT':
                saved = req.post_data_json
            route.fulfill(json=saved)
        elif path == 'projects':
            route.fulfill(json=[saved])
        elif path == 'workflows':
            route.fulfill(json=[workflow])
        elif path == 'health':
            route.fulfill(json=dict(comfyui=True, remote=None))
        elif path == 'session':
            route.fulfill(json=dict(projectId=PID))
        elif path == 'looks/saved':
            route.fulfill(json=[])
        elif path == 'jobs':
            route.fulfill(json=jobs)
        elif path == f'projects/{PID}/workflows/sing/run':
            runs.append(req.post_data_json)
            jobs[:] = [dict(id='late-job', kind='workflow', status='running', projectId=PID, progress=.2)]
            route.fulfill(json=jobs[0])
        elif path == 'jobs/late-job':
            if release_job:
                late = asset('late', 'Late singing take', '#9955bb', runs[-1]['sceneId'])
                jobs[0].update(status='done', progress=1, result=dict(assets=[late]))
                if not any(a['id'] == 'late' for a in saved['assets']):
                    saved['assets'].append(late)
            route.fulfill(json=jobs[0])
        else:
            route.fulfill(status=404, json=dict(detail='Isolated organization fixture'))

    page.route('**/api/**', api)

    def save():
        with page.expect_response(lambda r: r.request.method == 'PUT' and f'projects/{PID}' in r.url):
            page.locator('.s-save').click()

    def choose(name):
        page.get_by_role('button', name=f'Select scene {name}', exact=True).click()

    def take(name):
        return page.locator(f'.study-take[title^="{name}"]')

    def history(redo=False):
        page.locator('.study-nav').click(position=dict(x=2, y=2))
        page.keyboard.press('Meta+Shift+z' if redo else 'Meta+z')
        save()

    page.goto(f'{BASE}/#/studio?project={PID}')
    page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
    # Newly created empty scenes delete even while the + button retains focus.
    page.get_by_role('button', name='New scene', exact=True).click()
    save()
    empty_id = next(s['id'] for s in saved['board']['scenes'] if s['id'] not in {'a-scene', 'b-scene', 'arrival'})
    page.get_by_role('button', name='New scene', exact=True).focus()
    page.keyboard.press('Backspace')
    save()
    check('Backspace immediately deletes a new empty scene', all(s['id'] != empty_id for s in saved['board']['scenes']))
    history()
    check('Empty-scene deletion is undoable', any(s['id'] == empty_id for s in saved['board']['scenes']))
    choose(next(s['name'] for s in saved['board']['scenes'] if s['id'] == empty_id))
    page.keyboard.press('Delete')
    save()
    check('Delete removes a selected empty scene from the list', len(saved['board']['scenes']) == 3)
    check('No organizer dialog or tidy controls', page.get_by_role('button', name='Organize scenes', exact=True).count() == 0 and page.get_by_role('button', name='Tidy board', exact=True).count() == 0)

    choose('Phrase B')
    page.get_by_role('button', name='Generate take', exact=True).click()
    expect(page.get_by_role('button', name='Generating 20%', exact=True)).to_be_visible()
    page.get_by_role('button', name='Board', exact=True).click()
    canvas = page.get_by_role('region', name='Scene board canvas')
    page.get_by_role('button', name='Fit board', exact=True).click()
    def card(sid):
        return page.locator(f'.study-board-card[data-scene-id="{sid}"]')
    def title(sid):
        return card(sid).locator('.scene-title')
    def view():
        return tuple(float(canvas.get_attribute(f'data-{key}')) for key in ('x', 'y', 'zoom'))
    def drag_mouse(x, y, dx, dy, button='left'):
        page.mouse.move(x, y)
        page.mouse.down(button=button)
        page.mouse.move(x + dx, y + dy, steps=8)
        page.mouse.up(button=button)

    # Navigation moves the viewport, never project geometry or the film.
    before_view = view()
    r = canvas.bounding_box()
    drag_mouse(r['x'] + 60, r['y'] + r['height'] - 140, 36, -28)
    check('Mouse drag on blank canvas pans the board', abs(view()[0] - before_view[0] - 36) < .01 and abs(view()[1] - before_view[1] + 28) < .01)
    save()
    check('Panning leaves scene coordinates and timeline unchanged', saved['board']['scenes'] == original['board']['scenes'] and saved['layers'] == original['layers'])
    start = view()
    page.mouse.move(r['x'] + 60, r['y'] + r['height'] - 140)
    page.mouse.down()
    page.mouse.move(r['x'] + 110, r['y'] + r['height'] - 170, steps=5)
    page.keyboard.press('Escape')
    page.mouse.up()
    check('Escape cancels an in-progress pan', view() == start)
    page.get_by_role('button', name='Fit board', exact=True).click()
    for modifier, button in [('Space', 'left'), (None, 'middle')]:
        src = title('b-scene').bounding_box()
        start = view()
        canvas.focus()
        if modifier:
            page.keyboard.down(modifier)
        drag_mouse(src['x'] + src['width']/2, src['y'] + src['height']/2, 18, 16, button)
        if modifier:
            page.keyboard.up(modifier)
        check(f'{modifier or "Middle-button"} drag over a frame pans instead of moving it', abs(view()[0] - start[0] - 18) < .01 and abs(view()[1] - start[1] - 16) < .01)
        page.get_by_role('button', name='Fit board', exact=True).click()

    compact_view = view()
    page.get_by_role('button', name='Fullscreen board', exact=True).click()
    dialog = page.get_by_role('dialog', name='Fullscreen scene board', exact=True)
    expect(dialog).to_be_visible()
    expect(canvas).to_be_focused()
    page.wait_for_function("Number(document.querySelector('.study-canvas').dataset.zoom) > .8")
    r = dialog.bounding_box()
    check('Fullscreen board fills the window and fits all frames', r['width'] == 1440 and r['height'] == 1000 and canvas.bounding_box()['width'] > 1000)
    page.get_by_role('button', name='Focus selected scene', exact=True).focus()
    page.keyboard.press('Tab')
    expect(dialog.get_by_role('button', name='New scene', exact=True)).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(page.get_by_role('button', name='Focus selected scene', exact=True)).to_be_focused()
    page.locator('.s-save').evaluate('el => el.focus()')
    check('Fullscreen traps keyboard focus and keeps the editor inert', page.evaluate("!!document.activeElement.closest('.board-fullscreen')"))
    take('Singing B').click()
    preview = page.get_by_role('complementary', name='Board take preview')
    expect(preview).to_be_visible()
    expect(preview.get_by_role('img', name='Singing B', exact=True)).to_be_visible()
    check('Fullscreen previews stay on the board without playing a hidden editor preview', page.locator('.source-viewer').count() == 0)
    page.screenshot(path=str(OUT / 'fullscreen-board.png'))
    page.keyboard.press('Escape')
    expect(preview).to_have_count(0)
    expect(dialog).to_be_visible()
    check('Escape closes the take preview before exiting the board')
    page.get_by_role('button', name='New scene', exact=True).click()
    expect(page.locator('.study-board-card')).to_have_count(4)
    page.keyboard.press('Backspace')
    expect(page.locator('.study-board-card')).to_have_count(3)
    canvas.focus()
    page.keyboard.press('Meta+z')
    expect(page.locator('.study-board-card')).to_have_count(4)
    page.keyboard.press('Meta+Shift+z')
    expect(page.locator('.study-board-card')).to_have_count(3)
    check('Fullscreen supports immediate empty-scene delete, undo and redo')
    page.get_by_role('button', name='Fit board', exact=True).click()
    page.set_viewport_size(dict(width=1024, height=768))
    expect(page.get_by_role('button', name='Exit fullscreen board', exact=True)).to_be_visible()
    check('Fullscreen follows a window resize', dialog.bounding_box()['width'] == 1024 and dialog.bounding_box()['height'] == 768)
    page.set_viewport_size(dict(width=1440, height=1000))
    page.get_by_role('button', name='Exit fullscreen board', exact=True).focus()
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role('button', name='Fullscreen board', exact=True)).to_be_focused()
    check('Escape exits fullscreen, restores focus and the compact viewport', view() == compact_view)
    page.get_by_role('button', name='Fullscreen board', exact=True).click()
    page.get_by_role('button', name='Fit board', exact=True).click()
    take('Singing B').click()
    page.get_by_role('button', name='Open in editor', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role('region', name='Full take preview')).to_be_visible()
    page.keyboard.press('Escape')
    check('A board take can be opened in the editor')
    page.get_by_role('button', name='Fullscreen board', exact=True).click()
    page.get_by_role('button', name='Exit fullscreen board', exact=True).click()
    expect(dialog).not_to_be_visible()
    check('The fullscreen exit button also restores the editor')
    page.get_by_role('button', name='Fit board', exact=True).click()
    src, dst = title('b-scene').bounding_box(), card('a-scene').bounding_box()
    page.mouse.move(src['x'] + src['width'] / 2, src['y'] + src['height'] / 2)
    page.mouse.down()
    page.mouse.move(dst['x'] + dst['width'] / 2, dst['y'] + dst['height'] / 2, steps=12)
    expect(card('a-scene').get_by_text('Release to combine', exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / 'drag-combine.png'))
    page.mouse.up()
    save()
    check('Dragging a scene into another combines without changing film or assets', len(saved['board']['scenes']) == 2 and saved['layers'] == original['layers'] and saved['assets'] == original['assets'])
    check('References, recipes and retired IDs survive', current('a-scene')['refs'] == ['ref'] and len(current('a-scene')['recipes']) == 2 and current('a-scene')['mergedIds'] == ['b-scene'])
    history()
    check('Drag combine is one undo step', len(saved['board']['scenes']) == 3)
    history(True)
    check('Drag combine redo restores grouping', len(saved['board']['scenes']) == 2)
    page.get_by_role('button', name='Fit board', exact=True).click()
    title('a-scene').dblclick()
    field = page.get_by_label('Scene name on board: Phrase A', exact=True)
    field.fill('Maybe I laugh at myself')
    field.press('Enter')
    save()
    check('Double-click renames a frame inline', current('a-scene')['name'] == 'Maybe I laugh at myself')

    release_job = True
    expect(take('Late singing take')).to_be_visible(timeout=15000)
    save()
    check('In-flight result joins the combined scene', len(saved['board']['scenes']) == 2 and any(a['id'] == 'late' and a['source']['sceneId'] == 'b-scene' for a in saved['assets']))
    recipe = page.get_by_label('Scene recipe', exact=True)
    recipe.select_option('b-scene')
    expect(page.get_by_label('Direction', exact=True)).to_have_value('Held myself')
    page.get_by_label('Direction', exact=True).fill('A quieter held word')
    recipe.select_option('a-scene')
    expect(page.get_by_label('Direction', exact=True)).to_have_value('Quiet laugh')
    recipe.select_option('b-scene')
    expect(page.get_by_label('Direction', exact=True)).to_have_value('A quieter held word')
    save()
    check('Recipe switching preserves phrase audio', current('a-scene')['generation']['workflows']['sing']['mediaFiles']['audio']['path'] == 'b-scene-vocal.wav')

    page.get_by_role('button', name='Fit board', exact=True).click()
    take('Singing B').drag_to(card('arrival'))
    save()
    check('Take drag relocates membership only', saved['layers'] == original['layers'] and current('arrival')['clips'] == ['clip-b'] and 'b' not in current('a-scene')['takes'])
    history()
    check('Take drag is one undo step', 'b' in current('a-scene')['takes'] and 'b' not in current('arrival')['takes'])
    history(True)
    take('Singing B').click()
    page.keyboard.press('Backspace')
    save()
    check('Backspace on a take removes its board item, not the scene or media', len(saved['board']['scenes']) == 2 and 'b' not in current('arrival')['takes'] and any(a['id'] == 'b' for a in saved['assets']) and saved['layers'] == original['layers'])
    history()
    check('Removed take is restored by undo', 'b' in current('arrival')['takes'])
    page.reload()
    page.wait_for_selector('.stage-loading', state='hidden', timeout=60000)
    page.get_by_role('button', name='Board', exact=True).click()
    page.get_by_role('button', name='Fit board', exact=True).click()
    check('Take stays moved after reload', card('arrival').locator('[data-take-id="b"]').count() == 1 and card('a-scene').locator('[data-take-id="b"]').count() == 0)

    r = canvas.bounding_box()
    take('Late singing take').drag_to(canvas, target_position=dict(x=r['width'] - 65, y=r['height'] - 95))
    save()
    fresh = next(s for s in saved['board']['scenes'] if s['id'] not in {'a-scene', 'arrival'})
    check('A take dropped on blank canvas creates a scene', fresh['takes'] == ['late'] and fresh['refs'] == ['ref'])
    page.get_by_role('button', name='Fit board', exact=True).click()
    page.get_by_role('button', name='Collapse scene Arrival', exact=True).click()
    save()
    check('A frame collapses in place', current('arrival')['collapsed'])
    page.screenshot(path=str(OUT / 'direct-board.png'))
    page.get_by_role('button', name='Expand scene Arrival', exact=True).click()

    title('a-scene').click()
    title('arrival').click(modifiers=['Shift'])
    expect(page.locator('.scene-selection-actions')).to_contain_text('2 scenes')
    save()
    before = {s['id']: (s['x'], s['y']) for s in saved['board']['scenes']}
    src = title('arrival').bounding_box()
    page.mouse.move(src['x'] + src['width']/2, src['y'] + src['height']/2)
    page.mouse.down()
    page.mouse.move(src['x'] + src['width']/2 + 5, src['y'] + src['height']/2 + 38, steps=5)
    page.mouse.up()
    save()
    deltas = [(current(sid)['x'] - before[sid][0], current(sid)['y'] - before[sid][1]) for sid in ['a-scene', 'arrival']]
    assert all(abs(a-b) < 1e-6 for a,b in zip(*deltas)) and any(abs(v) > .01 for v in deltas[0]), deltas
    check('Selected frames move together')
    canvas.focus()
    page.keyboard.press('Meta+g')
    save()
    check('Command-G combines selected frames', len(saved['board']['scenes']) == 2)
    history()
    check('Keyboard combine is undoable', len(saved['board']['scenes']) == 3)

    page.get_by_role('button', name='Scenes', exact=True).click()
    source = page.get_by_role('button', name='Select scene Arrival', exact=True)
    target = page.get_by_role('button', name='Select scene Maybe I laugh at myself', exact=True)
    source.drag_to(target, target_position=dict(x=25, y=2))
    save()
    check('Dragging to a list edge reorders scenes', saved['board']['scenes'][0]['id'] == 'arrival' and saved['layers'] == original['layers'])

    page.get_by_role('button', name='Board', exact=True).click()
    page.get_by_role('button', name='Fit board', exact=True).click()
    boxes = [card(s['id']).bounding_box() for s in saved['board']['scenes']]
    zoom = float(canvas.get_attribute('data-zoom'))
    left, top = min(b['x'] for b in boxes) - 6, min(b['y'] for b in boxes) - 32 * zoom - 6
    right, bottom = max(b['x'] + b['width'] for b in boxes) + 6, max(b['y'] + b['height'] for b in boxes) + 6
    page.mouse.move(left, top)
    page.keyboard.down('Shift')
    page.mouse.down()
    page.mouse.move(right, bottom, steps=12)
    page.mouse.up()
    page.keyboard.up('Shift')
    expect(page.locator('.scene-selection-actions')).to_contain_text('3 scenes')
    page.keyboard.press('Backspace')
    save()
    check('Marquee + Backspace deletes selected frames, preserving film and assets', saved['board']['scenes'] == [] and saved['layers'] == original['layers'] and len(saved['assets']) == 4)
    canvas.focus()
    page.keyboard.press('Meta+z')
    save()
    check('Multi-scene deletion restores in one undo', len(saved['board']['scenes']) == 3)
    page.get_by_role('button', name='New scene', exact=True).click()
    save()
    empty_id = next(s['id'] for s in saved['board']['scenes'] if s['id'] not in {'a-scene', 'arrival', fresh['id']})
    page.get_by_role('button', name='Focus selected scene', exact=True).click()
    card(empty_id).click(position=dict(x=8, y=8))
    page.keyboard.press('Backspace')
    save()
    check('Clicking an empty board frame then Backspace deletes it immediately', all(s['id'] != empty_id for s in saved['board']['scenes']))
    check('No browser exceptions', not errors)
    print(json.dumps(dict(checks=len(checks), passed=checks, errors=errors), indent=2))
    browser.close()
