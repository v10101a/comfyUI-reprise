"""Browser regression: unresolved renderer promises must fail within the configured deadline."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.exporter import await_renderer
from playwright.sync_api import sync_playwright, Error

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        page.set_content('<canvas id="stage"></canvas>')
        page.evaluate('window.__typeset = {ready: new Promise(() => {}), renderFrame: () => new Promise(() => {})}')
        with patch('app.exporter.settings', SimpleNamespace(render_timeout=.1)):
            for frame, message in [(None, 'Renderer readiness timed out'), (2, 'Frame 2 timed out')]:
                try:
                    await_renderer(page, frame)
                except Error as exc:
                    assert message in str(exc), exc
                else:
                    raise AssertionError('Pending promise unexpectedly completed')
        print('PASS: both readiness and frame promises have bounded timeouts')
    finally:
        browser.close()
