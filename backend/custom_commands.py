"""
Менеджер кастомных команд - позволяет создавать свои команды
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

class CustomCommand:
    """Структура кастомной команды"""
    
    def __init__(self, name: str, trigger: str, action: str, description: str = ''):
        self.name = name
        self.trigger = trigger  # слово/фраза которая триггерит команду
        self.action = action    # что делать (может быть другая команда)
        self.description = description
        self.created_at = datetime.now().isoformat()
        self.usage_count = 0
        self.enabled = True
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'trigger': self.trigger,
            'action': self.action,
            'description': self.description,
            'created_at': self.created_at,
            'usage_count': self.usage_count,
            'enabled': self.enabled
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'CustomCommand':
        cmd = CustomCommand(
            name=data['name'],
            trigger=data['trigger'],
            action=data['action'],
            description=data.get('description', '')
        )
        cmd.created_at = data.get('created_at', cmd.created_at)
        cmd.usage_count = data.get('usage_count', 0)
        cmd.enabled = data.get('enabled', True)
        return cmd


class CustomCommandManager:
    """Управляет кастомными командами"""
    
    def __init__(self, db_path: str = 'data/custom_commands.json'):
        self.db_path = Path(db_path)
        self.commands: Dict[str, CustomCommand] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_commands()
        print(f"✅ Менеджер кастомных команд инициализирован ({len(self.commands)} команд)")
    
    def load_commands(self) -> None:
        """Загрузить команды из файла"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for cmd_name, cmd_data in data.items():
                        self.commands[cmd_name] = CustomCommand.from_dict(cmd_data)
                    print(f"📂 Загружено {len(self.commands)} кастомных команд")
            except Exception as e:
                print(f"❌ Ошибка загрузки команд: {e}")
    
    def save_commands(self) -> None:
        """Сохранить команды в файл"""
        try:
            data = {name: cmd.to_dict() for name, cmd in self.commands.items()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(self.commands)} команд")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def add_command(self, name: str, trigger: str, action: str, description: str = '') -> Dict:
        """Добавить новую команду"""
        if name in self.commands:
            return {'success': False, 'error': f'Команда "{name}" уже существует'}
        
        if not trigger or not action:
            return {'success': False, 'error': 'Триггер и действие обязательны'}
        
        cmd = CustomCommand(name, trigger, action, description)
        self.commands[name] = cmd
        self.save_commands()
        return {'success': True, 'message': f'Команда "{name}" добавлена', 'command': cmd.to_dict()}
    
    def update_command(self, name: str, **kwargs) -> Dict:
        """Обновить существующую команду"""
        if name not in self.commands:
            return {'success': False, 'error': f'Команда "{name}" не найдена'}
        
        cmd = self.commands[name]
        
        if 'trigger' in kwargs:
            cmd.trigger = kwargs['trigger']
        if 'action' in kwargs:
            cmd.action = kwargs['action']
        if 'description' in kwargs:
            cmd.description = kwargs['description']
        if 'enabled' in kwargs:
            cmd.enabled = kwargs['enabled']
        
        self.save_commands()
        return {'success': True, 'message': f'Команда "{name}" обновлена', 'command': cmd.to_dict()}
    
    def delete_command(self, name: str) -> Dict:
        """Удалить команду"""
        if name not in self.commands:
            return {'success': False, 'error': f'Команда "{name}" не найдена'}
        
        del self.commands[name]
        self.save_commands()
        return {'success': True, 'message': f'Команда "{name}" удалена'}
    
    def get_command(self, name: str) -> Optional[CustomCommand]:
        """Получить команду по названию"""
        return self.commands.get(name)
    
    def get_all_commands(self, enabled_only: bool = True) -> List[Dict]:
        """Получить все команды"""
        commands = [cmd.to_dict() for cmd in self.commands.values()]
        if enabled_only:
            commands = [c for c in commands if c['enabled']]
        return commands
    
    def find_command_by_trigger(self, trigger_word: str) -> Optional[CustomCommand]:
        """Найти команду по слову-триггеру"""
        for cmd in self.commands.values():
            if not cmd.enabled:
                continue
            
            if cmd.trigger.lower() in trigger_word.lower() or trigger_word.lower() in cmd.trigger.lower():
                return cmd
        return None
    
    def execute_custom_command(self, name: str) -> Dict:
        """Выполнить кастомную команду"""
        cmd = self.get_command(name)
        if not cmd:
            return {'success': False, 'error': f'Команда "{name}" не найдена'}
        
        if not cmd.enabled:
            return {'success': False, 'error': f'Команда "{name}" отключена'}
        
        cmd.usage_count += 1
        self.save_commands()
        
        return {
            'success': True,
            'message': f'Выполняю команду: {name}',
            'action': cmd.action,
            'command': cmd.to_dict()
        }
    
    def get_statistics(self) -> Dict:
        """Получить статистику команд"""
        total = len(self.commands)
        enabled = sum(1 for c in self.commands.values() if c.enabled)
        most_used = sorted(self.commands.values(), key=lambda c: c.usage_count, reverse=True)[:5]
        
        return {
            'total_commands': total,
            'enabled_commands': enabled,
            'disabled_commands': total - enabled,
            'most_used': [
                {'name': c.name, 'usage_count': c.usage_count} for c in most_used
            ]
        }
    
    def __repr__(self):
        return f"CustomCommandManager({len(self.commands)} команд)"


def get_custom_command_manager(db_path: str = 'data/custom_commands.json') -> CustomCommandManager:
    """Factory функция"""
    return CustomCommandManager(db_path)
