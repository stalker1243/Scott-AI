"""
Менеджер профилей пользователей - разные пользователи, разные команды и контексты
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

class UserProfile:
    """Профиль пользователя со своими данными"""
    
    def __init__(self, username: str = None, name: str = None, is_admin: bool = False):
        # Поддержка обоих параметров: username и name
        self.username = username or name or "Unknown"
        self.name = self.username  # Alias для совместимости с тестами
        self.is_admin = is_admin
        self.created_at = datetime.now().isoformat()
        self.last_active = datetime.now().isoformat()
        self.avatar = f"avatar_{self.username}.png"
        self.preferences = {
            'theme': 'dark',
            'language': 'ru',
            'notifications': True,
            'voice_type': 'male'  # 'male' или 'female'
        }
        self.context = {}  # Пустой контекст по умолчанию для совместимости с тестами
        self.custom_commands = []  # ID команд
        self.ifttt_rules = []      # ID правил
        self.macros = []           # ID макросов
        self.analytics_data = {}
        self.restricted_apps = []  # Если не admin
        self.restricted_commands = []
        self.enabled = True
    
    def update_activity(self):
        """Обновить время последней активности"""
        self.last_active = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            'username': self.username,
            'name': self.username,  # Alias for compatibility
            'is_admin': self.is_admin,
            'created_at': self.created_at,
            'last_active': self.last_active,
            'avatar': self.avatar,
            'preferences': self.preferences,
            'context': self.context,
            'custom_commands': self.custom_commands,
            'ifttt_rules': self.ifttt_rules,
            'macros': self.macros,
            'analytics_data': self.analytics_data,
            'restricted_apps': self.restricted_apps,
            'restricted_commands': self.restricted_commands,
            'enabled': self.enabled
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'UserProfile':
        profile = UserProfile(
            username=data['username'],
            is_admin=data.get('is_admin', False)
        )
        profile.created_at = data.get('created_at', profile.created_at)
        profile.last_active = data.get('last_active', profile.last_active)
        profile.avatar = data.get('avatar', profile.avatar)
        profile.preferences = data.get('preferences', profile.preferences)
        profile.context = data.get('context', profile.context)
        profile.custom_commands = data.get('custom_commands', [])
        profile.ifttt_rules = data.get('ifttt_rules', [])
        profile.macros = data.get('macros', [])
        profile.analytics_data = data.get('analytics_data', {})
        profile.restricted_apps = data.get('restricted_apps', [])
        profile.restricted_commands = data.get('restricted_commands', [])
        profile.enabled = data.get('enabled', True)
        return profile


class ProfileManager:
    """Управляет профилями пользователей"""
    
    def __init__(self, db_path: str = 'data/profiles.json'):
        self.db_path = Path(db_path)
        self.data_dir = str(self.db_path.parent)  # Для совместимости с тестами
        self.profiles: Dict[str, UserProfile] = {}
        self.current_user: Optional[str] = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_profiles()
        print(f"✅ Менеджер профилей инициализирован ({len(self.profiles)} профилей)")
    
    def load_profiles(self) -> None:
        """Загрузить профили из файла"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for username, profile_data in data.get('profiles', {}).items():
                        self.profiles[username] = UserProfile.from_dict(profile_data)
                    self.current_user = data.get('current_user')
                    print(f"📂 Загружено {len(self.profiles)} профилей")
            except Exception as e:
                print(f"❌ Ошибка загрузки профилей: {e}")
        else:
            # Создать профиль по умолчанию
            self.create_profile('Ты', is_admin=True)
            self.current_user = 'Ты'
            self.save_profiles()
    
    def save_profiles(self) -> None:
        """Сохранить профили в файл"""
        try:
            data = {
                'profiles': {name: profile.to_dict() for name, profile in self.profiles.items()},
                'current_user': self.current_user
            }
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 Сохранено {len(self.profiles)} профилей")
        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
    
    def create_profile(self, username: str = None, name: str = None, is_admin: bool = False) -> Dict:
        """Создать новый профиль"""
        # Поддержка обоих параметров
        user = username or name or None
        if not user:
            return {'success': False, 'message': 'Имя пользователя не указано', 'data': None}
            
        if user in self.profiles:
            return {'success': False, 'message': f'Профиль "{user}" уже существует', 'data': None}
        
        if not user or len(user) < 2:
            return {'success': False, 'message': 'Имя пользователя должно быть от 2 символов', 'data': None}
        
        profile = UserProfile(username=user, is_admin=is_admin)
        self.profiles[user] = profile
        self.save_profiles()
        return {'success': True, 'message': f'Профиль "{user}" создан', 'data': profile.to_dict()}
    
    def switch_profile(self, username: str) -> Dict:
        """Переключиться на другой профиль"""
        if username not in self.profiles:
            return {'success': False, 'message': f'Профиль "{username}" не найден', 'data': None}
        
        profile = self.profiles[username]
        if not profile.enabled:
            return {'success': False, 'message': f'Профиль "{username}" отключен', 'data': None}
        
        self.current_user = username
        profile.update_activity()
        self.save_profiles()
        return {'success': True, 'message': f'Переключились на профиль "{username}"', 'data': profile.to_dict()}
    
    def delete_profile(self, username: str) -> Dict:
        """Удалить профиль"""
        if username not in self.profiles:
            return {'success': False, 'message': f'Профиль "{username}" не найден', 'data': None}
        
        if username == 'Ты' and len(self.profiles) == 1:
            return {'success': False, 'message': 'Нельзя удалить основной профиль', 'data': None}
        
        del self.profiles[username]
        if self.current_user == username:
            self.current_user = list(self.profiles.keys())[0] if self.profiles else None
        
        self.save_profiles()
        return {'success': True, 'message': f'Профиль "{username}" удален'}
    
    def get_profile(self, username: str = None) -> Optional[UserProfile]:
        """Получить профиль"""
        if username is None:
            username = self.current_user
        return self.profiles.get(username)
    
    def get_current_profile(self) -> Optional[UserProfile]:
        """Получить текущий профиль"""
        return self.get_profile(self.current_user)
    
    def list_profiles(self) -> List[Dict]:
        """Список всех профилей"""
        return [profile.to_dict() for profile in self.profiles.values()]
    
    def update_profile(self, username: str, update_data: Dict = None, **kwargs) -> Dict:
        """Обновить профиль"""
        profile = self.get_profile(username)
        if not profile:
            return {'success': False, 'error': f'Профиль "{username}" не найден'}
        
        # Поддержка обоих вариантов: словарь или **kwargs
        data = update_data or kwargs
        
        if 'preferences' in data:
            profile.preferences.update(data['preferences'])
        if 'context' in data:
            profile.context.update(data['context'])
        if 'restricted_apps' in data:
            profile.restricted_apps = data['restricted_apps']
        if 'restricted_commands' in data:
            profile.restricted_commands = data['restricted_commands']
        if 'enabled' in data:
            profile.enabled = data['enabled']
        
        profile.update_activity()
        self.save_profiles()
        return {'success': True, 'message': f'Профиль "{username}" обновлен', 'data': profile.to_dict()}
    
    def check_command_allowed(self, username: str, command: str) -> bool:
        """Проверить разрешена ли команда для пользователя"""
        profile = self.get_profile(username)
        if not profile or profile.is_admin:
            return True
        return command not in profile.restricted_commands
    
    def check_app_allowed(self, username: str, app: str) -> bool:
        """Проверить разрешено ли приложение"""
        profile = self.get_profile(username)
        if not profile or profile.is_admin:
            return True
        return app not in profile.restricted_apps
    
    def add_restricted_app(self, username: str, app: str) -> Dict:
        """Добавить приложение в черный список"""
        profile = self.get_profile(username)
        if not profile:
            return {'success': False, 'error': f'Профиль "{username}" не найден'}
        
        if app not in profile.restricted_apps:
            profile.restricted_apps.append(app)
            self.save_profiles()
        
        return {'success': True, 'message': f'Приложение "{app}" добавлено в черный список'}
    
    def remove_restricted_app(self, username: str, app: str) -> Dict:
        """Удалить приложение из черного списка"""
        profile = self.get_profile(username)
        if not profile:
            return {'success': False, 'error': f'Профиль "{username}" не найден'}
        
        if app in profile.restricted_apps:
            profile.restricted_apps.remove(app)
            self.save_profiles()
        
        return {'success': True, 'message': f'Приложение "{app}" удалено из черного списка'}
    
    def get_statistics(self) -> Dict:
        """Получить статистику профилей"""
        total = len(self.profiles)
        admin_count = sum(1 for p in self.profiles.values() if p.is_admin)
        
        return {
            'total_profiles': total,
            'admin_count': admin_count,
            'user_count': total - admin_count,
            'current_user': self.current_user,
            'profiles': [
                {
                    'username': p.username,
                    'is_admin': p.is_admin,
                    'last_active': p.last_active,
                    'commands_count': len(p.custom_commands),
                    'rules_count': len(p.ifttt_rules)
                }
                for p in self.profiles.values()
            ]
        }
    
    def __repr__(self):
        return f"ProfileManager({len(self.profiles)} профилей, текущий: {self.current_user})"


def get_profile_manager(db_path: str = 'data/profiles.json') -> ProfileManager:
    """Factory функция"""
    return ProfileManager(db_path)
