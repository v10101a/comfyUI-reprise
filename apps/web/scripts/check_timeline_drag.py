"""Exercise Studio clip bodies, trim edges and undo with real pointer gestures.

Uses an in-memory project and intercepts every API write; no stored projects change.
"""
import argparse
import io
import json
import re
import wave
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://127.0.0.1:5174')
    ap.add_argument('--out', type=Path, default=Path('outputs/qa/timeline-drag'))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    project = json.loads(Path('apps/web/public/sample/project.json').read_text())
    project.update(id='timeline-drag-check', name='Timeline gesture check', duration=10, fps=24,
                   width=480, height=270, media={}, analysis={}, shots=[], surfaces=[],
                   look=None, grade=None, lineMeta={},
                   words=[{'id': wid, 'lineId': line, 'text': text, 'start': a, 'end': b,
                           'placement': 'overlay', 'preset': 'none'}
                          for wid, line, text, a, b in [('a', 'phrase', 'MOVE', 1, 2.5),
                                                       ('b', 'phrase', 'ME', 3, 4),
                                                       ('c', 'other', 'OTHER', 6, 7),
                                                       ('d', 'tiny', 'COMPACT CLIP', 8, 8.3)]])
    saved, errors, checks = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(10000)
        page.on('pageerror', lambda e: errors.append(str(e)))

        def api(route):
            req = route.request
            path = urlsplit(req.url).path
            if path == '/api/projects/' + project['id']:
                if req.method == 'PUT':
                    saved.append(req.post_data_json)
                route.fulfill(json=saved[-1] if saved else project)
            elif path == '/api/projects':
                route.fulfill(json=[project])
            elif path == '/api/jobs':
                route.fulfill(json=[])
            elif req.method not in ('GET', 'HEAD', 'OPTIONS'):
                route.abort()
            else:
                route.fulfill(status=404, json={})

        page.route('**/api/**', api)
        # A real decoded song, longer than the edit, without touching any user's media.
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b'\x00\x10\x00\xf0' * (30 * 4000))
        page.route('**/files/projects/' + project['id'] + '/media/song.wav',
                   lambda route: route.fulfill(body=audio.getvalue(), content_type='audio/wav'))
        page.goto(args.base + '/#/studio?project=' + project['id'])
        page.wait_for_selector('.word-chip')
        expect(page.get_by_role('button', name='Play', exact=True)).to_be_enabled()
        snap = page.get_by_role('button', name='Snap', exact=True)
        if snap.get_attribute('aria-pressed') == 'true':
            snap.click()
        pps = page.locator('.tl-ruler').bounding_box()['width'] / project['duration']

        def word(wid):
            return page.locator(f'.word-chip[data-word-id="{wid}"]')

        def snapshot():
            return page.locator('.word-chip').evaluate_all('''els => Object.fromEntries(els.map(e=>[
                e.dataset.wordId,e.title.split(' · ')[1].replace('s','').split('–').map(Number)]))''')

        def assert_times(wanted):
            try:
                page.wait_for_function('''wanted => Object.entries(wanted).every(([id,times])=>{
                    const e=document.querySelector('.word-chip[data-word-id="'+id+'"]');
                    return e && e.title.split(' · ')[1]===times.map(t=>t.toFixed(2)).join('–')+'s';
                })''', arg=wanted)
            except Exception:
                page.screenshot(path=str(args.out / 'failure.png'))
                print(json.dumps({'wanted': wanted, 'actual': snapshot(), 'passed': checks}), flush=True)
                raise

        baseline = snapshot()

        def undo():
            page.keyboard.press('Meta+z')
            assert_times(baseline)

        def drag(locator, seconds, x_fraction=.5, y_fraction=.5):
            locator.hover()
            box = locator.bounding_box()
            x, y = box['x'] + box['width'] * x_fraction, box['y'] + box['height'] * y_fraction
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + seconds * pps, y, steps=12)
            page.mouse.up()

        # The user's reported bug: grabbing a word must move both boundaries by the same amount.
        word('a').hover()
        assert word('a').evaluate('(e)=>getComputedStyle(e).cursor') == 'grab'
        drag(word('a'), .5)
        assert_times({**baseline, 'a': [1.5, 3]})
        checks.append('word body preserves duration and leaves other words alone')
        undo()

        drag(word('a'), 2.5)
        assert_times({**baseline, 'a': [3.5, 5]})
        checks.append('word can move past another word without losing the drag')
        undo()

        # Gap between words is the phrase body; moving it preserves every internal offset and duration.
        region = page.locator('[data-line-id="phrase"] .tl-region')
        drag(region, .5, x_fraction=1.75/3)
        assert_times({**baseline, 'a': [1.5, 3], 'b': [3.5, 4.5]})
        checks.append('phrase body moves all words rigidly; one undo restores the gesture')
        undo()

        for selector, delta, wanted, label in [
            ('[data-line-id="phrase"] .tl-region-start', -.5, {'a': [.5, 2.5]}, 'phrase start'),
            ('[data-line-id="phrase"] .tl-region-end', .5, {'b': [3, 4.5]}, 'phrase end'),
            ('[data-word-id="b"] .word-edge.tl-trim-start', -.25, {'b': [2.75, 4]}, 'word start'),
            ('[data-word-id="a"] .word-edge.tl-trim-end', .25, {'a': [1, 2.75]}, 'word end'),
        ]:
            edge = page.locator(selector)
            edge.hover()
            cursor = edge.evaluate('(e)=>getComputedStyle(e).cursor')
            assert 'url(' in cursor and 'ew-resize' in cursor, cursor
            drag(edge, delta)
            assert_times({**baseline, **wanted})
            checks.append(label + ' changes only its boundary; bracket cursor')
            undo()

        # Small clips retain a movable center instead of becoming one big trim target.
        tiny = page.locator('[data-line-id="tiny"]')
        expect(tiny).to_have_class(re.compile(r'compact'))
        drag(tiny.locator('.tl-region'), -.5)
        assert_times({**baseline, 'd': [7.5, 7.8]})
        checks.append('compact clip center moves without stretching')
        undo()

        # Use the original grab point even beyond the timeline limits.
        drag(word('a'), -2)
        assert_times({**baseline, 'a': [0, 1.5]})
        checks.append('movement clamps at the timeline start without shortening')
        undo()

        snap.click()
        drag(word('c'), -1.96)
        assert_times({**baseline, 'c': [4, 5]})
        checks.append('body movement snaps while preserving duration')
        undo()

        # Pointer capture must clear on cancellation, including the forced dragging cursor.
        edge = word('a').locator('.word-edge.tl-trim-end')
        edge.hover()
        page.mouse.down()
        expect(page.locator('.tl')).to_have_class(re.compile(r'drag-end'))
        edge.dispatch_event('pointercancel', {'pointerId': 1})
        page.mouse.up()
        expect(page.locator('.tl')).not_to_have_class(re.compile(r'drag-(?:start|end|move)'))
        assert_times(baseline)
        checks.append('pointer cancellation clears trim mode without editing')

        # Selection and inline text editing retain their existing click/double-click behavior.
        word('a').click()
        expect(page.get_by_role('textbox', name='Word text', exact=True)).to_have_value('MOVE')
        word('a').dblclick()
        expect(page.locator('.tl-inline')).to_be_visible()
        page.keyboard.press('Escape')
        assert_times(baseline)
        checks.append('click selects and double-click still opens inline text')

        # Audio used to trim from absolute pointer position and the live viewport scale.
        # Exercise the right edge when the clip fills the timeline, with unused source to reveal.
        project['media'] = {'audio': {'path': 'media/song.wav', 'duration': 30},
                            'audioClip': {'in': 5, 'out': 15, 'offset': 0}}
        page.route('**/files/projects/' + project['id'] + '/analysis/beats.json',
                   lambda route: route.fulfill(json={'beats':[n/2 for n in range(60)],'bpm':120}))
        saved.clear()
        page.reload()
        audio_out = page.get_by_role('slider', name='Song out', exact=True)
        expect(audio_out).to_have_attribute('aria-valuenow', '15')
        if snap.get_attribute('aria-pressed') == 'true':
            snap.click()
        length = page.get_by_label('Timeline length in seconds')

        def audio_value(name='Song out'):
            return float(page.get_by_role('slider', name=name, exact=True).get_attribute('aria-valuenow'))

        def audio_grab(name='Song out'):
            handle = page.get_by_role('slider', name=name, exact=True)
            handle.scroll_into_view_if_needed()
            edge = handle.bounding_box()
            x = edge['x'] + (2 if name == 'Song out' else 8)
            y = edge['y'] + edge['height'] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            return x, y

        def save():
            with page.expect_response(lambda r:r.request.method=='PUT' and '/projects/' + project['id'] in r.url):
                page.locator('.s-save').click()
            return saved[-1]

        # No need to move outside the browser: pull a few pixels toward the edge, then hold.
        x, y = audio_grab()
        page.wait_for_timeout(300)
        expect(audio_out).to_have_attribute('aria-valuenow', '15')
        expect(length).to_have_value('10.00')
        page.mouse.move(x + 5, y)
        assert x + 5 < page.viewport_size['width']
        values = []
        for _ in range(10):
            page.wait_for_timeout(100)
            values.append(audio_value())
        assert all(a <= b for a, b in zip(values, values[1:])), values
        assert values[-1] > 15.5, values
        assert float(length.input_value()) > 10.5
        page.mouse.up()
        tail = save()
        assert tail['duration'] > 10.5 and tail['media']['audioClip']['out'] > 15.5
        assert_times(baseline)
        checks.append('holding the song tail at the window edge scrolls and adds time after the edit')
        page.keyboard.press('Meta+z')
        expect(length).to_have_value('10.00')
        expect(audio_out).to_have_attribute('aria-valuenow', '15')
        checks.append('one undo restores the complete edge-extension gesture')

        # The opposite edge inserts time ahead of every existing word, preserving song sync.
        x, y = audio_grab('Song in')
        page.mouse.move(x - 7, y)
        values = []
        for _ in range(10):
            page.wait_for_timeout(100)
            values.append(audio_value('Song in'))
        assert all(a >= b for a, b in zip(values, values[1:])), values
        assert values[-1] < 4.5, values
        expect(page.locator('.tl-trim-status')).to_contain_text('before')
        page.mouse.up()
        head = save(); shift = head['timing']['sceneOffset']; clip = head['media']['audioClip']
        assert shift > .5 and abs(head['duration'] - 10 - shift) < 1e-6
        assert 0 <= clip['offset'] < 1/24 + .001
        assert_times({wid:[a+shift,b+shift] for wid,(a,b) in baseline.items()})
        # At every old lyric the same song sample is heard after the prepend.
        assert abs((1+shift) - (clip['offset']-clip['in']) - 6) < .002
        checks.append('song head inserts earlier time and shifts the edit without breaking lyric sync')
        page.keyboard.press('Meta+z')
        expect(length).to_have_value('10.00')
        expect(page.get_by_role('slider',name='Song in',exact=True)).to_have_attribute('aria-valuenow','5')
        assert_times(baseline)
        page.keyboard.press('Meta+Shift+z')
        expect(length).to_have_value(f"{head['duration']:.2f}")
        save();page.reload()
        expect(length).to_have_value(f"{head['duration']:.2f}")
        assert_times({wid:[a+shift,b+shift] for wid,(a,b) in baseline.items()})
        checks.append('prepended timeline survives undo, redo, save and reload')

        if snap.get_attribute('aria-pressed') == 'true':
            snap.click()
        scale=page.locator('.tl-ruler').bounding_box()['width']/head['duration']
        x,y=audio_grab('Song in')
        page.mouse.move(x+(5-head['media']['audioClip']['in'])*scale,y,steps=8);page.mouse.up()
        expect(length).to_have_value('10.00')
        assert_times(baseline)
        checks.append('shrinking the song head removes the added lead-in and returns the original edit to zero')

        # Existing projects can have a song head hidden before zero. Grab the visible boundary.
        project['media']['audioClip']['offset'] = -.75
        saved.clear();page.reload()
        expect(length).to_have_value('10.00')
        if snap.get_attribute('aria-pressed') == 'true':
            snap.click()
        scale = page.locator('.tl-ruler').bounding_box()['width'] / 10
        x, y = audio_grab('Song in')
        page.mouse.move(x + 8, y)
        page.wait_for_timeout(350)
        assert abs(audio_value('Song in') - (5.75 + 8/scale)) < .02
        page.mouse.up();expect(length).to_have_value('9.21')
        page.keyboard.press('Meta+z')
        expect(page.get_by_role('slider',name='Song in',exact=True)).to_have_attribute('aria-valuenow','5')
        x, y = audio_grab('Song in');page.mouse.move(x - 7, y)
        page.wait_for_timeout(750);page.mouse.up()
        clipped = save();shift = clipped['timing']['sceneOffset'];clip = clipped['media']['audioClip']
        assert shift > .2
        assert abs(shift + clip['in'] - clip['offset'] - 5.75) < .002
        checks.append('a previously clipped song head extends from the visible edge without a jump')

        # Source limits and zoomed auto-scroll use the same scale and remain reversible.
        project['media']['audioClip']['offset'] = 0
        saved.clear();page.reload()
        if snap.get_attribute('aria-pressed') == 'true':
            snap.click()
        scale = page.locator('.tl-ruler').bounding_box()['width'] / 10
        x,y=audio_grab();page.mouse.move(x+40*scale,y,steps=8);page.mouse.up()
        expect(audio_out).to_have_attribute('aria-valuenow','30')
        expect(length).to_have_value('25.00')
        scale=page.locator('.tl-ruler').bounding_box()['width']/25
        x,y=audio_grab();page.mouse.move(x-15*scale,y,steps=8);page.mouse.up()
        expect(length).to_have_value('10.00')
        scale=page.locator('.tl-ruler').bounding_box()['width']/10
        x,y=audio_grab();page.mouse.move(x-10*scale,y,steps=8);page.mouse.up()
        expect(length).to_have_value('8.33')
        assert_times(baseline)
        checks.append('shrinking an overshot tail refits the timeline while retaining the longest text clip')
        page.keyboard.press('Meta+z');expect(length).to_have_value('10.00')
        page.keyboard.press('=')
        x,y=audio_grab();viewport=page.locator('.tl-scroll').bounding_box()
        page.mouse.move(min(x+6,viewport['x']+viewport['width']-1),y)
        page.wait_for_timeout(1000);page.mouse.up()
        assert audio_value()>15.25
        page.keyboard.press('Meta+z');expect(length).to_have_value('10.00')
        page.get_by_role('button',name='Fit',exact=True).click()
        checks.append('source limits and zoomed edge-scroll extend predictably')

        snap.click()
        x,y=audio_grab();page.mouse.move(x+5,y)
        page.wait_for_timeout(1100);page.mouse.up()
        assert audio_value()>15.5
        page.keyboard.press('Meta+z');expect(length).to_have_value('10.00')
        checks.append('edge-scroll continues across beat snaps without sticking at the old boundary')

        page.evaluate('window.getSelection().removeAllRanges()')
        label=page.locator('.tl-length').bounding_box()
        page.mouse.move(label['x']+2,label['y']+label['height']/2);page.mouse.down()
        page.mouse.move(label['x']+35,label['y']+label['height']/2,steps=8);page.mouse.up()
        assert page.evaluate('window.getSelection().toString()') == ''
        assert page.locator('.tl-length').evaluate('(e)=>getComputedStyle(e).userSelect') == 'none'
        word('a').dblclick();expect(page.locator('.tl-inline')).to_be_visible()
        assert page.locator('.tl-inline').evaluate('(e)=>e.selectionEnd-e.selectionStart') == 4
        page.keyboard.press('Escape')
        checks.append('timeline labels cannot be selected; inline text remains editable/selectable')

        page.screenshot(path=str(args.out / 'timeline.png'))
        assert not errors, errors
        report = {'passed': True, 'checks': checks, 'savesIntercepted': len(saved)}
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        browser.close()


if __name__ == '__main__':
    main()
