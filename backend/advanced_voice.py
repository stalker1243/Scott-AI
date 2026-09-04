#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Advanced Voice Module for Scott AI v3.0
Голосовое распознавание и синтез речи Джарвиса на русском языке
"""

import os
import sys
import asyncio
import threading
import time
from typing import Optional, Callable
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Попытка импортировать все возможные библиотеки для распознавания речи
try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False
    logger.warning("⚠️ speech_recognition не установлен. Используйте: pip install SpeechRecognition")

try:
    import sounddevice as sd
    import numpy as np
    import scipy.io.wavfile as wavfile
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    logger.warning("⚠️ sounddevice/numpy/scipy не установлены. Для лучшего качества: pip install sounddevice scipy numpy")

try:
    from google.cloud import speech_v1
    HAS_GOOGLE_SPEECH = True
except ImportError:
    HAS_GOOGLE_SPEECH = False

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False
    logger.warning("⚠️ pyttsx3 не установлен. Используйте: pip install pyttsx3")

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    logger.warning("⚠️ edge-tts не установлен. Используйте: pip install edge-tts")

# Импортируем существующий TTS модуль
try:
    from scott_voice import ScottVoice
    HAS_SCOTT_VOICE = True
except ImportError:
    HAS_SCOTT_VOICE = False
    logger.warning("⚠️ scott_voice модуль не найден")


class AdvancedSpeechRecognizer:
    """
    Продвинутое голосовое распознавание с поддержкой нескольких движков
    
    Features:
    - Google Speech Recognition (онлайн, лучшее качество)
    - Windows Speech Recognition (оффлайн)
    - Sphinx (полностью оффлайн)
    - Поддержка русского языка
    """
    
    def __init__(self, language: str = "ru-RU", use_google: bool = False):
        """
        Инициализация речевого распознавателя
        
        Args:
            language: Язык ("ru-RU" для русского, "en-US" для английского)
            use_google: Использовать Google Speech API (требует интернета)
        """
        self.language = language
        self.use_google = use_google
        self.recognizer = None
        self.microphone = None
        self.is_listening = False
        self.recognized_text = None
        self.confidence = 0.0
        
        if HAS_SPEECH_RECOGNITION:
            try:
                self.recognizer = sr.Recognizer()
                # Не инициализируем микрофон здесь, сделаем это лениво
                logger.info("✅ SpeechRecognition инициализирован (микрофон инициализируется при необходимости)")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации SpeechRecognition: {e}")
                self.recognizer = None
        else:
            logger.error("❌ SpeechRecognition не доступен")
    
    def recognize_from_microphone(self, timeout: int = 8, phrase_time_limit: int = 20) -> Optional[str]:
        """
        Распознать речь с микрофона
        
        Args:
            timeout: Максимальное время ожидания начала говорения (сек)
            phrase_time_limit: Максимальная длительность фразы (сек)
        
        Returns:
            Распознанный текст или None
        """
        if not self.recognizer:
            logger.error("❌ Recognizer не инициализирован")
            return None
        
        try:
            # Инициализируем микрофон лениво
            if self.microphone is None:
                try:
                    self.microphone = sr.Microphone()
                except Exception as e:
                    logger.error(f"❌ Не удалось инициализировать микрофон: {e}")
                    return None
            
            with self.microphone as source:
                logger.info("🎤 Слушаю... (говорите)")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                # Захватить аудио с микрофона
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )
                
                logger.info("✅ Аудио захвачено. Распознаю...")
                
                # Попытка распознавания
                try:
                    # Сначала пробуем Google (если есть интернет)
                    if self.use_google:
                        text = self.recognizer.recognize_google(
                            audio,
                            language=self.language
                        )
                        logger.info(f"✅ Google распознала: {text}")
                        return text
                    
                    # Затем пробуем Windows Speech Recognition
                    try:
                        text = self.recognizer.recognize_sphinx(audio)
                        logger.info(f"✅ Sphinx распознала: {text}")
                        return text
                    except:
                        # Если Sphinx не работает, пробуем Google
                        text = self.recognizer.recognize_google(
                            audio,
                            language=self.language
                        )
                        logger.info(f"✅ Google распознала: {text}")
                        return text
                
                except sr.UnknownValueError:
                    logger.warning("⚠️ Не смогла разобрать речь. Попробуйте еще раз.")
                    return None
                except sr.RequestError as e:
                    logger.error(f"❌ Ошибка сервиса: {e}")
                    return None
        
        except sr.RequestError:
            logger.error("❌ Микрофон не доступен или сервис не ответил")
            return None
    
    def recognize_from_file(self, file_path: str) -> Optional[str]:
        """
        Распознать речь из файла
        
        Args:
            file_path: Путь к wav файлу
        
        Returns:
            Распознанный текст
        """
        if not self.recognizer or not os.path.exists(file_path):
            return None
        
        try:
            with sr.AudioFile(file_path) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio, language=self.language)
                logger.info(f"✅ Распознано из файла: {text}")
                return text
        except Exception as e:
            logger.error(f"❌ Ошибка распознавания файла: {e}")
            return None
    
    def listen_continuously(self, on_recognized: Callable[[str], None], stop_event: threading.Event):
        """
        Непрерывное слушание и распознавание (в отдельном потоке)
        
        Args:
            on_recognized: Callback функция при распознавании
            stop_event: threading.Event для остановки слушания
        """
        while not stop_event.is_set():
            try:
                text = self.recognize_from_microphone(timeout=5, phrase_time_limit=20)
                if text:
                    on_recognized(text)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при слушании: {e}")
                continue


class JarvisVoiceRussian:
    """
    Голос Джарвиса на русском языке
    
    Использует лучший доступный TTS движок:
    1. Edge TTS (лучшее качество)
    2. pyttsx3 (оффлайн, встроенный)
    3. Scott Voice (существующий модуль)
    """
    
    def __init__(self):
        """Инициализация голосового синтезатора"""
        self.tts_engine = self._init_tts_engine()
        self.is_speaking = False
        self.voice_speed = 100  # 50-200 (%)
        self.voice_volume = 90   # 0-100 (%)
        
        logger.info(f"✅ Jarvis Voice инициализирован (Engine: {self.tts_engine})")
    
    def _init_tts_engine(self) -> str:
        """Инициализировать лучший доступный TTS движок"""
        
        # 1. Попытка использовать Edge TTS (лучшее качество)
        if HAS_EDGE_TTS:
            logger.info("🎙️ Используем Edge TTS (лучшее качество)")
            return "edge-tts"
        
        # 2. Использовать pyttsx3 (встроенный)
        if HAS_PYTTSX3:
            logger.info("🎙️ Используем pyttsx3 (встроенный)")
            return "pyttsx3"
        
        # 3. Использовать существующий Scott Voice
        if HAS_SCOTT_VOICE:
            logger.info("🎙️ Используем Scott Voice (существующий)")
            return "scott"
        
        logger.error("❌ Ни один TTS движок не доступен!")
        return "none"
    
    def speak(self, text: str) -> bool:
        """
        Произнести текст голосом Джарвиса
        
        Args:
            text: Текст для произнесения
        
        Returns:
            True если успешно, False если ошибка
        """
        if not text:
            return False
        
        try:
            self.is_speaking = True
            logger.info(f"🔊 Джарвис говорит: {text[:50]}...")
            
            if self.tts_engine == "edge-tts":
                return self._speak_edge_tts(text)
            elif self.tts_engine == "pyttsx3":
                return self._speak_pyttsx3(text)
            elif self.tts_engine == "scott":
                return self._speak_scott(text)
            
            return False
        
        finally:
            self.is_speaking = False
    
    def _speak_edge_tts(self, text: str) -> bool:
        """Произнести через Edge TTS"""
        try:
            import asyncio
            asyncio.run(self._speak_edge_async(text))
            return True
        except Exception as e:
            logger.error(f"❌ Edge TTS ошибка: {e}")
            return False
    
    async def _speak_edge_async(self, text: str):
        """Асинхронное воспроизведение через Edge TTS"""
        try:
            communicate = edge_tts.Communicate(text, voice="ru-RU-DmitryNeural")
            await communicate.save("temp_voice.mp3")
            
            # Воспроизведение с использованием встроенного плеера
            import subprocess
            subprocess.Popen(["powershell", "-Command", 
                f"(New-Object System.Media.SoundPlayer 'temp_voice.mp3').PlaySync()"])
            
            logger.info("✅ Edge TTS воспроизведено")
        except Exception as e:
            logger.error(f"❌ Ошибка Edge TTS: {e}")
    
    def _speak_pyttsx3(self, text: str) -> bool:
        """Произнести через pyttsx3"""
        try:
            engine = pyttsx3.init()
            
            # Установить русский голос (если доступен)
            for voice in engine.getProperty('voices'):
                if 'Russian' in voice.name or 'ru' in voice.languages:
                    engine.setProperty('voice', voice.id)
                    break
            
            # Настроить скорость и громкость
            engine.setProperty('rate', self.voice_speed)
            engine.setProperty('volume', self.voice_volume / 100.0)
            
            # Произнести
            engine.say(text)
            engine.runAndWait()
            
            logger.info("✅ pyttsx3 воспроизведено")
            return True
        
        except Exception as e:
            logger.error(f"❌ pyttsx3 ошибка: {e}")
            return False
    
    def _speak_scott(self, text: str) -> bool:
        """Произнести через существующий Scott Voice модуль"""
        try:
            voice = ScottVoice()
            voice.speak(text)
            logger.info("✅ Scott Voice воспроизведено")
            return True
        except Exception as e:
            logger.error(f"❌ Scott Voice ошибка: {e}")
            return False
    
    def set_voice_speed(self, speed: int):
        """Установить скорость речи (50-200%)"""
        self.voice_speed = max(50, min(200, speed))
        logger.info(f"🎙️ Скорость речи: {self.voice_speed}%")
    
    def set_voice_volume(self, volume: int):
        """Установить громкость (0-100%)"""
        self.voice_volume = max(0, min(100, volume))
        logger.info(f"🎙️ Громкость: {self.voice_volume}%")


class JarvisVoiceAssistant:
    """
    Полнофункциональный голосовой ассистент Джарвис
    Объединяет распознавание и синтез речи
    """
    
    def __init__(self, language: str = "ru-RU"):
        """Инициализация ассистента"""
        self.language = language
        self.recognizer = AdvancedSpeechRecognizer(language=language)
        self.voice = JarvisVoiceRussian()
        self.is_active = False
        self.command_callback = None
        
        logger.info("✅ Jarvis Voice Assistant инициализирован")
    
    def listen_and_respond(self, callback: Callable[[str], str] = None) -> Optional[str]:
        """
        Слушать команду и произнести ответ
        
        Args:
            callback: Функция которая обрабатывает команду и возвращает ответ
        
        Returns:
            Распознанная команда или None
        """
        # Слушать команду
        command = self.recognizer.recognize_from_microphone()
        
        if not command:
            self.voice.speak("Прошу прощения, не смогла разобрать. Повторите, пожалуйста.")
            return None
        
        logger.info(f"📝 Распознанная команда: {command}")
        
        # Произнести подтверждение
        self.voice.speak("Понял, сэр. Выполняю.")
        
        # Обработать команду через callback
        if callback:
            response = callback(command)
            if response:
                self.voice.speak(response)
        
        return command
    
    def say(self, text: str):
        """Просто произнести текст"""
        self.voice.speak(text)
    
    def activate_continuous_listening(self, command_handler: Callable[[str], None]):
        """
        Активировать непрерывное слушание
        
        Args:
            command_handler: Функция для обработки команд
        """
        self.is_active = True
        self.command_callback = command_handler
        
        stop_event = threading.Event()
        listener_thread = threading.Thread(
            target=self.recognizer.listen_continuously,
            args=(command_handler, stop_event),
            daemon=True
        )
        listener_thread.start()
        
        logger.info("🎤 Непрерывное слушание активировано")
        return listener_thread, stop_event
    
    def deactivate_listening(self):
        """Деактивировать слушание"""
        self.is_active = False
        logger.info("🔇 Слушание деактивировано")


# Утилиты для тестирования
def test_speech_recognition():
    """Тест распознавания речи"""
    print("\n=== ТЕСТ РАСПОЗНАВАНИЯ РЕЧИ ===\n")
    
    recognizer = AdvancedSpeechRecognizer(language="ru-RU")
    
    print("🎤 Начинаю слушать... (говорите что-нибудь)")
    text = recognizer.recognize_from_microphone()
    
    if text:
        print(f"✅ Распознано: {text}")
    else:
        print("❌ Ошибка распознавания")


def test_voice_synthesis():
    """Тест синтеза голоса"""
    print("\n=== ТЕСТ СИНТЕЗА ГОЛОСА ===\n")
    
    voice = JarvisVoiceRussian()
    
    test_phrases = [
        "Здравствуйте, сэр. Я Джарвис.",
        "К вашим услугам.",
        "Выполняю команду.",
        "Система готова к работе."
    ]
    
    for phrase in test_phrases:
        print(f"🔊 Произношу: {phrase}")
        voice.speak(phrase)
        time.sleep(1)


def test_full_assistant():
    """Полный тест ассистента"""
    print("\n=== ПОЛНЫЙ ТЕСТ АССИСТЕНТА ===\n")
    
    assistant = JarvisVoiceAssistant(language="ru-RU")
    
    # Приветствие
    assistant.say("Добро пожаловать. Я Джарвис. Слушаю ваши команды.")
    
    # Пример обработчика команд
    def handle_command(cmd: str) -> str:
        cmd_lower = cmd.lower()
        
        if "привет" in cmd_lower:
            return "Здравствуйте. Как дела?"
        elif "время" in cmd_lower:
            import datetime
            return f"Сейчас {datetime.datetime.now().strftime('%H:%M')}"
        else:
            return f"Вы сказали: {cmd}"
    
    # Слушать команду
    assistant.listen_and_respond(handle_command)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test-recognition":
            test_speech_recognition()
        elif sys.argv[1] == "test-voice":
            test_voice_synthesis()
        elif sys.argv[1] == "test-all":
            test_voice_synthesis()
            test_speech_recognition()
            test_full_assistant()
        else:
            print("Usage: python advanced_voice.py [test-recognition|test-voice|test-all]")
    else:
        # По умолчанию - полный тест
        test_full_assistant()
