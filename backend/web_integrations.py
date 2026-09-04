"""
Интеграции со сторонними сервисами через их публичные API — вместо хрупкой
автоматизации браузера (клики по DOM, который может в любой момент измениться),
ищем через официальный API сервиса и просто открываем прямую ссылку на результат.
"""

import os
import webbrowser
from typing import Dict, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def _no_requests_error() -> Dict:
    return {"success": False, "message": "Библиотека requests не установлена — веб-интеграции недоступны"}


def search_youtube_video(query: str) -> Dict:
    """Найти видео на YouTube через YouTube Data API v3 и открыть его в браузере."""
    if not REQUESTS_AVAILABLE:
        return _no_requests_error()

    if not query.strip():
        return {"success": False, "message": "Не понял, что искать на YouTube — уточните запрос"}

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return {
            "success": False,
            "message": (
                "Не настроен YOUTUBE_API_KEY — получите бесплатный ключ в Google Cloud Console "
                "(включить YouTube Data API v3) и добавьте его в .env"
            ),
        }

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
        return {"success": True, "message": f'Включаю на YouTube: "{title}"', "url": url, "title": title}
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return {"success": False, "message": f"Ошибка YouTube API: {detail or str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Ошибка поиска на YouTube: {e}"}


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
        if e.response is not None and e.response.status_code == 403:
            return {"success": False, "message": "GitHub временно ограничил запросы (rate limit) — добавьте GITHUB_TOKEN в .env для более высокого лимита"}
        return {"success": False, "message": f"Ошибка GitHub API: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Ошибка поиска на GitHub: {e}"}
