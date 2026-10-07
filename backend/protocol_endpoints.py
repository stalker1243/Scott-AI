"""
Протоколы через API: список, составление, правка, запуск.

Само хранилище живёт в runtime — оно одно на процесс, и протокол, добавленный
через один экземпляр, должен быть виден всем остальным сразу, а не после
перезапуска.

Запуск здесь только начинается: шаги исполняет ассистент, и функция исполнения
приходит из main.py той же дорогой, что голос и слушатель. Импортировать main
отсюда нельзя — импорты замкнулись бы в кольцо.
"""

from typing import Dict, List, Optional, Union

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from . import runtime as scott_runtime
    from . import protocols as protocols_module
    from .protocol_jobs import ProtocolJobs
except ImportError:
    import runtime as scott_runtime
    import protocols as protocols_module
    from protocol_jobs import ProtocolJobs

router = APIRouter(prefix="/protocols", tags=["protocols"])
jobs = ProtocolJobs()


def _store():
    return scott_runtime.protocols


class StepIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    pause: float = Field(default=0.0, ge=0, le=60, allow_inf_nan=False)
    enabled: bool = True


class ProtocolIn(BaseModel):
    name: str
    steps: List[Union[str, StepIn]] = Field(default_factory=list, min_length=1, max_length=40)
    phrases: List[str] = Field(default_factory=list, max_length=20)
    description: str = ""
    enabled: bool = True
    repeat_count: int = Field(default=1, ge=1, le=20)
    stop_on_error: bool = True

    # Расписание словами: «по будням в 09:00», «каждый день в 23:00».
    #
    # Строкой, а не часами с номерами дней: человек пишет то же, что сказал бы
    # вслух, — тот же подход, что и у шагов протокола.
    schedule: str = ""


class ProtocolPatch(BaseModel):
    name: Optional[str] = None
    steps: Optional[List[Union[str, StepIn]]] = Field(default=None, min_length=1, max_length=40)
    phrases: Optional[List[str]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    schedule: Optional[str] = None
    repeat_count: Optional[int] = Field(default=None, ge=1, le=20)
    stop_on_error: Optional[bool] = None


@router.get("")
async def list_protocols() -> Dict:
    """Все протоколы, новые сверху."""
    store = _store()
    if store is None:
        return {"success": False, "message": "Протоколы не загружены", "protocols": []}

    items = sorted(store.all(), key=lambda p: p.created, reverse=True)
    return {"success": True, "protocols": [item.to_dict() for item in items]}


@router.get("/jobs/current")
async def current_job() -> Dict:
    return {"success": True, "job": jobs.current()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> Dict:
    job = jobs.get(job_id)
    return {"success": True, "job": job} if job else {"success": False, "error": "Запуск не найден"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict:
    return jobs.cancel(job_id)


@router.patch("/id/{protocol_id}")
async def update_by_id(protocol_id: str, body: ProtocolPatch) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}
    return store.update_by_id(protocol_id, **body.model_dump(exclude_none=True))


@router.delete("/id/{protocol_id}")
async def delete_by_id(protocol_id: str) -> Dict:
    store = _store()
    if store is None:
        return {"success": False, "error": "Протоколы не загружены"}
    return store.delete_by_id(protocol_id)


@router.post("/id/{protocol_id}/start")
async def start_by_id(protocol_id: str) -> Dict:
    store = _store()
    protocol = store.get_by_id(protocol_id) if store else None
    if protocol is None:
        return {"success": False, "error": "Протокол не найден"}
    if scott_runtime.run_protocol is None:
        return {"success": False, "error": "Ассистент ещё не готов"}
    return jobs.start(protocol, scott_runtime.run_protocol)


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
        steps=body.model_dump()["steps"],
        phrases=body.phrases,
        description=body.description,
        schedule=body.schedule,
        enabled=body.enabled,
        repeat_count=body.repeat_count,
        stop_on_error=body.stop_on_error,
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
