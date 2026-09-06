"""
Проверка обновлений через GitHub Releases.

До этого «проверка обновлений» существовала только на бумаге: эндпоинт
`/api/version/update-check` сравнивал версию из локального VERSION.json с ней
же самой и всегда отвечал «обновлений нет». Никуда он не ходил.

Здесь настоящая: спрашиваем у GitHub последний выпуск, сравниваем номера и,
если вышел новее, отдаём ссылку на установщик. Скачивать и запускать его —
дело лаунчера: это действие на компьютере человека, и решать должен он.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Репозиторий, где публикуются выпуски. Переопределяется переменной окружения:
# у форка адрес другой, а пересобирать программу ради этого незачем.
REPO = os.getenv("SCOTT_UPDATE_REPO", "stalker1243/Scott-AI")

API_URL = "https://api.github.com/repos/{repo}/releases/latest"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION.json"
CACHE_FILE = Path(__file__).resolve().parent / "data" / "update_check.json"

# Как часто ходить на GitHub. Без токена он разрешает 60 запросов в час на
# адрес, а проверять чаще раза в сутки нет смысла: выпуски выходят не чаще.
CHECK_INTERVAL_SECONDS = 24 * 60 * 60

# Таймаут запроса. Проверка обновлений идёт при запуске, и человек не должен
# ждать её ни секунды дольше необходимого: не ответил GitHub — и ладно.
TIMEOUT_SECONDS = 8


@dataclass
class UpdateInfo:
    """Что известно об обновлении. Поля пустые, если проверка не удалась."""

    update_available: bool = False
    current_version: str = ""
    latest_version: str = ""
    release_notes: str = ""
    download_url: str = ""
    asset_name: str = ""
    asset_size: int = 0
    published_at: str = ""
    release_url: str = ""
    checked_at: float = 0.0
    error: str = ""

    def as_dict(self) -> Dict:
        return asdict(self)


# ==================== Сравнение версий ====================

VERSION_PART = re.compile(r"(\d+)")


def parse_version(text: str) -> Tuple[List[int], bool]:
    """
    Разобрать «v1.2.3», «1.2», «1.0.0-beta» в числа плюс признак предрелиза.

    Теги на GitHub люди пишут по-разному, и падать из-за буквы «v» перед
    номером эта проверка не должна.
    """
    if not text:
        return [0], False

    text = text.strip().lstrip("vV")
    prerelease = bool(re.search(r"[-+](?:alpha|beta|rc|pre)", text, re.IGNORECASE))

    numbers = [int(part) for part in VERSION_PART.findall(text.split("-")[0].split("+")[0])]
    return (numbers or [0]), prerelease


def is_newer(candidate: str, current: str) -> bool:
    """
    Новее ли `candidate`, чем `current`.

    Предрелиз при равных числах считается СТАРШЕ обычной версии наоборот —
    «1.0.0-beta» не должен предлагаться тому, у кого уже стоит «1.0.0».
    """
    candidate_numbers, candidate_pre = parse_version(candidate)
    current_numbers, current_pre = parse_version(current)

    # Списки разной длины сравниваются честно: «1.2» и «1.2.0» — одно и то же.
    length = max(len(candidate_numbers), len(current_numbers))
    candidate_numbers += [0] * (length - len(candidate_numbers))
    current_numbers += [0] * (length - len(current_numbers))

    if candidate_numbers != current_numbers:
        return candidate_numbers > current_numbers

    # Числа равны: предрелиз старше выпуска, выпуск новее предрелиза.
    return current_pre and not candidate_pre


# ==================== Текущая версия ====================

def current_version() -> str:
    """Версия из VERSION.json — того же файла, что читает установщик."""
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return str(json.load(f).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


# ==================== Кэш ====================

def _read_cache() -> Optional[Dict]:
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(data: Dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # Не записался кэш — просто сходим на GitHub в следующий раз.
        pass


# ==================== Запрос к GitHub ====================

def _pick_installer(assets: List[Dict]) -> Optional[Dict]:
    """
    Выбрать из вложений релиза установщик для Windows.

    Берётся .exe, потому что именно его собирает installer/build.py. Если в
    релиз положили только исходники, обновление всё равно покажется — просто
    со ссылкой на страницу выпуска.
    """
    def suitable(asset: Dict) -> bool:
        name = (asset.get("name") or "").lower()
        # arm64 отсеивается: сборка лаунчера и встроенный Python — x64, и
        # предлагать человеку установщик под другую архитектуру нельзя.
        # Проверено на живом релизе PowerToys, где arm64-файл лежит первым.
        return name.endswith(".exe") and "arm64" not in name

    candidates = [asset for asset in assets if suitable(asset)]

    for asset in candidates:
        if "setup" in (asset.get("name") or "").lower():
            return asset

    return candidates[0] if candidates else None


def fetch_latest_release(repo: str = REPO) -> Tuple[Optional[Dict], str]:
    """
    Спросить у GitHub последний выпуск. Возвращает (данные, ошибка).

    Ошибки здесь — обычное дело: нет интернета, GitHub недоступен, лимит
    запросов исчерпан, репозиторий ещё без выпусков. Ни одна из них не должна
    выглядеть как поломка программы.
    """
    if not REQUESTS_AVAILABLE:
        return None, "библиотека requests недоступна"

    try:
        response = requests.get(
            API_URL.format(repo=repo),
            headers={"Accept": "application/vnd.github+json"},
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as e:
        return None, f"не удалось связаться с GitHub: {e}"

    if response.status_code == 404:
        return None, "у проекта пока нет опубликованных выпусков"

    if response.status_code == 403:
        return None, "GitHub временно ограничил запросы — попробуйте позже"

    if response.status_code != 200:
        return None, f"GitHub ответил {response.status_code}"

    try:
        return response.json(), ""
    except ValueError:
        return None, "GitHub вернул неразборчивый ответ"


# ==================== Проверка ====================

def check(force: bool = False, repo: str = REPO) -> UpdateInfo:
    """
    Проверить, вышла ли новая версия.

    Без `force` ответ берётся из кэша, пока не прошли сутки: GitHub ограничивает
    число запросов, а выпуски выходят куда реже.
    """
    version = current_version()

    cached = _read_cache()
    if not force and cached and time.time() - cached.get("checked_at", 0) < CHECK_INTERVAL_SECONDS:
        info = UpdateInfo(**{k: v for k, v in cached.items() if k in UpdateInfo.__annotations__})
        # Версия могла обновиться после кэша — тогда предлагать нечего.
        info.current_version = version
        info.update_available = is_newer(info.latest_version, version)
        return info

    release, error = fetch_latest_release(repo)
    if error:
        return UpdateInfo(current_version=version, checked_at=time.time(), error=error)

    # Своя версия неизвестна — предлагать обновление нельзя: любая чужая
    # покажется новее, и человек получит предложение поставить то, что у него
    # уже стоит. Так и случилось, когда VERSION.json не попал в дистрибутив.
    if version in ("", "0.0.0"):
        return UpdateInfo(
            current_version=version,
            latest_version=str((release or {}).get("tag_name") or "").lstrip("vV"),
            checked_at=time.time(),
            error="не удалось определить установленную версию (нет VERSION.json)",
        )

    tag = str((release or {}).get("tag_name") or "")
    asset = _pick_installer((release or {}).get("assets") or [])

    info = UpdateInfo(
        update_available=is_newer(tag, version),
        current_version=version,
        latest_version=tag.lstrip("vV"),
        release_notes=str((release or {}).get("body") or "").strip(),
        download_url=str((asset or {}).get("browser_download_url") or ""),
        asset_name=str((asset or {}).get("name") or ""),
        asset_size=int((asset or {}).get("size") or 0),
        published_at=str((release or {}).get("published_at") or ""),
        release_url=str((release or {}).get("html_url") or ""),
        checked_at=time.time(),
    )

    _write_cache(info.as_dict())
    return info
