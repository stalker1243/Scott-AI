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

@router.post("/say")
async def say_as_heard(request: Dict) -> Dict:
    """
    Пропустить фразу так, будто её услышал микрофон.

    Нужно для разбора самого частого вопроса — «слышит, но не отвечает».
    Голосовой путь состоит из полудюжины звеньев: запись, распознавание,
    проверка обращения, исполнение, синтез, воспроизведение. Любое из них
    может молча ничего не сделать, и понять какое, имея только микрофон и
    тишину в ответ, нельзя.

    Здесь первые два звена пропускаются, а остальные проходятся по-настоящему
    — с исполнением команды и ответом вслух. Если отсюда Scott отвечает, а с
    микрофона нет, дело в распознавании; если и отсюда молчит — дальше по
    цепочке.
    """
    if scott_runtime.listener is None:
        return _unavailable()

    text = (request.get("text") or "").strip()
    if not text:
        return {"success": False, "error": "Нужен текст фразы"}

    listener = scott_runtime.listener

    # Тот же путь, которым идут настоящие услышанные фразы.
    listener._dispatch(text)

    состояние = listener.status()

    return {
        "success": True,
        "heard": text,
        "dispatch": состояние.get("last_dispatch"),
        "command": состояние.get("last_command"),
        "error": состояние.get("last_error"),
    }
