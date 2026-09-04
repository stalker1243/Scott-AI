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
from pathlib import Path
from typing import Dict, List

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "device_config.json"

VALID_CHOICES = ("auto", "cuda", "cpu")

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
                return {k: v for k, v in data.items() if v in VALID_CHOICES}
    except Exception:
        # Испорченный файл не повод падать при старте: вернёмся к автоматике.
        pass
    return {}


def _save_config(config: Dict[str, str]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def get_choice(engine: str) -> str:
    """Что выбрано для движка: auto, cuda или cpu (без учёта того, что доступно)."""
    forced = os.getenv(ENV_VARS.get(engine, ""), "").strip().lower()
    if forced in ("cuda", "cpu"):
        return forced
    return _load_config().get(engine, "auto")


def is_locked_by_env(engine: str) -> bool:
    """Задано ли устройство переменной окружения — тогда кнопки в интерфейсе бессильны."""
    return os.getenv(ENV_VARS.get(engine, ""), "").strip().lower() in ("cuda", "cpu")


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
    return "cuda" if cuda_available() else "cpu"


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
        return {"success": False, "message": "Видеокарта недоступна: CUDA не найдена"}

    config = _load_config()
    config[engine] = choice
    try:
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


def describe() -> Dict:
    """Полная картина для интерфейса: что выбрано, что используется, что доступно."""
    return {
        "cuda_available": cuda_available(),
        "engines": {
            engine: {
                "choice": get_choice(engine),
                "device": resolve_device(engine),
                "locked_by_env": is_locked_by_env(engine),
                "env_var": ENV_VARS[engine],
            }
            for engine in ENV_VARS
        },
    }
