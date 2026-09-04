"""
FastAPI endpoints для компонентов v3.3
Профили, Шаблоны, Макросы, Версии, Голосовые правила
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Optional, List
from pydantic import BaseModel

router = APIRouter()

# Глобальная переменная для intelligent_answerer
intelligent_answerer = None

def set_intelligent_answerer(ia):
    """Установить intelligent_answerer для использования в endpoints"""
    global intelligent_answerer
    intelligent_answerer = ia
    print(f"📌 v33_endpoints: intelligent_answerer установлен: {intelligent_answerer is not None}")

# Pydantic models for request/response
class ProfileCreateRequest(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    is_admin: bool = False

class ProfileSwitchRequest(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None

class TemplateCreateRequest(BaseModel):
    name: str
    category: str
    description: str = ""
    commands: List[str] = None
    rules: List[Dict] = None
    icon: str = "🎯"

class TemplateApplyRequest(BaseModel):
    name: str

class MacroRecordRequest(BaseModel):
    name: str

class MacroActionRequest(BaseModel):
    action_type: str
    target: str
    x: int = 0
    y: int = 0
    details: Optional[Dict] = None

class MacroPlayRequest(BaseModel):
    name: str
    loop_count: int = 1

class VersionTrackRequest(BaseModel):
    item_id: str
    item_type: str
    data: Dict
    author: str = "system"
    description: str = ""

class VersionRollbackRequest(BaseModel):
    item_id: str
    version: int

class VoiceRuleRequest(BaseModel):
    text: str

class AskRequest(BaseModel):
    question: str
    context: Optional[str] = None

# Инициализируются из main.py
profile_manager = None
templates_manager = None
macro_recorder = None
version_manager = None
voice_rule_builder = None
intelligent_answerer = None


def init_v33_endpoints(pm, tm, mr, vm, vrb, ia=None):
    """Инициализировать manager'ы"""
    global profile_manager, templates_manager, macro_recorder, version_manager, voice_rule_builder, intelligent_answerer
    profile_manager = pm
    templates_manager = tm
    macro_recorder = mr
    version_manager = vm
    voice_rule_builder = vrb
    intelligent_answerer = ia


def success_response(message: str, data: any = None) -> Dict:
    """Стандартный успешный ответ"""
    return {
        "success": True,
        "message": message,
        "data": data
    }


def error_response(message: str, code: int = 400) -> Dict:
    """Стандартный ответ об ошибке"""
    return {
        "success": False,
        "message": message,
        "data": None
    }


# ============= PROFILES ENDPOINTS =============

@router.get("/profiles/list")
async def profiles_list():
    """Получить список всех профилей"""
    try:
        profiles = profile_manager.list_profiles()
        return success_response("Профили получены", profiles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/current")
async def profiles_current():
    """Получить текущий профиль"""
    try:
        profile = profile_manager.get_current_profile()
        if not profile:
            raise HTTPException(status_code=404, detail="Профиль не найден")
        return success_response("Текущий профиль", profile.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles/create")
async def profiles_create(request: ProfileCreateRequest):
    """Создать новый профиль"""
    try:
        username = request.name or request.username
        if not username or len(username.strip()) == 0:
            raise HTTPException(status_code=422, detail="Имя профиля не может быть пустым")
        
        result = profile_manager.create_profile(username=username, is_admin=request.is_admin)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            return error_response(result.get("message"))
    except HTTPException:
        raise
    except Exception as e:
        return error_response(f"Ошибка создания профиля: {str(e)}")


@router.post("/profiles/switch")
async def profiles_switch(request: ProfileSwitchRequest):
    """Переключиться на другой профиль"""
    try:
        username = request.name or request.username
        if not username:
            return error_response("Имя профиля не указано")
        
        result = profile_manager.switch_profile(username)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            return error_response(result.get("message"))
    except Exception as e:
        return error_response(f"Ошибка переключения профиля: {str(e)}")


@router.post("/profiles/delete")
async def profiles_delete(request: ProfileSwitchRequest):
    """Удалить профиль"""
    try:
        username = request.name or request.username
        if not username:
            return error_response("Имя профиля не указано")
        
        result = profile_manager.delete_profile(username)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            return error_response(result.get("message"))
    except Exception as e:
        return error_response(f"Ошибка удаления профиля: {str(e)}")


@router.post("/profiles/update")
async def profiles_update(username: str, **kwargs):
    """Обновить профиль"""
    try:
        result = profile_manager.update_profile(username, **kwargs)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/stats")
async def profiles_stats():
    """Получить статистику профилей"""
    try:
        stats = profile_manager.get_statistics()
        return success_response("Статистика профилей", stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= TEMPLATES ENDPOINTS =============

@router.get("/templates/list")
async def templates_list(category: Optional[str] = None):
    """Получить список шаблонов"""
    try:
        templates = templates_manager.list_templates(category)
        return success_response("Шаблоны получены", templates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/categories")
async def templates_categories():
    """Получить список категорий шаблонов"""
    try:
        categories = templates_manager.list_categories()
        return success_response("Категории получены", categories)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/popular")
async def templates_popular(limit: int = 5):
    """Получить популярные шаблоны"""
    try:
        templates = templates_manager.get_popular_templates(limit)
        return success_response("Популярные шаблоны получены", templates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/apply")
async def templates_apply(request: TemplateApplyRequest):
    """Применить шаблон"""
    try:
        result = templates_manager.apply_template(request.name)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/create")
async def templates_create(request: TemplateCreateRequest):
    """Создать кастомный шаблон"""
    try:
        result = templates_manager.create_custom_template(
            name=request.name, 
            category=request.category, 
            description=request.description, 
            commands=request.commands, 
            rules=request.rules,
            icon=request.icon
        )
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/delete")
async def templates_delete(request: TemplateApplyRequest):
    """Удалить шаблон"""
    try:
        result = templates_manager.delete_template(request.name)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= MACROS ENDPOINTS =============

@router.get("/macros/list")
async def macros_list(enabled_only: bool = True):
    """Получить список макросов"""
    try:
        macros = macro_recorder.list_macros(enabled_only)
        return success_response("Макросы получены", macros)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macros/status")
async def macros_status():
    """Получить статус записи макроса"""
    try:
        status = macro_recorder.get_recording_status()
        return success_response("Статус получен", status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macros/start-recording")
async def macros_start_recording(request: MacroRecordRequest):
    """Начать запись макроса"""
    try:
        result = macro_recorder.start_recording(request.name)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macros/stop-recording")
async def macros_stop_recording():
    """Остановить запись макроса"""
    try:
        result = macro_recorder.stop_recording()
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macros/record-action")
async def macros_record_action(request: MacroActionRequest):
    """Записать действие в макрос"""
    try:
        result = macro_recorder.record_action(
            request.action_type, request.target,
            x=request.x, y=request.y, details=request.details or {}
        )
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macros/execute")
async def macros_execute(request: MacroPlayRequest):
    """Выполнить макрос"""
    try:
        result = macro_recorder.execute_macro(request.name, request.loop_count)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macros/get")
async def macros_get(name: str):
    """Получить конкретный макрос"""
    try:
        macro = macro_recorder.get_macro(name)
        if macro:
            return success_response("Макрос получен", {
                "name": macro.name,
                "description": macro.description,
                "actions": [{"action_type": a.action_type, "target": a.target} for a in macro.actions],
                "created_at": macro.created_at,
                "execution_count": macro.execution_count,
                "loop_count": macro.loop_count
            })
        else:
            raise HTTPException(status_code=404, detail="Макрос не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/macros/delete")
async def macros_delete(name: str):
    """Удалить макрос"""
    try:
        # Нужно добавить метод delete в MacroRecorder если его нет
        if hasattr(macro_recorder, 'delete_macro'):
            result = macro_recorder.delete_macro(name)
            if result.get("success"):
                return success_response(result.get("message"), result.get("data"))
            else:
                raise HTTPException(status_code=400, detail=result.get("message"))
        else:
            raise HTTPException(status_code=501, detail="Метод не реализован")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= VERSIONS ENDPOINTS =============

@router.get("/versions/items")
async def versions_items():
    """Получить список всех элементов, для которых отслеживается история версий"""
    try:
        items = [
            {
                'item_id': h.item_id,
                'item_type': h.item_type,
                'current_version': h.current_version,
                'versions_count': len(h.versions),
            }
            for h in version_manager.histories.values()
        ]
        return success_response("Список элементов получен", items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions/history")
async def versions_history(item_id: str = None, item_type: str = "macro"):
    """Получить историю версий"""
    try:
        if not item_id:
            # Если не указан item_id, вернуть всю историю
            return success_response("История версий получена", {})
        history = version_manager.get_history(item_id)
        return success_response("История версий получена", history)
    except Exception as e:
        return error_response(f"Ошибка получения истории: {str(e)[:100]}")


@router.get("/versions/get")
async def versions_get(item_id: str, version_number: int, item_type: str = "macro"):
    """Получить конкретную версию"""
    try:
        version = version_manager.get_version(item_id, version_number)
        if version:
            return success_response("Версия получена", version)
        else:
            raise HTTPException(status_code=404, detail="Версия не найдена")
    except Exception as e:
        return error_response(f"Ошибка получения версии: {str(e)[:100]}")


# ============= AI ASSISTANT ENDPOINTS =============

# Временный отключён: основной обработчик /ask находится в backend/main.py
# чтобы команды типа «открой notepad» выполнялись как команды, а не как вопросы ИИ.


@router.post("/versions/track")
async def versions_track(request: VersionTrackRequest):
    """Отслеживать изменение"""
    try:
        result = version_manager.track_change(
            item_id=request.item_id, 
            item_type=request.item_type, 
            data=request.data, 
            author=request.author, 
            change_description=request.description
        )
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/rollback")
async def versions_rollback(request: VersionRollbackRequest):
    """Оккатить на предыдущую версию"""
    try:
        result = version_manager.rollback(request.item_id, request.version)
        if result.get("success"):
            return success_response(result.get("message"), result.get("data"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions/stats")
async def versions_stats():
    """Получить статистику версий"""
    try:
        stats = version_manager.get_statistics()
        return success_response("Статистика версий получена", stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= VOICE ENDPOINTS =============

@router.post("/voice/parse-rule")
async def voice_parse_rule(request: VoiceRuleRequest):
    """Распарсить голосовое правило"""
    try:
        if not request.text or not request.text.strip():
            return error_response("Текст команды не может быть пустым")
        
        result = voice_rule_builder.parse_voice_rule(request.text)
        if result.get('success') == False:
            return error_response(result.get('message', 'Не удалось распарсить команду'))
        return success_response("Правило распарсено", result)
    except Exception as e:
        return error_response(f"Ошибка парсинга правила: {str(e)[:100]}")


@router.post("/voice/parse-macro")
async def voice_parse_macro(request: VoiceRuleRequest):
    """Распарсить инструкцию для макроса"""
    try:
        result = voice_rule_builder.parse_macro_instruction(request.text)
        if result.get('success') == False:
            raise HTTPException(status_code=400, detail=result.get('message', 'Unknown error'))
        return success_response("Инструкция распарсена", result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/suggest-name")
async def voice_suggest_name(trigger_type: str, trigger_value: str):
    """Предложить имя для правила"""
    try:
        name = voice_rule_builder.suggest_rule_name(trigger_type, trigger_value)
        return success_response("Имя предложено", {"suggested_name": name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
