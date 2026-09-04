"""
Универсальный поиск и запуск установленных Windows-приложений — без ручного
ведения списка "имя → exe". Источники, которыми пользуется сама Windows:

1. Get-StartApps (PowerShell) — тот же самый каталог, которым пользуется
   системный поиск Windows (Win → начать печатать). Покрывает ВСЁ: обычные
   десктопные программы И приложения из Microsoft Store (UWP — Калькулятор,
   Paint, Фото и т.п.), которых нет ни в реестре, ни в файлах-ярлыках.
   Запускаются через `shell:appsFolder\\<AppID>` — универсальный механизм,
   работающий что для обычных .exe, что для UWP.
2. Реестр App Paths (HKLM/HKCU ...\\App Paths) — то же самое, что находит
   Win+R, когда вводишь "chrome" и жмёшь Enter.
3. Индекс ярлыков меню "Пуск" (*.lnk) — резервный источник на случай, если
   Get-StartApps недоступен (например, explorer.exe не запущен).

Порядок: алиас (короткие русские синонимы) → точное совпадение в
Get-StartApps/App Paths → нечёткое (fuzzy) совпадение по объединённому
каталогу. Если ничего не найдено — честно возвращается ошибка, а не
выдуманный успех.
"""

import glob
import json
import os
import re
import subprocess
import winreg
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple

APP_PATHS_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
]

START_MENU_DIRS = [
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
]

# Небольшой список коротких русских алиасов для самых частых приложений —
# не обязателен для работы (остальные источники покрывают всё сами),
# просто уточняет типичные запросы там, где название сильно отличается от exe.
ALIASES: Dict[str, str] = {
    "блокнот": "notepad",
    "проводник": "explorer",
    "калькулятор": "calculator",
    "браузер": "chrome",
    "хром": "chrome",
    "гугл хром": "chrome",
    "ворд": "word",
    "эксель": "excel",
    "паинт": "paint",
    "пэйнт": "paint",
    "командная строка": "cmd",
    "пауэршел": "powershell",
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "дискорд": "discord",
    "спотифай": "spotify",
    "стим": "steam",
    "скайп": "skype",
    "фаерфокс": "firefox",
    "аутлук": "outlook",
    "вс код": "code",
    "визуал студио код": "code",
    "плеер": "media player",
    "настройки": "settings",
    "параметры": "settings",
    "фото": "photos",
    "почта": "mail",
    "погода": "weather",
    "магазин": "microsoft store",
    "музыка": "groove music",
    "карты": "maps",
}

MIN_FUZZY_SCORE = 0.72

# kind: 'path' — обычный путь к .exe/.lnk (os.startfile/Popen);
#       'appid' — AppID из Get-StartApps (запуск через shell:appsFolder\<id>).
IndexEntry = Tuple[str, str]


@dataclass
class ResolvedApp:
    matched_name: str
    target: str
    kind: str  # 'path' | 'appid'
    source: str  # 'app_paths' | 'alias_app_paths' | 'startapps' | 'shortcut'


def _normalize(s: str) -> str:
    """
    Нормализовать имя для сравнения с каталогом.

    Раньше здесь снималось только ".exe"/".lnk" — а Whisper всегда
    транскрибирует фразы с точкой на конце ("открой телеграм." вместо
    "открой телеграм"), поэтому алиас "телеграм" не совпадал с "телеграм."
    ни разу, точный поиск тоже не срабатывал, а нечёткое сравнение
    сравнивало кириллицу с латиницей каталога и всегда давало почти нулевой
    score — приложение считалось "не найдено" даже когда оно точно
    установлено. Теперь снимается любая внешняя пунктуация/пробелы.
    """
    s = s.strip().lower()
    s = re.sub(r"\.(exe|lnk)$", "", s)
    s = s.strip(" .,!?:;—-")
    return s


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _resolve_app_paths(name: str) -> Optional[str]:
    """То же самое, что делает Win+R: ищет имя (точно) среди зарегистрированных App Paths."""
    for hive, subkey in APP_PATHS_KEYS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                i = 0
                while True:
                    try:
                        app_key_name = winreg.EnumKey(key, i)
                    except OSError:
                        break
                    i += 1
                    if _normalize(app_key_name) != name:
                        continue
                    try:
                        with winreg.OpenKey(key, app_key_name) as app_key:
                            path, _ = winreg.QueryValueEx(app_key, "")
                            if path and os.path.exists(path):
                                return path
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def _build_startapps_index() -> Dict[str, str]:
    """
    Get-StartApps — тот же каталог, которым пользуется поиск Windows.
    Возвращает {нормализованное_имя: AppID}.
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="ignore",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        index: Dict[str, str] = {}
        for item in data:
            name = (item or {}).get("Name", "")
            app_id = (item or {}).get("AppID", "")
            if name and app_id:
                index[_normalize(name)] = app_id
        return index
    except Exception:
        return {}


def _build_shortcut_index() -> Dict[str, str]:
    """Резервный источник: ярлыки меню "Пуск" ({нормализованное_имя: путь_к_.lnk})."""
    index: Dict[str, str] = {}
    for base in START_MENU_DIRS:
        if not os.path.isdir(base):
            continue
        for path in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            display_name = os.path.splitext(os.path.basename(path))[0]
            index[_normalize(display_name)] = path
    return index


_startapps_index_cache: Optional[Dict[str, str]] = None
_shortcut_index_cache: Optional[Dict[str, str]] = None


def _get_startapps_index() -> Dict[str, str]:
    global _startapps_index_cache
    if _startapps_index_cache is None:
        _startapps_index_cache = _build_startapps_index()
    return _startapps_index_cache


def _get_shortcut_index() -> Dict[str, str]:
    global _shortcut_index_cache
    if _shortcut_index_cache is None:
        _shortcut_index_cache = _build_shortcut_index()
    return _shortcut_index_cache


def refresh_index() -> Dict[str, int]:
    """Пересобрать оба индекса (например, после установки новых программ)."""
    global _startapps_index_cache, _shortcut_index_cache
    _startapps_index_cache = _build_startapps_index()
    _shortcut_index_cache = _build_shortcut_index()
    return {"startapps": len(_startapps_index_cache), "shortcuts": len(_shortcut_index_cache)}


def resolve_app(name: str) -> Optional[ResolvedApp]:
    """Найти приложение по произвольному имени пользователя (любой установленный софт)."""
    normalized = _normalize(name)
    if not normalized:
        return None

    alias = ALIASES.get(normalized)
    search_name = alias or normalized

    # 1. Точное совпадение в App Paths (быстро, надёжно для консольных/классических программ)
    path = _resolve_app_paths(normalized) or (_resolve_app_paths(alias) if alias else None)
    if path:
        return ResolvedApp(matched_name=search_name, target=path, kind="path",
                            source="app_paths" if not alias else "alias_app_paths")

    startapps = _get_startapps_index()
    shortcuts = _get_shortcut_index()

    # 2. Точное совпадение в каталоге Windows (Get-StartApps — самый полный источник)
    if search_name in startapps:
        return ResolvedApp(matched_name=search_name, target=startapps[search_name], kind="appid", source="startapps")
    if search_name in shortcuts:
        return ResolvedApp(matched_name=search_name, target=shortcuts[search_name], kind="path", source="shortcut")

    # 3. Нечёткое совпадение по объединённому каталогу (startapps приоритетнее при равном скоре)
    best_key, best_score, best_pool = None, 0.0, None
    for key in startapps:
        score = _similarity(search_name, key)
        if score > best_score:
            best_score, best_key, best_pool = score, key, "startapps"
    for key in shortcuts:
        score = _similarity(search_name, key)
        if score > best_score:
            best_score, best_key, best_pool = score, key, "shortcut"

    if best_key and best_score >= MIN_FUZZY_SCORE:
        if best_pool == "startapps":
            return ResolvedApp(matched_name=best_key, target=startapps[best_key], kind="appid", source="startapps")
        return ResolvedApp(matched_name=best_key, target=shortcuts[best_key], kind="path", source="shortcut")

    return None


def launch_app(name: str) -> Dict:
    """
    Найти и запустить приложение по имени.
    Возвращает {success, matched_name, source, error}.
    """
    resolved = resolve_app(name)
    if not resolved:
        return {
            "success": False,
            "matched_name": None,
            "source": None,
            "error": f'Не нашёл установленное приложение «{name}» — ни в каталоге Windows, ни в App Paths, ни среди ярлыков меню "Пуск".',
        }

    try:
        if resolved.kind == "appid":
            os.startfile(f"shell:appsFolder\\{resolved.target}")
        elif resolved.target.lower().endswith(".lnk"):
            # os.startfile сам разворачивает .lnk в целевую программу — как двойной клик.
            os.startfile(resolved.target)
        else:
            subprocess.Popen([resolved.target], shell=False)
        return {"success": True, "matched_name": resolved.matched_name, "source": resolved.source, "error": None}
    except Exception as e:
        return {"success": False, "matched_name": resolved.matched_name, "source": resolved.source, "error": str(e)}
