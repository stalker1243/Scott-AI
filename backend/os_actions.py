"""
Действия в операционной системе — в одном месте и на всех трёх платформах.

Раньше ветки `if platform.system() == 'Windows'` были рассыпаны по четырём
модулям, причём Linux-варианты писались вслепую и половина из них на живых
дистрибутивах не работает: `amixer set Master 5%+` ничего не меняет там, где
звуком заведует PipeWire, а `xdotool key XF86MonBrightnessUp` требует X11 и
оконного менеджера, который эту клавишу обрабатывает.

Здесь для каждого действия перечислены несколько способов, и выбирается первый
доступный в системе. Так одна и та же команда «сделай громче» работает и на
PipeWire, и на PulseAudio, и на голом ALSA.

**Проверено вживую только на Windows.** Linux-ветки написаны по документации
инструментов и покрыты тестами на выбор команды, но подтвердить, что громкость
действительно меняется в конкретном дистрибутиве, может только запуск там.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence

WINDOWS = "Windows"
MACOS = "Darwin"
LINUX = "Linux"

TIMEOUT = 10


def current_os() -> str:
    return platform.system()


def is_windows() -> bool:
    return current_os() == WINDOWS


def find_tool(*candidates: str) -> Optional[str]:
    """Первый из перечисленных инструментов, который есть в системе."""
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def _run(command: Sequence[str]) -> Dict:
    """Выполнить команду и вернуть единообразный результат."""
    try:
        result = subprocess.run(list(command), capture_output=True, text=True, timeout=TIMEOUT)
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip()}
        return {"success": False, "error": (result.stderr or result.stdout).strip() or f"код возврата {result.returncode}"}
    except FileNotFoundError:
        return {"success": False, "error": f"Не найдена программа: {command[0]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Команда выполнялась слишком долго"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== Громкость ====================
#
# Порядок кандидатов на Linux не случаен: wpctl — родной инструмент PipeWire,
# который сегодня стоит в большинстве дистрибутивов; pactl работает и с
# PulseAudio, и с PipeWire через слой совместимости; amixer остаётся последним
# рубежом для систем с голым ALSA.

def volume_command(direction: str) -> Optional[List[str]]:
    """Команда изменения громкости или None, если подходящего инструмента нет."""
    step_up = direction == "up"

    if is_windows():
        # nircmd умеет менять громкость точно, но он есть не у всех; без него
        # шлём мультимедийную клавишу через PowerShell — её понимает сам Windows.
        if find_tool("nircmd"):
            return ["nircmd", "changesysvolume", "2000" if step_up else "-2000"]
        key = "[char]175" if step_up else "[char]174"
        return [
            "powershell", "-NoProfile", "-Command",
            f"(New-Object -ComObject WScript.Shell).SendKeys({key})",
        ]

    if current_os() == MACOS:
        delta = "+10" if step_up else "-10"
        return [
            "osascript", "-e",
            f"set volume output volume (output volume of (get volume settings) {delta})",
        ]

    tool = find_tool("wpctl", "pactl", "amixer")
    if tool == "wpctl":
        return ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+" if step_up else "5%-"]
    if tool == "pactl":
        return ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%" if step_up else "-5%"]
    if tool == "amixer":
        return ["amixer", "-q", "set", "Master", "5%+" if step_up else "5%-"]
    return None


def change_volume(direction: str) -> Dict:
    command = volume_command(direction)
    if command is None:
        return {
            "success": False,
            "error": "Не нашёл, чем управлять звуком. Установите wpctl (PipeWire), pactl или amixer",
        }
    return _run(command)


# ==================== Яркость ====================

def brightness_command(direction: str) -> Optional[List[str]]:
    """
    Команда изменения яркости.

    На Linux это работает только для встроенных экранов ноутбуков: у настольных
    мониторов яркость живёт в самом мониторе и меняется по DDC/CI, для чего
    нужен отдельный инструмент (ddcutil) и права на шину I2C.
    """
    step_up = direction == "up"

    if is_windows():
        sign = "+" if step_up else "-"
        return [
            "powershell", "-NoProfile", "-Command",
            "$b=(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness;"
            "$m=Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods;"
            f"$m.WmiSetBrightness(1,[Math]::Max(0,[Math]::Min(100,$b{sign}10)))",
        ]

    if current_os() == MACOS:
        key = "144" if step_up else "145"
        return ["osascript", "-e", f'tell application "System Events" to key code {key}']

    tool = find_tool("brightnessctl", "light")
    if tool == "brightnessctl":
        return ["brightnessctl", "set", "10%+" if step_up else "10%-"]
    if tool == "light":
        return ["light", "-A" if step_up else "-U", "10"]
    return None


def change_brightness(direction: str) -> Dict:
    command = brightness_command(direction)
    if command is None:
        return {
            "success": False,
            "error": "Не нашёл, чем управлять яркостью. Установите brightnessctl или light",
        }
    return _run(command)


# ==================== Питание ====================
#
# На Linux намеренно используется systemctl, а не `sudo shutdown`: systemctl
# спрашивает разрешение через polkit, который в обычной пользовательской сессии
# выключение и перезагрузку разрешает без пароля. Вариант с sudo просто завис
# бы, ожидая ввода пароля, которого никто не увидит.

def power_command(action: str) -> Optional[List[str]]:
    """action: sleep | restart | shutdown."""
    if is_windows():
        if action == "sleep":
            return ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        if action == "restart":
            return ["shutdown", "/r", "/t", "30", "/c", "Перезагрузка инициирована Scott"]
        if action == "shutdown":
            return ["shutdown", "/s", "/t", "30", "/c", "Выключение инициировано Scott"]
        return None

    if current_os() == MACOS:
        verbs = {"sleep": "sleep", "restart": "restart", "shutdown": "shut down"}
        verb = verbs.get(action)
        return ["osascript", "-e", f'tell application "System Events" to {verb}'] if verb else None

    if find_tool("systemctl"):
        verbs = {"sleep": "suspend", "restart": "reboot", "shutdown": "poweroff"}
        verb = verbs.get(action)
        return ["systemctl", verb] if verb else None

    # Совсем старая система без systemd: shutdown с задержкой в минуту.
    fallback = {"restart": ["shutdown", "-r", "+1"], "shutdown": ["shutdown", "-h", "+1"]}
    return fallback.get(action)


def power_action(action: str) -> Dict:
    command = power_command(action)
    if command is None:
        return {"success": False, "error": f"Не знаю, как выполнить «{action}» на этой системе"}
    return _run(command)


# ==================== Папки пользователя ====================
#
# «Открой загрузки» — просьба про папку, а не про программу с таким названием.
# Раньше такие фразы уходили в поиск приложений и заканчивались
# бесполезным «Не нашёл установленное приложение „папку загрузки“».
#
# Имён у одной и той же папки много: человек говорит «загрузки», «скачанные»,
# «downloads» — всё это один каталог.

# Слова, которые почти наверняка означают именно папку: приложений с такими
# названиями не бывает.
ALWAYS_FOLDER = {
    "downloads": ("загрузки", "загрузку", "загрузка", "скачанные", "скачивания", "downloads"),
    "desktop": ("рабочий стол", "рабочем столе", "десктоп", "desktop"),
    "home": ("домашняя папка", "домашнюю папку", "домашняя директория", "home"),
}

# А эти совпадают с названиями приложений: «Фотографии» и «Музыка» есть в меню
# Пуск, и на просьбу «открой фотографии» человек чаще ждёт программу. Такие
# слова считаются папкой, только если сказано слово «папка» — иначе фраза
# уходит в обычный поиск приложений.
FOLDER_IF_EXPLICIT = {
    "documents": ("документы", "документами", "documents"),
    "pictures": ("изображения", "картинки", "фотографии", "фото", "pictures"),
    "music": ("музыка", "музыку", "музыкой", "music", "аудио"),
    "videos": ("видео", "фильмы", "videos", "movies"),
}

FOLDER_ALIASES = {**ALWAYS_FOLDER, **FOLDER_IF_EXPLICIT}

# Английские имена каталогов на Windows и ключи xdg на Linux.
_WINDOWS_FOLDERS = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}

_XDG_KEYS = {
    "downloads": "DOWNLOAD",
    "documents": "DOCUMENTS",
    "desktop": "DESKTOP",
    "pictures": "PICTURES",
    "music": "MUSIC",
    "videos": "VIDEOS",
}


def match_folder(text: str) -> Optional[str]:
    """
    Узнать в тексте название стандартной папки.

    Спорные слова («фотографии», «музыка») распознаются только вместе со словом
    «папка»: приложения с такими именами есть в меню Пуск, и на просьбу «открой
    фотографии» человек скорее ждёт программу, а не каталог. Однозначные
    («загрузки», «рабочий стол») срабатывают сразу.
    """
    lowered = text.lower().strip()
    explicit = "папк" in lowered or "директор" in lowered

    for key, names in ALWAYS_FOLDER.items():
        if any(name in lowered for name in names):
            return key

    if explicit:
        for key, names in FOLDER_IF_EXPLICIT.items():
            if any(name in lowered for name in names):
                return key

    return None


def user_folder(key: str) -> Optional[str]:
    """
    Путь к стандартной папке пользователя.

    На Linux сначала спрашиваем у xdg-user-dir: в локализованной системе папка
    может называться «Загрузки», и слепое ~/Downloads указало бы в пустоту.
    """
    home = str(Path.home())
    if key == "home":
        return home

    if is_windows():
        name = _WINDOWS_FOLDERS.get(key)
        return os.path.join(home, name) if name else None

    if current_os() == LINUX and find_tool("xdg-user-dir"):
        xdg_key = _XDG_KEYS.get(key)
        if xdg_key:
            result = _run(["xdg-user-dir", xdg_key])
            path = result.get("output", "").strip()
            if result["success"] and path and path != home:
                return path

    name = _WINDOWS_FOLDERS.get(key)
    return os.path.join(home, name) if name else None


def open_user_folder(key: str) -> Dict:
    """Открыть стандартную папку в файловом менеджере системы."""
    path = user_folder(key)
    if not path:
        return {"success": False, "error": f"Не знаю, где находится «{key}»"}
    if not os.path.isdir(path):
        return {"success": False, "error": f"Папка не найдена: {path}"}
    return open_path(path)


# ==================== Открытие файлов и ссылок ====================

def open_path(path: str) -> Dict:
    """Открыть файл или папку тем, чем система открывает такие вещи по умолчанию."""
    target = Path(path).expanduser()
    if not target.exists():
        return {"success": False, "error": f"Не найдено: {target}"}

    if is_windows():
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
            return {"success": True, "output": str(target)}
        except OSError as e:
            return {"success": False, "error": str(e)}

    opener = "open" if current_os() == MACOS else find_tool("xdg-open", "gio")
    if opener is None:
        return {"success": False, "error": "Не нашёл xdg-open — установите xdg-utils"}
    command = [opener, "open", str(target)] if opener == "gio" else [opener, str(target)]
    return _run(command)


def open_url(url: str) -> Dict:
    """Ссылку открывает браузер по умолчанию — webbrowser справляется на всех системах."""
    try:
        webbrowser.open(url)
        return {"success": True, "output": url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def shell_command(command: str) -> List[str]:
    """
    Как выполнить произвольную команду оболочки на этой системе.

    На Windows это PowerShell, на остальных — bash. Вызывающий код обязан
    проверять права: сюда попадает то, что пользователь произнёс вслух.
    """
    if is_windows():
        return ["powershell", "-NoProfile", "-Command", command]
    return ["/bin/bash", "-c", command]


def describe_capabilities() -> Dict:
    """
    Что из управления железом доступно на этой машине.

    Показывается в диагностике: на Linux без brightnessctl яркость не изменить
    вовсе, и лучше сказать об этом прямо, чем молча ничего не делать.
    """
    return {
        "os": current_os(),
        "громкость": bool(volume_command("up")),
        "яркость": bool(brightness_command("up")),
        "питание": bool(power_command("shutdown")),
        "инструменты": {
            "звук": find_tool("wpctl", "pactl", "amixer", "nircmd"),
            "яркость": find_tool("brightnessctl", "light"),
            "открытие_файлов": "startfile" if is_windows() else find_tool("xdg-open", "gio"),
            "systemctl": find_tool("systemctl"),
        },
    }
