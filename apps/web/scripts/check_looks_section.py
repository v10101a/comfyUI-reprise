"""Verify the Looks demo's shared audio clock and layer switching without writing projects.

Run with server/.venv/bin/python from the repository root. --smoke uses only the
existing flat-card and neon clips while a replacement grid is still rendering.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5174')
    parser.add_argument('--out', type=Path, default=Path('outputs/looks_r4/playback-check'))
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'base': args.base, 'smoke': args.smoke, 'switches': []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(15000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/**', lambda route: route.continue_()
                   if route.request.method in ('GET', 'HEAD', 'OPTIONS') else route.abort())
        try:
            page.goto(args.base, wait_until='domcontentloaded')
            section = page.locator('.sc-looks')
            section.scroll_into_view_if_needed()
            page.wait_for_function('''() => {
                const a=document.querySelector('.sc-looks audio');
                const v=document.querySelector('.sc-looks video');
                return a?.readyState>=2 && v?.readyState>=2;
            }''')
            page.wait_for_timeout(1200)
            report['initial'] = section.evaluate('''s => {
                const a=s.querySelector('audio'),v=s.querySelector('video');
                return {audioPaused:a.paused,videoPaused:v.paused,audioTime:a.currentTime,
                        videoTime:v.currentTime,audioDuration:a.duration,videoDuration:v.duration};
            }''')
            # Explicit play remains possible on browsers that block autoplay.
            if report['initial']['audioPaused']:
                section.locator('video').last.click()
            page.wait_for_function('''() => {
                const a=document.querySelector('.sc-looks audio'),v=document.querySelector('.sc-looks video');
                return !a.paused && !v.paused && v.currentTime>0;
            }''')
            section.locator('video').last.click()
            page.wait_for_function("document.querySelector('.sc-looks audio').paused")
            section.locator('audio').evaluate('(a)=>{a.currentTime=1.25}')
            # Each switch must keep the song's clock, including while paused.
            looks = section.locator('.sc-looks-row button')
            indices = [1, 4] if args.smoke else range(looks.count())
            for i in indices:
                looks.nth(i).click()
                grades = section.locator('.sc-looks-bar button')
                for j in ([0] if args.smoke or i == 0 else range(grades.count())):
                    if i != 0:
                        grades.nth(j).click()
                    page.wait_for_function('''() => {
                        const s=document.querySelector('.sc-looks'),v=s.querySelector('video');
                        return s.querySelectorAll('video').length===1 && v.readyState>=2 && !v.seeking;
                    }''')
                    state = section.evaluate('''s=>{
                        const a=s.querySelector('audio'),v=s.querySelector('video');
                        return {look:s.querySelector('.sc-looks-row [aria-pressed=true]').textContent,
                                src:v.currentSrc,videoTime:v.currentTime,audioTime:a.currentTime,
                                duration:v.duration,audioDuration:a.duration,paused:v.paused,
                                muted:v.muted,audios:s.querySelectorAll('audio').length};
                    }''')
                    report['switches'].append(state)
                    assert state['paused'] and state['muted'] and state['audios'] == 1, state
                    assert abs(state['videoTime'] - state['audioTime']) < .12, state
                    if not args.smoke:
                        assert abs(state['duration'] - 4) < .06, state
                        assert abs(state['audioDuration'] - state['duration']) < .06, state
            section.locator('video').last.click()
            page.wait_for_timeout(1500)
            playing = section.evaluate('''s=>{
                const a=s.querySelector('audio'),v=s.querySelector('video');
                return {audio:a.currentTime,video:v.currentTime,audioPaused:a.paused,videoPaused:v.paused};
            }''')
            assert not playing['audioPaused'] and not playing['videoPaused'], playing
            assert abs(playing['audio'] - playing['video']) < .15, playing
            report['playing'] = playing
            section.screenshot(path=str(args.out / 'looks.png'))
            assert not errors, errors
            report['passed'] = True
        except Exception as error:
            report['passed'] = False
            report['error'] = str(error)
            raise
        finally:
            report['pageErrors'] = errors
            (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            browser.close()
    print(json.dumps({'passed': True, 'switches': len(report['switches']), 'out': str(args.out)}))


if __name__ == '__main__':
    main()
