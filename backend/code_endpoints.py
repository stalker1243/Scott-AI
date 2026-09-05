"""
Написание и запуск программ через API.

Сборка и запуск разделены намеренно: код выполняется на компьютере
пользователя, и делать это без его отдельного слова неправильно.
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from . import code_assistant, code_tools
    from .intelligent_answerer import get_intelligent_answerer
except ImportError:
    import code_assistant
    import code_tools
    from intelligent_answerer import get_intelligent_answerer

router = APIRouter(prefix="/code", tags=["code"])


@router.get("/tools")
async def tools() -> Dict:
    """Чем эта машина умеет собирать и запускать программы."""
    return {"success": True, **code_tools.survey()}


@router.post("/write")
async def write(data: Dict) -> Dict:
    """
    Написать программу по просьбе.

    Тело: {"request": "напиши программу на C которая выводит Hello World",
           "language": "c" (необязательно), "name": "hello" (необязательно)}

    Программа только сохраняется. Собирать и запускать — отдельными вызовами:
    человек должен увидеть код прежде, чем тот выполнится на его машине.
    """
    request = (data.get("request") or "").strip()
    if not request:
        return JSONResponse(status_code=400, content={"success": False, "message": "Нужен текст просьбы"})

    result = code_assistant.write_program(
        request,
        get_intelligent_answerer(),
        language=(data.get("language") or "").strip() or None,
        name=(data.get("name") or "program").strip(),
    )

    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/build")
async def build(data: Dict) -> Dict:
    """Собрать написанное. Тело: {"path": "...", "language": "c"}."""
    path = (data.get("path") or "").strip()
    language = (data.get("language") or "").strip()
    if not path or not language:
        return JSONResponse(status_code=400, content={"success": False, "message": "Нужны path и language"})

    result = code_assistant.build_and_run(path, language, run_it=False)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/run")
async def run(data: Dict) -> Dict:
    """
    Собрать и запустить. Тело: {"path": "...", "language": "c"}.

    Отдельный вызов, а не флаг у /write: запуск программы — это действие на
    компьютере пользователя, и оно должно быть его отдельным решением.
    """
    path = (data.get("path") or "").strip()
    language = (data.get("language") or "").strip()
    if not path or not language:
        return JSONResponse(status_code=400, content={"success": False, "message": "Нужны path и language"})

    return code_assistant.build_and_run(path, language, run_it=True)


@router.get("/instructions")
async def instructions(path: str, language: str) -> Dict:
    """Как запустить программу руками — для тех, кто не хочет доверять это Scott."""
    return {
        "success": True,
        "instructions": code_tools.manual_instructions(path, language),
    }
