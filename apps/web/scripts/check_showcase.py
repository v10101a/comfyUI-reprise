"""Read-only checks for the current showcase, including API-free/mobile playback.
Run from the repo root with Vite and the API running; no project is edited.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
OUT = Path('outputs/showcase-check')
REGISTRY = Path(__file__).resolve().parents[1] / 'src/showcase-pieces.json'


def choose(page, name):
    page.locator('.sc-piece').filter(has=page.get_by_text(name, exact=True)).click()
    expect(page.get_by_role('heading', level=1)).to_have_text(name)
    page.wait_for_function('document.querySelector(".sc-stage > video")?.readyState >= 2')
    page.locator('.sc-stage > video').first.evaluate('(v) => v.pause()')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pieces = json.loads(REGISTRY.read_text())['pieces']
    song = next(piece for piece in pieces if piece['id'] == 'so-i-die')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.get_by_role('heading', level=1)).to_have_text(pieces[0]['name'])
        # Check every required clip/alternate, even if it is not selected initially.
        for piece in pieces:
            response = page.request.head(f"{BASE}/showcase/{piece['file']}")
            available = response.ok and response.headers.get('content-type', '').startswith('video/')
            if piece.get('optional') and not available:
                continue
            assert available, piece['file']
            expect(page.locator('.sc-name').get_by_text(piece['name'], exact=True)).to_be_visible()
            for alt in piece.get('alts', []):
                response = page.request.head(f"{BASE}/showcase/{alt['file']}")
                assert response.ok and response.headers.get('content-type', '').startswith('video/'), alt['file']

        choose(page, song['name'])
        video = page.locator('.sc-stage > video').first
        assert video.evaluate('(v) => v.currentSrc').split('?')[0].endswith('/' + song['file'])
        assert abs(video.evaluate('(v) => v.duration') - 23) < .1
        page.get_by_role('slider', name='seek', exact=True).fill('6')
        page.wait_for_function('Math.abs(document.querySelector(".sc-stage > video").currentTime - 6) < .1 && !document.querySelector(".sc-stage > video").seeking')
        page.get_by_role('button', name='play', exact=True).click()
        page.wait_for_function('document.querySelector(".sc-stage > video").currentTime > 6.2')
        page.get_by_role('button', name='pause', exact=True).click()
        projects = page.request.get(f'{BASE}/api/projects').json()
        assert song['project'] in {project['id'] for project in projects}, 'Missing local So I Die Studio project'
        expect(page.get_by_role('link', name='Open studio', exact=True)).to_have_attribute('href', f"#/studio?project={song['project']}")
        expect(page.get_by_role('link', name='download', exact=True)).to_have_attribute('href', video.get_attribute('src'))
        page.screenshot(path=str(OUT / 'desktop.png'), full_page=True)

        # Arrow navigation and the existing synchronized Original comparison still work.
        page.get_by_role('heading', level=1).click()
        page.keyboard.press('ArrowRight')
        expect(page.get_by_role('heading', level=1)).to_have_text(pieces[pieces.index(song) + 1]['name'])
        choose(page, pieces[0]['name'])
        page.get_by_role('button', name='Original', exact=True).click()
        expect(page.locator('.sc-layer.on')).to_be_visible()
        page.get_by_role('button', name='Typeset', exact=True).click()
        expect(page.locator('.sc-layer.on')).to_have_count(0)

        # A static checkout plays the same clip without the project API.
        offline = browser.new_page(viewport={'width': 390, 'height': 844})
        offline.on('pageerror', lambda error: errors.append(str(error)))
        offline.route('**/api/**', lambda route: route.abort())
        offline.goto(BASE)
        choose(offline, song['name'])
        expect(offline.get_by_role('link', name='Open studio', exact=True)).to_have_attribute('href', '#/studio')
        assert offline.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
        offline.screenshot(path=str(OUT / 'mobile.png'), full_page=True)
        assert not errors, errors
        browser.close()
    print('PASS: required media, So I Die playback/audio clock, seeking, Studio link, download, keyboard navigation, Original comparison, API-free mobile preview')
    print('Screenshots:', OUT)


if __name__ == '__main__':
    main()
