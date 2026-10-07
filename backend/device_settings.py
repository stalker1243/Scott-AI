"""
Какое устройство использовать для распознавания и синтеза речи.

Раньше выбор был только в .env, а логика продублирована в двух местах — в
main.py для Whisper и в silero_tts.py для Silero. Обычный пользователь
текстовые файлы не открывает, поэтому выбор переехал сюда и стал доступен из
Настроек лаунчера.

Порядок приоритетов, от старшего к младшему:

1. Переменная окружения (WHISPER_DEVICE / SILERO_DEVICE). Явное указание в
   .env всегда сильнее: если человек прописал его руками, значит на то была
   причина, и кнопка в интерфейсе не должна это молча переигрывать.
2. Выбор, сохранённый через интерфейс (data/device_config.json).
3. Автоматический выбор: видеокарта, если она доступна, иначе процессор.

Смысл ручного переключения не в тонкой настройке, а в аварийном выходе:
видеокарта может быть занята игрой, драйвер — сбоить, а torch — оказаться
собранным без CUDA. Разница по скорости при этом огромная (на процессоре
Whisper распознаёт короткую фразу около 6.6 с, на видеокарте — доли секунды),
поэтому по умолчанию всегда выбирается автоматика.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List

try:
    from .storage import atomic_write_text
except ImportError:
    from storage import atomic_write_text

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "device_config.json"

VALID_CHOICES = ("auto", "cuda", "rocm", "mps", "cpu")
_config_lock = threading.RLock()

# Движки, умеющие считать на графике Apple.
#
# Silero — это обычный PyTorch, и Metal ему доступен. А вот faster-whisper
# построен на CTranslate2, который Metal не поддерживает вовсе: там остаётся
# процессор, и просьбу о графике для него придётся вежливо не выполнить.
MPS_CAPABLE = ("silero",)

# Какому движку какая переменная окружения соответствует.
ENV_VARS = {
    "whisper": "WHISPER_DEVICE",
    "silero": "SILERO_DEVICE",
}

# Функции сброса моделей: движки регистрируют их здесь, чтобы после смены
# устройства модель перезагрузилась на новом. Без этого переключение вступало
# бы в силу только после перезапуска backend.
_reset_hooks: List = []


def register_reset_hook(fn) -> None:
    """Движок сообщает, как сбросить свою загруженную модель."""
    if fn not in _reset_hooks:
        _reset_hooks.append(fn)


def reset_loaded_models() -> None:
    """Выгрузить модели, чтобы они поднялись заново на выбранном устройстве."""
    for hook in list(_reset_hooks):
        try:
            hook()
        except Exception as e:
            print(f"⚠️ Не удалось выгрузить модель при смене устройства: {e}")


def _load_config() -> Dict[str, str]:
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in ENV_VARS and v in VALID_CHOICES}
    except Exception:
        # Испорченный файл не повод падать при старте: вернёмся к автоматике.
        pass
    return {}


def _save_config(config: Dict[str, str]) -> None:
    atomic_write_text(CONFIG_PATH, json.dumps(config, ensure_ascii=False, indent=2))


def rocm_build() -> bool:
    """HIP builds reuse torch.cuda; its name alone does not identify NVIDIA."""
    try:
        import torch
        return bool(getattr(getattr(torch, 'version', None), 'hip', None))
    except Exception:
        return False


def rocm_available() -> bool:
    try:
        import torch
        return rocm_build() and bool(torch.cuda.is_available())
    except Exception:
        return False


def cuda_available() -> bool:
    try:
        import torch

        return not rocm_build() and bool(torch.cuda.is_available())
    except Exception:
        return False


def mps_available() -> bool:
    """
    Доступна ли графика Apple (Metal Performance Shaders).

    Есть на машинах с процессорами Apple — с 2020 года это все новые Mac. На
    прежних, с процессорами Intel, ответ отрицательный, и работа идёт на
    процессоре.
    """
    try:
        import torch

        return bool(torch.backends.mps.is_available())
    except Exception:
        # На torch без поддержки Metal самого атрибута может не быть — это не
        # ошибка, а просто «нет».
        return False


def get_choice(engine: str) -> str:
    """Что выбрано для движка: auto, cuda или cpu (без учёта того, что доступно)."""
    forced = os.getenv(ENV_VARS.get(engine, ""), "").strip().lower()
    if forced in VALID_CHOICES:
        choice = forced
    else:
        with _config_lock:
            choice = _load_config().get(engine, "auto")
    # Existing HIP users may have set the PyTorch device spelling "cuda".
    return 'rocm' if choice == 'cuda' and rocm_build() else choice


def is_locked_by_env(engine: str) -> bool:
    """Задано ли устройство переменной окружения — тогда кнопки в интерфейсе бессильны."""
    return os.getenv(ENV_VARS.get(engine, ""), "").strip().lower() in VALID_CHOICES


def resolve_device(engine: str) -> str:
    """
    Устройство, на котором движок должен работать прямо сейчас.

    Просьба о видеокарте, которой нет, молча приводит к процессору: падать
    из-за настройки, которую человек мог поставить давно и на другой машине,
    неправильно.
    """
    choice = get_choice(engine)
    if choice == "cpu":
        return "cpu"

    if choice == "cuda":
        return "cuda" if cuda_available() else "cpu"

    if choice == 'rocm':
        # torch.device('rocm') is invalid. AMD HIP intentionally uses 'cuda'.
        return 'cuda' if rocm_available() else 'cpu'

    if choice == "mps":
        return "mps" if engine in MPS_CAPABLE and mps_available() else "cpu"

    # Автоматика: NVIDIA CUDA, AMD ROCm/HIP, Apple Metal, затем процессор.
    #
    # Порядок не спорный — на одной машине доступно что-то одно. Важнее другое:
    # на Mac процессор для синтеза заметно медленнее, а Metal там есть у всех
    # машин с процессорами Apple, и не пользоваться им значило бы отдать
    # человеку заведомо худшую работу без причины.
    if cuda_available():
        return "cuda"
    if rocm_available():
        return 'cuda'
    if engine in MPS_CAPABLE and mps_available():
        return "mps"
    return "cpu"


def set_choice(engine: str, choice: str) -> Dict:
    """Сохранить выбор и выгрузить модели, чтобы он вступил в силу сразу."""
    if engine not in ENV_VARS:
        return {"success": False, "message": f"Неизвестный движок: {engine}"}
    if choice not in VALID_CHOICES:
        return {"success": False, "message": f"Допустимо только: {', '.join(VALID_CHOICES)}"}

    if is_locked_by_env(engine):
        return {
            "success": False,
            "message": (
                f"Устройство задано в .env через {ENV_VARS[engine]} — "
                "уберите переменную, чтобы управлять выбором отсюда"
            ),
        }

    if choice == "cuda" and not cuda_available():
        return {"success": False, "message": "Видеокарта NVIDIA недоступна: CUDA не найдена"}

    if choice == 'rocm' and not rocm_available():
        return {'success': False, 'message': 'AMD ROCm/HIP недоступен. Нужны совместимая видеокарта, драйвер AMD и сборка PyTorch для ROCm. Подробности: docs/amd-support.md.'}

    if choice == "mps":
        if engine not in MPS_CAPABLE:
            return {
                "success": False,
                "message": "Распознавание речи на графике Apple не работает — "
                           "библиотека, которая его считает, поддерживает только процессор",
            }
        if not mps_available():
            return {"success": False, "message": "Графика Apple недоступна: Metal не найден"}

    try:
        with _config_lock:
            config = _load_config()
            config[engine] = choice
            _save_config(config)
    except OSError as e:
        return {"success": False, "message": f"Не удалось сохранить выбор: {e}"}

    reset_loaded_models()

    return {
        "success": True,
        "engine": engine,
        "choice": choice,
        "device": resolve_device(engine),
        "message": "Модели перезагрузятся на выбранном устройстве при следующем обращении",
    }


def device_label(device: str) -> str:
    return {'cpu': 'процессор', 'mps': 'графика Apple (Metal)',
            'cuda': 'AMD (ROCm/HIP)' if rocm_build() else 'NVIDIA (CUDA)'}.get(device, device)


def device_options(engine: str) -> List[Dict]:
    return [
        {'id': 'auto', 'title': 'Авто', 'available': True},
        {'id': 'cuda', 'title': 'NVIDIA', 'available': cuda_available()},
        {'id': 'rocm', 'title': 'AMD', 'available': rocm_available()},
        *([{'id': 'mps', 'title': 'Apple', 'available': mps_available()}] if engine in MPS_CAPABLE else []),
        {'id': 'cpu', 'title': 'Процессор', 'available': True},
    ]


def describe() -> Dict:
    """Выбор, устройство для загрузки моделей и доступные ускорители."""
    return {
        "cuda_available": cuda_available(),
        'rocm_available': rocm_available(),
        'rocm_build': rocm_build(),
        'mps_available': mps_available(),
        "engines": {
            engine: {
                "choice": get_choice(engine),
                "device": resolve_device(engine),
                'device_label': device_label(resolve_device(engine)),
                'backend': ('rocm' if rocm_build() else 'cuda') if resolve_device(engine) == 'cuda' else resolve_device(engine),
                'options': device_options(engine),
                "locked_by_env": is_locked_by_env(engine),
                "env_var": ENV_VARS[engine],
            }
            for engine in ENV_VARS
        },
    }
