#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🎤 VOICE NAME TRIGGER SYSTEM v1.0
Система для активации Скотта по имени
Скотт реагирует только когда произносят его имя перед командой
"""

import re
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class VoiceTriggerResult:
    """Результат проверки voice trigger"""
    has_trigger: bool                      # Есть ли trigger
    name_used: Optional[str]              # Какое имя использовано
    command_text: str                      # Чистый текст команды (без имени)
    confidence: float                      # Уверенность (0-1)
    trigger_position: str                  # Где находится имя (start, middle, end)


class VoiceNameTrigger:
    """Система активации по имени"""
    
    # Все способы произнесения имени
    TRIGGER_NAMES = {
        # Русский
        'скотт': 'Scott',
        'скот': 'Scott',
        'скати': 'Scott',
        'скоти': 'Scott',
        
        # Английский
        'scott': 'Scott',
        'scott,': 'Scott',
        'scott.': 'Scott',
        
        # Формальные обращения
        'мистер скотт': 'Mr. Scott',
        'мр скотт': 'Mr. Scott',
        'мистер': 'Mr.',
        
        # Неформальные обращения
        'привет скотт': 'Hello Scott',
        'привет': 'Hello',
        'слушай скотт': 'Listen Scott',
        'слушай': 'Listen',
    }
    
    # Позиции где может быть имя
    TRIGGER_POSITIONS = ['start', 'middle', 'end']
    
    # Минимальная длина команды после имени
    MIN_COMMAND_LENGTH = 2
    
    def __init__(self, enabled: bool = True, require_trigger: bool = True):
        """
        Инициализация trigger системы
        
        Args:
            enabled: Включена ли система
            require_trigger: Требуется ли имя для активации
        """
        self.enabled = enabled
        self.require_trigger = require_trigger
        self.trigger_count = 0  # Счётчик срабатываний
        self.last_trigger_name = None  # Последнее использованное имя
    
    @staticmethod
    def _starts_with_name(text: str, name: str) -> bool:
        """
        Фраза начинается ИМЕНЕМ, а не словом, которое с него начинается.

        Простой startswith здесь давал ложные срабатывания на каждом слове,
        начинающемся со «скот»: «скотч закончился» превращался в обращение к
        Scott с командой «ч закончился», «скотина» — в «ина». Имя должно
        заканчиваться границей слова.
        """
        if not text.startswith(name):
            return False
        tail = text[len(name):]
        return not tail or not (tail[0].isalpha() or tail[0] == '-')

    @staticmethod
    def _ends_with_name(text: str, name: str) -> bool:
        """Фраза заканчивается именем, а не словом, которое им заканчивается."""
        if not text.endswith(name):
            return False
        head = text[:len(text) - len(name)]
        return not head or not (head[-1].isalpha() or head[-1] == '-')

    def check_trigger(self, text: str) -> VoiceTriggerResult:
        """
        Проверить наличие trigger в тексте
        
        Args:
            text: Распознанный текст
            
        Returns:
            VoiceTriggerResult с результатами проверки
        """
        if not self.enabled:
            # Если trigger отключен, возвращаем весь текст как команду
            return VoiceTriggerResult(
                has_trigger=False,
                name_used=None,
                command_text=text,
                confidence=1.0,
                trigger_position='none'
            )
        
        if not text or len(text.strip()) < 1:
            return VoiceTriggerResult(
                has_trigger=False,
                name_used=None,
                command_text="",
                confidence=0.0,
                trigger_position='none'
            )
        
        # Нормализируем текст.
        #
        # Пунктуация по краям снимается ДО поиска, а не после. Живая проверка
        # показала, почему это важно: «Спасибо, Скотт!» проходило мимо, потому
        # что строка заканчивается восклицательным знаком, а не именем —
        # endswith('скотт') не срабатывал. При этом «открой блокнот, Скотт» без
        # знака работало, и разница выглядела необъяснимой.
        #
        # Перечислять варианты с пунктуацией в TRIGGER_NAMES (там уже есть
        # 'scott,' и 'scott.') — заведомо проигрышный путь: знаков больше, чем
        # можно предусмотреть, и Whisper ставит их как ему вздумается.
        normalized_text = text.lower().strip()
        normalized_text = re.sub(r'^[\s,.!?…]+|[\s,.!?…]+$', '', normalized_text)
        
        # ==========================================
        # ПРОВЕРКА В НАЧАЛЕ (ВЫСОКИЙ ПРИОРИТЕТ)
        # ==========================================
        for trigger_name, full_name in self.TRIGGER_NAMES.items():
            if self._starts_with_name(normalized_text, trigger_name):
                # Извлекаем команду
                command_start = len(trigger_name)
                remaining_text = normalized_text[command_start:].strip()
                
                # Удаляем пунктуацию после имени
                remaining_text = re.sub(r'^[,.\s!?]+', '', remaining_text).strip()
                
                if len(remaining_text) >= self.MIN_COMMAND_LENGTH:
                    result = VoiceTriggerResult(
                        has_trigger=True,
                        name_used=full_name,
                        command_text=remaining_text,
                        confidence=0.95,  # Высокая уверенность (начало)
                        trigger_position='start'
                    )
                    self._update_stats(result)
                    return result
        
        # ==========================================
        # ПРОВЕРКА В КОНЦЕ (СРЕДНИЙ ПРИОРИТЕТ)
        # ==========================================
        for trigger_name, full_name in self.TRIGGER_NAMES.items():
            if self._ends_with_name(normalized_text, trigger_name):
                # Извлекаем команду
                command_end = len(normalized_text) - len(trigger_name)
                command_text = normalized_text[:command_end].strip()
                
                # Удаляем пунктуацию перед именем
                command_text = re.sub(r'[,.\s!?]+$', '', command_text).strip()
                
                if len(command_text) >= self.MIN_COMMAND_LENGTH:
                    result = VoiceTriggerResult(
                        has_trigger=True,
                        name_used=full_name,
                        command_text=command_text,
                        confidence=0.75,  # Средняя уверенность (конец)
                        trigger_position='end'
                    )
                    self._update_stats(result)
                    return result

        # ==========================================
        # ТОЛЬКО ИМЯ, БЕЗ КОМАНДЫ
        # ==========================================
        # «Скотт?» — это обращение, пусть и без просьбы. Считать его «мимо»
        # неправильно: человек позвал, и молчание в ответ выглядит поломкой.
        # Команда при этом пустая, и вызывающий код решает, что с этим делать —
        # слушатель, например, отвечает, что слышит, но команды не было.
        if normalized_text in self.TRIGGER_NAMES:
            result = VoiceTriggerResult(
                has_trigger=True,
                name_used=self.TRIGGER_NAMES[normalized_text],
                command_text='',
                confidence=0.9,
                trigger_position='start'
            )
            self._update_stats(result)
            return result
        
        # ==========================================
        # ПРОВЕРКА В СЕРЕДИНЕ (НИЗКИЙ ПРИОРИТЕТ)
        # ==========================================
        for trigger_name, full_name in self.TRIGGER_NAMES.items():
            # Ищем слово как отдельное слово (не часть другого слова)
            pattern = r'\b' + re.escape(trigger_name) + r'\b'
            match = re.search(pattern, normalized_text)
            
            if match:
                # Удаляем имя из текста
                before = normalized_text[:match.start()].strip()
                after = normalized_text[match.end():].strip()
                
                # Берём команду (предпочтительно - то что после имени)
                command_text = after if after else before
                command_text = re.sub(r'[,.\s!?]+', ' ', command_text).strip()
                
                if len(command_text) >= self.MIN_COMMAND_LENGTH:
                    result = VoiceTriggerResult(
                        has_trigger=True,
                        name_used=full_name,
                        command_text=command_text,
                        confidence=0.65,  # Низкая уверенность (в середине)
                        trigger_position='middle'
                    )
                    self._update_stats(result)
                    return result
        
        # ==========================================
        # Trigger НЕ НАЙДЕН
        # ==========================================
        
        # Если требуется trigger - отклоняем команду
        if self.require_trigger:
            return VoiceTriggerResult(
                has_trigger=False,
                name_used=None,
                command_text="",
                confidence=0.0,
                trigger_position='none'
            )
        
        # Если trigger не требуется - возвращаем весь текст
        return VoiceTriggerResult(
            has_trigger=False,
            name_used=None,
            command_text=text,
            confidence=0.5,  # Средняя уверенность (без trigger)
            trigger_position='none'
        )
    
    def _update_stats(self, result: VoiceTriggerResult):
        """Обновить статистику"""
        if result.has_trigger:
            self.trigger_count += 1
            self.last_trigger_name = result.name_used
    
    def get_stats(self) -> dict:
        """Получить статистику использования"""
        return {
            'total_triggers': self.trigger_count,
            'last_trigger_name': self.last_trigger_name,
            'enabled': self.enabled,
            'require_trigger': self.require_trigger
        }
    
    def reset_stats(self):
        """Сбросить статистику"""
        self.trigger_count = 0
        self.last_trigger_name = None
    
    def set_enabled(self, enabled: bool):
        """Включить/выключить trigger"""
        self.enabled = enabled
        status = "включена" if enabled else "выключена"
        print(f"🎤 Voice Name Trigger {status}")
    
    def set_require_trigger(self, require: bool):
        """Установить требование trigger"""
        self.require_trigger = require
        status = "требуется" if require else "не требуется"
        print(f"🎤 Voice Name Trigger {status} для активации")


# Глобальный экземпляр
_trigger_system = None


def get_voice_trigger() -> VoiceNameTrigger:
    """Получить глобальный экземпляр VoiceNameTrigger"""
    global _trigger_system
    if _trigger_system is None:
        _trigger_system = VoiceNameTrigger(enabled=True, require_trigger=True)
    return _trigger_system


def check_voice_trigger(text: str) -> VoiceTriggerResult:
    """Проверить trigger в тексте (функция-обёртка)"""
    trigger = get_voice_trigger()
    return trigger.check_trigger(text)


def activate_voice_command(recognized_text: str) -> Tuple[bool, str, str]:
    """
    Активировать голосовую команду с проверкой trigger
    
    Args:
        recognized_text: Распознанный текст
    
    Returns:
        (should_execute, command, reason)
    """
    result = check_voice_trigger(recognized_text)
    
    if result.has_trigger:
        return (True, result.command_text, f"Trigger найден: {result.name_used}")
    elif not get_voice_trigger().require_trigger:
        return (True, result.command_text, "Trigger не требуется")
    else:
        return (False, "", "Имя не произнесено, команда игнорирована")


# ==========================================
# ТЕСТИРОВАНИЕ
# ==========================================
if __name__ == "__main__":
    print("🎤 VOICE NAME TRIGGER SYSTEM - ТЕСТИРОВАНИЕ\n")
    
    trigger = VoiceNameTrigger(enabled=True, require_trigger=True)
    
    # Тестовые примеры
    test_cases = [
        # Начало
        "скотт какая сейчас температура",
        "скотт открой браузер",
        "scott play music",
        
        # Конец
        "какая температура скотт",
        "открой браузер скотт",
        
        # В середине
        "скажи скотт когда выход нового фильма",
        "скотт мне нужна информация",
        
        # Без trigger
        "какая сейчас температура",
        "открой браузер",
        
        # Вариации
        "скот открой двери",
        "привет скотт",
        "мистер скотт проверь статус",
    ]
    
    print(f"{'Текст':<40} | {'Trigger':<7} | {'Команда':<30} | {'Уверенность':<5}\n")
    print("=" * 95)
    
    for text in test_cases:
        result = trigger.check_trigger(text)
        trigger_status = "✅ ДА" if result.has_trigger else "❌ НЕТ"
        confidence = f"{result.confidence*100:.0f}%"
        
        print(f"{text:<40} | {trigger_status:<7} | {result.command_text:<30} | {confidence:<5}")
    
    print("\n" + "=" * 95)
    print(f"\n📊 Статистика:")
    stats = trigger.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
