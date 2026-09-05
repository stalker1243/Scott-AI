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

import configparser
import glob
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

IS_WINDOWS = platform.system() == "Windows"

# winreg существует только на Windows: на Linux безусловный импорт уронил бы
# весь модуль, а с ним и запуск приложений целиком.
if IS_WINDOWS:
    import winreg

    APP_PATHS_KEYS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
else:
    winreg = None
    APP_PATHS_KEYS = []

# Куда Linux складывает описания установленных приложений. Flatpak и snap
# добавляют свои каталоги — без них половина программ на современном рабочем
# столе оказалась бы невидимой.
DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    "/var/lib/snapd/desktop/applications",
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
    kind: str  # 'path' | 'appid' (Windows) | 'desktop' (Linux)
    source: str  # 'app_paths' | 'alias_app_paths' | 'startapps' | 'shortcut' | 'desktop'


# Кириллица → латиница. Названия игр и программ человек произносит по-русски
# («дельтарун», «дискорд»), а в каталоге Windows они записаны латиницей, и
# посимвольное сравнение двух алфавитов даёт почти ноль. Перечислять всё
# алиасами бессмысленно — установленных программ у каждого свои, поэтому
# запрос переводится в латиницу и сравнивается уже с ней.
CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

# Окончания винительного падежа: «запусти дельтаруна», «открой фотошопа».
# Whisper передаёт сказанное дословно, а в каталоге название стоит в
# именительном.
CASE_ENDINGS = ("а", "у", "ом", "ы", "и")


def transliterate(name: str) -> str:
    """Перевести кириллическое название в латиницу; латиница остаётся как есть."""
    return "".join(CYRILLIC_TO_LATIN.get(char, char) for char in name.lower())


def _strip_case_ending(name: str) -> str:
    """Убрать русское падежное окончание, если под ним остаётся осмысленное слово."""
    for ending in CASE_ENDINGS:
        if len(name) > len(ending) + 3 and name.endswith(ending):
            return name[: -len(ending)]
    return name


def _search_variants(name: str) -> list:
    """
    Варианты написания запроса — от точного к вольному.

    Порядок важен: сначала то, что человек сказал, и лишь потом догадки.
    Совпадение по исходному имени всегда надёжнее, чем по обрубленному.
    """
    variants = [name]
    has_cyrillic = any(char in CYRILLIC_TO_LATIN for char in name)

    if has_cyrillic:
        variants.append(transliterate(name))

    without_ending = _strip_case_ending(name)
    if without_ending != name:
        variants.append(without_ending)
        if has_cyrillic:
            variants.append(transliterate(without_ending))

    seen = set()
    return [v for v in variants if v and not (v in seen or seen.add(v))]


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
    """
    Насколько похожи запрос и название из каталога.

    Посимвольного сходства мало: «firefox» и «Firefox Web Browser» — одно и то
    же приложение, но SequenceMatcher даёт всего 0.54, потому что подпись в
    меню втрое длиннее запроса. Поэтому запрос, целиком входящий в название,
    получает высокую оценку отдельно — иначе на Linux, где программы подписаны
    развёрнуто, не нашлось бы почти ничего.

    Слишком короткие запросы (меньше трёх символов) такой прибавки не
    получают: «vs» совпало бы с доброй половиной каталога.
    """
    ratio = SequenceMatcher(None, a, b).ratio()

    if len(a) >= 3 and len(b) >= 3:
        if b.startswith(a) or a.startswith(b):
            ratio = max(ratio, 0.9)
        elif f" {a} " in f" {b} ":
            ratio = max(ratio, 0.85)
        elif f" {b} " in f" {a} " and len(a) <= len(b) * 2:
            # Обратное вхождение — название каталога внутри запроса — годится
            # только для коротких запросов. Иначе любая длинная фраза,
            # где случайно упомянута программа, её запускает: на «напомним мне
            # 18:00 зайти в discord» Scott открыл Discord сию секунду и
            # отрапортовал об успехе, вместо того чтобы поставить напоминание.
            ratio = max(ratio, 0.85)

    return ratio


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
        # OutputEncoding задаётся явно: PowerShell на русской Windows выводит в
        # кодировке консоли, а не в UTF-8, и кириллица приходила испорченной.
        # С errors="ignore" она просто исчезала — «Калькулятор» превращался в
        # пустую строку и в каталог не попадал. Так пропадали 58 приложений из
        # 203: все, чьи имена по-русски.
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",
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


def _build_desktop_index() -> Dict[str, str]:
    """
    Каталог приложений Linux: {нормализованное_имя: путь_к_.desktop}.

    Читается поле Name (и localized Name[ru], если есть) — пользователь называет
    программу так, как она подписана в меню, а не именем исполняемого файла.
    Скрытые записи (NoDisplay=true) пропускаются: это служебные ассоциации типов
    файлов, а не то, что человек просит открыть.
    """
    index: Dict[str, str] = {}

    for directory in DESKTOP_DIRS:
        if not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, "**", "*.desktop"), recursive=True):
            try:
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                parser.read(path, encoding="utf-8")
                if not parser.has_section("Desktop Entry"):
                    continue
                entry = parser["Desktop Entry"]

                if entry.get("NoDisplay", "false").strip().lower() == "true":
                    continue
                if entry.get("Type", "Application").strip() != "Application":
                    continue

                names = [entry.get("Name", ""), entry.get("Name[ru]", "")]
                for name in names:
                    key = _normalize(name)
                    if key and key not in index:
                        index[key] = path
            except Exception:
                # Битый .desktop не должен ломать весь индекс: пропускаем его.
                continue

    return index


_desktop_index_cache: Optional[Dict[str, str]] = None


def _get_desktop_index() -> Dict[str, str]:
    global _desktop_index_cache
    if _desktop_index_cache is None:
        _desktop_index_cache = _build_desktop_index()
    return _desktop_index_cache


def _launch_desktop_entry(path: str) -> None:
    """
    Запустить приложение по его .desktop-файлу.

    gtk-launch и gio делают это правильно — с учётом окружения, переменных и
    поля Exec со всеми его подстановками вроде %U. Если ни того, ни другого нет,
    приходится разбирать Exec самостоятельно, вырезая подстановки: они
    предназначены для передачи файлов и без них команда работает.
    """
    entry_id = os.path.splitext(os.path.basename(path))[0]

    if shutil.which("gtk-launch"):
        subprocess.Popen(["gtk-launch", entry_id], start_new_session=True)
        return
    if shutil.which("gio"):
        subprocess.Popen(["gio", "launch", path], start_new_session=True)
        return

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path, encoding="utf-8")
    exec_line = parser["Desktop Entry"].get("Exec", "").strip()
    if not exec_line:
        raise RuntimeError(f"В {path} нет строки Exec")

    argv = [part for part in exec_line.split() if not part.startswith("%")]
    if not argv:
        raise RuntimeError(f"Пустая команда запуска в {path}")
    subprocess.Popen(argv, start_new_session=True)


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


def _resolve_linux(search_name: str) -> Optional[ResolvedApp]:
    """
    Найти приложение среди .desktop-файлов: точное совпадение, затем нечёткое.

    Логика та же, что и на Windows, — отличается только источник каталога.
    Нечёткое совпадение здесь особенно уместно: пользователь говорит «браузер»
    или «файрфокс», а в меню приложение подписано «Firefox Web Browser».
    """
    index = _get_desktop_index()
    if not index:
        return None

    if search_name in index:
        return ResolvedApp(matched_name=search_name, target=index[search_name],
                           kind="desktop", source="desktop")

    best_key, best_score = None, 0.0
    for key in index:
        score = _similarity(search_name, key)
        if score > best_score:
            best_score, best_key = score, key

    if best_key and best_score >= MIN_FUZZY_SCORE:
        return ResolvedApp(matched_name=best_key, target=index[best_key],
                           kind="desktop", source="desktop")
    return None


def resolve_app(name: str) -> Optional[ResolvedApp]:
    """Найти приложение по произвольному имени пользователя (любой установленный софт)."""
    normalized = _normalize(name)
    if not normalized:
        return None

    alias = ALIASES.get(normalized)
    search_name = alias or normalized

    if not IS_WINDOWS:
        # На Linux алиасы вида «блокнот» → «notepad.exe» бессмысленны, поэтому
        # ищем и по исходному имени тоже: подписи в меню там свои.
        return _resolve_linux(search_name) or _resolve_linux(normalized)

    # 1. Точное совпадение в App Paths (быстро, надёжно для консольных/классических программ)
    path = _resolve_app_paths(normalized) or (_resolve_app_paths(alias) if alias else None)
    if path:
        return ResolvedApp(matched_name=search_name, target=path, kind="path",
                            source="app_paths" if not alias else "alias_app_paths")

    startapps = _get_startapps_index()
    shortcuts = _get_shortcut_index()

    # 2. Точное совпадение в каталоге Windows (Get-StartApps — самый полный источник).
    #
    # Проверяются ОБА варианта: и алиас, и то, что сказал пользователь. Раньше
    # алиас подменял исходное имя целиком, и это мешало: «калькулятор» уходил
    # искаться как «calculator», а в русской Windows приложение подписано
    # «Калькулятор» — совпадения не находилось ни по одному источнику. Алиас
    # должен дополнять запрос, а не вытеснять его.
    exact_candidates = []
    for base in (search_name, normalized):
        for variant in _search_variants(base):
            if variant not in exact_candidates:
                exact_candidates.append(variant)

    for candidate in exact_candidates:
        if candidate in startapps:
            return ResolvedApp(matched_name=candidate, target=startapps[candidate],
                               kind="appid", source="startapps")
        if candidate in shortcuts:
            return ResolvedApp(matched_name=candidate, target=shortcuts[candidate],
                               kind="path", source="shortcut")

    # 3. Нечёткое совпадение по объединённому каталогу (startapps приоритетнее при равном скоре)
    best_key, best_score, best_pool = None, 0.0, None
    candidates = exact_candidates
    for candidate in candidates:
        for key in startapps:
            score = _similarity(candidate, key)
            if score > best_score:
                best_score, best_key, best_pool = score, key, "startapps"
        for key in shortcuts:
            score = _similarity(candidate, key)
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
            "error": (
                f'Не нашёл установленное приложение «{name}» — ни в каталоге Windows, '
                'ни в App Paths, ни среди ярлыков меню "Пуск".'
                if IS_WINDOWS else
                f'Не нашёл установленное приложение «{name}» среди .desktop-файлов '
                '(/usr/share/applications, ~/.local/share/applications, flatpak, snap).'
            ),
        }

    try:
        if resolved.kind == "desktop":
            _launch_desktop_entry(resolved.target)
        elif resolved.kind == "appid":
            os.startfile(f"shell:appsFolder\\{resolved.target}")
        elif resolved.target.lower().endswith(".lnk"):
            # os.startfile сам разворачивает .lnk в целевую программу — как двойной клик.
            os.startfile(resolved.target)
        else:
            subprocess.Popen([resolved.target], shell=False)
        return {"success": True, "matched_name": resolved.matched_name, "source": resolved.source, "error": None}
    except Exception as e:
        return {"success": False, "matched_name": resolved.matched_name, "source": resolved.source, "error": str(e)}
