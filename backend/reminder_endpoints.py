"""
Напоминания через API: список, добавление, отмена.

Сама служба живёт в runtime — она одна на процесс и держит фоновый поток,
который будит дела в срок.
"""

from datetime import datetime
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import runtime as scott_runtime
    from . import reminders as reminders_module
except ImportError:
    import runtime as scott_runtime
    import reminders as reminders_module

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _service():
    return scott_runtime.reminders


@router.get("")
async def list_reminders() -> Dict:
    """Что ещё не сработало и что уже прошло."""
    service = _service()
    if service is None:
        return {"success": False, "message": "Служба напоминаний не запущена", "reminders": []}

    items = service.all()
    return {
        "success": True,
        "reminders": [
            {
                "id": item.id,
                "text": item.text,
                "due": item.due,
                "done": item.done,
                "created": item.created,
            }
            for item in sorted(items, key=lambda i: i.due)
        ],
        "pending": len(service.pending()),
    }


@router.post("/add")
async def add_reminder(data: Dict) -> Dict:
    """
    Добавить напоминание.

    Тело: {"text": "...", "due": "2026-09-05T15:30:00"} либо
    {"phrase": "напомни через 10 минут выключить плиту"} — во втором случае
    время и тема разбираются из живой речи.
    """
    service = _service()
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "message": "Служба напоминаний не запущена"})

    phrase = (data.get("phrase") or "").strip()
    if phrase:
        due = reminders_module.parse_time(phrase)
        if due is None:
            return JSONResponse(status_code=400, content={
                "success": False,
                "message": "Не понял, на какое время — скажите «через десять минут» или «в 15:30»",
            })
        text = reminders_module.extract_subject(phrase) or phrase
    else:
        text = (data.get("text") or "").strip()
        raw_due = (data.get("due") or "").strip()
        if not text or not raw_due:
            return JSONResponse(status_code=400, content={"success": False, "message": "Нужны text и due"})
        try:
            due = datetime.fromisoformat(raw_due)
        except ValueError:
            return JSONResponse(status_code=400, content={"success": False, "message": "Время должно быть в формате ISO"})

    item = service.add(text, due)
    return {
        "success": True,
        "id": item.id,
        "text": item.text,
        "due": item.due,
        "message": f"Напомню {due.strftime('%d.%m в %H:%M')}: {item.text}",
    }


@router.post("/cancel")
async def cancel_reminder(data: Dict) -> Dict:
    """Отменить напоминание по идентификатору."""
    service = _service()
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "message": "Служба напоминаний не запущена"})

    reminder_id = (data.get("id") or "").strip()
    if not service.cancel(reminder_id):
        return JSONResponse(status_code=404, content={"success": False, "message": "Такого напоминания нет"})

    return {"success": True, "message": "Напоминание отменено"}


@router.post("/clear")
async def clear_done() -> Dict:
    """Убрать уже сработавшие — чтобы список не разрастался."""
    service = _service()
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "message": "Служба напоминаний не запущена"})

    removed = service.clear_done()
    return {"success": True, "removed": removed, "message": f"Убрано записей: {removed}"}
