"""
Эндпоинты диагностики: логи, сведения о машине и сбор отчёта об ошибке.

Отдельный роутер, потому что это единственная часть API, предназначенная не
для работы ассистента, а для разбора его поломок на чужом компьютере.
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

try:
    from . import diagnostics
except ImportError:
    import diagnostics

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/system")
async def system_info() -> Dict:
    """Сведения о машине: ОС, память, видеокарта, версии, текущие настройки."""
    return diagnostics.collect_system_info()


@router.get("/gpu")
async def gpu_info() -> Dict:
    """
    Отдельно про видеокарту — лаунчер показывает это в настройках.

    Здесь же видно главную ловушку проекта: torch, установленный обычной
    командой, собран без CUDA и видеокарту не использует, сколько бы её ни
    было в компьютере.
    """
    return diagnostics.collect_gpu_info()


@router.get("/errors")
async def recent_errors(limit: int = 50) -> Dict:
    """Последние ошибки из лога — то, что показывается на вкладке «Логи»."""
    return {"success": True, "errors": diagnostics.recent_errors(limit)}


@router.get("/logs")
async def read_log(name: str = "backend_errors.log", lines: int = 200) -> Dict:
    """Хвост конкретного лога. Секреты вырезаны."""
    result = diagnostics.tail_log(name, lines)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)
    return result


@router.get("/logs/available")
async def available_logs() -> Dict:
    """Какие логи вообще есть и насколько они велики."""
    files = []
    for name, path in diagnostics.LOG_FILES.items():
        files.append({
            "name": name,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        })
    return {"success": True, "logs": files}


@router.post("/report")
async def build_report(data: Dict = None) -> Dict:
    """
    Собрать архив с логами и сведениями о машине.

    Тело необязательное: {"note": "что случилось своими словами"}. Описание от
    пользователя обычно ценнее всех логов вместе взятых, поэтому попадает в
    архив отдельным файлом.
    """
    note = (data or {}).get("note") if isinstance(data, dict) else None
    result = diagnostics.build_report(note)
    if not result.get("success"):
        return JSONResponse(status_code=500, content=result)
    return result


@router.get("/report/download")
async def download_report(path: str):
    """
    Отдать собранный архив файлом.

    Скачивать можно только из папки отчётов: имя приходит от клиента, и без
    этой проверки параметром `path` можно было бы вытянуть любой файл с диска.
    """
    from pathlib import Path

    target = Path(path).resolve()
    reports_dir = diagnostics.REPORTS_DIR.resolve()

    if reports_dir not in target.parents or not target.is_file():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Скачивать можно только собранные отчёты"},
        )

    return FileResponse(target, filename=target.name, media_type="application/zip")
