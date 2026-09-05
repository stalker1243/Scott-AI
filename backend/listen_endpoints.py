"""
Управление прослушиванием микрофона.

Отдельно от `/speech_to_text`, который принимает готовый файл: здесь Scott
слушает сам и решает, когда к нему обратились.
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import runtime as scott_runtime
    from . import listener as listener_module
except ImportError:
    import runtime as scott_runtime
    import listener as listener_module

router = APIRouter(prefix="/listen", tags=["listen"])


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Прослушивание недоступно: не создан слушатель или нет библиотеки sounddevice",
        },
    )


@router.get("/status")
async def status() -> Dict:
    """
    Слушает ли Scott сейчас и что он слышал.

    Возвращает и уровень фонового шума: если Scott не реагирует, первым делом
    смотрят сюда — при слишком высоком фоне речь не преодолевает порог.
    """
    if scott_runtime.listener is None:
        return {
            "listening": False,
            "available": listener_module.HAS_SOUNDDEVICE,
            "message": "Слушатель не создан",
        }
    return scott_runtime.listener.status()


@router.post("/start")
async def start() -> Dict:
    """Начать слушать микрофон. Команды выполняются только после обращения по имени."""
    if scott_runtime.listener is None:
        return _unavailable()

    result = scott_runtime.listener.start()
    if not result.get("success"):
        return JSONResponse(status_code=503, content=result)
    return {**result, **scott_runtime.listener.status()}


@router.post("/stop")
async def stop() -> Dict:
    """Перестать слушать."""
    if scott_runtime.listener is None:
        return _unavailable()
    return {**scott_runtime.listener.stop(), **scott_runtime.listener.status()}


@router.get("/devices")
async def devices() -> Dict:
    """Микрофоны, доступные в системе, — чтобы выбрать нужный, если их несколько."""
    return {"success": True, "devices": listener_module.list_input_devices()}
