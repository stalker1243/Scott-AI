"""
Профиль и личность Scott
Определяет характер, стиль общения, голос и поведение
"""

import json
from pathlib import Path
from typing import Dict, Optional


class ScottProfile:
    """Профиль и личность Scott AI"""
    
    DEFAULT_PROFILE = {
        # Основная информация
        "name": "Scott",
        "version": "2.0",
        "personality": "professional",  # professional, casual, friendly, formal
        
        # Голос и речь
        "voice": {
            "enabled": True,
            "engine": "edge-tts",
            "language": "ru-RU",
            "accent": "british",  # british, american, neutral
            "speed": 1.0,  # 0.5 - 2.0
            "pitch": 1.0
        },
        
        # Поведение
        "behavior": {
            "max_response_length": 500,  # Максимум символов в ответе
            "use_emojis": True,
            "be_polite": True,
            "explain_actions": True,
            "suggest_alternatives": True,
            "remember_context": True,
            "max_memory_items": 100
        },
        
        # Предпочтения пользователя
        "user": {
            "name": "Sir",
            "language": "ru",  # ru, en
            "timezone": "Europe/Moscow",
            "preferred_browser": "chrome",
            "preferred_editor": "vscode"
        },
        
        # Реакции и фразы
        "responses": {
            "greeting": [
                "Доброе утро, сэр. Я к вашим услугам.",
                "Добрый день. Чем я могу вам помочь?",
                "Здравствуйте. Я готов выполнить ваш приказ.",
            ],
            "farewell": [
                "До свидания, сэр.",
                "Всего вам доброго.",
                "Я здесь, если вам что-то понадобится.",
            ],
            "acknowledgement": [
                "Есть, сэр.",
                "Понял, сэр.",
                "Выполняю.",
                "Как пожелаете.",
                "Немедленно, сэр.",
            ],
            "success": [
                "Готово, сэр.",
                "Выполнено успешно.",
                "Всё сделано.",
                "Именно так, сэр.",
            ],
            "error": [
                "Прошу прощения, не смог выполнить.",
                "Произошла ошибка, сэр.",
                "К сожалению, не удалось.",
                "Мне очень жаль, сэр.",
            ],
            "question": [
                "Могу я вам чем-то помочь?",
                "Что вы хотите, чтобы я сделал?",
                "Какой-то ещё приказ?",
                "Вам нужно что-нибудь ещё?",
            ],
            "thinking": [
                "Одну минутку, сэр...",
                "Я обрабатываю запрос...",
                "Позвольте мне проверить...",
                "Сейчас найду информацию...",
            ]
        },
        
        # Функции включены/выключены
        "features": {
            "voice_input": True,
            "voice_output": True,
            "web_search": True,
            "currency_info": True,
            "weather": True,
            "news": True,
            "file_operations": True,
            "app_launch": True,
            "system_monitoring": True,
            "automation": False,  # Пока отключено
            "learning": False  # Пока отключено
        },
        
        # Стили ответов
        "styles": {
            "search_result_format": "markdown",  # markdown, plain, rich
            "error_verbosity": "normal",  # quiet, normal, verbose
            "info_level": "normal"  # brief, normal, detailed
        }
    }
    
    def __init__(self, profile_file: str = "scott_profile.json"):
        self.profile_file = Path(profile_file)
        self.profile = self._load_profile()
        print("✅ Профиль Scott загружен")
    
    def _load_profile(self) -> Dict:
        """Загрузить профиль из файла или использовать default"""
        if self.profile_file.exists():
            try:
                with open(self.profile_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Ошибка загрузки профиля: {e}, использую default")
        
        return self.DEFAULT_PROFILE.copy()
    
    def save_profile(self):
        """Сохранить профиль в файл"""
        try:
            with open(self.profile_file, 'w', encoding='utf-8') as f:
                json.dump(self.profile, f, ensure_ascii=False, indent=2)
            print(f"✅ Профиль сохранён: {self.profile_file}")
        except Exception as e:
            print(f"❌ Ошибка сохранения профиля: {e}")
    
    def get(self, key: str, default=None):
        """Получить значение из профиля"""
        keys = key.split('.')
        value = self.profile
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, key: str, value):
        """Установить значение в профиль"""
        keys = key.split('.')
        obj = self.profile
        
        for k in keys[:-1]:
            if k not in obj:
                obj[k] = {}
            obj = obj[k]
        
        obj[keys[-1]] = value
        self.save_profile()
    
    def get_response(self, response_type: str) -> str:
        """Получить случайный ответ из библиотеки"""
        import random
        
        responses = self.profile.get('responses', {}).get(response_type, [])
        if responses:
            return random.choice(responses)
        return "..."
    
    def get_name(self) -> str:
        """Получить имя Scott"""
        return self.profile.get('name', 'Scott')
    
    def get_user_name(self) -> str:
        """Получить имя пользователя"""
        return self.profile.get('user', {}).get('name', 'Sir')
    
    def get_language(self) -> str:
        """Получить язык"""
        return self.profile.get('user', {}).get('language', 'ru')
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Проверить включена ли функция"""
        return self.profile.get('features', {}).get(feature, False)
    
    def __repr__(self):
        return f"ScottProfile(name={self.get_name()}, language={self.get_language()})"


def get_scott_profile() -> ScottProfile:
    """Factory функция для получения профиля Scott"""
    return ScottProfile()
