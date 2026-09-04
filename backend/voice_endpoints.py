#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Voice Endpoints for Scott AI v3.0
Полная поддержка голосовых команд через REST API
"""

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional
import io
import asyncio

# Попытаемся импортировать голосовые компоненты, но не будем инициализировать их сразу
try:
    from advanced_voice import (
        AdvancedSpeechRecognizer,
        JarvisVoiceRussian,
        JarvisVoiceAssistant
    )
    HAS_VOICE_COMPONENTS = True
except ImportError as e:
    print(f"⚠️ Ошибка импорта голосовых компонентов: {e}")
    HAS_VOICE_COMPONENTS = False

# Создаем router для голосовых endpoints
voice_router = APIRouter(prefix="/voice", tags=["voice"])

# Глобальные объекты для голоса - ленивая инициализация
_recognizer = None
_jarvis_voice = None
_current_voice_type = 'dmitry'  # Текущий выбранный голос

def get_recognizer():
    global _recognizer
    if _recognizer is None and HAS_VOICE_COMPONENTS:
        try:
            _recognizer = AdvancedSpeechRecognizer(language="ru-RU", use_google=True)
            print("✅ AdvancedSpeechRecognizer инициализирован")
        except Exception as e:
            print(f"⚠️ Ошибка инициализации распознавателя: {e}")
            _recognizer = None
    return _recognizer

def get_jarvis_voice():
    global _jarvis_voice, _current_voice_type
    if _jarvis_voice is None and HAS_VOICE_COMPONENTS:
        try:
            from jarvis_voice import JarvisVoice
            _jarvis_voice = JarvisVoice(voice_type=_current_voice_type)
            print(f"✅ JarvisVoice инициализирован с голосом: {_current_voice_type}")
        except Exception as e:
            print(f"⚠️ Ошибка инициализации голоса: {e}")
            _jarvis_voice = None
    return _jarvis_voice


@voice_router.post("/recognize")
async def recognize_speech(
    language: str = "ru-RU",
    timeout: int = 8
) -> JSONResponse:
    """
    Распознать речь с микрофона
    
    Args:
        language: Язык (ru-RU, en-US)
        timeout: Максимальное время ожидания (сек)
    
    Returns:
        {
            "success": bool,
            "text": str,
            "confidence": float,
            "duration": float
        }
    """
    try:
        recognizer = get_recognizer()
        if recognizer is None:
            return JSONResponse({
                "success": False,
                "message": "❌ Распознаватель речи недоступен"
            }, status_code=503)
        
        # Переключить язык если нужно
        recognizer.language = language
        
        # Распознать речь
        text = recognizer.recognize_from_microphone(timeout=timeout, phrase_time_limit=20) if recognizer else None
        
        if text:
            return JSONResponse({
                "success": True,
                "text": text,
                "language": language,
                "message": f"✅ Распознано: {text}"
            })
        else:
            return JSONResponse({
                "success": False,
                "text": None,
                "message": "⚠️ Не смогла разобрать речь"
            }, status_code=400)
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка распознавания: {e}"
        }, status_code=500)


@voice_router.post("/recognize-file")
async def recognize_from_file(
    file: UploadFile = File(...),
    language: str = "ru-RU"
) -> JSONResponse:
    """
    Распознать речь из загруженного файла
    
    Args:
        file: Audio файл (WAV, MP3)
        language: Язык (ru-RU, en-US)
    
    Returns:
        {
            "success": bool,
            "text": str,
            "filename": str
        }
    """
    try:
        # Сохранить файл временно
        contents = await file.read()
        temp_file = f"temp_{file.filename}"
        
        with open(temp_file, "wb") as f:
            f.write(contents)
        
        # Распознать
        recognizer = get_recognizer()
        if recognizer is None:
            return JSONResponse({"success": False, "message": "❌ Распознаватель речи недоступен"}, status_code=503)
        recognizer.language = language
        text = recognizer.recognize_from_file(temp_file)
        
        # Удалить временный файл
        import os
        os.remove(temp_file)
        
        if text:
            return JSONResponse({
                "success": True,
                "text": text,
                "filename": file.filename,
                "message": f"✅ Распознано из файла: {text}"
            })
        else:
            return JSONResponse({
                "success": False,
                "message": "⚠️ Не смогла разобрать файл"
            }, status_code=400)
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка: {e}"
        }, status_code=500)


@voice_router.post("/speak")
async def speak_text(
    text: str = Form(...),
    voice: str = Form(default="jarvis"),
    speed: int = Form(default=100),
    volume: int = Form(default=90)
) -> JSONResponse:
    """
    Произнести текст голосом Джарвиса
    
    Args:
        text: Текст для произнесения
        voice: Тип голоса (jarvis, male, female)
        speed: Скорость речи (50-200%)
        volume: Громкость (0-100%)
    
    Returns:
        {
            "success": bool,
            "text": str,
            "duration": float
        }
    """
    try:
        # Установить параметры голоса
        voice = get_jarvis_voice()
        if voice is None:
            return JSONResponse({"success": False, "message": "❌ Голосовая система недоступна"}, status_code=503)
        voice.set_voice_speed(speed)
        voice.set_voice_volume(volume)
        
        # Произнести текст
        success = voice.speak(text)
        
        if success:
            return JSONResponse({
                "success": True,
                "text": text,
                "voice": voice,
                "speed": speed,
                "volume": volume,
                "message": "✅ Текст произнесен"
            })
        else:
            return JSONResponse({
                "success": False,
                "message": "❌ Ошибка при произнесении"
            }, status_code=500)
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка: {e}"
        }, status_code=500)


@voice_router.post("/speak-stream")
async def speak_stream(
    text: str = Form(...),
    voice: str = Form(default="jarvis")
) -> StreamingResponse:
    """
    Произнести текст и вернуть как audio stream (mp3)
    
    Args:
        text: Текст для произнесения
        voice: Тип голоса
    
    Returns:
        MP3 audio stream
    """
    try:
        # Генерировать речь через Edge TTS
        import edge_tts
        
        async def generate():
            communicate = edge_tts.Communicate(
                text, 
                voice="ru-RU-DmitryNeural"  # Джарвис на русском
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        
        return StreamingResponse(
            generate(),
            media_type="audio/mpeg"
        )
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка: {e}"
        }, status_code=500)


@voice_router.get("/status")
async def voice_status() -> JSONResponse:
    """
    Получить статус голосовой системы
    
    Returns:
        {
            "recognizer": "active/inactive",
            "voice": "ready/not_ready",
            "microphone": "available/not_available",
            "engines": [list of available engines]
        }
    """
    try:
        from advanced_voice import (
            HAS_SPEECH_RECOGNITION,
            HAS_EDGE_TTS,
            HAS_PYTTSX3,
            HAS_SOUNDDEVICE
        )
        
        return JSONResponse({
            "recognizer": "active" if HAS_SPEECH_RECOGNITION else "inactive",
            "voice": "ready" if (HAS_EDGE_TTS or HAS_PYTTSX3) else "not_ready",
            "microphone": "available" if HAS_SOUNDDEVICE else "checking",
            "engines": {
                "speech_recognition": HAS_SPEECH_RECOGNITION,
                "edge_tts": HAS_EDGE_TTS,
                "pyttsx3": HAS_PYTTSX3,
                "sounddevice": HAS_SOUNDDEVICE
            },
            "current_voice": "ru-RU-DmitryNeural (Jarvis)",
            "message": "✅ Голосовая система готова"
        })
    
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "error": str(e),
            "message": f"❌ Ошибка: {e}"
        }, status_code=500)


@voice_router.post("/command-voice")
async def voice_command(
    timeout: int = Form(default=8),
    language: str = Form(default="ru-RU")
) -> JSONResponse:
    """
    Полный цикл: слушаем команду, обрабатываем, произносим ответ
    
    Args:
        timeout: Максимальное время для команды
        language: Язык распознавания
    
    Returns:
        {
            "success": bool,
            "command": str,
            "response": str,
            "processing_time": float
        }
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Слушать команду
        print("🎤 Слушаю команду...")
        recognizer.language = language
        command = recognizer.recognize_from_microphone(timeout=timeout, phrase_time_limit=20)
        
        if not command:
            jarvis_voice.speak("Прошу прощения, не смогла разобрать. Попробуйте еще раз.")
            return JSONResponse({
                "success": False,
                "message": "⚠️ Команда не распознана"
            }, status_code=400)
        
        print(f"📝 Распознана команда: {command}")
        
        # 2. Произнести подтверждение
        jarvis_voice.speak("Понял, сэр. Выполняю.")
        
        # 3. Вернуть результат
        processing_time = time.time() - start_time
        
        return JSONResponse({
            "success": True,
            "command": command,
            "processing_time": processing_time,
            "message": f"✅ Команда обработана: {command}"
        })
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка обработки команды: {e}"
        }, status_code=500)


@voice_router.post("/set-voice")
async def set_voice(voice_type: str = Form(...)) -> JSONResponse:
    """
    Переключить голос Джарвиса
    
    Args:
        voice_type: Тип голоса (dmitry, ryan, neural, amira)
    
    Returns:
        {
            "success": bool,
            "voice_type": str,
            "message": str
        }
    """
    global _jarvis_voice, _current_voice_type
    
    try:
        # Переинициализировать голос с новым типом
        _current_voice_type = voice_type
        
        # Если голос уже был инициализирован, переключить его
        if _jarvis_voice is not None:
            success = _jarvis_voice.set_voice(voice_type)
            if success:
                return JSONResponse({
                    "success": True,
                    "voice_type": voice_type,
                    "message": f"✅ Голос изменён на: {voice_type}"
                })
            else:
                return JSONResponse({
                    "success": False,
                    "message": f"❌ Неизвестный голос: {voice_type}"
                }, status_code=400)
        else:
            # Голос ещё не инициализирован, просто сохраняем тип
            return JSONResponse({
                "success": True,
                "voice_type": voice_type,
                "message": f"✅ Голос будет использован: {voice_type}"
            })
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка при переключении голоса: {e}"
        }, status_code=500)


@voice_router.get("/voices")
async def get_available_voices() -> JSONResponse:
    """
    Получить список доступных голосов
    
    Returns:
        {
            "available_voices": {
                "dmitry": "Дмитрий (Русский)",
                "ryan": "Ryan (Британский JARVIS)",
                ...
            },
            "current_voice": str
        }
    """
    try:
        from jarvis_voice import JarvisVoice
        
        voices_dict = {
            code: info['name'] 
            for code, info in JarvisVoice.VOICES.items()
        }
        
        return JSONResponse({
            "available_voices": voices_dict,
            "current_voice": _current_voice_type,
            "message": "✅ Список голосов получен"
        })
    
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": f"❌ Ошибка: {e}"
        }, status_code=500)


# Экспортируем router
__all__ = ["voice_router"]
