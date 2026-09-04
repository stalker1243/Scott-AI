"""
Настройки, которые пользователь меняет из лаунчера, а не в текстовых файлах.

Пока здесь только выбор устройства для распознавания и синтеза речи — то, что
раньше жило исключительно в .env и потому было недоступно тем, кто .env не
открывает.
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import device_settings
except ImportError:
    import device_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/device")
async def get_device() -> Dict:
    """
    Что выбрано и что используется на самом деле.

    Это разные вещи: при выборе «авто» на машине без видеокарты выбор остаётся
    «auto», а устройством будет «cpu». Лаунчер показывает и то, и другое.
    """
    return {"success": True, **device_settings.describe()}


@router.post("/device")
async def set_device(data: Dict) -> Dict:
    """
    Сменить устройство: {"engine": "whisper"|"silero", "choice": "auto"|"cuda"|"cpu"}.

    Модели после этого выгружаются и поднимаются заново уже на новом
    устройстве — перезапускать backend не нужно. Первое обращение после смены
    поэтому будет дольше обычного: заново идёт загрузка весов.
    """
    engine = (data.get("engine") or "").strip().lower()
    choice = (data.get("choice") or "").strip().lower()

    result = device_settings.set_choice(engine, choice)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)

    return {**result, **device_settings.describe()}
