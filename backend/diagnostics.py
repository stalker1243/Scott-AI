"""
Сбор сведений о работе Scott: что за машина, что в логах, что пошло не так.

Нужно для одной практической цели — чтобы пользователь мог одним действием
собрать всё необходимое и отправить разработчику. Без этого о поломке на чужом
компьютере узнать нечего: «не работает» не отладишь.

Главное требование к этому модулю — НИЧЕГО СЕКРЕТНОГО В ОТЧЁТ. Пользователь
отправляет архив постороннему человеку, и API-ключ внутри означал бы, что мы
своими руками устроили утечку. Поэтому значения переменных окружения не
попадают в отчёт никогда (только имена и признак «задано/пусто»), а весь
текст логов проходит через маскировку.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

# Файлы, которые имеет смысл прикладывать к отчёту. Пути относительные —
# так же они выглядят и внутри архива.
# Журнал лаунчера лежит в папке пользователя, а не рядом с программой: она
# может быть установлена туда, где записывать нельзя. Именно в нём видно
# падения при запуске — те самые случаи, когда «нажимаю ярлык, и ничего».
LAUNCHER_LOG = Path(os.path.expanduser("~")) / "AppData" / "Local" / "ScottAI" / "logs" / "launcher.log"

LOG_FILES = {
    "launcher.log": LAUNCHER_LOG,
    "backend_errors.log": PROJECT_DIR / "backend_errors.log",
    "dangerous_actions.log": BACKEND_DIR / "logs" / "dangerous_actions.log",
    "secure_exec.log": BACKEND_DIR / "logs" / "secure_exec.log",
    "timings.jsonl": BACKEND_DIR / "logs" / "timings.jsonl",
}

# Куда складываются собранные архивы.
REPORTS_DIR = PROJECT_DIR / "reports"

# Что считать секретом. Ключи разных сервисов имеют узнаваемые префиксы, но
# полагаться только на них нельзя: EXECUTE_TOKEN придумывает пользователь и
# выглядеть он может как угодно. Поэтому значения из окружения маскируются
# отдельно, по факту совпадения со строкой (см. mask_secrets).
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gsk_[A-Za-z0-9_-]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE),
]

# Переменные, значения которых секретны по определению.
SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _secret_values() -> List[str]:
    """Текущие значения секретных переменных — их нужно вырезать из логов дословно."""
    values = []
    for name, value in os.environ.items():
        if any(hint in name.upper() for hint in SECRET_ENV_HINTS) and value and len(value) >= 8:
            values.append(value)
    return values


def mask_secrets(text: str) -> str:
    """
    Вырезать из текста всё, что похоже на ключ.

    Сначала подставляются конкретные значения из окружения (самый надёжный
    способ: что бы пользователь ни придумал в качестве EXECUTE_TOKEN, оно
    известно дословно), затем — общие шаблоны известных сервисов на случай,
    если в лог попал чужой ключ или ключ из прошлого запуска.
    """
    for value in _secret_values():
        text = text.replace(value, "***СКРЫТО***")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("***СКРЫТО***", text)
    return text


def collect_system_info() -> Dict:
    """Сведения о машине и окружении: то, что первым делом спрашивают при разборе проблемы."""
    info: Dict = {
        "собрано": datetime.now().isoformat(timespec="seconds"),
        "система": {
            "ос": f"{platform.system()} {platform.release()}",
            "версия_ос": platform.version(),
            "архитектура": platform.machine(),
            "python": sys.version.split()[0],
        },
    }

    try:
        import psutil

        info["железо"] = {
            "ядер_логических": psutil.cpu_count(),
            "ядер_физических": psutil.cpu_count(logical=False),
            "озу_гб": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        }
    except Exception as e:
        info["железо"] = {"ошибка": str(e)}

    info["видеокарта"] = collect_gpu_info()

    versions = {}
    for package in ("torch", "openai-whisper", "fastapi", "numpy", "edge-tts"):
        try:
            from importlib.metadata import version

            versions[package] = version(package)
        except Exception:
            versions[package] = "не установлен"
    info["версии"] = versions

    # Только имена переменных и признак заполненности. Значения не попадают в
    # отчёт ни при каких обстоятельствах.
    env_state = {}
    for name in sorted(os.environ):
        if name.startswith(("WHISPER_", "SILERO_", "TTS_", "BACKEND_", "WARMUP_")) or any(
            hint in name.upper() for hint in SECRET_ENV_HINTS
        ):
            value = os.environ.get(name, "")
            if any(hint in name.upper() for hint in SECRET_ENV_HINTS):
                env_state[name] = "задано" if value else "пусто"
            else:
                env_state[name] = value
    info["настройки"] = env_state

    return info


def collect_gpu_info() -> Dict:
    """
    Что известно про видеокарту и какое устройство реально используется.

    Отдельная функция, потому что это первое, о чём спрашивают при жалобе на
    медленную работу: `pip install torch` ставит сборку для процессора и молча
    игнорирует видеокарту — так Whisper молотил 6.6 секунды вместо долей секунды.
    """
    result: Dict = {"cuda_доступна": False}
    try:
        import torch

        result["torch"] = torch.__version__
        result["сборка_с_cuda"] = "+cu" in torch.__version__
        result["cuda_доступна"] = bool(torch.cuda.is_available())
        if result["cuda_доступна"]:
            result["устройство"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            result["память_гб"] = round(props.total_memory / 1024 ** 3, 1)
        elif not result["сборка_с_cuda"]:
            result["подсказка"] = (
                "Установлена сборка torch для процессора. Видеокарта задействована не будет: "
                "pip install --index-url https://download.pytorch.org/whl/cu126 torch"
            )
    except ImportError:
        result["torch"] = "не установлен"
    except Exception as e:
        result["ошибка"] = str(e)
    return result


def tail_log(name: str, lines: int = 200) -> Dict:
    """Последние строки одного из известных логов, с вырезанными секретами."""
    path = LOG_FILES.get(name)
    if path is None:
        return {"success": False, "message": f"Неизвестный лог: {name}"}
    if not path.exists():
        return {"success": True, "name": name, "lines": [], "message": "Файл ещё не создан"}

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"success": False, "message": f"Не удалось прочитать {name}: {e}"}

    tail = content.splitlines()[-max(1, lines):]
    return {
        "success": True,
        "name": name,
        "size_bytes": path.stat().st_size,
        "lines": [mask_secrets(line) for line in tail],
    }


def _summarise_traceback(block: List[str]) -> str:
    """
    Выжать из трейсбека строку, ради которой его читают.

    Это последняя непустая строка — «ValueError: не найден голос eugene».
    Строки «File ...» полезны при разборе, но в списке из десяти ошибок
    занимают всё место, не отвечая на вопрос «что случилось».
    """
    for line in reversed(block):
        text = line.strip()
        if text and not text.startswith(("File ", "Traceback", "During handling",
                                         "The above exception")):
            return text
    return "Traceback без сообщения"


def recent_errors(limit: int = 50) -> List[Dict]:
    """
    Только ошибки из основного лога — то, что интересно человеку.

    Уровень логирования в проекте DEBUG, и полный файл на сотни килобайт
    читать бессмысленно: там подробности работы COM-объектов и HTTP-запросов.

    Трейсбек сворачивается в одну запись: показывается его последняя строка,
    где тип исключения и сообщение. Раньше в списке было шесть одинаковых
    «Traceback (most recent call last):» — по ним нельзя понять ровно ничего.
    """
    path = LOG_FILES["backend_errors.log"]
    if not path.exists():
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    found: List[Dict] = []
    block: List[str] = []
    block_stamp = ""

    def flush_block() -> None:
        """Закрыть накопленный трейсбек одной записью."""
        nonlocal block, block_stamp
        if block:
            found.append({
                "time": block_stamp,
                "text": mask_secrets(_summarise_traceback(block))[:500],
                "details": mask_secrets("\n".join(block))[:4000],
            })
            block = []
            block_stamp = ""

    for line in content.splitlines():
        stamp_match = re.match(r"^(\d{4}-\d{2}-\d{2} [\d:,]+)", line)
        stamp = stamp_match.group(1) if stamp_match else ""

        if line.lstrip().startswith("Traceback (most recent call last)"):
            flush_block()
            block = [line.strip()]
            block_stamp = stamp
            continue

        if block:
            # Трейсбек продолжается, пока строки идут с отступом или это
            # заголовки вложенных исключений.
            if line.startswith((" ", "\t")) or line.strip().startswith(
                ("During handling", "The above exception")
            ):
                block.append(line.rstrip())
                continue

            # Первая строка без отступа — это и есть само исключение.
            if line.strip():
                block.append(line.strip())
            flush_block()
            continue

        if re.search(r"\b(ERROR|CRITICAL|Exception)\b", line):
            found.append({
                "time": stamp,
                "text": mask_secrets(line.strip())[:500],
                "details": "",
            })

    flush_block()

    # Одинаковые ошибки подряд схлопываем: в логе они повторяются десятками,
    # а человеку важен факт и сколько раз это случилось.
    collapsed: List[Dict] = []
    for entry in found:
        if collapsed and collapsed[-1]["text"] == entry["text"]:
            collapsed[-1]["count"] = collapsed[-1].get("count", 1) + 1
            collapsed[-1]["time"] = entry["time"] or collapsed[-1]["time"]
            continue
        entry["count"] = 1
        collapsed.append(entry)

    return collapsed[-max(1, limit):]


def build_report(note: Optional[str] = None) -> Dict:
    """
    Собрать архив для отправки разработчику.

    Кладём логи (с вырезанными секретами), сведения о машине и, если
    пользователь его написал, описание проблемы своими словами — оно обычно
    полезнее всего остального.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = REPORTS_DIR / f"scott_report_{stamp}.zip"

    system_info = collect_system_info()

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "system_info.json",
                json.dumps(system_info, ensure_ascii=False, indent=2),
            )
            if note:
                archive.writestr("описание_проблемы.txt", note)

            for name, path in LOG_FILES.items():
                if not path.exists():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                archive.writestr(f"logs/{name}", mask_secrets(text))
    except OSError as e:
        return {"success": False, "message": f"Не удалось собрать отчёт: {e}"}

    return {
        "success": True,
        "path": str(archive_path),
        "folder": str(REPORTS_DIR),
        "size_bytes": archive_path.stat().st_size,
        "message": f"Отчёт собран: {archive_path.name}",
    }
