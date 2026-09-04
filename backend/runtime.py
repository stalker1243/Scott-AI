"""
Компоненты, которые живут всё время работы процесса, — в одном месте.

Раньше они создавались прямо в main.py, и это мешало разносить эндпоинты по
роутерам: фабрики вроде get_ifttt_manager() возвращают КАЖДЫЙ РАЗ НОВЫЙ
экземпляр, а не синглтон, поэтому роутер, вызвавший фабрику у себя, получил бы
менеджер с собственным состоянием в памяти. Правила, добавленные через один
экземпляр, не были бы видны другому до перезапуска. Здесь же экземпляр
создаётся ровно один раз, при импорте модуля, и все обращаются к нему.

Импортировать следует сам модуль, а не имена из него:

    from runtime import extended_executor      # так НЕЛЬЗЯ
    import runtime; runtime.extended_executor  # а так правильно

Разница существенна для флагов и ссылок, которые могут быть переопределены:
`from` копирует значение в момент импорта, и позднейшая замена объекта в
runtime до импортировавшего не дойдёт.
"""

# Двойные импорты (относительный, затем обычный) — тот же приём, что и в
# main.py: backend запускается и как пакет, и как скрипт из своей папки.

# ==================== Расширенные команды (v3.1) ====================
try:
    try:
        from .command_executor_extended import get_extended_executor
    except ImportError:
        from command_executor_extended import get_extended_executor
    HAS_EXTENDED_EXECUTOR = True
    extended_executor = get_extended_executor()
except ImportError:
    HAS_EXTENDED_EXECUTOR = False
    extended_executor = None
    print("⚠️ Расширенный исполнитель не доступен")


# ==================== Компоненты v3.2 ====================
try:
    try:
        from .context_manager import get_context_manager
        from .custom_commands import get_custom_command_manager
        from .ifttt_rules import get_ifttt_manager
        from .analytics_manager import get_analytics_manager
    except ImportError:
        from context_manager import get_context_manager
        from custom_commands import get_custom_command_manager
        from ifttt_rules import get_ifttt_manager
        from analytics_manager import get_analytics_manager

    context_manager = get_context_manager()
    custom_commands_manager = get_custom_command_manager()
    ifttt_manager = get_ifttt_manager()
    analytics_manager = get_analytics_manager(extended_executor)

    HAS_V32_FEATURES = True
    print("✅ Компоненты v3.2 загружены")
except ImportError as e:
    HAS_V32_FEATURES = False
    print(f"⚠️ Компоненты v3.2 не доступны: {e}")
    context_manager = None
    custom_commands_manager = None
    ifttt_manager = None
    analytics_manager = None
