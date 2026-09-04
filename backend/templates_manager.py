"""
Менеджер шаблонов - готовые сценарии для быстрого старта
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class Template:
    """Шаблон готового сценария"""
    
    def __init__(self, name: str, category: str, description: str = "",
                 commands: List[str] = None, rules: List[Dict] = None, icon: str = '🎯'):
        self.name = name
        self.category = category  # 'morning', 'work', 'evening', 'gaming', 'custom'
        self.description = description
        self.commands = commands or []  # Список команд для создания
        self.rules = rules or []  # Список правил для создания
        self.icon = icon
        self.created_at = datetime.now().isoformat()
        self.popularity = 0  # Сколько раз использован этот шаблон
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'category': self.category,
            'description': self.description,
            'commands': self.commands,
            'rules': self.rules,
            'icon': self.icon,
            'created_at': self.created_at,
            'popularity': self.popularity
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'Template':
        template = Template(
            name=data['name'],
            category=data['category'],
            description=data['description'],
            commands=data.get('commands', []),
            rules=data.get('rules', []),
            icon=data.get('icon', '🎯')
        )
        template.created_at = data.get('created_at', template.created_at)
        template.popularity = data.get('popularity', 0)
        return template


class TemplateManager:
    """Управляет шаблонами"""
    
    def __init__(self, db_path: str = 'data/templates.json'):
        self.db_path = Path(db_path)
        self.data_dir = str(self.db_path.parent)  # Для совместимости с тестами
        self.templates: Dict[str, Template] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Сначала грузим то, что уже есть на диске (включая пользовательские
        # шаблоны), и только потом добавляем недостающие встроенные — раньше
        # здесь вызывался init_default_templates() без предварительной
        # загрузки, и он же перезаписывал файл только 7 дефолтами при каждом
        # старте, теряя все кастомные шаблоны пользователя.
        self.load_templates()
        self.init_default_templates()
        print(f"✅ Менеджер шаблонов инициализирован ({len(self.templates)} шаблонов)")
    
    def init_default_templates(self) -> None:
        """Добавить встроенные шаблоны — только те, которых ещё нет (не
        перезаписывает уже загруженные/пользовательские)."""
        default_templates = [
            # Утренняя рутина
            Template(
                name='Утренняя рутина',
                category='morning',
                description='Полный набор для начала рабочего дня',
                icon='🌅',
                commands=[
                    'Открой Chrome',
                    'Открой Telegram',
                    'Открой Spotify',
                    'Включи фокус-режим'
                ],
                rules=[
                    {
                        'name': 'утро-автоматика',
                        'action_type': 'execute_command',
                        'action_value': 'открой Chrome и Telegram',
                        'conditions': [
                            {'trigger_type': 'time', 'trigger_value': '09:00', 'negate': False}
                        ]
                    }
                ]
            ),
            
            # Рабочий режим
            Template(
                name='Рабочий режим',
                category='work',
                description='Активируй рабочее пространство',
                icon='💼',
                commands=[
                    'Открой VS Code',
                    'Открой Excel',
                    'Открой Outlook',
                    'Отключи отвлекающие приложения'
                ],
                rules=[
                    {
                        'name': 'работа-включение',
                        'action_type': 'execute_command',
                        'action_value': 'открой VS Code и Excel',
                        'conditions': [
                            {'trigger_type': 'command_contains', 'trigger_value': 'работа', 'negate': False}
                        ]
                    }
                ]
            ),
            
            # Конец дня
            Template(
                name='Конец рабочего дня',
                category='evening',
                description='Заверши рабочий день и расслабься',
                icon='🌆',
                commands=[
                    'Закрой все приложения',
                    'Выключи уведомления',
                    'Включи музыку для отдыха',
                    'Скажи до встречи'
                ],
                rules=[
                    {
                        'name': 'конец-дня',
                        'action_type': 'send_notification',
                        'action_value': 'Рабочий день завершен!',
                        'conditions': [
                            {'trigger_type': 'time', 'trigger_value': '17:00', 'negate': False}
                        ]
                    }
                ]
            ),
            
            # Игровой режим
            Template(
                name='Игровой режим',
                category='gaming',
                description='Оптимизация для игр',
                icon='🎮',
                commands=[
                    'Закрой браузер',
                    'Отключи уведомления',
                    'Включи полноэкранный режим',
                    'Максимум производительности'
                ],
                rules=[]
            ),
            
            # Режим сна
            Template(
                name='Спокойной ночи',
                category='evening',
                description='Подготовка ко сну',
                icon='😴',
                commands=[
                    'Выключи все свет',
                    'Закрой все программы',
                    'Отключи все уведомления',
                    'Запусти расслабляющую музыку'
                ],
                rules=[
                    {
                        'name': 'сон-автоматика',
                        'action_type': 'execute_command',
                        'action_value': 'выключи все',
                        'conditions': [
                            {'trigger_type': 'time', 'trigger_value': '22:00', 'negate': False}
                        ]
                    }
                ]
            ),
            
            # Фокус режим
            Template(
                name='Режим фокусировки',
                category='work',
                description='Максимальная концентрация',
                icon='🎯',
                commands=[
                    'Отключи интернет',
                    'Закрой социальные сети',
                    'Запусти таймер 25 минут',
                    'Включи фоновую музыку'
                ],
                rules=[]
            ),
            
            # Встреча
            Template(
                name='Во время встречи',
                category='work',
                description='Автоматические действия во время переговоров',
                icon='📞',
                commands=[
                    'Выключи все звуки',
                    'Закрой уведомления',
                    'Откройноту для заметок',
                    'Запусти запись экрана'
                ],
                rules=[]
            ),
        ]
        
        added_any = False
        for template in default_templates:
            if template.name not in self.templates:
                self.templates[template.name] = template
                added_any = True

        if added_any:
            self.save_templates()
    
    def load_templates(self) -> None:
        """Загрузить шаблоны из файла"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for template_name, template_data in data.items():
                        self.templates[template_name] = Template.from_dict(template_data)
                    print(f"📂 Загружено {len(self.templates)} шаблонов")
            except Exception as e:
                print(f"❌ Ошибка загрузки шаблонов: {e}")
    
    def save_templates(self) -> None:
        """Сохранить шаблоны в файл"""
        try:
            data = {name: template.to_dict() for name, template in self.templates.items()}
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(self.templates)} шаблонов")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def get_template(self, name: str) -> Optional[Template]:
        """Получить шаблон"""
        return self.templates.get(name)
    
    def list_templates(self, category: str = None) -> List[Dict]:
        """Получить список шаблонов"""
        templates = [t.to_dict() for t in self.templates.values()]
        if category:
            templates = [t for t in templates if t['category'] == category]
        return templates
    
    def list_categories(self) -> List[str]:
        """Получить список категорий"""
        return list(set(t.category for t in self.templates.values()))
    
    def apply_template(self, template_name: str) -> Dict:
        """
        Применить шаблон (получить список команд и правил для создания)
        """
        template = self.get_template(template_name)
        if not template:
            return {'success': False, 'error': f'Шаблон "{template_name}" не найден'}
        
        template.popularity += 1
        self.save_templates()
        
        return {
            'success': True,
            'message': f'Применяю шаблон "{template_name}"',
            'data': template.to_dict(),
            'todo': {
                'create_commands': template.commands,
                'create_rules': template.rules
            }
        }
    
    def create_custom_template(self, name: str, category: str = 'custom', description: str = '',
                              commands: List[str] = None, rules: List[Dict] = None, icon: str = '⭐') -> Dict:
        """Создать кастомный шаблон"""
        if name in self.templates:
            return {'success': False, 'error': f'Шаблон "{name}" уже существует'}
        
        commands = commands or []
        rules = rules or []
        
        template = Template(name, category, description, commands, rules, icon)
        self.templates[name] = template
        self.save_templates()
        
        return {'success': True, 'message': f'Шаблон "{name}" создан', 'data': template.to_dict()}
    
    def delete_template(self, name: str) -> Dict:
        """Удалить шаблон"""
        if name not in self.templates:
            return {'success': False, 'error': f'Шаблон "{name}" не найден'}
        
        del self.templates[name]
        self.save_templates()
        return {'success': True, 'message': f'Шаблон "{name}" удален'}
    
    def get_popular_templates(self, limit: int = 5) -> List[Dict]:
        """Получить популярные шаблоны"""
        sorted_templates = sorted(self.templates.values(), key=lambda t: t.popularity, reverse=True)
        return [t.to_dict() for t in sorted_templates[:limit]]
    
    def __repr__(self):
        return f"TemplateManager({len(self.templates)} шаблонов)"


def get_template_manager(db_path: str = 'data/templates.json') -> TemplateManager:
    """Factory функция"""
    return TemplateManager(db_path)
