"""
Менеджер контекстов - запоминает переменные и контекст разговора
"""

from typing import Dict, Any, List
from datetime import datetime
import json

class ContextManager:
    """Управляет контекстом разговора и переменными"""
    
    def __init__(self):
        self.context: Dict[str, Any] = {}
        self.history: List[Dict] = []
        self.variables: Dict[str, Any] = {
            'current_app': None,
            'current_folder': None,
            'last_search': None,
            'user_name': 'User',
            'last_command': None,
            'last_response': None,
        }
        print("✅ Менеджер контекстов инициализирован")
    
    def set_variable(self, key: str, value: Any) -> None:
        """Установить переменную контекста"""
        self.variables[key] = value
        print(f"📝 Переменная установлена: {key} = {value}")
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """Получить значение переменной"""
        return self.variables.get(key, default)
    
    def update_context(self, data: Dict[str, Any]) -> None:
        """Обновить контекст"""
        self.context.update(data)
    
    def get_context(self) -> Dict[str, Any]:
        """Получить весь контекст"""
        return {
            'variables': self.variables,
            'context': self.context,
            'history_size': len(self.history)
        }
    
    def add_to_history(self, command: str, response: str, command_type: str = '') -> None:
        """Добавить взаимодействие в историю контекста"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'command': command,
            'response': response,
            'type': command_type,
            'context_snapshot': dict(self.variables)
        }
        self.history.append(entry)
        
        # Обновить текущий контекст
        self.variables['last_command'] = command
        self.variables['last_response'] = response
        
        # Очистить историю если она слишком большая
        if len(self.history) > 100:
            self.history = self.history[-100:]
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """Получить последние взаимодействия"""
        return self.history[-limit:]
    
    def infer_from_context(self, command: str) -> Dict[str, Any]:
        """
        Выводы из контекста:
        "открой его" -> если last_app = Chrome, то "открой Chrome"
        "перейди там" -> если last_search, то открыть в браузере
        """
        inferences = {}
        
        # Анализ местоимений и указателей
        if 'его' in command or 'ее' in command or 'это' in command:
            if self.variables['current_app']:
                inferences['inferred_app'] = self.variables['current_app']
        
        if 'там' in command or 'туда' in command:
            if self.variables['current_folder']:
                inferences['inferred_folder'] = self.variables['current_folder']
            elif self.variables['last_search']:
                inferences['inferred_search'] = self.variables['last_search']
        
        if 'еще' in command or 'опять' in command:
            if self.variables['last_command']:
                inferences['repeat_last'] = True
                inferences['last_command'] = self.variables['last_command']
        
        return inferences
    
    def clear_context(self) -> None:
        """Очистить контекст"""
        self.context = {}
        self.history = []
        self.variables = {
            'current_app': None,
            'current_folder': None,
            'last_search': None,
            'user_name': 'User',
            'last_command': None,
            'last_response': None,
        }
        print("🧹 Контекст очищен")
    
    def export_context(self) -> Dict:
        """Экспортировать контекст для сохранения"""
        return {
            'variables': self.variables,
            'context': self.context,
            'history': self.history[-50:]  # Последние 50 элементов
        }
    
    def import_context(self, data: Dict) -> None:
        """Импортировать контекст из сохраненных данных"""
        if 'variables' in data:
            self.variables.update(data['variables'])
        if 'context' in data:
            self.context.update(data['context'])
        if 'history' in data:
            self.history = data['history']
        print("✅ Контекст восстановлен")
    
    def __repr__(self):
        return f"ContextManager(vars={len(self.variables)}, history={len(self.history)})"


def get_context_manager() -> ContextManager:
    """Factory функция"""
    return ContextManager()
