"""
Рекордер макросов - запись и воспроизведение последовательностей действий
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class ActionType(Enum):
    """Типы действий в макросе"""
    CLICK = 'click'                    # Клик мыши
    TYPE = 'type'                      # Ввод текста
    WAIT = 'wait'                      # Ожидание N мс
    COMMAND = 'command'                # Выполнить Scott команду
    KEY_PRESS = 'key_press'            # Нажать клавишу
    OPEN_APP = 'open_app'              # Открыть приложение
    SCREENSHOT = 'screenshot'          # Снимок экрана


class MacroAction:
    """Одно действие в макросе"""
    
    def __init__(self, action_type: str, target: str, timestamp: int,
                 x: int = 0, y: int = 0, details: Dict = None):
        self.action_type = action_type
        self.target = target  # Текст, приложение, клавиша или координаты
        self.timestamp = timestamp  # Время от начала записи
        self.x = x  # X координата для кликов
        self.y = y  # Y координата для кликов
        self.details = details or {}
    
    def to_dict(self) -> Dict:
        return {
            'action_type': self.action_type,
            'target': self.target,
            'timestamp': self.timestamp,
            'x': self.x,
            'y': self.y,
            'details': self.details
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'MacroAction':
        return MacroAction(
            action_type=data['action_type'],
            target=data['target'],
            timestamp=data['timestamp'],
            x=data.get('x', 0),
            y=data.get('y', 0),
            details=data.get('details', {})
        )


class Macro:
    """Макрос - последовательность записанных действий"""
    
    def __init__(self, name: str, description: str = ''):
        self.name = name
        self.description = description
        self.actions: List[MacroAction] = []
        self.created_at = datetime.now().isoformat()
        self.last_executed = None
        self.execution_count = 0
        self.enabled = True
        self.loop_count = 1  # Сколько раз повторять макрос
    
    def add_action(self, action_type: str, target: str, timestamp: int,
                  x: int = 0, y: int = 0, details: Dict = None) -> None:
        """Добавить действие к макросу"""
        action = MacroAction(action_type, target, timestamp, x, y, details)
        self.actions.append(action)
    
    def get_duration(self) -> int:
        """Получить общую длительность макроса в миллисекундах"""
        if not self.actions:
            return 0
        return max(action.timestamp for action in self.actions)
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'actions': [action.to_dict() for action in self.actions],
            'created_at': self.created_at,
            'last_executed': self.last_executed,
            'execution_count': self.execution_count,
            'enabled': self.enabled,
            'loop_count': self.loop_count,
            'duration_ms': self.get_duration()
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Macro':
        macro = Macro(
            name=data['name'],
            description=data.get('description', '')
        )
        
        for action_data in data.get('actions', []):
            macro.actions.append(MacroAction.from_dict(action_data))
        
        macro.created_at = data.get('created_at', macro.created_at)
        macro.last_executed = data.get('last_executed')
        macro.execution_count = data.get('execution_count', 0)
        macro.enabled = data.get('enabled', True)
        macro.loop_count = data.get('loop_count', 1)
        return macro


class MacroRecorder:
    """Менеджер макросов - запись и воспроизведение"""
    
    def __init__(self, db_path: str = 'data/macros.json'):
        self.db_path = Path(db_path)
        self.data_dir = str(self.db_path.parent)  # Для совместимости с тестами
        self.macros: Dict[str, Macro] = {}
        self.is_recording = False
        self.current_recording: Optional[Macro] = None
        self.recording_start_time = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_macros()
        print(f"✅ Рекордер макросов инициализирован ({len(self.macros)} макросов)")
    
    def load_macros(self) -> None:
        """Загрузить макросы из файла"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for macro_name, macro_data in data.items():
                        self.macros[macro_name] = Macro.from_dict(macro_data)
                    print(f"📂 Загружено {len(self.macros)} макросов")
            except Exception as e:
                print(f"❌ Ошибка загрузки макросов: {e}")
    
    def save_macros(self) -> None:
        """Сохранить макросы в файл"""
        try:
            data = {name: macro.to_dict() for name, macro in self.macros.items()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(self.macros)} макросов")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def start_recording(self, macro_name: str, description: str = '') -> Dict:
        """Начать запись нового макроса"""
        if self.is_recording:
            return {'success': False, 'message': 'Запись уже идет', 'data': None}
        
        if macro_name in self.macros:
            return {'success': False, 'message': f'Макрос "{macro_name}" уже существует', 'data': None}
        
        self.is_recording = True
        self.current_recording = Macro(macro_name, description)
        self.recording_start_time = datetime.now()
        
        return {'success': True, 'message': f'Запись макроса "{macro_name}" началась 🔴', 'data': {'name': macro_name, 'recording': True}}
    
    def stop_recording(self) -> Dict:
        """Остановить запись"""
        if not self.is_recording or not self.current_recording:
            return {'success': False, 'message': 'Нет активной записи', 'data': None}
        
        macro = self.current_recording
        macro_name = macro.name
        
        self.macros[macro_name] = macro
        self.save_macros()
        
        self.is_recording = False
        duration = macro.get_duration()
        
        result = {
            'success': True,
            'message': f'Запись макроса "{macro_name}" завершена ✅',
            'data': macro.to_dict(),
            'stats': {
                'total_actions': len(macro.actions),
                'duration_ms': duration,
                'duration_s': round(duration / 1000, 2)
            }
        }
        
        self.current_recording = None
        return result
    
    def cancel_recording(self) -> Dict:
        """Отменить запись"""
        if not self.is_recording:
            return {'success': False, 'message': 'Нет активной записи', 'data': None}
        
        self.is_recording = False
        macro_name = self.current_recording.name if self.current_recording else 'unknown'
        self.current_recording = None
        
        return {'success': True, 'message': f'Запись макроса "{macro_name}" отменена ❌', 'data': {'name': macro_name}}
    
    def record_action(self, action_type: str, target: str, x: int = 0, y: int = 0,
                     details: Dict = None) -> Dict:
        """Записать действие"""
        if not self.is_recording or not self.current_recording:
            return {'success': False, 'message': 'Запись не активна', 'data': None}
        
        timestamp = int((datetime.now() - self.recording_start_time).total_seconds() * 1000)
        self.current_recording.add_action(action_type, target, timestamp, x, y, details)
        
        return {'success': True, 'message': f'Действие записано ({action_type})', 'data': {'timestamp_ms': timestamp}}
    
    def execute_macro(self, macro_name: str, loop_count: int = 1) -> Dict:
        """Выполнить макрос"""
        macro = self.get_macro(macro_name)
        if not macro:
            return {'success': False, 'message': f'Макрос "{macro_name}" не найден', 'data': None}
        
        if not macro.enabled:
            return {'success': False, 'message': f'Макрос "{macro_name}" отключен', 'data': None}
        
        if not macro.actions:
            return {'success': False, 'message': f'Макрос "{macro_name}" пуст (нет действий)', 'data': None}
        
        macro.last_executed = datetime.now().isoformat()
        macro.execution_count += 1
        self.save_macros()
        
        return {
            'success': True,
            'message': f'Выполняю макрос "{macro_name}" (повтор: {loop_count})',
            'data': {
                'macro': macro.to_dict(),
                'execution': {
                    'total_actions': len(macro.actions),
                    'duration_ms': macro.get_duration(),
                    'loop_count': loop_count,
                    'total_duration_ms': macro.get_duration() * loop_count
                }
            }
        }
    
    def get_macro(self, name: str) -> Optional[Macro]:
        """Получить макрос"""
        return self.macros.get(name)
    
    def delete_macro(self, name: str) -> Dict:
        """Удалить макрос"""
        if name not in self.macros:
            return {'success': False, 'message': f'Макрос "{name}" не найден', 'data': None}
        
        del self.macros[name]
        self.save_macros()
        return {'success': True, 'message': f'Макрос "{name}" удален', 'data': {'name': name}}
    
    def list_macros(self, enabled_only: bool = True) -> List[Dict]:
        """Список всех макросов"""
        macros = [m.to_dict() for m in self.macros.values()]
        if enabled_only:
            macros = [m for m in macros if m['enabled']]
        return macros
    
    def get_recording_status(self) -> Dict:
        """Получить статус записи"""
        if not self.is_recording:
            return {'is_recording': False, 'current_macro': None}
        
        elapsed = int((datetime.now() - self.recording_start_time).total_seconds() * 1000)
        
        return {
            'is_recording': True,
            'current_macro': self.current_recording.name,
            'elapsed_ms': elapsed,
            'elapsed_s': round(elapsed / 1000, 2),
            'actions_recorded': len(self.current_recording.actions)
        }
    
    def __repr__(self):
        return f"MacroRecorder({len(self.macros)} макросов, запись: {self.is_recording})"


def get_macro_recorder(db_path: str = 'data/macros.json') -> MacroRecorder:
    """Factory функция"""
    return MacroRecorder(db_path)
