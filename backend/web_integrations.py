"""
Интеграции со сторонними сервисами через их публичные API — вместо хрупкой
автоматизации браузера (клики по DOM, который может в любой момент измениться),
ищем через официальный API сервиса и просто открываем прямую ссылку на результат.
"""

import os
import webbrowser
from typing import Dict, Optional
from urllib.parse import quote_plus

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def _no_requests_error() -> Dict:
    return {"success": False, "message": "Библиотека requests не установлена — веб-интеграции недоступны"}


def _open_youtube_results(query: str, reason: str = "") -> Dict:
    """
    Открыть страницу результатов поиска YouTube — путь, которому не нужен ключ.

    Пользователю остаётся один клик по нужному ролику, зато команда работает
    всегда: без настроенного ключа, при исчерпанной квоте (10 000 единиц в
    сутки, поиск стоит 100 — около сотни запросов в день) и при любом сбое
    самого API.
    """
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    webbrowser.open(url)
    return {
        "success": True,
        "message": f'Открываю поиск на YouTube: "{query}"',
        "url": url,
        "via": "search_page",
        "reason": reason,
    }


def _open_github_results(query: str, reason: str = "") -> Dict:
    """Открыть страницу поиска репозиториев — запасной путь, когда API не ответил."""
    url = f"https://github.com/search?q={quote_plus(query)}&type=repositories"
    webbrowser.open(url)
    return {
        "success": True,
        "message": f'Открываю поиск на GitHub: "{query}"',
        "url": url,
        "via": "search_page",
        "reason": reason,
    }


def search_youtube_video(query: str) -> Dict:
    """
    Найти видео на YouTube и открыть его в браузере.

    С ключом YOUTUBE_API_KEY открывается сразу нужный ролик, без ключа — страница
    результатов поиска. Раньше отсутствие ключа означало, что команда просто не
    работает: Scott отвечал инструкцией, как ключ получить, и на этом всё
    заканчивалось. Ключ должен улучшать команду, а не быть условием её работы,
    поэтому любой сбой API — истёкшая квота, отозванный ключ, недоступный
    googleapis.com — тоже приводит к странице результатов, а не к отказу.
    """
    if not REQUESTS_AVAILABLE:
        return _no_requests_error()

    if not query.strip():
        return {"success": False, "message": "Не понял, что искать на YouTube — уточните запрос"}

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return _open_youtube_results(query, reason="ключ не настроен")

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": 1,
                "key": api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return {"success": False, "message": f'Ничего не нашёл на YouTube по запросу "{query}"'}

        video_id = items[0]["id"]["videoId"]
        title = items[0]["snippet"]["title"]
        url = f"https://www.youtube.com/watch?v={video_id}"

        webbrowser.open(url)
        return {"success": True, "message": f'Включаю на YouTube: "{title}"', "url": url, "title": title, "via": "api"}
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return _open_youtube_results(query, reason=f"YouTube API отказал: {detail or e}")
    except Exception as e:
        return _open_youtube_results(query, reason=f"YouTube API недоступен: {e}")


def search_github_repo(query: str) -> Dict:
    """Найти репозиторий на GitHub через Search API и открыть его страницу в браузере."""
    if not REQUESTS_AVAILABLE:
        return _no_requests_error()

    if not query.strip():
        return {"success": False, "message": "Не понял, какой репозиторий искать на GitHub — уточните запрос"}

    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 1},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return {"success": False, "message": f'Ничего не нашёл на GitHub по запросу "{query}"'}

        repo = items[0]
        full_name = repo["full_name"]
        url = repo["html_url"]
        stars = repo.get("stargazers_count", 0)

        webbrowser.open(url)
        return {"success": True, "message": f"Открываю репозиторий {full_name} ({stars}⭐)", "url": url, "full_name": full_name}
    except requests.exceptions.HTTPError as e:
        # Та же логика, что и у YouTube: лучше открыть страницу поиска, чем
        # отказать. Без токена GitHub даёт 10 поисков в минуту, с токеном 30 —
        # упереться в это можно разве что случайно, но когда упрёшься, команда
        # должна всё равно сработать.
        if e.response is not None and e.response.status_code == 403:
            return _open_github_results(query, reason="GitHub временно ограничил запросы")
        return _open_github_results(query, reason=f"GitHub API отказал: {e}")
    except Exception as e:
        return _open_github_results(query, reason=f"GitHub API недоступен: {e}")
