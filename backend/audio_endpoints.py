"""
Настройки звука: устройства, громкость, тихий режим.

Отдельным файлом, а не в main.py: тот и без того разросся до двух с половиной
тысяч строк, и складывать туда каждую новую пару обработчиков — прямой путь к
файлу, в котором ничего не найти.
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import audio_settings
    from . import runtime as scott_runtime
except ImportError:
    import audio_settings
    import runtime as scott_runtime

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/settings")
async def read_settings() -> Dict:
    """Текущие настройки звука вместе со списком доступных устройств."""
    return audio_settings.describe()


@router.post("/settings")
async def write_settings(request: Dict) -> Dict:
    """
    Изменить настройки звука. Меняется только то, что прислали.

    Смена микрофона требует перезапуска прослушивания: поток к устройству уже
    открыт, и на лету его не переключить. Делаем это сами, чтобы человеку не
    приходилось догадываться, почему выбор «не сработал».
    """
    known = {"input_device", "output_device", "volume", "quiet"}
    changes = {k: v for k, v in request.items() if k in known}

    if not changes:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Нечего менять"},
        )

    before = audio_settings.get_settings()
    settings = audio_settings.update(**changes)

    restarted = False
    if settings["input_device"] != before["input_device"]:
        restarted = _restart_listening()

    return {
        "success": True,
        "settings": settings,
        "listening_restarted": restarted,
        "message": _describe_change(before, settings),
    }


@router.post("/quiet")
async def toggle_quiet(request: Dict) -> Dict:
    """
    Включить или выключить тихий режим одним переключателем.

    Отдельно от общих настроек, потому что дёргают его чаще всего: это кнопка
    «помолчи», а не редактирование конфигурации.
    """
    quiet = bool(request.get("quiet", False))
    settings = audio_settings.set_quiet(quiet)

    if quiet:
        # Оборвать то, что звучит прямо сейчас. Иначе просьба замолчать
        # оставила бы Scott договаривать начатую фразу — а просят обычно
        # именно потому, что слушать её больше не хотят.
        _stop_current_speech()

    return {
        "success": True,
        "quiet": settings["quiet"],
        "message": "Scott больше ничего не говорит" if quiet else "Scott снова говорит вслух",
    }


def _stop_current_speech() -> None:
    try:
        try:
            from .speech_player import get_player, PLAYBACK_AVAILABLE
        except ImportError:
            from speech_player import get_player, PLAYBACK_AVAILABLE
        if PLAYBACK_AVAILABLE:
            get_player().stop()
    except Exception as e:
        print(f"⚠️ Не удалось оборвать речь: {e}")


def _restart_listening() -> bool:
    """Перезапустить прослушивание, если оно шло. Возвращает, случилось ли это."""
    listener = scott_runtime.listener
    if listener is None:
        return False

    try:
        if not listener.status().get("running"):
            return False
        listener.stop()
        listener.start()
        return True
    except Exception as e:
        print(f"⚠️ Не удалось перезапустить прослушивание: {e}")
        return False


def _describe_change(before: Dict, after: Dict) -> str:
    """Короткая человеческая сводка того, что изменилось."""
    parts = []

    if before["quiet"] != after["quiet"]:
        parts.append("тихий режим включён" if after["quiet"] else "тихий режим выключен")

    if before["volume"] != after["volume"]:
        parts.append(f"громкость {after['volume']}%")

    if before["output_device"] != after["output_device"]:
        parts.append(f"вывод: {after['output_device'] or 'системный'}")

    if before["input_device"] != after["input_device"]:
        parts.append(f"микрофон: {after['input_device'] or 'системный'}")

    return "; ".join(parts) if parts else "Ничего не изменилось"
