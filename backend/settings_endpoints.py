"""
Настройки, которые пользователь меняет из лаунчера, а не в текстовых файлах.

Пока здесь только выбор устройства для распознавания и синтеза речи — то, что
раньше жило исключительно в .env и потому было недоступно тем, кто .env не
открывает.
"""

import asyncio
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
    Что выбрано и на каком устройстве будут загружены модели.

    Это разные вещи: при выборе «авто» на машине без видеокарты выбор остаётся
    «auto», а устройством будет «cpu». После ошибки GPU уже загруженная модель
    может продолжить на CPU; это поле отражает выбор для следующей загрузки.
    """
    return {"success": True, **await asyncio.to_thread(device_settings.describe)}


@router.post("/device")
async def set_device(data: Dict) -> Dict:
    """
    Сменить устройство: engine whisper|silero, choice auto|cuda|rocm|mps|cpu.

    Модели после этого выгружаются и поднимаются заново уже на новом
    устройстве — перезапускать backend не нужно. Первое обращение после смены
    поэтому будет дольше обычного: заново идёт загрузка весов.
    """
    if not isinstance(data.get('engine'), str) or not isinstance(data.get('choice'), str):
        return JSONResponse(status_code=400, content={'success': False, 'message': 'Укажите движок и устройство строками.'})
    engine = data['engine'].strip().lower()
    choice = data['choice'].strip().lower()

    result = await asyncio.to_thread(device_settings.set_choice, engine, choice)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)

    return {**result, **await asyncio.to_thread(device_settings.describe)}
