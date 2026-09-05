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

import os
import shutil
import subprocess
import sys
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
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        return False


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
        _report(progress, "Скачиваю torch — это самая долгая часть, несколько минут…", 0.1)
        result = subprocess.run(
            [executable, "-m", "pip", "install", "--no-warn-script-location", *torch_args],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            step.error = f"не удалось поставить torch: {result.stderr[-400:]}"
            return step

        _report(progress, "Ставлю остальные библиотеки…", 0.6)
        result = subprocess.run(
            [executable, "-m", "pip", "install", "--no-warn-script-location", "-r", str(requirements)],
            capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            step.error = f"не удалось поставить зависимости: {result.stderr[-400:]}"
            return step

    except subprocess.TimeoutExpired:
        step.error = "установка затянулась дольше часа — вероятно, оборвалась сеть"
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


if __name__ == "__main__":
    # Запуск из установщика: печатаем ход работы в консоль.
    outcome = prepare()
    if not outcome.done:
        print(f"ОШИБКА: {outcome.error}", file=sys.stderr)
        sys.exit(1)
