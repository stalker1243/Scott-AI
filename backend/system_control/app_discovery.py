"""
Авто-обнаружение приложений в Windows.

Цель: запускать программы по "человеческому имени", без жёстких путей.

Источники:
- PATH (shutil.which)
- Реестр: App Paths (HKLM/HKCU) — часто содержит пути к exe

Важно: без агрессивного сканирования диска (это долго и небезопасно).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, List
import os
import re
import shutil
from pathlib import Path


@dataclass
class AppMatch:
    name: str
    command: str  # что передать в subprocess.Popen / os.startfile
    source: str


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def find_app_command(query: str) -> Optional[AppMatch]:
    """
    Возвращает команду запуска для приложения по названию.
    Пример query: "google chrome", "chrome", "notepad", "discord"
    """
    q = _norm(query)
    if not q:
        return None

    # Частые алиасы
    aliases: Dict[str, str] = {
        "гугл хром": "chrome",
        "google chrome": "chrome",
        "хром": "chrome",
        "браузер": "msedge",
        "edge": "msedge",
        "проводник": "explorer",
        "explorer": "explorer",
        "блокнот": "notepad",
        "notepad": "notepad",
        "калькулятор": "calc",
        "vscode": "code",
        "visual studio code": "code",
        "код": "code",
        "дискорд": "discord",
        "discord": "discord",
        "телеграм": "telegram",
        "telegram": "telegram",
        "стим": "steam",
        "steam": "steam",
        "обс": "obs64",
        "obs": "obs64",
    }
    exe_name = aliases.get(q, q)

    # 1) PATH
    path_hit = shutil.which(exe_name) or shutil.which(f"{exe_name}.exe")
    if path_hit:
        return AppMatch(name=query, command=path_hit, source="PATH")

    # 2) Реестр App Paths
    reg = _find_in_app_paths_registry(exe_name)
    if reg:
        return AppMatch(name=query, command=reg, source="Registry App Paths")

    # 3) Для Chrome - поиск в стандартных местах установки
    if exe_name == "chrome" or "chrome" in q:
        chrome_path = _find_chrome_in_standard_locations()
        if chrome_path:
            return AppMatch(name=query, command=chrome_path, source="Standard Locations")

    # 4) Ярлыки (Рабочий стол, Пуск)
    shortcut = _find_in_shortcuts(q)
    if shortcut:
        return shortcut

    return None


def _find_in_shortcuts(q_norm: str) -> Optional[AppMatch]:
    """
    Ищет приложение по ярлыкам .lnk:
    1) Desktop пользователя
    2) Public Desktop
    3) Start Menu (пользователь)
    4) Start Menu (общий)
    """
    if os.name != "nt":
        return None

    desktop_user = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    desktop_public = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Desktop"

    start_user = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_common = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    roots = [desktop_user, desktop_public, start_user, start_common]

    words = [w for w in q_norm.split(" ") if w]
    if not words:
        return None

    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*.lnk"):
                name = _norm(p.stem)
                if all(w in name for w in words):
                    target = _resolve_lnk_target(p)
                    if target:
                        return AppMatch(name=p.stem, command=target, source=f"Shortcut target ({root.name})")
                    return AppMatch(name=p.stem, command=str(p), source=f"Shortcut ({root.name})")
        except Exception:
            continue

    return None


def _resolve_lnk_target(path: Path) -> Optional[str]:
    """
    Попытка получить TargetPath .lnk без внешних зависимостей.
    В этом проекте держим нулевую зависимость: если COM недоступен — просто возвращаем None.
    """
    return None


def _find_in_app_paths_registry(exe_name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import winreg
    except Exception:
        return None

    candidates = [exe_name, f"{exe_name}.exe"]
    # Для Chrome также ищем "Google Chrome" и "chrome.exe"
    if exe_name == "chrome":
        candidates.extend(["Google Chrome", "Google Chrome.exe", "chrome.exe"])

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for root, base in roots:
        for cand in candidates:
            key_path = base + "\\" + cand
            try:
                with winreg.OpenKey(root, key_path) as k:
                    # (Default) обычно содержит полный путь к exe
                    val, _ = winreg.QueryValueEx(k, None)
                    if isinstance(val, str) and val:
                        # Проверяем, что путь существует
                        if os.path.exists(val):
                            return val
            except OSError:
                continue
            except Exception:
                continue

    return None


def _find_chrome_in_standard_locations() -> Optional[str]:
    """Поиск Google Chrome в стандартных местах установки Windows."""
    if os.name != "nt":
        return None

    from pathlib import Path

    # Стандартные пути установки Chrome
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))

    chrome_paths = [
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]

    for path in chrome_paths:
        if path.exists() and path.is_file():
            return str(path)

    return None


def scan_installed_apps(limit: int = 256) -> List[AppMatch]:
    """
    Возвращает список установленных приложений (по данным реестра App Paths).

    Это быстрый и безопасный способ получить "короткий" список программ без
    полного сканирования всего диска.
    """
    apps: Dict[str, AppMatch] = {}

    if os.name != "nt":
        return []

    try:
        import winreg
    except Exception:
        return []

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for root, base in roots:
        try:
            with winreg.OpenKey(root, base) as key:
                index = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(key, sub_name) as sub:
                            val, _ = winreg.QueryValueEx(sub, None)
                            if isinstance(val, str) and val and os.path.exists(val):
                                # Используем имя без расширения как "человекочитаемое"
                                pretty_name = os.path.splitext(sub_name)[0]
                                if pretty_name.lower() not in apps:
                                    apps[pretty_name.lower()] = AppMatch(
                                        name=pretty_name,
                                        command=val,
                                        source="Registry App Paths",
                                    )
                    except OSError:
                        continue
                    except Exception:
                        continue
        except OSError:
            continue
        except Exception:
            continue

    # Возвращаем первые N приложений, отсортированных по имени
    result = sorted(apps.values(), key=lambda a: a.name.lower())
    if limit and limit > 0:
        result = result[:limit]
    return result

