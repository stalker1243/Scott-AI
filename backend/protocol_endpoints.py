"""
Протоколы через API: список, составление, правка, запуск.

Само хранилище живёт в runtime — оно одно на процесс, и протокол, добавленный
через один экземпляр, должен быть виден всем остальным сразу, а не после
перезапуска.

Запуск здесь только начинается: шаги исполняет ассистент, и функция исполнения
приходит из main.py той же дорогой, что голос и слушатель. Импортировать main
отсюда нельзя — импорты замкнулись бы в кольцо.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from . import runtime as scott_runtime
    from . import protocols as protocols_module
except ImportError:
    import runtime as scott_runtime
    import protocols as protocols_module

router = APIRouter(prefix="/protocols", tags=["protocols"])


def _store():
    return scott_runtime.protocols


class StepIn(BaseModel):
    text: str
    pause: float = 0.0


class ProtocolIn(BaseModel):
    name: str
    steps: List[Any] = []
    phrases: List[str] = []
    description: str = ""

    # Расписание словами: «по будням в 09:00», «каждый день в 23:00».
    #
    # Строкой, а не часами с номерами дней: человек пишет то же, что сказал бы
    # вслух, — тот же подход, что и у шагов протокола.
    schedule: str = ""


class ProtocolPatch(BaseModel):
    name: Optional[str] = None
    steps: Optional[List[Any]] = None
    phrases: Optional[List[str]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    schedule: Optional[str] = None


@router.get("")
async def list_protocols() -> Dict:
    """Все протоколы, новые сверху."""
    store = _store()
    if store is None:
        return {"success": False, "message": "Протоколы не загружены", "protocols": []}

    items = sorted(store.all(), key=lambda p: p.created, reverse=True)
    return {"success": True, "protocols": [item.to_dict() for item in items]}


@router.get("/{name}")
async def get_protocol(name: str) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}

    protocol = store.get(name)
    if not protocol:
        return {"success": False, "error": f"Протокол «{name}» не найден"}

    return {"success": True, "protocol": protocol.to_dict()}


@router.post("")
async def add_protocol(body: ProtocolIn) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}

    return store.add(
        name=body.name,
        steps=body.steps,
        phrases=body.phrases,
        description=body.description,
        schedule=body.schedule,
    )


@router.patch("/{name}")
async def update_protocol(name: str, body: ProtocolPatch) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}

    # Передаём только то, что человек действительно менял: иначе пустое поле
    # формы затирает описание, которое никто не трогал.
    changes = {key: value for key, value in body.model_dump().items() if value is not None}
    return store.update(name, **changes)


@router.delete("/{name}")
async def delete_protocol(name: str) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}

    return store.delete(name)


@router.post("/{name}/run")
async def run_protocol(name: str) -> Dict:
    """
    Выполнить протокол прямо сейчас.

    Тот же путь, что и по голосу: каждый шаг уходит в разбор и исполнение как
    обычная фраза.
    """
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}

    protocol = store.get(name)
    if not protocol:
        return {"success": False, "error": f"Протокол «{name}» не найден"}

    runner = scott_runtime.run_protocol
    if runner is None:
        return {"success": False, "error": "Ассистент ещё не готов выполнять шаги"}

    result = await runner(protocol)

    return {
        "success": result.ok,
        "message": result.summary(),
        "steps": [
            {"text": step.text, "ok": step.ok, "response": step.response}
            for step in result.steps
        ],
        "stopped_at": result.stopped_at,
        "error": result.error,
    }
