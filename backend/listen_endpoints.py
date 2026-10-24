"""
Управление прослушиванием микрофона.

Отдельно от `/speech_to_text`, который принимает готовый файл: здесь Scott
слушает сам и решает, когда к нему обратились.
"""

from typing import Dict
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import runtime as scott_runtime
except ImportError:
    import runtime as scott_runtime
try:
    if __package__:
        from . import listener as listener_module
    else:
        import listener as listener_module
except (ImportError, OSError):
    # Keep status/history/control routes available on a partial audio install.
    listener_module = None

router = APIRouter(prefix="/listen", tags=["listen"])

_control_lock = None
_control_loop = None


def _control():
    global _control_lock, _control_loop
    loop = asyncio.get_running_loop()
    if _control_loop is not loop:
        _control_loop, _control_lock = loop, asyncio.Lock()
    return _control_lock






def _voice_preparation():
    try:
        from .voice_prepare import preparation
    except ImportError:
        from voice_prepare import preparation
    return preparation


def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "message": "Голосовой режим недоступен. Проверьте настройки звука.",
        },
    )


@router.get("/heard")
async def heard(limit: int = 50) -> Dict:
    """
    Что Scott услышал и что из этого вышло.

    Голосом он умеет меньше, чем в чате, — и это первое, что замечает человек.
    Но разбор у голоса и чата ОДИН И ТОТ ЖЕ: дело не в возможностях, а в
    тексте, который до разбора доходит. Здесь видно, каким он приходит.

    Смотреть надо на долю прошедших мимо: если Scott слышит сказанное, но не
    узнаёт в нём своё имя, лечить надо имя, а не разбор команд.
    """
    try:
        from . import heard_log
    except ImportError:
        import heard_log

    записи = heard_log.read(limit)

    return {
        "success": True,
        "heard": list(reversed(записи)),
        "summary": heard_log.summary(),
    }


@router.post("/heard/clear")
async def clear_heard() -> Dict:
    """Забыть услышанное. Это речь человека, и он вправе её стереть."""
    try:
        from . import heard_log
    except ImportError:
        import heard_log

    heard_log.clear()
    return {"success": True, "message": "Журнал услышанного очищен"}


@router.get("/level")
async def input_level() -> Dict:
    listener = scott_runtime.listener
    return {"listening": bool(listener and listener.is_running),
            "level": listener.input_level() if listener else 0.0}


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
            "available": bool(listener_module and listener_module.HAS_SOUNDDEVICE),
            "message": "Слушатель не создан",
        }
    return scott_runtime.listener.status()


@router.post("/start")
async def start() -> Dict:
    """Включить локальное распознавание с обращением по имени."""
    async with _control():
        return await _start_whisper()


async def _start_whisper() -> Dict:
    if scott_runtime.listener is None:
        return _unavailable()

    preparation = _voice_preparation()
    epoch = preparation.listening_requested()
    result = await asyncio.to_thread(scott_runtime.listener.start)
    if not result.get("success"):
        ident = preparation.listening_failed(epoch)
        await asyncio.to_thread(preparation.cancel_listening,ident)
        return JSONResponse(status_code=503, content=result)
    state = scott_runtime.listener.status()
    if state.get('listening'):
        preparation.start_listening(epoch)
    else:
        ident = preparation.listening_failed(epoch)
        await asyncio.to_thread(preparation.cancel_listening,ident)
    return {**result, **state, 'voice_preparation':preparation.snapshot()}


@router.post("/stop")
async def stop() -> Dict:
    """Перестать слушать."""
    async with _control():
        return await _stop_whisper()


async def _stop_whisper() -> Dict:
    preparation = _voice_preparation()
    ident = preparation.listening_stopped()
    if scott_runtime.listener is None:
        await asyncio.to_thread(preparation.cancel_listening,ident)
        return _unavailable()
    def stop_listener():
        preparation.cancel_listening(ident)
        return scott_runtime.listener.stop()
    result = await asyncio.to_thread(stop_listener)
    return {**result, **scott_runtime.listener.status(), 'voice_preparation':preparation.snapshot()}


@router.get("/devices")
async def devices() -> Dict:
    """Микрофоны, доступные в системе, — чтобы выбрать нужный, если их несколько."""
    if listener_module is None:
        return _unavailable()
    return {"success": True, "devices": await asyncio.to_thread(listener_module.list_input_devices)}

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
    await asyncio.to_thread(listener._dispatch, text)

    состояние = listener.status()

    return {
        "success": True,
        "heard": text,
        "dispatch": состояние.get("last_dispatch"),
        "command": состояние.get("last_command"),
        "error": состояние.get("last_error"),
    }
