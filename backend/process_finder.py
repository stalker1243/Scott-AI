"""
Поиск запущенной программы по тому, как её называет человек.

Просьба «закрой дискорд» раньше превращалась в попытку убить процесс
`дискорд.exe`: имя бралось из фразы почти как есть, и если приложения не было
в списке псевдонимов, закрывать оказывалось нечего. Хуже того, результат никто
не проверял — Scott в любом случае отвечал «закрыл».

Здесь ищется то, что действительно работает в системе: по имени файла, по
транслитерации («дискорд» → `discord`) и по заголовку окна. Ответ строится по
факту, а не по намерению.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    PSUTIL_AVAILABLE = False

from difflib import SequenceMatcher

try:
    from .app_resolver import ALIASES, transliterate, _normalize
except ImportError:  # pragma: no cover - запуск не пакетом
    from app_resolver import ALIASES, transliterate, _normalize

# Процессы, которые нельзя закрывать по голосовой просьбе. Человек, сказавший
# «закрой проводник», вряд ли хочет остаться без панели задач, а «закрой
# систему» не должно превращаться в убийство служб.
PROTECTED = {
    "system", "system idle process", "csrss", "wininit", "winlogon", "services",
    "lsass", "smss", "svchost", "dwm", "explorer", "shellexperiencehost",
    "sihost", "ctfmon", "runtimebroker", "searchhost", "textinputhost",
    "systemd", "init", "gnome-shell", "plasmashell", "xorg", "wayland",
    "pipewire", "pulseaudio",
}

# Сам Scott и его backend: закрывать себя по просьбе «закрой скотт» — верный
# способ оборвать разговор на полуслове.
OWN = {"scottai", "scottai.avalonia", "python", "python3", "pythonw"}


@dataclass
class RunningApp:
    """Найденный процесс и то, насколько уверенно он опознан."""

    pid: int
    name: str
    title: str
    score: float


def _window_titles() -> dict:
    """
    Заголовки окон по идентификатору процесса.

    Нужны потому, что имя файла и название на экране часто расходятся:
    «Яндекс Браузер» — это `browser.exe`, а «Диспетчер задач» — `Taskmgr.exe`.
    Без окон такие просьбы не выполнить.
    """
    titles: dict = {}

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return titles

    if not hasattr(ctypes, "windll"):
        return titles

    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        titles.setdefault(pid.value, buffer.value)
        return True

    try:
        user32.EnumWindows(callback_type(collect), 0)
    except Exception:
        pass

    return titles


def _match_score(query: str, name: str, title: str) -> float:
    """
    Насколько процесс похож на то, что назвал человек.

    Ноль означает «не он»: закрывать что попало опаснее, чем не закрыть
    ничего.
    """
    name = (name or "").lower().removesuffix(".exe")
    title = (title or "").lower()

    # Пустое имя процесса совпадало с любым запросом: `query.startswith("")`
    # всегда истинно. На живой системе из-за этого «закрой хром» находило
    # безымянный системный процесс с уверенностью 0.85.
    if not query or not name:
        return 0.0

    if query == name:
        return 1.0

    # Название на экране человек и произносит: «закрой телеграм» при окне
    # «Telegram (12)».
    if title and (query in title or title.startswith(query)):
        return 0.9

    if name.startswith(query) or query.startswith(name):
        return 0.85

    if query in name:
        return 0.7

    # Транслитерация не бывает точной: «дискорд» превращается в «diskord», а
    # процесс называется «discord». Побуквенно это разные слова, на слух —
    # одно и то же, поэтому сравниваем нестрого.
    if len(query) >= 5:
        similarity = SequenceMatcher(None, query, name).ratio()
        if similarity >= 0.8:
            return similarity * 0.8

    return 0.0


def find_running(query: str, limit: int = 5) -> List[RunningApp]:
    """
    Найти работающие программы, похожие на запрос.

    Запрос проверяется и как есть, и в транслитерации: люди говорят
    «дискорд», а процесс называется `Discord.exe`. Список отсортирован —
    первым идёт самый уверенный.
    """
    if not PSUTIL_AVAILABLE:
        return []

    normalized = _normalize(query)
    if not normalized:
        return []

    variants = {normalized}

    # Готовый список псевдонимов — тот же, по которому программы открываются.
    # Короткие названия транслитерация не вытягивает: «хром» превращается в
    # «khrom», что на «chrome» уже не похоже.
    alias = ALIASES.get(normalized)
    if alias:
        variants.add(alias)

    latin = transliterate(normalized.replace(" ", ""))
    if latin:
        variants.add(latin)

    # Падежное окончание тоже мешает: «закрой дискорда».
    for variant in list(variants):
        if len(variant) > 4:
            variants.add(re.sub(r"(а|у|ом|ы|и|е|я)$", "", variant))

    titles = _window_titles()
    found: List[RunningApp] = []

    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = (process.info.get("name") or "")
            base = name.lower().removesuffix(".exe")

            if base in PROTECTED or base in OWN:
                continue

            title = titles.get(process.info["pid"], "")
            score = max(_match_score(v, name, title) for v in variants)

            if score > 0:
                found.append(RunningApp(process.info["pid"], name, title, score))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # У браузеров и мессенджеров десятки процессов с одним именем — оставляем
    # уникальные имена, чтобы человек видел понятный ответ.
    found.sort(key=lambda app: (-app.score, app.name.lower()))

    unique: List[RunningApp] = []
    seen = set()
    for app in found:
        key = app.name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(app)

    return unique[:limit]


def close_running(query: str) -> dict:
    """
    Закрыть программу по названию.

    Закрываются ВСЕ процессы с этим именем: у браузеров и мессенджеров их
    десятки, и убийство одного ничего не даёт — окно останется на месте.

    Возвращает {success, message, name, killed}.
    """
    if not PSUTIL_AVAILABLE:
        return {"success": False, "message": "psutil недоступен — закрывать нечем", "killed": 0}

    candidates = find_running(query)
    if not candidates:
        return {
            "success": False,
            "message": f"Не нашёл запущенное приложение «{query}»",
            "killed": 0,
        }

    target = candidates[0]
    target_name = target.name.lower()
    killed = 0
    denied = 0

    for process in psutil.process_iter(["pid", "name"]):
        try:
            if (process.info.get("name") or "").lower() != target_name:
                continue

            process.terminate()
            killed += 1
        except psutil.AccessDenied:
            denied += 1
        except psutil.NoSuchProcess:
            continue

    if killed == 0:
        return {
            "success": False,
            "message": (f"Нашёл «{target.name}», но закрыть не дала система — "
                        "у процесса больше прав, чем у Scott"),
            "name": target.name,
            "killed": 0,
        }

    # Название на экране понятнее имени файла: «Discord» вместо «Discord.exe».
    label = target.title.split(" — ")[-1].strip() if target.title else target.name
    note = "" if denied == 0 else f" (ещё {denied} не поддались — нужны права администратора)"

    return {
        "success": True,
        "message": f"Закрыл {label}{note}",
        "name": target.name,
        "killed": killed,
    }
