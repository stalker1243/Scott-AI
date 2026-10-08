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
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
TORCH_CPU_PIN = 'torch==2.9.1+cpu'
ROCM_INDEX = 'https://stable.repo.amd.com/rocm/whl-next/'
TORCH_ROCM_VERSION = '2.13.0+rocm10.0.0'
ROCM_ARCHITECTURES = ('all', 'gfx908', 'gfx90a', 'gfx942', 'gfx950', 'gfx1030',
    'gfx1100', 'gfx1101', 'gfx1102', 'gfx1103', 'gfx1150', 'gfx1151', 'gfx1152',
    'gfx1153', 'gfx1200', 'gfx1201')


def rocm_requirement(gfx: str = 'all') -> List[str]:
    """Official AMD profile; driver/GPU compatibility is checked separately."""
    if gfx not in ROCM_ARCHITECTURES:
        raise ValueError('Укажите архитектуру вроде gfx1100 или all')
    return ['--index-url', ROCM_INDEX, f'torch[device-{gfx}]=={TORCH_ROCM_VERSION}']

Progress = Callable[[str, float], None]


def _stream_process(command, on_line, timeout, **kwargs) -> int:
    """Enforce a wall-clock deadline even when a child stops producing output."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace', bufsize=1, **kwargs)
    lines = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                line = lines.get(timeout=min(.2, remaining))
            except queue.Empty:
                continue
            if line is None:
                return process.wait(timeout=max(.01, deadline - time.monotonic()))
            on_line(line.strip())
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        reader.join(timeout=2)
        process.stdout.close()


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
    command = [executable, "-m", "pip", "install", "--no-warn-script-location", "--no-cache-dir",
               "--timeout", "30", "--retries", "3", *args]

    with tempfile.TemporaryDirectory(prefix="scott_pip_") as tmp:
        folder = Path(tmp)
        # Своя временная папка нужна не для чистоты, а чтобы было за чем
        # наблюдать: в общем %TEMP% лежит чужое, и размер там ничего не значит.
        env = dict(os.environ, PYTHONUNBUFFERED="1", TMP=tmp, TEMP=tmp, TMPDIR=tmp)

        tail: List[str] = []
        _report(progress, message, start)

        with _DownloadWatcher(folder, progress, message, start, span) as watcher:
            try:
                def consume(line):
                    if not line:
                        return

                    tail.append(line)
                    del tail[:-40]

                    size = _parse_download_size(line)
                    if size:
                        watcher.expected = size

                code = _stream_process(command, consume, timeout, env=env)
            except subprocess.TimeoutExpired:
                return False, "установка затянулась — вероятно, оборвалась сеть"

        return code == 0, "\n".join(tail[-12:])


def models_ready() -> bool:
    try:
        from .model_setup import models_ready as verified
    except ImportError:
        from model_setup import models_ready as verified
    return verified()


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
    if os.getenv('SCOTT_TORCH_BACKEND', '').strip().lower() == 'cpu':
        return ['--index-url', CPU_INDEX, TORCH_CPU_PIN], 'По настройке SCOTT_TORCH_BACKEND=cpu ставлю сборку для процессора.'
    if has_nvidia_gpu():
        name = gpu_name() or "видеокарта NVIDIA"
        return (
            ["--index-url", CUDA_INDEX, TORCH_CUDA],
            f"Нашлась {name} — ставлю сборку с поддержкой видеокарты (около 4 ГБ). "
            "Ускорение речи зависит от карты и драйвера.",
        )

    if sys.platform == "darwin":
        # Та же обычная сборка, но объяснять её надо иначе: видеокарты NVIDIA
        # на Mac не бывает вовсе, и «не найдена» прозвучало бы как поломка. При
        # этом работа не сводится к процессору — графика Apple приходит в
        # обычной сборке с PyPI, и синтез речи ею пользуется.
        return (
            [TORCH_CPU],
            "Ставлю сборку для Mac. Синтез речи пойдёт на графике Apple, "
            "распознавание — на процессоре: библиотека, которая его считает, "
            "графику Apple не поддерживает.",
        )

    try:
        from .gpu_hardware import amd_adapters
    except ImportError:
        from gpu_hardware import amd_adapters
    adapters = amd_adapters()
    if adapters:
        if sys.version_info[:2] < (3, 11) or sys.version_info[:2] > (3, 14):
            return (['--index-url', CPU_INDEX, TORCH_CPU_PIN], 'Найдена AMD, но профиль ROCm требует Python 3.11–3.14. Пока ставлю сборку для процессора; см. docs/amd-support.md.')
        return (rocm_requirement(), f"Найдена {adapters[0]['name']} — ставлю PyTorch для AMD ROCm/HIP. "
                'Для ускорения нужны поддерживаемая карта и совместимый драйвер; см. docs/amd-support.md.')

    return (
        ['--index-url', CPU_INDEX, TORCH_CPU_PIN],
        "Ставлю сборку для процессора без CUDA-зависимостей. "
        "Распознавание речи будет медленнее, чем на поддерживаемой видеокарте.",
    )


def dependencies_ready(python: Optional[str] = None) -> bool:
    """Check the installed requirements separately from downloadable weights."""
    executable = python or sys.executable
    try:
        result = subprocess.run(
            # omegaconf проверяется наравне с остальными: без него падает не
            # импорт backend, а загрузка модели Silero — то есть уже после
            # того, как мастер отчитается об успехе.
            [executable, "-c", "import torch, whisper, fastapi, omegaconf; "
             "from importlib.metadata import version; from packaging.requirements import Requirement; "
             "from pathlib import Path; import os; "
             f"lines = Path({str(Path(__file__).with_name('requirements.txt'))!r}).read_text(encoding='utf-8').splitlines(); "
             "reqs = [Requirement(line) for line in lines if line.strip() and not line.lstrip().startswith('#')]; "
             "assert all(r.specifier.contains(version(r.name), prereleases=True) for r in reqs if r.marker is None or r.marker.evaluate()); "
             "assert os.getenv('SCOTT_TORCH_BACKEND', '').lower() != 'cpu' or (torch.version.cuda is None and torch.version.hip is None); print('ok')"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or "ok" not in result.stdout:
            return False
    except Exception:
        return False

    return True


def is_ready(python: Optional[str] = None) -> bool:
    if not dependencies_ready(python):
        return False
    if python is None or Path(python).absolute() == Path(sys.executable).absolute():
        return models_ready()
    try:
        result = subprocess.run([python, str(Path(__file__).resolve()), '--models-check'],
                                capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def has_pip(executable: str) -> bool:
    """Есть ли pip у этого Python."""
    try:
        result = subprocess.run(
            [executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_pip(executable: str, progress: Optional[Progress] = None) -> Optional[str]:
    """
    Убедиться, что pip есть, и поставить его, если нет.

    Во встроенной сборке Python (той, что лежит в дистрибутиве) pip
    отсутствует — она урезана намеренно. Установщик кладёт рядом с python.exe
    файл get-pip.py; им pip и ставится. Возвращает текст ошибки или None, если
    всё в порядке.
    """
    if has_pip(executable):
        return None

    get_pip = Path(executable).resolve().parent / "get-pip.py"
    if not get_pip.exists():
        return (
            "у этого Python нет pip, и рядом не нашлось get-pip.py — "
            f"ожидался файл {get_pip}"
        )

    _report(progress, "Готовлю установщик пакетов…", 0.03)

    try:
        result = subprocess.run(
            [executable, str(get_pip), "--no-warn-script-location", "--no-cache-dir"],
            capture_output=True, text=True, timeout=900,
            encoding="utf-8", errors="replace",
        )
    except Exception as e:
        return f"не удалось поставить pip: {e}"

    if result.returncode != 0:
        return f"не удалось поставить pip: {(result.stderr or result.stdout)[-300:]}"

    if not has_pip(executable):
        return "pip установился, но не запускается"

    return None


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

    # Без pip дальше делать нечего: во встроенной сборке Python его нет.
    pip_error = ensure_pip(executable, progress)
    if pip_error:
        step.error = pip_error
        return step

    try:
        # Keep a manually configured ROCm wheel even when preparing missing
        # dependencies/models, or running from another Python interpreter.
        probe = subprocess.run([executable, '-c', 'import torch; print(bool(torch.version.hip))'],
            capture_output=True, text=True, timeout=30)
        preserve_rocm = (probe.returncode == 0 and probe.stdout.strip() == 'True'
                         and os.getenv('SCOTT_TORCH_BACKEND', '').strip().lower() != 'cpu')
    except (OSError, subprocess.TimeoutExpired):
        preserve_rocm = False

    try:
        # Доли шкалы поделены по весу: torch — почти четыре гигабайта, всё
        # остальное вместе — меньше сотни мегабайт.
        ok, tail = (True, '') if preserve_rocm else _run_pip(
            executable, torch_args, progress,
            "Скачиваю torch — самая долгая часть, несколько минут…",
            start=0.10, span=0.45,
        )
        if not ok:
            if ROCM_INDEX in torch_args:
                _report(progress, 'Не удалось установить профиль AMD. Ставлю CPU, чтобы Scott мог работать; см. docs/amd-support.md.', 0.45)
                ok, tail = _run_pip(executable,
                    ['--index-url', CPU_INDEX, TORCH_CPU_PIN],
                    progress, 'Ставлю запасную сборку torch для процессора…', start=0.45, span=0.10)
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
    """Relay live byte progress from the selected Python's model worker."""
    executable = python or sys.executable
    step = Step(title="Загрузка моделей")

    try:
        _report(progress, "Готовлю распознавание и локальный голос…", .76)

        def consume(line):
            try:
                event = json.loads(line)
            except ValueError:
                return
            if event.get('type') == 'progress':
                _report(progress, event['message'], event['fraction'])
            elif event.get('type') == 'error':
                step.error = event['message']

        code = _stream_process([executable, '-u', str(Path(__file__).resolve()), '--models', '--json'],
                               consume, 3600, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        if code != 0:
            if not step.error:
                step.error = 'Не удалось подготовить модели. Проверьте интернет и нажмите «Повторить».'
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

    if dependencies_ready(python):
        _report(progress, 'Библиотеки уже установлены. Продолжаю подготовку моделей…', .75)
    else:
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

    try:
        from .model_setup import load_environment, prepare_models, DownloadError
    except ImportError:
        from model_setup import load_environment, prepare_models, DownloadError
    load_environment()

    if '--models-check' in argv:
        return 0 if models_ready() else 2

    if os.name != 'nt' and os.getenv('SCOTT_SETUP_GROUP') == '1' and '--models' not in argv:
        # QProcess owns this child. Give cancellation its entire process group.
        if os.getpgrp() != os.getpid():
            os.setsid()

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

    if '--models' in argv:
        try:
            prepare_models(report)
            outcome = Step(title='Модели', done=True)
        except (DownloadError, ValueError, OSError) as error:
            outcome = Step(title='Модели', error=str(error))
    else:
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
