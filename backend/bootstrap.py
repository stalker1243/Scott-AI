"""
Подготовка машины к работе Scott: зависимости и модели.

Это то, ради чего затевался установщик. Раньше человек должен был сам поставить
Python 3.13, отдельной командой torch нужной сборки, потом .NET — и ни один из
шагов не прощал ошибки. Особенно второй: обычная команда `pip install torch`
ставит сборку для процессора, молча игнорируя видеокарту, и Scott после этого
работает впятеро медленнее без всякого объяснения.

Здесь всё это делается за него: определяется видеокарта, выбирается правильная
сборка, скачиваются модели. Модуль рассчитан на два способа вызова — из
установщика и из лаунчера при первом запуске, — поэтому о ходе работы он
сообщает через callback, а не печатает в консоль, которую всё равно никто не
увидит.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

# Сборка torch с поддержкой видеокарты живёт на отдельном индексе — на обычном
# PyPI её просто нет. Версия CUDA 12.6 выбрана как самая широко поддерживаемая
# драйверами; более новые сборки требуют свежих драйверов, а разница в скорости
# для наших моделей неразличима.
CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_CUDA = "torch==2.9.1+cu126"
TORCH_CPU = "torch"

Progress = Callable[[str, float], None]


@dataclass
class Step:
    """Один шаг подготовки — чтобы лаунчер мог показать, что происходит."""

    title: str
    done: bool = False
    error: str = ""


def _report(progress: Optional[Progress], message: str, fraction: float) -> None:
    if progress:
        try:
            progress(message, fraction)
        except Exception:
            pass
    else:
        print(f"[{fraction * 100:3.0f}%] {message}")


# pip печатает размер файла перед загрузкой: «Downloading torch-….whl (3.9 GB)».
# Это единственное надёжное число: сам прогресс-бар без терминала печатается
# одной итоговой строкой, когда всё уже скачано.
PIP_SIZE = re.compile(r"Downloading\s+\S+\s+\(([\d.]+)\s*(kB|MB|GB)\)", re.IGNORECASE)

UNITS = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}


def _parse_download_size(line: str) -> Optional[float]:
    """Размер скачиваемого файла в байтах, если pip его назвал."""
    match = PIP_SIZE.search(line)
    if not match:
        return None
    try:
        return float(match.group(1)) * UNITS[match.group(2).lower()]
    except (ValueError, KeyError):
        return None


def _folder_size(path: Path) -> int:
    """Сколько байт лежит в папке. Ошибки игнорируются: файлы могут исчезать
    прямо во время обхода — pip их удаляет, закончив с ними."""
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def _human(size: float) -> str:
    """«820 МБ», «3.9 ГБ» — для строки состояния."""
    if size >= UNITS["gb"]:
        return f"{size / UNITS['gb']:.1f} ГБ"
    return f"{size / UNITS['mb']:.0f} МБ"


class _DownloadWatcher:
    """
    Наблюдатель за временной папкой pip.

    Считать прогресс по выводу pip нельзя, а вот файл, который он туда кладёт,
    растёт на глазах. Ожидаемый размер сообщает сам pip строкой Downloading —
    до тех пор доля неизвестна, и показывается только объём.
    """

    def __init__(self, folder: Path, progress: Optional[Progress], message: str,
                 start: float, span: float):
        self.folder = folder
        self.progress = progress
        self.message = message
        self.start = start
        self.span = span
        self.expected: Optional[float] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> "_DownloadWatcher":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(0.7):
            size = _folder_size(self.folder)
            if size <= 0:
                continue

            if not self.expected:
                _report(self.progress, f"{self.message} {_human(size)}", self.start)
                continue

            if size >= self.expected:
                # Скачивание кончилось: дальше pip распаковывает архив в ту же
                # папку, и её размер обгоняет размер файла. Показывать «541 МБ
                # из 111 МБ» бессмысленно — говорим, что происходит на самом
                # деле, и держим полосу на месте.
                _report(self.progress, "Распаковываю и устанавливаю…", self.start + self.span)
                continue

            share = size / self.expected
            _report(self.progress, f"{self.message} {_human(size)} из {_human(self.expected)}",
                    self.start + self.span * share)


def _run_pip(
    executable: str,
    args: List[str],
    progress: Optional[Progress],
    message: str,
    start: float,
    span: float,
    timeout: int = 3600,
) -> tuple[bool, str]:
    """
    Запустить pip, показывая, сколько уже скачано.

    Возвращает (успех, последние строки вывода) — хвост нужен для сообщения об
    ошибке: без него человек видит «не удалось поставить torch» и ничего
    больше.
    """
    command = [executable, "-m", "pip", "install", "--no-warn-script-location", *args]

    with tempfile.TemporaryDirectory(prefix="scott_pip_") as tmp:
        folder = Path(tmp)
        # Своя временная папка нужна не для чистоты, а чтобы было за чем
        # наблюдать: в общем %TEMP% лежит чужое, и размер там ничего не значит.
        env = dict(os.environ, PYTHONUNBUFFERED="1", TMP=tmp, TEMP=tmp, TMPDIR=tmp)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

        tail: List[str] = []
        _report(progress, message, start)

        with _DownloadWatcher(folder, progress, message, start, span) as watcher:
            try:
                for line in process.stdout or []:
                    line = line.strip()
                    if not line:
                        continue

                    tail.append(line)
                    del tail[:-40]

                    size = _parse_download_size(line)
                    if size:
                        watcher.expected = size

                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                return False, "установка затянулась — вероятно, оборвалась сеть"

        return process.returncode == 0, "\n".join(tail[-12:])


def models_ready() -> bool:
    """
    Скачаны ли модели речи.

    Проверяются файлы в кэше torch, а не импорт: библиотеки могут стоять, а
    веса — нет, и тогда первая же голосовая команда уходит качать 700 МБ,
    заставляя человека ждать молча.
    """
    cache = Path(os.path.expanduser("~")) / ".cache"
    whisper_model = cache / "whisper" / "small.pt"
    silero = cache / "torch" / "hub" / "snakers4_silero-models_master"
    return whisper_model.exists() and silero.exists()


def has_nvidia_gpu() -> bool:
    """
    Есть ли в машине видеокарта NVIDIA.

    Проверяется до установки torch, поэтому спросить у него нельзя. nvidia-smi
    ставится вместе с драйвером: если он отвечает — карта есть и драйвер жив,
    а это ровно то, что нужно знать перед выбором сборки.
    """
    if not shutil.which("nvidia-smi"):
        return False
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def gpu_name() -> Optional[str]:
    """Название видеокарты — его показывают пользователю при установке."""
    if not has_nvidia_gpu():
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
    except Exception:
        return None


def torch_requirement() -> tuple[List[str], str]:
    """
    Чем ставить torch на этой машине и как это объяснить человеку.

    Возвращает аргументы для pip и понятное описание выбора: пользователь должен
    видеть, почему установка займёт четыре гигабайта или, наоборот, почему
    Scott будет работать медленнее.
    """
    if has_nvidia_gpu():
        name = gpu_name() or "видеокарта NVIDIA"
        return (
            ["--index-url", CUDA_INDEX, TORCH_CUDA],
            f"Нашлась {name} — ставлю сборку с поддержкой видеокарты (около 4 ГБ). "
            "На ней распознавание речи занимает доли секунды вместо шести.",
        )
    return (
        [TORCH_CPU],
        "Видеокарта NVIDIA не найдена — ставлю сборку для процессора. "
        "Scott будет работать, но распознавание речи займёт около шести секунд на фразу.",
    )


def is_ready(python: Optional[str] = None) -> bool:
    """Всё ли уже установлено — чтобы не запускать подготовку повторно."""
    executable = python or sys.executable
    try:
        result = subprocess.run(
            [executable, "-c", "import torch, whisper, fastapi; print('ok')"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or "ok" not in result.stdout:
            return False
    except Exception:
        return False

    # Библиотеки без моделей — ещё не готовность: первая же команда уйдёт
    # качать 700 МБ, и человек будет ждать молча.
    return models_ready()


def install_dependencies(python: Optional[str] = None, progress: Optional[Progress] = None) -> Step:
    """
    Поставить всё, что нужно backend.

    torch ставится отдельно и первым: он самый тяжёлый, и именно на нём проще
    всего ошибиться — поэтому сборка выбирается по факту наличия видеокарты, а
    не по надежде, что пользователь прочитает инструкцию.
    """
    executable = python or sys.executable
    requirements = Path(__file__).resolve().parent / "requirements.txt"

    torch_args, explanation = torch_requirement()
    _report(progress, explanation, 0.05)

    step = Step(title="Установка зависимостей")

    try:
        # Доли шкалы поделены по весу: torch — почти четыре гигабайта, всё
        # остальное вместе — меньше сотни мегабайт.
        ok, tail = _run_pip(
            executable, torch_args, progress,
            "Скачиваю torch — самая долгая часть, несколько минут…",
            start=0.10, span=0.45,
        )
        if not ok:
            step.error = f"не удалось поставить torch: {tail[-400:]}"
            return step

        ok, tail = _run_pip(
            executable, ["-r", str(requirements)], progress,
            "Ставлю остальные библиотеки…",
            start=0.55, span=0.20, timeout=1800,
        )
        if not ok:
            step.error = f"не удалось поставить зависимости: {tail[-400:]}"
            return step

    except Exception as e:
        step.error = str(e)
        return step

    step.done = True
    _report(progress, "Библиотеки установлены", 0.75)
    return step


def download_models(python: Optional[str] = None, progress: Optional[Progress] = None) -> Step:
    """
    Скачать модели распознавания и синтеза заранее.

    Иначе они подтянутся при первой же голосовой команде, и человек прождёт
    минуты, не понимая, что происходит: Whisper «small» весит около 700 МБ,
    Silero — 40 МБ.
    """
    executable = python or sys.executable
    step = Step(title="Загрузка моделей")

    code = (
        "import whisper, torch;"
        "whisper.load_model('small');"
        "torch.hub.load(repo_or_dir='snakers4/silero-models', model='silero_tts',"
        " language='ru', speaker='v4_ru', trust_repo=True)"
    )

    try:
        _report(progress, "Скачиваю модели распознавания и синтеза речи (около 700 МБ)…", 0.8)
        result = subprocess.run(
            [executable, "-c", code],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            step.error = f"не удалось скачать модели: {result.stderr[-400:]}"
            return step
    except subprocess.TimeoutExpired:
        step.error = "загрузка моделей затянулась — вероятно, оборвалась сеть"
        return step
    except Exception as e:
        step.error = str(e)
        return step

    step.done = True
    _report(progress, "Модели загружены", 0.95)
    return step


def prepare(python: Optional[str] = None, progress: Optional[Progress] = None) -> Step:
    """Полная подготовка: зависимости и модели. Возвращает первый неудавшийся шаг."""
    if is_ready(python):
        _report(progress, "Всё уже установлено", 1.0)
        return Step(title="Готово", done=True)

    step = install_dependencies(python, progress)
    if not step.done:
        return step

    step = download_models(python, progress)
    if not step.done:
        return step

    _report(progress, "Scott готов к работе", 1.0)
    return Step(title="Готово", done=True)


def _emit(payload: dict) -> None:
    """Одно событие — одна строка JSON. Читает лаунчер."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    """
    Точка входа для установщика и лаунчера.

    С ключом --json ход работы печатается строками JSON: лаунчеру нужен не
    текст, а доля выполнения, иначе он не сможет показать полосу прогресса.
    Без ключа — обычный человекочитаемый вывод в консоль.
    """
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv

    if "--check" in argv:
        # Быстрая проверка без установки: лаунчер спрашивает, нужен ли мастер.
        ready = is_ready()
        if as_json:
            _emit({"type": "check", "ready": ready, "gpu": gpu_name()})
        else:
            print("готово" if ready else "нужна подготовка")
        return 0 if ready else 2

    def report(message: str, fraction: float) -> None:
        if as_json:
            _emit({"type": "progress", "message": message, "fraction": round(fraction, 4)})
        else:
            print(f"[{fraction * 100:3.0f}%] {message}", flush=True)

    outcome = prepare(progress=report)

    if not outcome.done:
        if as_json:
            _emit({"type": "error", "message": outcome.error})
        else:
            print(f"ОШИБКА: {outcome.error}", file=sys.stderr)
        return 1

    if as_json:
        _emit({"type": "done"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
