"""
IFTTT система - если X произойдет, то выполнить Y
Расширенная с Smart Conditions (AND/OR/NOT логика)
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from enum import Enum


class Condition:
    """Одно условие (триггер) в правиле"""
    
    def __init__(self, trigger_type: str, trigger_value: str, negate: bool = False):
        self.trigger_type = trigger_type
        self.trigger_value = trigger_value
        self.negate = negate  # Инвертировать результат (NOT)
    
    def evaluate(self, input_value: str) -> bool:
        """Оценить условие"""
        result = False
        
        if self.trigger_type == 'command_contains':
            result = self.trigger_value.lower() in input_value.lower()
        elif self.trigger_type == 'command_equals':
            result = self.trigger_value.lower() == input_value.lower()
        elif self.trigger_type == 'time':
            # Проверка времени будет в основном логике
            result = True
        elif self.trigger_type == 'app_opened':
            result = input_value.lower() == self.trigger_value.lower()
        else:
            result = True
        
        return not result if self.negate else result
    
    def to_dict(self) -> Dict:
        return {
            'trigger_type': self.trigger_type,
            'trigger_value': self.trigger_value,
            'negate': self.negate
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Condition':
        return Condition(
            trigger_type=data['trigger_type'],
            trigger_value=data['trigger_value'],
            negate=data.get('negate', False)
        )

class TriggerType(Enum):
    """Типы триггеров"""
    TIME = 'time'                    # время (HH:MM)
    TIME_RANGE = 'time_range'        # диапазон времени (9:00-17:00)
    COMMAND_CONTAINS = 'command_contains'  # команда содержит слово
    COMMAND_EQUALS = 'command_equals'      # команда равна
    EVERY_N_MINUTES = 'every_n_minutes'    # каждые N минут
    EVERY_N_HOURS = 'every_n_hours'        # каждые N часов
    WHEN_APP_OPENS = 'when_app_opens'      # когда открывается приложение
    WHEN_FILE_CREATED = 'when_file_created'  # когда создан файл
    AFTER_LAST_COMMAND = 'after_last_command'  # через N сек после последней команды

class ActionType(Enum):
    """Типы действий"""
    EXECUTE_COMMAND = 'execute_command'      # выполнить команду
    SEND_NOTIFICATION = 'send_notification'  # отправить уведомление
    RUN_SCRIPT = 'run_script'                # запустить скрипт
    OPEN_APP = 'open_app'                    # открыть приложение
    SEND_MESSAGE = 'send_message'            # отправить сообщение
    CUSTOM_ACTION = 'custom_action'          # кастомное действие


class Rule:
    """Правило IFTTT с поддержкой Smart Conditions (AND/OR/NOT)"""
    
    def __init__(self, name: str, action_type: ActionType, action_value: str, 
                 description: str = '', logic: str = 'AND'):
        self.name = name
        self.conditions: List[Condition] = []  # Может быть несколько условий
        self.logic = logic  # 'AND' или 'OR' - как комбинировать условия
        self.action_type = action_type
        self.action_value = action_value
        self.description = description
        self.created_at = datetime.now().isoformat()
        self.enabled = True
        self.execution_count = 0
        self.last_execution = None
    
    def add_condition(self, trigger_type: str, trigger_value: str, negate: bool = False) -> None:
        """Добавить условие к правилу"""
        self.conditions.append(Condition(trigger_type, trigger_value, negate))
    
    def evaluate(self, input_value: str) -> bool:
        """
        Оценить все условия согласно логике
        AND: все условия должны быть True
        OR: хотя бы одно условие должно быть True
        """
        if not self.conditions:
            return True  # Если нет условий, правило всегда выполняется
        
        results = [cond.evaluate(input_value) for cond in self.conditions]
        
        if self.logic == 'AND':
            return all(results)
        elif self.logic == 'OR':
            return any(results)
        else:
            return all(results)  # По умолчанию AND
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'conditions': [cond.to_dict() for cond in self.conditions],
            'logic': self.logic,
            'action_type': self.action_type.value,
            'action_value': self.action_value,
            'description': self.description,
            'created_at': self.created_at,
            'enabled': self.enabled,
            'execution_count': self.execution_count,
            'last_execution': self.last_execution
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Rule':
        rule = Rule(
            name=data['name'],
            action_type=ActionType(data['action_type']),
            action_value=data['action_value'],
            description=data.get('description', ''),
            logic=data.get('logic', 'AND')
        )
        
        # Загрузить условия
        for cond_data in data.get('conditions', []):
            rule.conditions.append(Condition.from_dict(cond_data))
        
        rule.created_at = data.get('created_at', rule.created_at)
        rule.enabled = data.get('enabled', True)
        rule.execution_count = data.get('execution_count', 0)
        rule.last_execution = data.get('last_execution')
        return rule


class IFTTTManager:
    """Управляет правилами IFTTT"""
    
    def __init__(self, db_path: str = 'data/ifttt_rules.json'):
        self.db_path = Path(db_path)
        self.rules: Dict[str, Rule] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_rules()
        print(f"✅ Менеджер IFTTT инициализирован ({len(self.rules)} правил)")
    
    def load_rules(self) -> None:
        """Загрузить правила из файла"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for rule_name, rule_data in data.items():
                        self.rules[rule_name] = Rule.from_dict(rule_data)
                    print(f"📂 Загружено {len(self.rules)} IFTTT правил")
            except Exception as e:
                print(f"❌ Ошибка загрузки правил: {e}")
    
    def save_rules(self) -> None:
        """Сохранить правила в файл"""
        try:
            data = {name: rule.to_dict() for name, rule in self.rules.items()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(self.rules)} правил")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def add_rule(self, name: str, action_type: str, action_value: str,
                 conditions_data: List[Dict] = None, logic: str = 'AND',
                 description: str = '') -> Dict:
        """Добавить новое правило с условиями"""
        if name in self.rules:
            return {'success': False, 'error': f'Правило "{name}" уже существует'}
        
        try:
            action = ActionType(action_type)
        except ValueError as e:
            return {'success': False, 'error': f'Неверный тип действия: {e}'}
        
        rule = Rule(name, action, action_value, description, logic)
        
        # Добавить условия если они предоставлены
        if conditions_data:
            for cond in conditions_data:
                rule.add_condition(
                    trigger_type=cond.get('trigger_type', ''),
                    trigger_value=cond.get('trigger_value', ''),
                    negate=cond.get('negate', False)
                )
        
        self.rules[name] = rule
        self.save_rules()
        return {'success': True, 'message': f'Правило "{name}" добавлено', 'rule': rule.to_dict()}
    
    def update_rule(self, name: str, **kwargs) -> Dict:
        """Обновить правило"""
        if name not in self.rules:
            return {'success': False, 'error': f'Правило "{name}" не найдено'}
        
        rule = self.rules[name]
        
        if 'action_value' in kwargs:
            rule.action_value = kwargs['action_value']
        if 'description' in kwargs:
            rule.description = kwargs['description']
        if 'enabled' in kwargs:
            rule.enabled = kwargs['enabled']
        if 'logic' in kwargs:
            rule.logic = kwargs['logic']
        if 'conditions' in kwargs:
            rule.conditions = []
            for cond in kwargs['conditions']:
                rule.add_condition(
                    trigger_type=cond.get('trigger_type', ''),
                    trigger_value=cond.get('trigger_value', ''),
                    negate=cond.get('negate', False)
                )
        
        self.save_rules()
        return {'success': True, 'message': f'Правило "{name}" обновлено', 'rule': rule.to_dict()}
    
    def delete_rule(self, name: str) -> Dict:
        """Удалить правило"""
        if name not in self.rules:
            return {'success': False, 'error': f'Правило "{name}" не найдено'}
        
        del self.rules[name]
        self.save_rules()
        return {'success': True, 'message': f'Правило "{name}" удалено'}
    
    def get_rule(self, name: str) -> Optional[Rule]:
        """Получить правило"""
        return self.rules.get(name)
    
    def get_all_rules(self, enabled_only: bool = True) -> List[Dict]:
        """Получить все правила"""
        rules = [rule.to_dict() for rule in self.rules.values()]
        if enabled_only:
            rules = [r for r in rules if r['enabled']]
        return rules
    
    def check_triggers(self, trigger_type: str, trigger_value: str) -> List[Rule]:
        """
        Проверить какие правила должны быть выполнены
        """
        triggered_rules = []
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Оценить все условия в правиле
            if rule.evaluate(trigger_value):
                triggered_rules.append(rule)
        
        return triggered_rules
    
    def add_condition_to_rule(self, rule_name: str, trigger_type: str, trigger_value: str,
                              negate: bool = False) -> Dict:
        """Добавить условие к существующему правилу"""
        rule = self.get_rule(rule_name)
        if not rule:
            return {'success': False, 'error': f'Правило "{rule_name}" не найдено'}
        
        rule.add_condition(trigger_type, trigger_value, negate)
        self.save_rules()
        return {'success': True, 'message': f'Условие добавлено к правилу "{rule_name}"', 'rule': rule.to_dict()}
    
    def remove_condition_from_rule(self, rule_name: str, condition_index: int) -> Dict:
        """Удалить условие из правила"""
        rule = self.get_rule(rule_name)
        if not rule:
            return {'success': False, 'error': f'Правило "{rule_name}" не найдено'}
        
        if condition_index < 0 or condition_index >= len(rule.conditions):
            return {'success': False, 'error': 'Индекс условия недействителен'}
        
        del rule.conditions[condition_index]
        self.save_rules()
        return {'success': True, 'message': f'Условие удалено из правила "{rule_name}"', 'rule': rule.to_dict()}
    
    def set_rule_logic(self, rule_name: str, logic: str) -> Dict:
        """Установить логику для правила (AND или OR)"""
        rule = self.get_rule(rule_name)
        if not rule:
            return {'success': False, 'error': f'Правило "{rule_name}" не найдено'}
        
        if logic not in ['AND', 'OR']:
            return {'success': False, 'error': 'Логика должна быть AND или OR'}
        
        rule.logic = logic
        self.save_rules()
        return {'success': True, 'message': f'Логика правила "{rule_name}" установлена на {logic}', 'rule': rule.to_dict()}
    
    def execute_rule(self, rule_name: str) -> Dict:
        """Выполнить правило"""
        rule = self.get_rule(rule_name)
        if not rule:
            return {'success': False, 'error': f'Правило "{rule_name}" не найдено'}
        
        if not rule.enabled:
            return {'success': False, 'error': f'Правило "{rule_name}" отключено'}
        
        rule.execution_count += 1
        rule.last_execution = datetime.now().isoformat()
        self.save_rules()
        
        return {
            'success': True,
            'message': f'Правило "{rule_name}" выполнено',
            'action_type': rule.action_type.value,
            'action_value': rule.action_value,
            'rule': rule.to_dict()
        }
    
    def get_statistics(self) -> Dict:
        """Получить статистику"""
        total = len(self.rules)
        enabled = sum(1 for r in self.rules.values() if r.enabled)
        most_triggered = sorted(self.rules.values(), key=lambda r: r.execution_count, reverse=True)[:5]
        
        return {
            'total_rules': total,
            'enabled_rules': enabled,
            'disabled_rules': total - enabled,
            'most_triggered': [
                {'name': r.name, 'execution_count': r.execution_count} for r in most_triggered
            ]
        }
    
    def __repr__(self):
        return f"IFTTTManager({len(self.rules)} правил)"


def get_ifttt_manager(db_path: str = 'data/ifttt_rules.json') -> IFTTTManager:
    """Factory функция"""
    return IFTTTManager(db_path)
