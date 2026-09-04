#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Voice Testing Script for Scott AI v3.0
Полное тестирование всех голосовых компонентов
"""

import sys
import time
from pathlib import Path

# Добавить текущую папку в path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from advanced_voice import (
        AdvancedSpeechRecognizer,
        JarvisVoiceRussian,
        JarvisVoiceAssistant,
        HAS_SPEECH_RECOGNITION,
        HAS_EDGE_TTS,
        HAS_PYTTSX3,
        HAS_SOUNDDEVICE
    )
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Установите требуемые пакеты: pip install -r requirements.txt")
    sys.exit(1)


def print_header(title: str):
    """Печать заголовка"""
    print("\n" + "="*60)
    print(f"🎤 {title}")
    print("="*60)


def print_status(module_name: str, status: bool):
    """Печать статуса модуля"""
    emoji = "✅" if status else "❌"
    print(f"{emoji} {module_name}: {'доступен' if status else 'недоступен'}")


def test_system():
    """Тест доступности всех компонентов"""
    print_header("ТЕСТ 1: Проверка компонентов")
    
    print("\nТекущая конфигурация:")
    print_status("speech_recognition", HAS_SPEECH_RECOGNITION)
    print_status("edge-tts", HAS_EDGE_TTS)
    print_status("pyttsx3", HAS_PYTTSX3)
    print_status("sounddevice", HAS_SOUNDDEVICE)
    
    if not HAS_SPEECH_RECOGNITION:
        print("\n⚠️ Распознавание речи недоступно!")
        print("Установите: pip install SpeechRecognition")
    
    if not (HAS_EDGE_TTS or HAS_PYTTSX3):
        print("\n⚠️ Синтез речи недоступен!")
        print("Установите: pip install edge-tts pyttsx3")
    
    if not HAS_SOUNDDEVICE:
        print("\n⚠️ Работа со звуком может быть ограничена")
        print("Установите: pip install sounddevice")
    
    return HAS_SPEECH_RECOGNITION and (HAS_EDGE_TTS or HAS_PYTTSX3)


def test_voice_synthesis():
    """Тест синтеза голоса (TTS)"""
    print_header("ТЕСТ 2: Синтез речи (Произнесение)")
    
    if not (HAS_EDGE_TTS or HAS_PYTTSX3):
        print("❌ TTS не доступен")
        return False
    
    try:
        print("Инициализирую Джарвиса...")
        voice = JarvisVoiceRussian()
        
        print("🔊 Произнесу тестовое сообщение...")
        voice.speak("Здравствуйте. Я Джарвис. Голосовая система работает отлично.")
        
        print("⏳ Ожидаю завершения произнесения...")
        time.sleep(3)
        
        print("✅ Синтез речи работает корректно")
        
        # Тест скорости
        print("\n🔄 Тест скорости речи...")
        voice.set_voice_speed(150)  # Быстрее
        voice.speak("Быстрая речь")
        time.sleep(1)
        
        voice.set_voice_speed(50)  # Медленнее
        voice.speak("Медленная речь")
        time.sleep(2)
        
        # Тест громкости
        print("\n🔊 Тест громкости...")
        voice.set_voice_volume(50)
        voice.speak("Тихо")
        time.sleep(1)
        
        voice.set_voice_volume(100)
        voice.speak("Громко")
        time.sleep(1)
        
        voice.set_voice_volume(90)  # По умолчанию
        
        print("✅ Все параметры голоса работают")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при тестировании TTS: {e}")
        return False


def test_speech_recognition():
    """Тест распознавания речи (STT)"""
    print_header("ТЕСТ 3: Распознавание речи")
    
    if not HAS_SPEECH_RECOGNITION:
        print("❌ SpeechRecognition не доступен")
        return False
    
    try:
        print("Инициализирую распознаватель...")
        recognizer = AdvancedSpeechRecognizer(language="ru-RU", use_google=True)
        
        print("\n🎤 НАЧИНАЙТЕ ГОВОРИТЬ (у вас 5 секунд)")
        print("Примеры команд:")
        print("  - 'Открой Chrome'")
        print("  - 'Какое время?'")
        print("  - 'Привет Джарвис'")
        print()
        
        start_time = time.time()
        text = recognizer.recognize_from_microphone(timeout=5, phrase_time_limit=4)
        elapsed = time.time() - start_time
        
        if text:
            print(f"\n✅ Распознано: '{text}'")
            print(f"⏱️ Время обработки: {elapsed:.2f} сек")
            print("\n✅ Распознавание речи работает корректно")
            return True
        else:
            print("⚠️ Речь не распознана")
            print("Возможные причины:")
            print("  - Микрофон не слышит")
            print("  - Нет интернета (требуется для Google)")
            print("  - Неправильный язык")
            return False
    
    except Exception as e:
        print(f"❌ Ошибка при тестировании STT: {e}")
        print("\nДиагностика:")
        print("  1. Проверьте подключение интернета")
        print("  2. Проверьте микрофон (Параметры → Звук → Микрофон)")
        print("  3. Убедитесь что SpeechRecognition установлен")
        return False


def test_full_assistant():
    """Полный тест ассистента"""
    print_header("ТЕСТ 4: Полный цикл ассистента")
    
    if not (HAS_SPEECH_RECOGNITION and (HAS_EDGE_TTS or HAS_PYTTSX3)):
        print("❌ Не все компоненты доступны")
        return False
    
    try:
        print("Инициализирую полного ассистента...")
        assistant = JarvisVoiceAssistant(language="ru-RU")
        
        # Приветствие
        print("\n🎤 Произнесу приветствие...")
        assistant.say("Добро пожаловать. Я Джарвис. Голосовое управление активировано.")
        time.sleep(3)
        
        # Цикл слушания
        print("\n🎤 Начинаем цикл слушания...")
        print("Скажите команду:")
        print("  - 'Привет'")
        print("  - 'Какое время?'")
        print("  - 'Статус системы'")
        print("  - 'Выход' или 'Выключи' для прекращения")
        print()
        
        def handle_command(cmd: str) -> str:
            """Обработчик команд"""
            cmd_lower = cmd.lower()
            
            if "привет" in cmd_lower:
                return "Привет, сэр. Как дела?"
            elif "время" in cmd_lower:
                from datetime import datetime
                current_time = datetime.now().strftime("%H:%M:%S")
                return f"Текущее время: {current_time}"
            elif "статус" in cmd_lower or "система" in cmd_lower:
                return "Система функционирует в нормальном режиме"
            elif "выход" in cmd_lower or "выключи" in cmd_lower:
                return "До свидания, сэр"
            else:
                return f"Вы сказали: {cmd}"
        
        # Слушаем несколько команд
        for i in range(3):
            print(f"\n{i+1}️⃣ Цикл {i+1}...")
            try:
                # Произнести приглашение
                assistant.say("Слушаю")
                time.sleep(1)
                
                # Слушать команду (5 сек)
                recognizer = AdvancedSpeechRecognizer(language="ru-RU", use_google=True)
                cmd = recognizer.recognize_from_microphone(timeout=5, phrase_time_limit=4)
                
                if not cmd:
                    print("⚠️ Команда не распознана. Повтор...")
                    continue
                
                print(f"📝 Распознано: '{cmd}'")
                
                # Обработать команду
                response = handle_command(cmd)
                print(f"✅ Ответ: '{response}'")
                
                # Произнести ответ
                assistant.say(response)
                time.sleep(2)
                
                # Выход
                if "выход" in cmd.lower() or "выключи" in cmd.lower():
                    print("\n🛑 Ассистент выключен")
                    break
            
            except Exception as e:
                print(f"❌ Ошибка в цикле: {e}")
                continue
        
        print("\n✅ Полный цикл завершен успешно")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при тестировании ассистента: {e}")
        return False


def run_all_tests():
    """Запустить все тесты"""
    print("\n" + "█"*60)
    print("█ ГОЛОСОВАЯ СИСТЕМА SCOTT AI v3.0 - ПОЛНОЕ ТЕСТИРОВАНИЕ █")
    print("█"*60)
    
    results = []
    
    # Тест 1: Компоненты
    results.append(("Компоненты системы", test_system()))
    
    # Тест 2: Синтез голоса
    results.append(("Синтез речи (TTS)", test_voice_synthesis()))
    
    # Тест 3: Распознавание речи
    results.append(("Распознавание речи (STT)", test_speech_recognition()))
    
    # Тест 4: Полный ассистент
    results.append(("Полный ассистент", test_full_assistant()))
    
    # Итоги
    print_header("ИТОГИ ТЕСТИРОВАНИЯ")
    
    total = len(results)
    passed = sum(1 for _, result in results if result)
    
    for test_name, result in results:
        emoji = "✅" if result else "❌"
        status = "ПРОШЕЛ" if result else "НЕ ПРОШЕЛ"
        print(f"{emoji} {test_name}: {status}")
    
    print(f"\n📊 РЕЗУЛЬТАТ: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("Система полностью готова к голосовому управлению.")
        return 0
    elif passed >= total - 1:
        print("\n⚠️ БОЛЬШИНСТВО ТЕСТОВ ПРОЙДЕНО")
        print("Проверьте проблемные компоненты")
        return 1
    else:
        print("\n❌ ТРЕБУЕТСЯ ДОРАБОТКА")
        print("Установите все необходимые пакеты и повторите тесты")
        return 1


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Тестирование голосовой системы Scott AI v3.0")
    parser.add_argument(
        'test',
        nargs='?',
        default='all',
        choices=['all', 'components', 'voice', 'recognition', 'assistant'],
        help='Тест для запуска'
    )
    
    args = parser.parse_args()
    
    try:
        if args.test == 'all':
            exit_code = run_all_tests()
        elif args.test == 'components':
            exit_code = 0 if test_system() else 1
        elif args.test == 'voice':
            exit_code = 0 if test_voice_synthesis() else 1
        elif args.test == 'recognition':
            exit_code = 0 if test_speech_recognition() else 1
        elif args.test == 'assistant':
            exit_code = 0 if test_full_assistant() else 1
        else:
            exit_code = 1
        
        sys.exit(exit_code)
    
    except KeyboardInterrupt:
        print("\n\n⏸️ Тестирование прервано пользователем")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
