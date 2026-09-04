"""
Расширенное управление компьютером: PowerShell, файлы, громкость, яркость,
питание, ссылки, планировщик и журнал выполненных команд.

Опасные операции (PowerShell, удаление файла, выключение/перезагрузка/сон)
закрыты Bearer-токеном EXECUTE_TOKEN и ограничителем частоты — те же
зависимости, что были на них в main.py; защита работает fail-closed, без
заданного токена доступ запрещён всегда.

Исполнитель берётся из runtime, а не создаётся здесь: get_extended_executor()
отдаёт каждый раз новый объект, и своя копия вела бы отдельный журнал команд.
"""

from typing import Dict

from fastapi import APIRouter, Depends

try:
    from .security import require_scott_token, check_rate_limit
    from .runtime import extended_executor, HAS_EXTENDED_EXECUTOR
except ImportError:
    from security import require_scott_token, check_rate_limit
    from runtime import extended_executor, HAS_EXTENDED_EXECUTOR

router = APIRouter(tags=["extended"])


@router.post("/extended/powershell", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def execute_powershell(data: Dict):
    """Выполнить PowerShell команду"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    command = data.get('command', '')
    if not command:
        return {"success": False, "error": "Команда не указана"}
    
    result = extended_executor.execute_powershell(command)
    extended_executor.log_command(command, 'powershell', result['success'], result.get('output', ''))
    return result

@router.post("/extended/file/open-folder")
async def file_open_folder(data: Dict):
    """Открыть папку"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    path = data.get('path', '')
    if not path:
        return {"success": False, "error": "Путь не указан"}
    
    result = extended_executor.open_folder(path)
    extended_executor.log_command(f"open_folder:{path}", 'file_operation', result['success'])
    return result

@router.post("/extended/file/delete", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def file_delete(data: Dict):
    """Удалить файл"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    file_path = data.get('path', '')
    if not file_path:
        return {"success": False, "error": "Путь файла не указан"}
    
    result = extended_executor.delete_file(file_path)
    extended_executor.log_command(f"delete_file:{file_path}", 'file_operation', result['success'])
    return result

@router.post("/extended/file/copy")
async def file_copy(data: Dict):
    """Скопировать файл"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    src = data.get('src', '')
    dest = data.get('dest', '')
    
    if not src or not dest:
        return {"success": False, "error": "Источник и назначение обязательны"}
    
    result = extended_executor.copy_file(src, dest)
    extended_executor.log_command(f"copy_file:{src}->{dest}", 'file_operation', result['success'])
    return result

@router.post("/extended/system/volume-up")
async def system_volume_up():
    """Увеличить громкость"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.volume_up()
    extended_executor.log_command('volume_up', 'system_command', result['success'])
    return result

@router.post("/extended/system/volume-down")
async def system_volume_down():
    """Уменьшить громкость"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.volume_down()
    extended_executor.log_command('volume_down', 'system_command', result['success'])
    return result

@router.post("/extended/system/brightness-up")
async def system_brightness_up():
    """Увеличить яркость"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.brightness_up()
    extended_executor.log_command('brightness_up', 'system_command', result['success'])
    return result

@router.post("/extended/system/brightness-down")
async def system_brightness_down():
    """Уменьшить яркость"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.brightness_down()
    extended_executor.log_command('brightness_down', 'system_command', result['success'])
    return result

@router.post("/extended/system/sleep", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def system_sleep():
    """Включить спящий режим"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.sleep_system()
    extended_executor.log_command('sleep', 'system_command', result['success'])
    return result

@router.post("/extended/system/restart", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def system_restart():
    """Перезагрузить систему"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.restart_system()
    extended_executor.log_command('restart', 'system_command', result['success'])
    return result

@router.post("/extended/system/shutdown", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def system_shutdown():
    """Выключить систему"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    result = extended_executor.shutdown_system()
    extended_executor.log_command('shutdown', 'system_command', result['success'])
    return result

@router.post("/extended/url/open")
async def url_open(data: Dict):
    """Открыть URL"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    url = data.get('url', '')
    if not url:
        return {"success": False, "error": "URL не указан"}
    
    result = extended_executor.open_url(url)
    extended_executor.log_command(f"open_url:{url}", 'open_url', result['success'])
    return result

@router.post("/extended/schedule/add")
async def schedule_add(data: Dict):
    """Добавить запланированную команду"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    command = data.get('command', '')
    time_str = data.get('time', '')
    command_type = data.get('type', 'powershell')
    
    if not command or not time_str:
        return {"success": False, "error": "Команда и время обязательны"}
    
    return extended_executor.schedule_command(command, time_str, command_type)

@router.get("/extended/schedule/list")
async def schedule_list():
    """Получить список запланированных команд"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    return extended_executor.list_scheduled_commands()

@router.post("/extended/schedule/cancel")
async def schedule_cancel(data: Dict):
    """Отменить запланированную команду"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    task_id = data.get('task_id')
    if task_id is None:
        return {"success": False, "error": "ID задачи не указан"}
    
    return extended_executor.cancel_scheduled_command(task_id)

@router.get("/extended/metrics")
async def extended_metrics():
    """Получить метрики"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    return extended_executor.get_metrics()

@router.get("/extended/history")
async def extended_history(limit: int = 50):
    """Получить историю команд"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    return extended_executor.get_command_history(limit)

@router.post("/extended/history/clear")
async def extended_history_clear():
    """Очистить историю"""
    if not HAS_EXTENDED_EXECUTOR:
        return {"success": False, "error": "Расширенный исполнитель не доступен"}
    
    return extended_executor.clear_history()
