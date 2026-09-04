"""
Парсер голосовых команд для создания правил
Понимает естественный язык и преобразует в структурированные правила
"""

import re
from typing import Dict, Optional, List, Tuple


class VoiceRuleBuilder:
    """Парсит голосовые команды и создает правила"""
    
    # Шаблоны для распознавания
    RULE_PATTERNS = {
        'if_then': r'(?:если|когда)\s+(.+?)\s+(?:то|тогда)\s+(.+)',
        'create_command': r'(?:создай|добавь)\s+команду\s+["\']?(.+?)["\']?\s+(?:для|это)\s+(.+)',
        'apply_template': r'(?:применить|активировать)\s+шаблон\s+["\']?(.+?)["\']',
        'set_profile': r'(?:переключись|переходи)\s+(?:на|к)\s+профиль\s+["\']?(.+?)["\']',
    }
    
    TRIGGER_KEYWORDS = {
        'command': ['я скажу', 'ты услышишь', 'услышу', 'скажу', 'при слове'],
        'time': ['в ', 'каждый день', 'по расписанию', 'каждые'],
        'app': ['откроется', 'запустится'],
    }
    
    ACTION_KEYWORDS = {
        'execute_command': ['открой', 'запусти', 'включи', 'выполни', 'делай'],
        'send_notification': ['скажи', 'уведоми', 'напомни'],
        'open_app': ['открой', 'запусти', 'включи'],
    }
    
    def __init__(self):
        self.last_parsed = None
    
    def parse_voice_rule(self, text: str) -> Dict:
        """
        Парсить голосовую команду и вернуть структурированное правило
        
        Примеры:
        - "создай правило если я скажу работа то открой VS Code"
        - "если время 09:00 то открой браузер и включи музыку"
        - "когда я скажу начало дня то запусти Excel и Chrome"
        """
        text = text.lower().strip()
        
        # Попробовать распознать как правило если-то
        if_then_match = re.search(self.RULE_PATTERNS['if_then'], text)
        if if_then_match:
            condition_text = if_then_match.group(1).strip()
            action_text = if_then_match.group(2).strip()
            
            return self._build_rule_from_parts(condition_text, action_text)
        
        # Попробовать распознать как команду
        create_cmd_match = re.search(self.RULE_PATTERNS['create_command'], text)
        if create_cmd_match:
            cmd_name = create_cmd_match.group(1).strip()
            cmd_action = create_cmd_match.group(2).strip()
            
            return {
                'success': True,
                'type': 'command',
                'name': cmd_name,
                'action': cmd_action,
                'confidence': 0.9
            }
        
        # Попробовать распознать как применение шаблона
        template_match = re.search(self.RULE_PATTERNS['apply_template'], text)
        if template_match:
            template_name = template_match.group(1).strip()
            
            return {
                'success': True,
                'type': 'template',
                'name': template_name,
                'confidence': 0.85
            }
        
        return {
            'success': False,
            'message': 'Не удалось распознать команду',
            'data': None,
            'confidence': 0,
            'text': text
        }
    
    def _build_rule_from_parts(self, condition_text: str, action_text: str) -> Dict:
        """Построить правило из условия и действия"""
        # Определить тип триггера
        trigger_type, trigger_value = self._parse_condition(condition_text)
        
        if not trigger_type:
            return {'success': False, 'message': f'Неизвестный тип триггера: {condition_text}', 'data': None}
        
        # Определить тип действия
        action_type, action_value = self._parse_action(action_text)
        
        if not action_type:
            return {'success': False, 'message': f'Неизвестное действие: {action_text}', 'data': None}
        
        rule_name = f"Правило - {condition_text[:30]}"
        
        return {
            'success': True,
            'type': 'rule',
            'name': rule_name,
            'trigger_type': trigger_type,
            'trigger_value': trigger_value,
            'action_type': action_type,
            'action_value': action_value,
            'condition_text': condition_text,
            'action_text': action_text,
            'confidence': 0.85
        }
    
    def _parse_condition(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Парсить условие и вернуть (тип, значение)"""
        text = text.lower().strip()
        
        # Проверить на команду
        for keyword in self.TRIGGER_KEYWORDS['command']:
            if keyword in text:
                # Извлечь слово
                match = re.search(rf'{keyword}\s+["\']?(.+?)["\']?\s*$', text)
                if match:
                    value = match.group(1).strip()
                    return ('command_contains', value)
        
        # Проверить на время
        for keyword in self.TRIGGER_KEYWORDS['time']:
            if keyword in text:
                # Извлечь время
                time_match = re.search(r'(\d{1,2}):(\d{2})', text)
                if time_match:
                    return ('time', f"{time_match.group(1)}:{time_match.group(2)}")
                
                # Или период
                period_match = re.search(r'каждые?\s+(\d+)\s+(минут|часов)', text)
                if period_match:
                    return ('every_n_minutes', int(period_match.group(1)))
        
        # Проверить на приложение
        for keyword in self.TRIGGER_KEYWORDS['app']:
            if keyword in text:
                match = re.search(rf'{keyword}\s+["\']?(.+?)["\']?\s*$', text)
                if match:
                    value = match.group(1).strip()
                    return ('app_opened', value)
        
        return None, None
    
    def _parse_action(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Парсить действие и вернуть (тип, значение)"""
        text = text.lower().strip()
        
        # Проверить на выполнение команды
        for keyword in self.ACTION_KEYWORDS['execute_command']:
            if text.startswith(keyword):
                value = text[len(keyword):].strip()
                return ('execute_command', value)
        
        # Проверить на уведомление
        for keyword in self.ACTION_KEYWORDS['send_notification']:
            if text.startswith(keyword):
                value = text[len(keyword):].strip()
                return ('send_notification', value)
        
        # По умолчанию считать это команда
        if text:
            return ('execute_command', text)
        
        return None, None
    
    def parse_macro_instruction(self, text: str) -> Dict:
        """
        Парсить инструкцию для макроса
        
        Примеры:
        - "клик по координатам 100 200"
        - "напечатай привет мир"
        - "жди 2 секунды"
        """
        text = text.lower().strip()
        
        # Клик
        click_match = re.search(r'клик\s+(?:по|в)\s+(\d+)\s+(\d+)', text)
        if click_match:
            return {
                'success': True,
                'action_type': 'click',
                'x': int(click_match.group(1)),
                'y': int(click_match.group(2)),
                'confidence': 0.9
            }
        
        # Ввод текста
        if 'напечатай' in text or 'введи' in text:
            value = re.sub(r'(?:напечатай|введи)\s+', '', text).strip()
            return {
                'success': True,
                'action_type': 'type',
                'target': value,
                'confidence': 0.85
            }
        
        # Ожидание
        wait_match = re.search(r'жди\s+(\d+)\s+(?:сек|секунд)', text)
        if wait_match:
            return {
                'success': True,
                'action_type': 'wait',
                'target': str(int(wait_match.group(1)) * 1000),  # в миллисекунды
                'confidence': 0.9
            }
        
        # Команда
        if 'выполни' in text or 'запусти' in text:
            value = re.sub(r'(?:выполни|запусти)\s+', '', text).strip()
            return {
                'success': True,
                'action_type': 'command',
                'target': value,
                'confidence': 0.85
            }
        
        return {'success': False, 'message': f'Неизвестная инструкция: {text}', 'data': None}
    
    def suggest_rule_name(self, trigger_type: str, trigger_value: str) -> str:
        """Сгенерировать название правила"""
        names = {
            'command_contains': f'Когда услышу "{trigger_value}"',
            'time': f'В {trigger_value}',
            'app_opened': f'Когда откроется {trigger_value}',
            'every_n_minutes': f'Каждые {trigger_value} минут',
        }
        
        return names.get(trigger_type, f'Правило: {trigger_value}')
    
    def validate_rule(self, rule_data: Dict) -> Dict:
        """Проверить правило на корректность"""
        if 'error' in rule_data:
            return {'valid': False, 'error': rule_data['error']}
        
        if rule_data.get('type') == 'rule':
            required_fields = ['trigger_type', 'trigger_value', 'action_type', 'action_value']
            for field in required_fields:
                if not rule_data.get(field):
                    return {'valid': False, 'error': f'Отсутствует поле: {field}'}
        
        return {'valid': True, 'confidence': rule_data.get('confidence', 0.5)}


def get_voice_rule_builder() -> VoiceRuleBuilder:
    """Factory функция"""
    return VoiceRuleBuilder()
