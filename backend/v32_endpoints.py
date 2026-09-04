"""
Возможности версии 3.2: текущий контекст работы, пользовательские команды,
правила «если — то» и аналитика по истории.

Собраны вместе не по смыслу, а по происхождению: все четыре менеджера
приходят одним набором и включаются одним флагом HAS_V32_FEATURES — если
какого-то модуля нет, недоступны сразу все, и каждый эндпоинт честно
сообщает об этом вместо того, чтобы падать.

Менеджеры берутся из runtime: их фабрики отдают каждый раз новый объект, и
собственная копия здесь означала бы, что правило, добавленное через API, не
видно тому экземпляру, которым пользуется остальной backend.
"""

from typing import Dict

from fastapi import APIRouter

try:
    from .runtime import (
        HAS_V32_FEATURES,
        context_manager,
        custom_commands_manager,
        ifttt_manager,
        analytics_manager,
    )
except ImportError:
    from runtime import (
        HAS_V32_FEATURES,
        context_manager,
        custom_commands_manager,
        ifttt_manager,
        analytics_manager,
    )

router = APIRouter(tags=["v3.2"])


@router.get("/context/current")
async def get_current_context():
    """Получить текущий контекст"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    return context_manager.get_context()

@router.post("/context/set-variable")
async def set_context_variable(data: Dict):
    """Установить переменную контекста"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    key = data.get('key')
    value = data.get('value')
    
    if not key:
        return {"error": "Ключ обязателен"}
    
    context_manager.set_variable(key, value)
    return {"success": True, "message": f"Переменная '{key}' установлена"}

@router.post("/context/clear")
async def clear_context():
    """Очистить контекст"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    context_manager.clear_context()
    return {"success": True, "message": "Контекст очищен"}

@router.get("/context/history")
async def get_context_history(limit: int = 20):
    """Получить историю контекста"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return {"history": context_manager.get_history(limit)}

@router.post("/custom-commands/add")
async def add_custom_command(data: Dict):
    """Добавить кастомную команду"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return custom_commands_manager.add_command(
        name=data.get('name', ''),
        trigger=data.get('trigger', ''),
        action=data.get('action', ''),
        description=data.get('description', '')
    )

@router.post("/custom-commands/update")
async def update_custom_command(data: Dict):
    """Обновить кастомную команду"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    name = data.get('name')
    if not name:
        return {"error": "Имя команды обязательно"}

    updates = {k: v for k, v in data.items() if k != 'name'}
    return custom_commands_manager.update_command(name, **updates)

@router.post("/custom-commands/delete")
async def delete_custom_command(data: Dict):
    """Удалить кастомную команду"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    name = data.get('name')
    if not name:
        return {"error": "Имя команды обязательно"}
    
    return custom_commands_manager.delete_command(name)

@router.get("/custom-commands/list")
async def list_custom_commands(enabled_only: bool = True):
    """Получить список кастомных команд"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return {"commands": custom_commands_manager.get_all_commands(enabled_only)}

@router.get("/custom-commands/stats")
async def custom_commands_stats():
    """Получить статистику кастомных команд"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return custom_commands_manager.get_statistics()

@router.post("/custom-commands/execute")
async def execute_custom_command(data: Dict):
    """Выполнить кастомную команду"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    name = data.get('name')
    if not name:
        return {"error": "Имя команды обязательно"}
    
    return custom_commands_manager.execute_custom_command(name)

@router.post("/ifttt/add-rule")
async def add_ifttt_rule(data: Dict):
    """Добавить IFTTT правило"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    trigger_type = data.get('trigger_type', '')
    trigger_value = data.get('trigger_value', '')
    conditions_data = [{'trigger_type': trigger_type, 'trigger_value': trigger_value}] if trigger_type else None

    return ifttt_manager.add_rule(
        name=data.get('name', ''),
        action_type=data.get('action_type', ''),
        action_value=data.get('action_value', ''),
        conditions_data=conditions_data,
        logic=data.get('logic', 'AND'),
        description=data.get('description', '')
    )

@router.post("/ifttt/update-rule")
async def update_ifttt_rule(data: Dict):
    """Обновить IFTTT правило"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    name = data.get('name')
    if not name:
        return {"error": "Имя правила обязательно"}

    updates = {k: v for k, v in data.items() if k != 'name'}
    return ifttt_manager.update_rule(name, **updates)

@router.post("/ifttt/delete-rule")
async def delete_ifttt_rule(data: Dict):
    """Удалить IFTTT правило"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    name = data.get('name')
    if not name:
        return {"error": "Имя правила обязательно"}
    
    return ifttt_manager.delete_rule(name)

@router.get("/ifttt/rules")
async def list_ifttt_rules(enabled_only: bool = True):
    """Получить список IFTTT правил"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return {"rules": ifttt_manager.get_all_rules(enabled_only)}

@router.get("/ifttt/stats")
async def ifttt_stats():
    """Получить статистику IFTTT"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return ifttt_manager.get_statistics()

@router.post("/ifttt/check-triggers")
async def check_ifttt_triggers(data: Dict):
    """Проверить какие правила должны быть выполнены"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    trigger_type = data.get('trigger_type')
    trigger_value = data.get('trigger_value')
    
    if not trigger_type or not trigger_value:
        return {"error": "Тип триггера и значение обязательны"}
    
    triggered_rules = ifttt_manager.check_triggers(trigger_type, trigger_value)
    return {"triggered_rules": [rule.to_dict() for rule in triggered_rules]}

@router.get("/analytics/comprehensive")
async def get_comprehensive_analytics():
    """Получить полную аналитику"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_comprehensive_analytics()

@router.get("/analytics/daily")
async def get_daily_analytics(days: int = 7):
    """Получить статистику по дням"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_daily_statistics(days)

@router.get("/analytics/hourly")
async def get_hourly_analytics(hours: int = 24):
    """Получить статистику по часам"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_hourly_statistics(hours)

@router.get("/analytics/command-types")
async def get_command_types_analytics():
    """Получить распределение по типам команд"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_command_type_distribution()

@router.get("/analytics/top-apps")
async def get_top_apps(limit: int = 10):
    """Получить топ приложений"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_top_apps(limit)

@router.get("/analytics/response-time")
async def get_response_time_analytics():
    """Получить статистику времени отклика"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_average_response_time()

@router.get("/analytics/trends")
async def get_trend_analysis():
    """Получить анализ тренда"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.get_trend_analysis()

@router.get("/analytics/recommendations")
async def get_analytics_recommendations():
    """Получить рекомендации"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return {"recommendations": analytics_manager.get_recommendations()}

@router.post("/analytics/export")
async def export_analytics():
    """Экспортировать аналитику"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты v3.2 не доступны"}
    
    return analytics_manager.export_analytics()

@router.post("/ifttt/add-condition")
async def add_condition_to_rule(data: Dict):
    """Добавить условие к правилу"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты не доступны"}
    return ifttt_manager.add_condition_to_rule(
        rule_name=data.get('rule_name', ''),
        trigger_type=data.get('trigger_type', ''),
        trigger_value=data.get('trigger_value', ''),
        negate=data.get('negate', False)
    )

@router.post("/ifttt/remove-condition")
async def remove_condition_from_rule(data: Dict):
    """Удалить условие из правила"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты не доступны"}
    return ifttt_manager.remove_condition_from_rule(
        rule_name=data.get('rule_name', ''),
        condition_index=data.get('condition_index', 0)
    )

@router.post("/ifttt/set-logic")
async def set_rule_logic(data: Dict):
    """Установить логику правила (AND/OR)"""
    if not HAS_V32_FEATURES:
        return {"error": "Компоненты не доступны"}
    return ifttt_manager.set_rule_logic(
        rule_name=data.get('rule_name', ''),
        logic=data.get('logic', 'AND')
    )
