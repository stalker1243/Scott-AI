"""
Управление ИИ-ассистентом: статус, выбор провайдера и модели, температура,
память диалога, а также /ai/execute — выполнение команды по запросу извне.

Доступ к /ai/execute ограничен: пускаем либо с самой машины, либо по секрету
в заголовке. Проверка перенесена как есть — она защищает от того, чтобы
сторонняя страница в браузере дёргала выполнение команд на компьютере.

Оба геттера живут в своих модулях, поэтому берутся напрямую:
get_intelligent_answerer() отдаёт единственный экземпляр на процесс, а
get_command_executor() создаёт новый — здесь так и было задумано, исполнитель
команд состояния не хранит. Голос приходит из runtime, потому что его создаёт
ScottAI при старте, а импортировать main.py роутеру нельзя.
"""

import asyncio
import os
from typing import Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

try:
    from . import runtime as scott_runtime
    from .intelligent_answerer import get_intelligent_answerer
    from .command_executor import get_command_executor
except ImportError:
    import runtime as scott_runtime
    from intelligent_answerer import get_intelligent_answerer
    from command_executor import get_command_executor

router = APIRouter(tags=["ai"])


@router.get("/ai/status")
async def get_ai_status():
    """Получить статус ИИ-ассистента"""
    ia = get_intelligent_answerer()
    if not ia:
        return {"error": "ИИ-ассистент не инициализирован"}

    return {
        "enabled": ia.enabled,
        "model": ia.model,
        "provider": ia.api_provider,
        "temperature": ia.temperature,
        "memory_messages": len(ia.memory.conversations),
        "max_history": ia.memory.max_history,
        "api_connected": ia.enabled
    }

@router.get("/ai/providers")
async def list_ai_providers():
    """Список провайдеров ИИ с их моделями и текущим активным — для выбора в Настройках"""
    ia = get_intelligent_answerer()
    if not ia:
        return {"error": "ИИ-ассистент не инициализирован"}

    return {
        "providers": ia.get_available_providers(),
        "active_provider": ia.api_provider,
        "active_model": ia.model,
    }

@router.post("/ai/configure")
async def configure_ai(request: Dict):
    """
    Переключить провайдера/модель ИИ, опционально со своим API-ключом.
    Тело: {"provider": "Groq" | "OpenAI" | "DeepSeek", "model": "...", "api_key": "..." (опционально)}
    """
    ia = get_intelligent_answerer()
    if not ia:
        return {"success": False, "error": "ИИ-ассистент не инициализирован"}

    provider = request.get("provider", "").strip()
    model = request.get("model", "").strip()
    api_key = (request.get("api_key") or "").strip() or None

    if not provider or not model:
        return {"success": False, "error": "Провайдер и модель обязательны"}

    return ia.configure(provider, model, api_key)

@router.post("/ai/execute")
async def ai_execute(request: Dict, http_request: Request):
    """Выполнить безопасную системную команду от имени ИИ.

    Защита:
    - Разрешено только с localhost, или
    - Требуется заголовок `X-SCOTT-KEY` совпадающий с переменной окружения `SCOTT_API_KEY`.
    Тело запроса: {"command_type": "open_app", "params": {"name": "notepad"}, "announce": true}
    """
    # Проверка доступа
    secret = os.getenv('SCOTT_API_KEY')
    header_key = None
    try:
        header_key = http_request.headers.get('X-SCOTT-KEY')
    except Exception:
        header_key = None

    client_host = None
    try:
        client_host = http_request.client.host
    except Exception:
        client_host = None

    allowed = False
    if client_host in ('127.0.0.1', '::1', 'localhost'):
        allowed = True
    if secret and header_key and secret == header_key:
        allowed = True

    if not allowed:
        return JSONResponse(status_code=403, content={"success": False, "message": "Доступ запрещён"})

    command_type = request.get('command_type')
    params = request.get('params', {}) or {}
    announce = bool(request.get('announce', False))

    if not command_type:
        return JSONResponse(status_code=400, content={"success": False, "message": "Не указана команда"})

    try:
        executor = get_command_executor()
        result = executor.execute(command_type, **params)

        # Озвучивание результата, если требуется и голос доступен.
        # to_thread по той же причине, что и в /speak — генерация речи занимает
        # секунды и иначе застопорила бы весь event loop.
        try:
            if announce and scott_runtime.scott_voice:
                await asyncio.to_thread(scott_runtime.scott_voice.speak_to_file, str(result))
        except Exception as e:
            print(f"⚠️ Ошибка при озвучивании результата: {e}")

        return JSONResponse(status_code=200, content={"success": True, "result": result})
    except Exception as e:
        print(f"❌ Ошибка выполнения команды через /ai/execute: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@router.post("/ai/toggle")
async def toggle_ai_mode(enabled: bool):
    """Включить/выключить ИИ-режим"""
    ia = get_intelligent_answerer()
    if not ia:
        return {"error": "ИИ-ассистент не инициализирован"}
    
    # Это просто информационный endpoint - реальное включение/выключение
    # делается через конфиг
    return {
        "status": "success",
        "ai_enabled": ia.enabled,
        "message": f"ИИ {'включен' if ia.enabled else 'отключен'}"
    }

@router.post("/ai/set-model")
async def set_ai_model(model: str):
    """Установить модель ИИ (gpt-3.5-turbo или gpt-4)"""
    ia = get_intelligent_answerer()
    if not ia or not ia.enabled:
        return {"error": "ИИ-ассистент недоступен"}
    
    valid_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]
    if model not in valid_models:
        return {"error": f"Модель {model} не поддерживается. Доступные: {valid_models}"}
    
    ia.set_model(model)
    return {"status": "success", "model": model}

@router.post("/ai/temperature")
async def set_temperature(temp: float):
    """Установить температуру (креативность) ИИ (0.0-1.0)"""
    ia = get_intelligent_answerer()
    if not ia or not ia.enabled:
        return {"error": "ИИ-ассистент недоступен"}
    
    ia.set_temperature(temp)
    return {"status": "success", "temperature": ia.temperature}

@router.post("/ai/clear-memory")
async def clear_ai_memory():
    """Очистить память разговоров"""
    ia = get_intelligent_answerer()
    if not ia:
        return {"error": "ИИ-ассистент не инициализирован"}
    
    ia.clear_memory()
    return {"status": "success", "message": "Память очищена"}

@router.get("/ai/memory-stats")
async def get_memory_stats():
    """Получить статистику памяти"""
    ia = get_intelligent_answerer()
    if not ia:
        return {"error": "ИИ-ассистент не инициализирован"}
    
    return {
        "messages_count": len(ia.memory.conversations),
        "max_history": ia.memory.max_history,
        "conversations": ia.memory.conversations[-5:]  # Последние 5 сообщений
    }
