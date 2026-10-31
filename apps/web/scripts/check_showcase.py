"""Check showcase playback, presentation, deep links, and API-free/mobile use.
Run from the repo root while Vite and the API are running.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('TYPESET_WEB_URL', 'http://127.0.0.1:5174')
OUT = Path('outputs/showcase-check')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE)
        expect(page.get_by_role('heading', level=1)).to_contain_text('Words belong')
        page.wait_for_function('document.querySelector(".show-player video")?.readyState >= 2')
        expect(page.get_by_role('button', name='Pause preview', exact=True)).to_be_visible()
        page.get_by_role('button', name='Pause preview', exact=True).click()
        page.screenshot(path=str(OUT / 'desktop.png'), full_page=True)

        page.get_by_role('button', name='Starting image', exact=True).click()
        expect(page.locator('.show-player > img')).to_be_visible()
        assert page.locator('.show-player video').count() == 0
        page.get_by_role('button', name='Final result', exact=True).click()
        page.wait_for_function('document.querySelector(".show-player video")?.readyState >= 2')
        page.get_by_role('slider', name='Seek preview').fill('2')
        assert page.locator('.show-player video').evaluate('(v) => v.currentTime') >= 1.9

        page.get_by_role('button', name='Presentation mode').click()
        expect(page.locator('.showcase')).to_have_class('showcase is-presenting')
        page.keyboard.press('ArrowRight')
        expect(page.locator('.show-caption h2')).to_have_text('Give words a place.')
        page.get_by_role('button', name='Text overlay', exact=True).click()
        page.wait_for_function('document.querySelector(".show-player video")?.readyState >= 2')
        expect(page.locator('.show-player')).to_have_class('show-player has-alpha')
        page.get_by_role('slider', name='Seek preview').fill('1.3')
        page.wait_for_function('!document.querySelector(".show-player video").seeking')
        page.screenshot(path=str(OUT / 'presentation.png'))
        page.keyboard.press('Escape')
        expect(page.locator('.showcase')).to_have_class('showcase')
        expect(page.get_by_role('button', name='Presentation mode')).to_be_focused()

        page.get_by_role('button', name='View LOUDER material study').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).not_to_be_visible()

        # The selected kinetic demo opens the real editable project when the API is available.
        page.get_by_role('link', name='Open this clip in studio').click()
        expect(page.get_by_role('textbox', name='Project name')).to_have_value('Typeset — typography demo')
        expect(page.locator('.word-chip')).to_have_count(25)
        page.get_by_role('link', name='Back to showcase').click()
        expect(page.get_by_role('heading', level=1)).to_be_visible()

        # Saved outputs and the offline editor remain usable without the API.
        offline = browser.new_page(viewport={'width': 390, 'height': 844})
        offline.on('pageerror', lambda error: errors.append(str(error)))
        offline.route('**/api/**', lambda route: route.abort())
        offline.goto(BASE)
        offline.wait_for_function('document.querySelector(".show-player video")?.readyState >= 2')
        assert offline.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
        offline.screenshot(path=str(OUT / 'mobile.png'), full_page=True)
        offline.get_by_role('link', name='Open studio', exact=False).first.click()
        expect(offline.locator('.word-chip')).to_have_count(25)
        assert not errors, errors
        browser.close()
    print('PASS: gallery playback, seeking, source/result, alpha preview, presentation keys, lightbox, editor deep link, API-free preview, mobile layout')
    print('Screenshots:', OUT)


if __name__ == '__main__':
    main()
