"""One owned browser session. Fixed YouTube operations, no model-generated code."""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, quote_plus, urlparse


class BrowserFailure(ValueError):
    pass


def video_id(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('www.youtube.com', 'youtube.com', 'm.youtube.com') or parsed.path != '/watch':
        return None
    value = parse_qs(parsed.query).get('v', [''])[0]
    return value if re.fullmatch(r'[A-Za-z0-9_-]{11}', value) else None


class YouTubeDriver:
    def __init__(self, page, progress=lambda *args: None):
        self.page, self.progress = page, progress

    async def navigate(self, url):
        await self.page.goto(url, wait_until='domcontentloaded', timeout=25000)
        # Only the explicit refusal of optional cookies is automatic.
        refusal = self.page.get_by_role('button', name=re.compile(r'^(Reject all|Отклонить все|Не принимать)$', re.I)).first
        if await refusal.is_visible():
            await refusal.click(timeout=5000)

    async def search(self, query):
        self.progress('search', 'Ищем видео на YouTube', .35)
        await self.navigate('https://www.youtube.com/results?search_query=' + quote_plus(query))
        links = self.page.locator('ytd-video-renderer a#video-title')
        try:
            await links.first.wait_for(state='visible', timeout=15000)
        except Exception:
            raise BrowserFailure('Не удалось прочитать результаты YouTube. Проверьте страницу в окне Scott.') from None
        rows = await links.evaluate_all('(items) => items.slice(0, 20).map(a => ({title:a.textContent, url:a.href}))')
        candidates, seen = [], set()
        for row in rows:
            ident = video_id(row.get('url', ''))
            if ident and ident not in seen:
                seen.add(ident)
                candidates.append({'video_id': ident, 'title': ' '.join(str(row.get('title', '')).split())[:200] or 'Видео'})
            if len(candidates) == 5:
                break
        if not candidates:
            raise BrowserFailure('Подходящих видео не найдено. Уточните запрос.')
        return candidates

    async def playback(self, action, ident=None):
        if ident:
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', ident):
                raise BrowserFailure('Некорректное видео.')
            self.progress('open', 'Открываем выбранное видео', .65)
            await self.navigate('https://www.youtube.com/watch?v=' + ident)
        current = video_id(self.page.url)
        if not current or (ident and current != ident):
            raise BrowserFailure('В окне Scott нет выбранного видео YouTube.')
        await self.page.locator('video').first.wait_for(state='attached', timeout=15000)
        paused = await self.page.evaluate('() => document.querySelector("video").paused')
        target = action == 'pause'
        if paused != target:
            await self.page.locator('.ytp-play-button').first.click(timeout=5000)
        self.progress('verify', 'Проверяем паузу' if target else 'Проверяем воспроизведение', .85)
        if target:
            await self.page.wait_for_function('() => document.querySelector("video")?.paused === true', timeout=8000)
        else:
            before = await self.page.evaluate('() => document.querySelector("video").currentTime')
            await self.page.wait_for_function('t => { const v=document.querySelector("video"); return v && !v.paused && !v.ended && v.currentTime > t + .15 && !document.querySelector(".html5-video-player.ad-showing"); }', arg=before, timeout=20000)
        if video_id(self.page.url) != current:
            raise BrowserFailure('Страница изменилась во время проверки. Повторите команду.')
        title = await self.page.title()
        return {'video_id': current, 'title': title.removesuffix(' - YouTube')[:200], 'paused': target, 'verified': True}


async def serve(home, headless=False):
    sys.path.insert(0, str(home / 'libraries'))
    from playwright.async_api import async_playwright
    from browser_control_config import browser_options
    context = page = None
    last_id = ''
    def emit(**event):
        print(json.dumps(event, ensure_ascii=False), flush=True)
    def closed():
        nonlocal context, page
        context = page = None
        emit(type='window_closed', id=last_id)
    async with async_playwright() as playwright:
        try:
            while line := await asyncio.to_thread(sys.stdin.readline):
                if len(line) > 4096:
                    continue
                job = json.loads(line)
                last_id = job['id']
                def progress(stage, message, fraction):
                    emit(type='progress', id=last_id, stage=stage, message=message, progress=fraction)
                try:
                    if context is None:
                        progress('browser', 'Открываем браузер Scott', .1)
                        context = await playwright.chromium.launch_persistent_context(
                            str(home / 'profile'), headless=headless, accept_downloads=False,
                            timeout=20000, **browser_options(home))
                        context.on('close', closed)
                        page = context.pages[0] if context.pages else await context.new_page()
                        page.on('dialog', lambda dialog: asyncio.create_task(dialog.dismiss()))
                        emit(type='window_open', id=last_id)
                    driver = YouTubeDriver(page, progress)
                    result, action = {}, job['action']
                    async with asyncio.timeout(70):
                        if action == 'home':
                            await driver.navigate('https://www.youtube.com')
                            result['message'] = 'YouTube открыт в окне Scott'
                        elif action in ('search', 'play'):
                            result['candidates'] = await driver.search(job['query'])
                            if action == 'play':
                                result['playback'] = await driver.playback('resume', result['candidates'][0]['video_id'])
                                result['message'] = 'Воспроизведение подтверждено'
                            else:
                                result['message'] = 'Выберите видео или скажите «включи второе»'
                        elif action in ('select', 'pause', 'resume'):
                            result['playback'] = await driver.playback('pause' if action == 'pause' else 'resume', job.get('video_id'))
                            result['message'] = 'Видео на паузе' if action == 'pause' else 'Воспроизведение подтверждено'
                        else:
                            raise BrowserFailure('Неизвестная команда браузеру.')
                    emit(type='result', id=last_id, state='complete', progress=1., **result)
                except BrowserFailure as error:
                    emit(type='result', id=last_id, state='failed', message=str(error))
                except Exception:
                    emit(type='result', id=last_id, state='failed', message='Не удалось завершить действие в браузере. Проверьте страницу; реклама, вход или сеть могут мешать воспроизведению.')
        finally:
            if context:
                await context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--owner', type=int, default=0)
    parser.add_argument('--owner-created', type=float, default=0.)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    from browser_control_config import watch_owner
    watch_owner(args.owner, args.owner_created)
    try:
        asyncio.run(serve(args.home, args.headless))
    except Exception:
        print(json.dumps({'type': 'fatal', 'message': 'Браузер недоступен. Повторите подготовку; на Linux также проверьте библиотеки Chromium.'}, ensure_ascii=False), flush=True)
        raise SystemExit(1)
