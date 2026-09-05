#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Scott AI Assistant - FastAPI Backend V2.1
Главный сервер с расширенным функционалом команд и интеллектуальным распознаванием вопросов
"""

import os
import sys
import io
import time

# Своя папка — в пути поиска модулей.
#
# Обычный Python добавляет туда каталог запускаемого скрипта сам, а встроенная
# сборка из дистрибутива — нет: файл ._pth переводит её в изолированный режим.
# Из-за этого на чужой машине backend падал сразу: «No module named security»,
# хотя security.py лежит рядом с main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Установить UTF-8 кодировку для вывода.
#
# Консоль Windows по умолчанию отдаёт cp1251, и эмодзи в сообщениях валят
# print с UnicodeEncodeError. Но подменять поток вслепую нельзя: под pytest
# вывод уже перехвачен, и подмена его буфера ломает захват — прогон падает с
# «I/O operation on closed file» ещё до первой проверки. Поэтому оборачиваем
# только то, что ещё не в UTF-8.
def _force_utf8(stream):
    encoding = (getattr(stream, 'encoding', '') or '').lower().replace('-', '')
    if encoding == 'utf8':
        return stream
    try:
        return io.TextIOWrapper(stream.buffer, encoding='utf-8')
    except (AttributeError, ValueError):
        return stream


sys.stdout = _force_utf8(sys.stdout)
sys.stderr = _force_utf8(sys.stderr)

# 🔑 Загрузить переменные из .env файла
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException, Form, Request, Depends
from security import require_scott_token, check_rate_limit
from timing import stage as timing_stage, snapshot as timing_snapshot, reset as timing_reset
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
from typing import Dict, Optional
from contextlib import asynccontextmanager
import uvicorn
import logging
import traceback

# Когда запускаем backend/main.py как скрипт, нужно гарантировать, что каталог backend в sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Импортируем наши модули
try:
    from scott_voice import ScottVoice, ScottVoiceAsync
except Exception as e:
    try:
        from .scott_voice import ScottVoice, ScottVoiceAsync
    except Exception as e2:
        print(f"⚠️ Не удалось импортировать scott_voice: {e} / {e2}")
        # Заглушки, чтобы приложение могло запускаться без TTS
        class ScottVoice:
            def __init__(self):
                print("⚠️ ScottVoice заглушка инициализирована — pyttsx3 недоступен")
                self.engine = None
            async def speak(self, text, save_file=None):
                return None
            def speak_to_file(self, text):
                return None
            def play_audio(self, audio_file):
                return None

        class ScottVoiceAsync:
            def __init__(self):
                self.voice = ScottVoice()
            async def speak_and_play(self, text: str):
                return None

try:
    from .command_executor import get_command_executor
    from .command_parser import get_command_parser
    from .fast_intent import get_fast_intent_engine
    from .question_answerer import get_question_answerer
    from .web_scraper import get_web_scraper
    from .scott_profile import get_scott_profile
    from .knowledge_base import get_knowledge_base
    from .system_monitor import get_system_monitor
    from .intelligent_answerer import init_intelligent_answerer, get_intelligent_answerer
    from .voice_name_trigger import get_voice_trigger, check_voice_trigger
    from .web_integrations import web_integrations
except ImportError:
    from command_executor import get_command_executor
    from command_parser import get_command_parser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    from web_scraper import get_web_scraper
    from scott_profile import get_scott_profile
    from knowledge_base import get_knowledge_base
    from system_monitor import get_system_monitor
    from intelligent_answerer import init_intelligent_answerer, get_intelligent_answerer
    from voice_name_trigger import get_voice_trigger, check_voice_trigger
    import web_integrations as web_integrations

# Расширенные команды (v3.1) и компоненты v3.2 создаются в runtime.py и берутся
# оттуда — тем же модулем пользуются роутеры. Держать создание здесь нельзя:
# фабрики вроде get_ifttt_manager() возвращают каждый раз новый экземпляр, и у
# роутера оказался бы менеджер с собственным состоянием в памяти.
try:
    from . import runtime as scott_runtime
    from . import device_settings as scott_device_settings
except ImportError:
    import runtime as scott_runtime
    import device_settings as scott_device_settings

HAS_EXTENDED_EXECUTOR = scott_runtime.HAS_EXTENDED_EXECUTOR
extended_executor = scott_runtime.extended_executor

HAS_V32_FEATURES = scott_runtime.HAS_V32_FEATURES
context_manager = scott_runtime.context_manager
custom_commands_manager = scott_runtime.custom_commands_manager
ifttt_manager = scott_runtime.ifttt_manager
analytics_manager = scott_runtime.analytics_manager

# Расширенные компоненты (v3.3)
try:
    try:
        from .profile_manager import get_profile_manager
        from .templates_manager import get_template_manager
        from .macro_recorder import get_macro_recorder
        from .version_manager import get_version_manager
        from .voice_rule_builder import get_voice_rule_builder
        from .v33_endpoints import router as v33_router, init_v33_endpoints
    except ImportError:
        from profile_manager import get_profile_manager
        from templates_manager import get_template_manager
        from macro_recorder import get_macro_recorder
        from version_manager import get_version_manager
        from voice_rule_builder import get_voice_rule_builder
        from v33_endpoints import router as v33_router, init_v33_endpoints
    
    profile_manager = get_profile_manager()
    templates_manager = get_template_manager()
    macro_recorder = get_macro_recorder()
    version_manager = get_version_manager()
    voice_rule_builder = get_voice_rule_builder()
    
    # Инициализируем endpoints (передаем intelligent_answerer если доступен)
    ia = intelligent_answerer if 'intelligent_answerer' in dir() else None
    init_v33_endpoints(profile_manager, templates_manager, macro_recorder, version_manager, voice_rule_builder, ia)
    
    HAS_V33_FEATURES = True
    print("✅ Компоненты v3.3 загружены")
except ImportError as e:
    HAS_V33_FEATURES = False
    print(f"⚠️ Компоненты v3.3 не доступны: {e}")
    profile_manager = None
    templates_manager = None
    macro_recorder = None
    version_manager = None
    voice_rule_builder = None
    v33_router = None

# Версионные компоненты (v3.0)
try:
    try:
        from .version_endpoints import version_router
    except ImportError:
        from version_endpoints import version_router
    HAS_VERSION_ENDPOINTS = True
except ImportError:
    HAS_VERSION_ENDPOINTS = False
    version_router = None
    print("⚠️ Версионные endpoints не доступны.")


# Инициализация
# ============= LIFESPAN CONTEXT MANAGER =============

# Настройка логирования в файл для сбора traceback при падениях
log_path = os.path.join(os.path.dirname(__file__), '..', 'backend_errors.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Глобальная печать неперехваченных исключений
def _global_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error('Uncaught exception', exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = _global_excepthook

# asyncio loop exceptions
try:
    loop = asyncio.get_event_loop()
    def _asyncio_exception_handler(loop, context):
        msg = context.get('message', 'Asyncio exception')
        exc = context.get('exception')
        logging.error('Asyncio exception: %s', msg, exc_info=exc)
    loop.set_exception_handler(_asyncio_exception_handler)
except Exception:
    logging.exception('Failed to set asyncio exception handler')


# ==================== ПРОГРЕВ МОДЕЛЕЙ ====================
# Whisper и Silero грузятся лениво, при первом обращении, и вся эта плата
# ложилась на первую голосовую команду пользователя: около 6 с на загрузку
# Whisper и 1.5 с на Silero, а сверх загрузки — ещё по паре секунд на первые
# прогоны, пока CUDA дотягивает ядра под реальную работу. Замерено: первая
# команда после запуска обходилась в 7.3 с (4.5 на синтез, 2.7 на
# распознавание), тогда как прогретые модели дают ~120 мс и ~490 мс.
#
# Прогрев идёт фоновой задачей, а не в теле lifespan: сервер должен отвечать
# на /health сразу, иначе лаунчер минуту показывает статус «offline».
WARMUP_MODELS = os.getenv("WARMUP_MODELS", "1").strip().lower() not in ("0", "false", "no")


def _warmup_silero_in_thread(barrier: threading.Barrier) -> None:
    """
    Прогнать через Silero несколько холостых фраз внутри потока tts_executor.

    Прогонов именно три, и это не запас на всякий случай: замеры показывают,
    что первые ДВА вызова save_wav стоят около двух секунд каждый, а начиная
    с третьего укладываются в 10-15 мс. Причём вход при этом один и тот же —
    дело не в длине фразы, а в том, что CUDA дотягивает ядра под реальную
    работу. Один холостой прогон, как было сначала, снимал только половину
    платы, и первая фраза пользователя всё равно ждала две секунды.

    Прогревается тот же путь, которым идут запросы (save_wav, а не apply_tts):
    прогрев соседнего пути ничего не даёт.

    Барьер разводит задачи по РАЗНЫМ потокам пула: без него пул выполнил бы
    обе последовательно в первом освободившемся потоке, а второй остался бы
    холодным.
    """
    tmp_path = None
    try:
        import silero_tts
        barrier.wait(timeout=60)
        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="scott_warmup_")
        os.close(fd)
        model = silero_tts.get_model()
        for _ in range(3):
            model.save_wav(
                text="разогрев",
                speaker=silero_tts.DEFAULT_SILERO_VOICE,
                sample_rate=silero_tts.SAMPLE_RATE,
                audio_path=tmp_path,
            )
    except Exception as e:
        print(f"⚠️ Прогрев Silero в потоке не удался: {e}")
    finally:
        # Файл временный и одноразовый: в audio_cache он не нужен, там лежат
        # настоящие ответы Scott, которые переиспользуются между запусками.
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _warmup_whisper_sync() -> None:
    """Загрузить Whisper и прогнать через него секунду тишины."""
    import numpy as np
    model = _get_whisper_model()
    model.transcribe(
        np.zeros(16000, dtype=np.float32),
        language="ru",
        fp16=(_whisper_device == "cuda"),
    )


async def _watch_parent() -> None:
    """
    Завершиться, если тот, кто нас запустил, исчез.

    Лаунчер гасит backend при выходе, но только когда закрывается штатно.
    Стоит завершить его через диспетчер задач — и backend остаётся сиротой:
    держит порт 8000 и занимает видеокарту, а пользователь считает, что вышел
    из программы. Проверено на живом запуске, так и происходило.

    PID родителя приходит в переменной окружения: при обычном запуске из
    терминала её нет, и слежка не включается — иначе backend завершался бы,
    как только разработчик закроет свою консоль.
    """
    raw = os.getenv("SCOTT_PARENT_PID", "").strip()
    if not raw.isdigit():
        return

    parent_pid = int(raw)
    print(f"👁️ Слежу за родителем (PID {parent_pid}): исчезнет — завершусь")

    try:
        import psutil
    except ImportError:
        return

    while True:
        await asyncio.sleep(5)
        if not psutil.pid_exists(parent_pid):
            print("👋 Лаунчер закрылся — останавливаюсь, чтобы не висеть без дела")
            # Мягкая остановка невозможна: uvicorn держит цикл, а сигналы на
            # Windows приходят не туда. Завершаем процесс явно.
            os._exit(0)


async def _warmup_models() -> None:
    """
    Разогреть тяжёлые модели в фоне, чтобы первая команда шла по горячему пути.

    Порядок не случаен: сначала синтез (полторы секунды), потом распознавание
    (шесть) — если пользователь заговорит с Scott сразу после запуска, к этому
    моменту голос уже будет готов ответить.
    """
    loop = asyncio.get_running_loop()

    # --- Синтез речи ---
    try:
        import scott_voice
        current = scott_voice.get_current_voice()
        if scott_voice._is_silero_voice(current):
            t = time.perf_counter()
            import silero_tts
            # Веса тянем один раз в отдельном потоке: если бы обе задачи пула
            # вызвали get_model() разом, они бы грузили модель параллельно.
            await asyncio.to_thread(silero_tts.get_model)
            barrier = threading.Barrier(TTS_WORKERS)
            await asyncio.gather(*[
                loop.run_in_executor(tts_executor, _warmup_silero_in_thread, barrier)
                for _ in range(TTS_WORKERS)
            ])
            print(f"🔥 Silero прогрет за {(time.perf_counter() - t) * 1000:.0f} мс "
                  f"({TTS_WORKERS} потока)")
        else:
            print(f"ℹ️ Прогрев синтеза пропущен: активен облачный голос «{current}»")
    except Exception as e:
        print(f"⚠️ Прогрев синтеза не удался: {e}")

    # --- Распознавание речи ---
    try:
        t = time.perf_counter()
        await asyncio.to_thread(_warmup_whisper_sync)
        print(f"🔥 Whisper прогрет за {(time.perf_counter() - t) * 1000:.0f} мс")
    except Exception as e:
        print(f"⚠️ Прогрев Whisper не удался: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Обработка запуска и завершения приложения
    Заменяет deprecated @app.on_event()
    """
    # ===== STARTUP =====
    print("\n" + "="*80)
    print("🚀 Scott AI Backend запущен!")
    print("="*80)
    print(f"📍 API: http://localhost:8000")
    print(f"📍 WebSocket: ws://localhost:8000/ws/chat")
    print(f"📍 Docs: http://localhost:8000/docs")
    print("="*80 + "\n")

    # Слушателю нужен этот цикл, чтобы возвращать в него услышанные команды.
    _set_main_loop(asyncio.get_running_loop())

    warmup_task = asyncio.create_task(_warmup_models()) if WARMUP_MODELS else None
    asyncio.create_task(_watch_parent())

    yield  # Приложение работает здесь

    if warmup_task and not warmup_task.done():
        warmup_task.cancel()
    
    # ===== SHUTDOWN =====
    print("\n" + "="*80)
    print("👋 Scott AI Backend остановлен")
    print("="*80 + "\n")


app = FastAPI(
    title="Scott AI Assistant v2.1",
    lifespan=lifespan
)

# Exception handler for HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "data": None
        },
    )

# CORS
# Источники ограничены петлевым адресом. Со «*» и allow_credentials любая
# открытая в браузере страница могла слать запросы на localhost:8000 — то есть
# посторонний сайт получал возможность запускать программы на компьютере
# пользователя. Лаунчер ходит с этой же машины, ему звёздочка не нужна.
_LOCAL_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in ("1420", "5173", "8000", "8001", "3000")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secure execution router (token-protected, whitelisted commands)
try:
    try:
        from .secure_exec import router as secure_exec_router
    except ImportError:
        from secure_exec import router as secure_exec_router
    app.include_router(secure_exec_router, prefix="/internal")
    print("🔒 Secure exec endpoint mounted at /internal/execute")
except ImportError:
    print("⚠️ secure_exec router not available")

# Подключить версионные endpoints (v3.0)
if HAS_VERSION_ENDPOINTS and version_router:
    app.include_router(version_router)

# Подключить endpoints v3.3 (Профили, Шаблоны, Макросы, Версии, Голос)
if HAS_V33_FEATURES and v33_router:
    app.include_router(v33_router)

# Расширенное управление компьютером (v3.1): PowerShell, файлы, громкость,
# питание, планировщик. Живёт в extended_endpoints.py.
try:
    try:
        from .extended_endpoints import router as extended_router
    except ImportError:
        from extended_endpoints import router as extended_router
    app.include_router(extended_router)
except ImportError as e:
    print(f"⚠️ Расширенные endpoints не подключены: {e}")

# Возможности v3.2: контекст, пользовательские команды, IFTTT, аналитика.
# Живут в v32_endpoints.py.
try:
    try:
        from .v32_endpoints import router as v32_router
    except ImportError:
        from v32_endpoints import router as v32_router
    app.include_router(v32_router)
except ImportError as e:
    print(f"⚠️ Endpoints v3.2 не подключены: {e}")

# Управление ИИ-ассистентом (провайдер, модель, память). Живёт в ai_endpoints.py.
try:
    try:
        from .ai_endpoints import router as ai_router
    except ImportError:
        from ai_endpoints import router as ai_router
    app.include_router(ai_router)
except ImportError as e:
    print(f"⚠️ Endpoints управления ИИ не подключены: {e}")

# Диагностика: логи, сведения о машине, сбор отчёта об ошибке для отправки
# разработчику. Живёт в diagnostics_endpoints.py.
try:
    try:
        from .diagnostics_endpoints import router as diagnostics_router
    except ImportError:
        from diagnostics_endpoints import router as diagnostics_router
    app.include_router(diagnostics_router)
except ImportError as e:
    print(f"⚠️ Endpoints диагностики не подключены: {e}")

# Настройки, доступные из лаунчера: выбор устройства для речи.
try:
    try:
        from .settings_endpoints import router as settings_router
    except ImportError:
        from settings_endpoints import router as settings_router
    app.include_router(settings_router)
except ImportError as e:
    print(f"⚠️ Endpoints настроек не подключены: {e}")

# Прослушивание микрофона: старт, остановка, состояние.
try:
    try:
        from .listen_endpoints import router as listen_router
    except ImportError:
        from listen_endpoints import router as listen_router
    app.include_router(listen_router)
except ImportError as e:
    print(f"⚠️ Endpoints прослушивания не подключены: {e}")

# Напоминания и отложенные дела.
try:
    try:
        from .reminder_endpoints import router as reminder_router
    except ImportError:
        from reminder_endpoints import router as reminder_router
    app.include_router(reminder_router)
except ImportError as e:
    print(f"⚠️ Endpoints напоминаний не подключены: {e}")

# Написание, сборка и запуск программ.
try:
    try:
        from .code_endpoints import router as code_router
    except ImportError:
        from code_endpoints import router as code_router
    app.include_router(code_router)
except ImportError as e:
    print(f"⚠️ Endpoints работы с кодом не подключены: {e}")

# ✨ Инициализируем intelligent_answerer перед использованием в endpoints
print("\n✨ Ранняя инициализация IntelligentAnswerer...")
try:
    from .intelligent_answerer import init_intelligent_answerer
except ImportError:
    from intelligent_answerer import init_intelligent_answerer
intelligent_answerer = init_intelligent_answerer()
print(f"✅ intelligent_answerer инициализирован: {intelligent_answerer is not None}")

# ✨ Передаём intelligent_answerer в v33_endpoints
try:
    from .v33_endpoints import set_intelligent_answerer
except ImportError:
    from v33_endpoints import set_intelligent_answerer
set_intelligent_answerer(intelligent_answerer)
print(f"✅ intelligent_answerer передан в v33_endpoints")

# Глобальные компоненты
scott_voice = None
recognizer = None
executor = None
command_parser = None
fast_intent_engine = None
question_answerer = None
web_scraper = None
scott_profile = None
knowledge_base = None
system_monitor = None
voice_trigger = None
TTS_WORKERS = 2
tts_executor = ThreadPoolExecutor(max_workers=TTS_WORKERS)

# Служебные слова, вырезаемые из фразы при извлечении поискового запроса для
# веб-интеграций (см. ScottAI._extract_web_query) — то, что осталось после
# вырезания, и есть то, что реально нужно искать.
YOUTUBE_FILLER_WORDS = {
    'скотт', 'scott', 'ютуб', 'ютубе', 'ютубу', 'youtube', 'найди', 'найти',
    'включи', 'включить', 'открой', 'открыть', 'запусти', 'запустить',
    'поищи', 'искать', 'поиск', 'видео', 'ролик', 'про', 'на', 'в', 'из', 'и',
}
# Слова, которыми человек уточняет «просто открой сайт»: после их вырезания
# запрос оказывается пустым, и Scott открывает главную вместо поиска. В логе
# была фраза «открой youtube в главное меню» — Scott искал на YouTube «главное
# меню».
SITE_WORDS = {
    'главную', 'главная', 'главное', 'меню', 'сайт', 'сайты', 'страницу',
    'страница', 'приложение', 'просто', 'мне', 'пожалуйста',
}

GITHUB_FILLER_WORDS = {
    'скотт', 'scott', 'гитхаб', 'гитхабе', 'github', 'зайди', 'зайти',
    'открой', 'открыть', 'найди', 'найти', 'выбери', 'выбрать', 'поищи',
    'поиск', 'репозиторий', 'репозиторию', 'репо', 'этот', 'эту', 'это',
    'на', 'в', 'и',
}


class ScottAI:
    """Главный AI мозг Scott"""
    
    def __init__(self):
        global scott_voice, recognizer, executor, command_parser
        global fast_intent_engine, question_answerer, web_scraper, scott_profile, knowledge_base, system_monitor
        global intelligent_answerer, voice_trigger
        
        print("🤖 Инициализирую Scott AI...")
        
        try:
            # Инициализируем все компоненты (кроме intelligent_answerer который уже инициализирован выше)
            scott_voice = ScottVoice()
            # Роутеры берут голос отсюда: импортировать main.py им нельзя —
            # получилось бы кольцо импортов.
            scott_runtime.set_scott_voice(scott_voice)
            executor = get_command_executor()
            command_parser = get_command_parser()
            fast_intent_engine = get_fast_intent_engine()
            question_answerer = get_question_answerer()
            web_scraper = get_web_scraper()
            scott_profile = get_scott_profile()
            knowledge_base = get_knowledge_base()
            system_monitor = get_system_monitor()
            
            # intelligent_answerer уже инициализирован выше
            print(f"📌 intelligent_answerer используется: {intelligent_answerer is not None}")
            
            voice_trigger = get_voice_trigger()
            
            print(f"🎤 Voice Name Trigger активирован (требуется произнесение имени)")
        except Exception as e:
            print(f"❌ Ошибка в ScottAI.__init__: {e}")
            import traceback
            traceback.print_exc()
        
        self.scott_voice = scott_voice
        self.voice_async = ScottVoiceAsync()

        # Последняя написанная программа: следом человек говорит «запусти», и
        # повторять, что именно запускать, ему не приходится.
        self.last_program = None
        
        # Фразы для ответов (когда режим тишины выключен)
        self.acknowledgement_phrases = [
            "К вашим услугам,",
            "Слушаю вас,",
            "Да, сэр,",
            "Готов помочь,",
            "Есть, сэр,",
            "Понял, выполняю,",
            "Прямо сейчас,",
            "С удовольствием,",
            "Вашу команду исполню,",
            "Работаю над этим,"
        ]
        
        self.execution_phrases = [
            "Выполняю запрос,",
            "Обрабатываю информацию,",
            "Ищу данные,",
            "Выполняю команду,",
            "Работаю,",
            "Загружаю,",
            "Анализирую,",
            "Проверяю,",
        ]
        
        self.completion_phrases = [
            "Готово.",
            "Сделано.",
            "Операция завершена.",
            "Выполнено.",
            "Работа закончена.",
            "Всё готово.",
        ]
        
        print("✅ Scott AI полностью инициализирован!")
        print(f"   Профиль: {scott_profile.get_name()}")
        print(f"   Язык: {scott_profile.get_language()}")
        print(f"   Версия: {scott_profile.get('version')}")
    
    def get_phrase_for_response(self) -> str:
        """Получить случайную фразу для ответа (когда режим тишины выключен)"""
        import random
        phrases = self.acknowledgement_phrases + self.execution_phrases
        return random.choice(phrases)
    
    async def process_command(self, text: str, quiet_mode: bool = False, user_name: str = "User") -> Dict:
        """
        Обёртка над _process_command_impl: замеряет время отклика и пишет
        каждую команду в analytics_manager — раньше это нигде не вызывалось,
        и вкладка аналитики всегда показывала бы пустые данные.
        """
        start = time.time()
        with timing_stage("00.команда.всего"):
            result = await self._process_command_impl(text, quiet_mode=quiet_mode, user_name=user_name)
        if HAS_V32_FEATURES:
            try:
                analytics_manager.record_command(
                    command_type=result.get("type", "unknown"),
                    command=text,
                    success="error" not in result.get("type", ""),
                    response_time=time.time() - start,
                )
            except Exception as e:
                print(f"⚠️ Не удалось записать аналитику: {e}")
        return result

    async def _process_command_impl(self, text: str, quiet_mode: bool = False, user_name: str = "User") -> Dict:
        """
        Главный метод обработки команд
        Парсит, выполняет и возвращает результат

        Приоритет обработки:
        1. Память (быстрые ответы)
        2. Вопросы (встроенная база + ИИ если включен)
        3. Команды (парсинг и выполнение)
        """
        print(f"\n👤 Пользователь ({user_name}): {text}")

        try:
            # 1. Проверяем память (если есть прямой ответ)
            with timing_stage("память.поиск"):
                memory_result = knowledge_base.search_memory(text)
            if memory_result:
                for key, data in memory_result.items():
                    response = data.get("value")
                    if not response or 'processing:' in response.lower():
                        continue
                    print(f"💾 Из памяти: {response}")
                    return {
                        "type": "memory",
                        "response": response,
                        "source": "knowledge_base",
                        "quiet_mode": quiet_mode
                    }

            lower_text = text.lower().strip()
            with timing_stage("intent.быстрый"):
                intent = fast_intent_engine.detect(text)
            print(f"🔎 Быстрый intent: {intent}")

            # Веб-интеграции (YouTube/GitHub) — проверяем ДО общей логики
            # вопрос/команда: упоминание конкретного сервиса однозначно
            # указывает на намерение, и не нужно рисковать тем, что
            # is_question()/command_parser (уже не раз ловили баги на
            # пересечении их словарей синонимов) неверно всё переклассифицируют.
            if any(w in lower_text for w in ('ютуб', 'youtube')):
                query = self._extract_web_query(text, YOUTUBE_FILLER_WORDS | SITE_WORDS)
                with timing_stage("веб.youtube"):
                    # Искать нечего — значит человек просил открыть сам сайт.
                    if not query:
                        result = web_integrations.open_service_home("youtube")
                    else:
                        result = web_integrations.search_youtube_video(query)
                print(f"🎬 YouTube: {result['message']}")
                return {"type": "youtube_search", "response": result["message"], "quiet_mode": quiet_mode}

            if any(w in lower_text for w in ('гитхаб', 'github')):
                query = self._extract_web_query(text, GITHUB_FILLER_WORDS | SITE_WORDS)
                with timing_stage("веб.github"):
                    if not query:
                        result = web_integrations.open_service_home("github")
                    else:
                        result = web_integrations.search_github_repo(query)
                print(f"🐙 GitHub: {result['message']}")
                return {"type": "github_search", "response": result["message"], "quiet_mode": quiet_mode}

            # fast_intent_engine уже надёжно распознаёт команды действия (open_app,
            # create_file, powershell и т.д.) даже когда фраза оформлена как вопрос —
            # "Можешь открыть блокнот?" — intent.is_command будет True. Раньше здесь
            # использовался узкий список english-ключевых слов ('notepad', 'chrome', ...),
            # который не покрывал русские названия ('блокнот', 'проводник') и любые
            # команды кроме open_app — переключились на уже вычисленный intent.
            # 2. Вопросы и неявные вопросы (пропускаем, если это явная команда действия)
            if not intent.is_command and question_answerer.is_question(text):
                with timing_stage("ответ.локальный"):
                    answer = question_answerer.answer(text)
                if answer:
                    knowledge_base.add_conversation(text, answer)
                    print(f"🤖 Scott: {answer}")
                    return {
                        "type": "question",
                        "response": answer,
                        "quiet_mode": quiet_mode
                    }

                if intelligent_answerer:
                    print(f"🧠 Использую ИИ для ответа...")
                    with timing_stage("ответ.llm"):
                        ai_answer = intelligent_answerer.answer_question(text)
                    if ai_answer:
                        print(f"✨ Ответ от ИИ: {ai_answer[:100]}...")
                        knowledge_base.add_conversation(text, ai_answer)
                        return {
                            "type": "ai_question",
                            "response": ai_answer,
                            "quiet_mode": quiet_mode,
                            "ai_model": intelligent_answerer.model
                        }

                fallback_answer = "Извините, я не знаю ответ на этот вопрос. Попробуйте переформулировать или задайте другой вопрос."
                print(f"❓ Fallback ответ: {fallback_answer}")
                knowledge_base.add_conversation(text, fallback_answer)
                return {
                    "type": "question",
                    "response": fallback_answer,
                    "quiet_mode": quiet_mode
                }

            # 3. Парсим команду. Если fast_intent уже уверен, что это команда,
            # сначала снимаем вежливую/вопросительную обёртку — command_parser
            # заметно надёжнее на чистом императиве ("открой блокнот"), чем на
            # "Скотт, можешь открыть блокнот?".
            command_text = self._strip_command_wrapper(text) if intent.is_command else text
            with timing_stage("команда.парсинг"):
                parsed = command_parser.parse(command_text)
            print(f"🔍 Распарсена команда ({'очищено: ' + command_text if command_text != text else 'как есть'}): {parsed}")

            # fast_intent распознаёт управление громкостью и яркостью, а также
            # запрос списка процессов — по регулярным выражениям с якорями.
            # command_parser этих формулировок не знает и возвращает на «сделай
            # громче» тип unknown, а решение о выполнении принимается именно по
            # нему, поэтому команда молча превращалась в вопрос к LLM. Там, где
            # парсер ничего не понял, а интент уверен, доверяем интенту: он для
            # того и вычисляется раньше.
            if parsed.command_type == 'unknown' and intent.intent_type in ('system_command', 'list_processes', 'open_folder', 'reminder', 'write_code', 'run_code'):
                print(f"↪️ Парсер не понял фразу, беру тип из интента: {intent.intent_type}")
                parsed.command_type = intent.intent_type
                parsed.main_param = intent.main_param

            # Отдельный случай: парсер уверенно считает «открой загрузки»
            # запуском приложения, потому что видит глагол «открой». Интент же
            # разобрался, что речь о папке — и он тут точнее.
            if intent.intent_type == 'open_folder' and parsed.command_type in ('open_app', 'unknown'):
                parsed.command_type = 'open_folder'
                parsed.main_param = intent.main_param

            # Напоминание сильнее любого разбора: во фразе «напомни через час
            # открыть почту» парсер видит «открыть почту» и предлагает сделать
            # это немедленно — то есть ровно не то, о чём просили.
            if intent.intent_type == 'reminder':
                parsed.command_type = 'reminder'
                parsed.main_param = intent.main_param

            # Просьба написать программу тоже сильнее разбора: во фразе
            # «напиши программу на C» парсер видит «программу» и пытается
            # что-то запустить.
            if intent.intent_type == 'write_code':
                parsed.command_type = 'write_code'
                parsed.main_param = intent.main_param

            if intent.intent_type == 'run_code':
                parsed.command_type = 'run_code'
                parsed.main_param = intent.main_param

            explicit_action = any(
                lower_text.startswith(prefix) for prefix in [
                    'открой ', 'запусти ', 'открыть ', 'включи ', 'вкл ',
                    'start ', 'launch ', 'run ', 'open ', 'open file ', 'открой файл '
                ]
            )
            explicit_system = any(keyword in lower_text for keyword in [
                'notepad', 'chrome', 'code', 'vscode', 'cmd', 'powershell', 'explorer',
                'paint', 'word', 'excel', 'telegram', 'discord', 'spotify', 'browser'
            ])
            action_command_types = {
                'open_app', 'close_app', 'create_file', 'create_folder', 'open_website',
                'get_currency', 'get_weather', 'get_news', 'system_info', 'manage_window',
                'file_operation', 'system_command', 'open_url',
                'list_processes', 'open_folder', 'reminder', 'write_code', 'run_code'
            }
            # 'powershell' и 'run_script' здесь намеренно отсутствуют. /command
            # не требует токена, и стоит появиться ветке выполнения для этих
            # типов — произвольная команда оболочки станет доступна любому, кто
            # дотянулся до порта. Выполнять их можно только через
            # /extended/powershell и /internal/execute: там есть и Bearer-токен,
            # и ограничитель частоты, и белый список.
            SHELL_TYPES = {'powershell', 'run_script'}
            explicit_search = any(
                keyword in lower_text for keyword in ['найди', 'ищи', 'гугли', 'поиск', 'search', 'find', 'look for', 'google', 'поискать', 'гугль', 'яндекс']
            )

            if parsed.command_type == 'search' and not explicit_search and self._is_question_like(text, lower_text, intent):
                print("❗ Переопределяю поиск как вопрос на основе вопросной формы текста")
                with timing_stage("ответ.локальный"):
                    answer = question_answerer.answer(text)
                if answer:
                    knowledge_base.add_conversation(text, answer)
                    print(f"🤖 Scott: {answer}")
                    return {
                        "type": "question",
                        "response": answer,
                        "quiet_mode": quiet_mode
                    }
                if intelligent_answerer and intelligent_answerer.enabled:
                    print(f"🧠 Использую ИИ для ответа на вопрос, который распознан как неявный")
                    with timing_stage("ответ.llm"):
                        ai_answer, success = intelligent_answerer.answer(text, use_memory=True)
                    if success and ai_answer:
                        knowledge_base.add_conversation(text, ai_answer)
                        return {
                            "type": "ai_question",
                            "response": ai_answer,
                            "quiet_mode": quiet_mode,
                            "ai_model": intelligent_answerer.model
                        }
                fallback_answer = "Извините, я не знаю ответ на этот вопрос. Попробуйте переформулировать или задайте другой вопрос."
                knowledge_base.add_conversation(text, fallback_answer)
                return {
                    "type": "question",
                    "response": fallback_answer,
                    "quiet_mode": quiet_mode
                }

            looks_like_search = parsed.command_type == 'search' and explicit_search
            should_execute_action = (
                parsed.command_type in action_command_types
                or looks_like_search
                or explicit_action
                or explicit_system
            )

            if parsed.command_type in SHELL_TYPES:
                refusal = (
                    "Выполнять команды оболочки голосом я не буду — это делается "
                    "через защищённый эндпоинт с токеном."
                )
                print(f"🛡️ Отказ: попытка выполнить «{parsed.command_type}» через /command")
                knowledge_base.add_conversation(text, refusal)
                return {
                    "type": "refused",
                    "response": refusal,
                    "quiet_mode": quiet_mode,
                }

            if should_execute_action:
                with timing_stage("команда.выполнение"):
                    response = await self._execute_parsed_command(parsed, text)
                knowledge_base.add_conversation(text, response)
                print(f"🤖 Scott: {response}")
                return {
                    "type": "command",
                    "command": parsed.command_type,
                    "response": response,
                    "confidence": getattr(parsed, 'confidence', None),
                    "quiet_mode": quiet_mode
                }

            if question_answerer.is_question(text) or len(lower_text.split()) <= 5:
                with timing_stage("ответ.локальный"):
                    answer = question_answerer.answer(text)
                if answer:
                    knowledge_base.add_conversation(text, answer)
                    print(f"🤖 Scott: {answer}")
                    return {
                        "type": "question",
                        "response": answer,
                        "quiet_mode": quiet_mode
                    }
                if intelligent_answerer and intelligent_answerer.enabled:
                    print(f"🧠 Использую ИИ для ответа на короткий вопрос...")
                    with timing_stage("ответ.llm"):
                        ai_answer, success = intelligent_answerer.answer(text, use_memory=True)
                    if success and ai_answer:
                        knowledge_base.add_conversation(text, ai_answer)
                        return {
                            "type": "ai_question",
                            "response": ai_answer,
                            "quiet_mode": quiet_mode,
                            "ai_model": intelligent_answerer.model
                        }
                fallback_answer = "Привет! Я Scott. Я могу ответить на вопросы, помочь с командами и поддержать обычный разговор."
                knowledge_base.add_conversation(text, fallback_answer)
                print(f"🤖 Scott: {fallback_answer}")
                return {
                    "type": "question",
                    "response": fallback_answer,
                    "quiet_mode": quiet_mode
                }

            with timing_stage("команда.выполнение"):
                response = await self._execute_parsed_command(parsed, text)
            knowledge_base.add_conversation(text, response)
            print(f"🤖 Scott: {response}")
            return {
                "type": "command",
                "command": parsed.command_type,
                "response": response,
                "confidence": getattr(parsed, 'confidence', None),
                "quiet_mode": quiet_mode
            }

        except Exception as e:
            error_msg = f"❌ Ошибка: {str(e)}"
            print(error_msg)
            return {
                "type": "error",
                "response": error_msg,
                "error": str(e)
            }

    def _is_question_like(self, text: str, lower_text: str, intent: str) -> bool:
        """Определить, следует ли интерпретировать фразу как вопрос."""
        if text.strip().endswith('?'):
            return True
        if intent and intent.lower() == 'question':
            return True
        question_keywords = [
            'что', 'где', 'когда', 'как', 'почему', 'зачем', 'сколько',
            'чей', 'чья', 'чьё', 'кем', 'какой', 'какая', 'какое', 'какие',
            'который', 'есть ли', 'можно ли', 'правда ли'
        ]
        for keyword in question_keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', lower_text):
                return True
        return False

    def _strip_command_wrapper(self, text: str) -> str:
        """
        Убрать вежливую/вопросительную обёртку вокруг явной команды
        ("Скотт, можешь открыть блокнот?" → "открыть блокнот"), чтобы
        command_parser видел чистый императив — без этого он не распознаёт
        команду и уходит в LLM с ответом "у меня нет доступа к ОС".
        """
        t = text.strip()
        if t.endswith('?'):
            t = t[:-1].strip()

        name_prefixes = ('скотт,', 'скотт ', 'scott,', 'scott ')
        lower_t = t.lower()
        for name in name_prefixes:
            if lower_t.startswith(name):
                t = t[len(name):].strip()
                lower_t = t.lower()
                break

        wrappers = [
            'не мог бы ты ', 'не могла бы ты ', 'не мог ли ты ',
            'можешь ли ты ', 'можешь ты ', 'ты можешь ли ', 'ты можешь ',
            'можешь ', 'пожалуйста, ', 'пожалуйста ',
        ]
        changed = True
        while changed:
            changed = False
            for w in wrappers:
                if lower_t.startswith(w):
                    t = t[len(w):].strip()
                    lower_t = t.lower()
                    changed = True

        return t or text.strip()

    def _extract_web_query(self, text: str, filler_words: list) -> str:
        """
        Вырезать служебные слова (имя сервиса, глаголы-триггеры) из фразы,
        оставив только то, что реально нужно искать — например, из
        "Скотт, найди на ютубе видео про запуск ракеты" получить
        "запуск ракеты". Тот же принцип, что и в command_parser._extract_parameter,
        но локально для веб-интеграций, чтобы не трогать общий (и уже не раз
        ломавшийся на пересечении категорий) словарь COMMAND_SYNONYMS.
        """
        words = self._strip_command_wrapper(text).split()
        kept = [w for w in words if w.lower().strip('.,!?:;—-') not in filler_words]
        return ' '.join(kept).strip()

    async def _execute_parsed_command(self, parsed, original_text: str) -> str:
        """
        Выполнить распарсенную команду
        """
        cmd_type = parsed.command_type
        param = parsed.main_param
        context = parsed.context

        # Получаем профиль Scott
        scott_name = scott_profile.get_name()
        user_name = scott_profile.get_user_name()
        lang = context.get('language', 'ru')

        # Говорим что выполняем
        ack = scott_profile.get_response('acknowledgement')
        print(f"   {ack}")

        # ============= ОТКРЫТЬ ПРИЛОЖЕНИЕ =============
        if cmd_type == 'open_app':
            result = executor.execute('open_app', name=param)

            # Приложения не нашлось — возможно, речь о сайте. Порядок именно
            # такой: установленная программа всегда важнее веб-версии, а вот
            # «открой гугл» до этого места доходило с отказом «не нашёл
            # установленное приложение «гугл»».
            if "❌" in result:
                site = web_integrations.open_site(param)
                if site:
                    return site["message"]

            if "✅" in result:
                # Название открытого приложения обязательно называется вслух.
                # Раньше ответом было безликое «Выполнено успешно», и когда
                # Scott ошибался приложением, человек узнавал об этом только
                # по выскочившему окну: на просьбу поставить напоминание он
                # открыл Discord и отрапортовал об успехе.
                return result.replace("✅ ", "")
            return result

        # ============= СОЗДАТЬ ФАЙЛ =============
        elif cmd_type == 'create_file':
            location = context.get('location')
            result = executor.execute('create_file', path=param, location=location)
            if "✅" in result:
                return f"{scott_profile.get_response('success')} {result}"
            return result

        # ============= СОЗДАТЬ ПАПКУ =============
        elif cmd_type == 'create_folder':
            result = executor.execute('create_folder', path=param)
            if "✅" in result:
                return scott_profile.get_response('success')
            return result

        # ============= ПОЛУЧИТЬ ВАЛЮТУ / КУРС =============
        elif cmd_type == 'search' and any(word in original_text.lower() for word in 
                                          ['доллар', 'евро', 'bitcoin', 'курс', 'dollar', 'euro', 'btc']):
            if 'доллар' in original_text.lower() or 'dollar' in original_text.lower():
                result = executor.execute('get_currency', currency='dollar')
            elif 'евро' in original_text.lower() or 'euro' in original_text.lower():
                result = executor.execute('get_currency', currency='euro')
            elif 'bitcoin' in original_text.lower() or 'btc' in original_text.lower():
                result = executor.execute('get_currency', currency='bitcoin')
            else:
                result = executor.execute('get_currency', currency='dollar')
            return result

        # ============= ПОЛУЧИТЬ ПОГОДУ =============
        elif cmd_type == 'get_weather':
            city = param if param != 'неизвестно' else 'Moscow'
            result = executor.execute('get_weather', city=city)
            return result

        # ============= ПОЛУЧИТЬ НОВОСТИ =============
        elif cmd_type == 'get_news':
            topic = param if param != 'неизвестно' else 'technology'
            result = executor.execute('get_news', topic=topic)
            return result

        # ============= ПОЛУЧИТЬ ИНФОРМАЦИЮ О СИСТЕМЕ =============
        elif cmd_type == 'system_info':
            result = executor.execute('get_system_info')
            return result

        # ============= СИСТЕМНЫЕ КОМАНДЫ (громкость, яркость, питание) =============
        # Ветки для этого типа здесь не было вовсе: парсер исправно превращал
        # «увеличь громкость» в system_command с main_param='volume_up', а
        # выполнять было некому — команда доходила до общего конца метода и
        # Scott отвечал «Я вас слушаю», как будто не понял.
        elif cmd_type == 'system_command':
            result = executor.execute('system_command', main_param=param)
            return result

        # ============= ЗАПУСТИТЬ НАПИСАННОЕ =============
        elif cmd_type == 'run_code':
            try:
                from . import code_assistant
            except ImportError:
                import code_assistant

            program = self.last_program
            if not program:
                return "Сначала попросите написать программу — потом запущу."

            outcome = code_assistant.build_and_run(program["path"], program["language"], run_it=True)
            if outcome["stage"] == "build" and not outcome["success"]:
                return "❌ Программа не собралась:\n" + outcome["error"][:600]
            if not outcome["success"]:
                return "❌ Программа завершилась с ошибкой:\n" + outcome.get("error", "")[:400]

            output = outcome.get("output") or "(программа ничего не вывела)"
            return "✅ Запустил. Вывод программы:\n" + output

        # ============= НАПИСАТЬ ПРОГРАММУ =============
        elif cmd_type == 'write_code':
            try:
                from . import code_assistant
            except ImportError:
                import code_assistant

            written = code_assistant.write_program(
                original_text,
                get_intelligent_answerer(),
                name="scott_program",
            )
            if not written["success"]:
                return f"❌ {written['message']}"

            # Запоминаем последнюю программу: следом человек скажет «запусти»,
            # и повторять, что именно запускать, ему не придётся.
            self.last_program = written

            # Код обрамляется как блок markdown: по этой рамке лаунчер рисует
            # его моноширинным шрифтом с кнопкой «Копировать», а синтез речи
            # такие блоки не произносит.
            preview = f"```{written['language']}\n{written['code'].strip()}\n```"
            return (
                f"Готово, написал на {written['display']}. Файл: {written['path']}\n\n"
                f"{preview}\n\n"
                "Скажите «запусти программу», если хотите её выполнить."
            )

        # ============= НАПОМИНАНИЕ =============
        elif cmd_type == 'reminder':
            try:
                from . import reminders as reminders_module
            except ImportError:
                import reminders as reminders_module

            service = scott_runtime.reminders
            if service is None:
                return "❌ Служба напоминаний не запущена"

            when = reminders_module.parse_time(original_text)
            if when is None:
                return ("Не понял, на какое время. Скажите, например, "
                        "«напомни через десять минут» или «напомни в 15:30»")

            subject = reminders_module.extract_subject(original_text)
            item = service.add(subject or "напоминание", when)
            return f"✅ Напомню {when.strftime('%d.%m в %H:%M')}: {item.text}"

        # ============= ОТКРЫТЬ ПАПКУ =============
        elif cmd_type == 'open_folder':
            try:
                from . import os_actions
            except ImportError:
                import os_actions

            result = os_actions.open_user_folder(param)
            if result["success"]:
                return f"✅ Открыл папку: {result.get('output', param)}"
            return f"❌ {result['error']}"

        # ============= СПИСОК ПРОЦЕССОВ =============
        elif cmd_type == 'list_processes':
            result = executor.execute('list_processes')
            return result

        # ============= ОТКРЫТЬ САЙТ =============
        elif cmd_type == 'open_website':
            result = executor.execute('open_website', url=param)
            return result

        # ============= ПОИСК (По умолчанию через Google) =============
        elif cmd_type == 'search':
            print(f"🔍 Ищу в браузере: {param}")
            result = executor.execute('search_browser', query=param)
            if web_scraper:
                try:
                    search_result = web_scraper.search_google(param)
                    if search_result.get('status') == 'success':
                        articles = search_result.get('results', [])
                        if articles:
                            first = articles[0]
                            info = f"Первый результат: {first['title']}. {first['description']}"
                            return f"{result}\n\nПервая информация: {info[:200]}..."
                except Exception:
                    pass
            return result

        # ============= ЗАКРЫТЬ ПРИЛОЖЕНИЕ =============
        elif cmd_type == 'close_app':
            result = executor.execute('close_app', name=param)
            if "✅" in result:
                return scott_profile.get_response('success')
            return result

        # ============= УПРАВЛЕНИЕ ОКНАМИ =============
        elif cmd_type == 'manage_window':
            if 'alt+tab' in original_text.lower():
                import pyautogui
                pyautogui.hotkey('alt', 'tab')
                return "Переключаюсь на следующее окно"
            return "Окна управляются"

        # ============= НЕИЗВЕСТНАЯ КОМАНДА - СПРАШИВАЕМ AI =============
        else:
            response = knowledge_base.query_ai(original_text)
            knowledge_base.learn_from_question(original_text, response)
            return response

    async def process_voice_input(self, audio_data: bytes) -> str:
        """Обработать голосовой ввод с проверкой Voice Name Trigger"""
        try:
            # Распознаём речь
            text = recognizer.transcribe(audio_data)
            print(f"🎤 Распознано: {text}")
            
            # 🎤 VOICE NAME TRIGGER - Проверяем наличие имени
            trigger_result = check_voice_trigger(text)
            
            if not trigger_result.has_trigger:
                # Имя не произнесено
                message = f"⏭️  Команда игнорирована: требуется произнести имя 'Скотт' (услышано: {text})"
                print(message)
                return message
            
            # ✅ Имя найдено - обрабатываем команду
            print(f"🎤 Voice Trigger найден: {trigger_result.name_used}")
            print(f"📝 Команда: {trigger_result.command_text} (уверенность: {trigger_result.confidence*100:.0f}%)")
            
            # Обрабатываем как текстовую команду
            result = await self.process_command(trigger_result.command_text)
            return result.get('response', 'Не смог обработать')
        except Exception as e:
            return f"❌ Ошибка распознавания: {str(e)}"


# Инициализируем Scott AI
scott_ai = ScottAI()


# ============= ПРОСЛУШИВАНИЕ МИКРОФОНА =============
# Scott слушает сам и выполняет только то, что сказано после его имени.
# Слушатель создаётся здесь, потому что ему нужны Whisper и обработчик команд,
# а роутер берёт готовый экземпляр из runtime — иначе импорты замкнулись бы.

_main_loop = None


def _set_main_loop(loop) -> None:
    """Запомнить главный event loop: из него слушатель будет выполнять команды."""
    global _main_loop
    _main_loop = loop


def _listener_transcribe(audio) -> str:
    """
    Распознать фразу, пришедшую с микрофона.

    Whisper принимает массив напрямую — писать её во временный файл, как это
    делает /speech_to_text для загруженных файлов, здесь незачем.
    """
    model = _get_whisper_model()
    with timing_stage("01.распознавание.whisper"):
        result = model.transcribe(audio, language="ru", fp16=(_whisper_device == "cuda"))
    return (result.get("text") or "").strip()


def _listener_handle(text: str) -> None:
    """
    Выполнить услышанную команду и озвучить ответ.

    Вызывается из рабочего потока слушателя, а обработка команд асинхронная,
    поэтому корутина передаётся в главный event loop. Ждать результат здесь
    нельзя дольше разумного: пока поток занят, следующая фраза не разбирается.
    """
    if _main_loop is None:
        print("⚠️ Главный цикл ещё не готов — команда пропущена")
        return

    async def run() -> None:
        result = await scott_ai.process_command(text)
        response = result.get("response", "")
        if not response:
            return
        print(f"🤖 Scott: {response}")
        voice = scott_runtime.scott_voice
        if voice is None:
            return

        # На время ответа прослушивание приостанавливается: микрофон слышит
        # колонки, и собственный голос возвращается к Scott как новая фраза.
        # На живой проверке он так распознал сам себя — «Мимо: "Попробую
        # открыть Google Chrome"». Пока в ответе нет его имени, дело кончается
        # лишней работой Whisper, но стоит ему произнести «Скотт» — и он начнёт
        # разговаривать сам с собой без остановки.
        listening = scott_runtime.listener
        if listening is not None:
            listening.suspend()
        try:
            path = await asyncio.to_thread(voice.speak_to_file, response)
            if path:
                await asyncio.to_thread(voice.play_audio, path)
        except Exception as e:
            print(f"⚠️ Не удалось озвучить ответ: {e}")
        finally:
            if listening is not None:
                # Небольшая пауза на эхо: звук из колонок доходит до микрофона
                # с задержкой и не обрывается ровно на последнем слове.
                await asyncio.sleep(0.4)
                listening.resume()

    asyncio.run_coroutine_threadsafe(run(), _main_loop)


# ============= НАПОМИНАНИЯ =============
# Scott работает в фоне, поэтому «напомни через час» должно пережить и
# закрытие окна, и перезапуск — служба хранит дела в файле и сама следит за
# временем.

def _speak_reminder(item) -> None:
    """
    Произнести напоминание вслух.

    Вызывается из потока службы, а озвучивание асинхронное, поэтому корутина
    передаётся в главный цикл — тем же способом, каким это делает слушатель.
    """
    text = f"Напоминаю: {item.text}" if item.text else "Напоминание"
    print(f"⏰ {text}")

    if _main_loop is None:
        return

    async def run() -> None:
        voice = scott_runtime.scott_voice
        if voice is None:
            return
        listening = scott_runtime.listener
        if listening is not None:
            listening.suspend()
        try:
            path = await asyncio.to_thread(voice.speak_to_file, text)
            if path:
                await asyncio.to_thread(voice.play_audio, path)
        except Exception as e:
            print(f"⚠️ Не удалось озвучить напоминание: {e}")
        finally:
            if listening is not None:
                await asyncio.sleep(0.4)
                listening.resume()

    asyncio.run_coroutine_threadsafe(run(), _main_loop)


try:
    try:
        from .reminders import ReminderService
    except ImportError:
        from reminders import ReminderService

    scott_reminders = ReminderService(on_fire=_speak_reminder)
    scott_reminders.start()
    scott_runtime.set_reminders(scott_reminders)
    print(f"⏰ Служба напоминаний запущена (в очереди: {len(scott_reminders.pending())})")
except Exception as e:
    scott_reminders = None
    print(f"⚠️ Служба напоминаний недоступна: {e}")


try:
    try:
        from .listener import VoiceListener
    except ImportError:
        from listener import VoiceListener

    scott_listener = VoiceListener(
        transcribe=_listener_transcribe,
        handle_command=_listener_handle,
        check_trigger=check_voice_trigger,
    )
    scott_runtime.set_listener(scott_listener)
    print("🎧 Слушатель готов (микрофон включается по команде из лаунчера)")
except Exception as e:
    scott_listener = None
    print(f"⚠️ Слушатель недоступен: {e}")


# ============= REST ENDPOINTS =============

@app.get("/health")
async def health():
    """Проверка здоровья сервера"""
    return {
        "status": "online",
        "scott": "ready",
        "message": "Scott AI Assistant is online",
        "version": scott_profile.get('version'),
        "ai_name": scott_profile.get_name()
    }


@app.get("/profile")
async def get_profile():
    """Получить профиль Scott"""
    return {
        "name": scott_profile.get_name(),
        "version": scott_profile.get('version'),
        "language": scott_profile.get_language(),
        "user": scott_profile.get('user'),
        "features": scott_profile.get('features')
    }


def _collect_metrics() -> Dict:
    return {
        "metrics": system_monitor.get_metrics(),
        "cpu_info": system_monitor.get_cpu_info(),
        "memory_info": system_monitor.get_memory_info(),
        "disk_info": system_monitor.get_disk_info()
    }


@app.get("/metrics")
async def get_metrics():
    """
    Получить метрики системы.

    psutil.cpu_percent(interval=...) внутри system_monitor блокирует поток на
    0.1-0.2с — вызвано синхронно это стопорит весь asyncio event loop на каждый
    опрос (фронтенд опрашивает раз в 3с), поэтому выполняем в отдельном потоке.
    """
    return await asyncio.to_thread(_collect_metrics)


@app.get("/timings")
async def get_timings():
    """
    Сводка по времени этапов обработки: сколько раз вызывался этап, среднее,
    медиана, p95, максимум и суммарный вклад. Нужна, чтобы решать вопросы
    оптимизации (в том числе "стоит ли переписывать этот кусок на C++")
    по фактическим цифрам, а не по ощущениям.

    Этапы отсортированы по суммарному вкладу — первым идёт то, что съедает
    больше всего времени при реальном использовании.
    """
    return timing_snapshot()


@app.post("/timings/reset")
async def reset_timings():
    """Обнулить накопленную статистику (например, перед чистым замером)."""
    timing_reset()
    return {"success": True, "message": "Статистика замеров сброшена"}


@app.get("/processes")
async def get_processes():
    """Получить информацию о процессах"""
    return {
        "processes": system_monitor.get_process_info(10)
    }


@app.post("/command")
async def execute_command(command: Dict):
    """
    Выполнить команду (текстовую или голосовую)
    
    Примеры:
    - {"text": "открой Chrome"}
    - {"text": "какой курс доллара"}
    - {"text": "создай файл на рабочем столе"}
    - {"text": "...", "quiet_mode": false, "user_name": "Фантом", "ai_name": "Scott"}
    """
    text = command.get("text", "") or command.get("command", "")
    quiet_mode = command.get("quiet_mode", False)
    user_name = command.get("user_name", "User")
    ai_name = command.get("ai_name", "JARVIS")
    
    if not text:
        return {"error": "Текст команды не предоставлен", "status": "error"}
    
    result = await scott_ai.process_command(text, quiet_mode=quiet_mode, user_name=user_name)
    
    # Добавить фразу если режим не тишины
    phrase = ""
    if not quiet_mode:
        phrase = scott_ai.get_phrase_for_response()
    
    return {
        **result,
        "phrase": phrase,
        "quiet_mode": quiet_mode,
        "ai_name": ai_name
    }


_whisper_model_cache = None
_whisper_device = None


def _resolve_whisper_device() -> str:
    """
    Выбрать устройство для Whisper: видеокарта, если доступна, иначе процессор.

    Замеры (GET /timings) показали, что распознавание речи — это ~72% всего
    времени голосового цикла: 6.6с из 9с на модели small, потому что torch стоял
    в CPU-сборке и RTX 3060 просто простаивала. На GPU та же модель отрабатывает
    за доли секунды.

    Сам выбор живёт в device_settings: переменная WHISPER_DEVICE в .env, затем
    сохранённый через Настройки лаунчера выбор, затем автоматика.
    """
    return scott_device_settings.resolve_device("whisper")


def _unload_whisper_model() -> None:
    """Выгрузить модель, чтобы она поднялась заново на выбранном устройстве."""
    global _whisper_model_cache, _whisper_device
    _whisper_model_cache = None
    _whisper_device = None
    print("🔊 Модель Whisper выгружена — поднимется заново на выбранном устройстве")


scott_device_settings.register_reset_hook(_unload_whisper_model)


def _get_whisper_model():
    """
    Загрузить модель Whisper один раз и переиспользовать между запросами —
    раньше whisper.load_model() вызывался заново на КАЖДОЕ голосовое сообщение
    (лишние секунды на каждый запрос, особенно заметно в hands-free режиме,
    где распознавание идёт часто). Имя модели берётся из .env (WHISPER_MODEL).
    """
    global _whisper_model_cache, _whisper_device
    if _whisper_model_cache is None:
        import whisper
        model_name = os.getenv("WHISPER_MODEL", "small")
        device = _resolve_whisper_device()
        print(f"🔊 Загружаю модель Whisper «{model_name}» на {device.upper()} (один раз, кэшируется)...")
        try:
            _whisper_model_cache = whisper.load_model(model_name, device=device)
            _whisper_device = device
        except Exception as e:
            # Не хватило видеопамяти, битый драйвер и т.п. — распознавание не
            # должно отваливаться целиком, спокойно откатываемся на процессор.
            if device != "cpu":
                print(f"⚠️ Не удалось загрузить модель на {device.upper()} ({e}); откатываюсь на CPU")
                _whisper_model_cache = whisper.load_model(model_name, device="cpu")
                _whisper_device = "cpu"
            else:
                raise
        print(f"✅ Модель Whisper «{model_name}» загружена на {_whisper_device.upper()}")
    return _whisper_model_cache


def _transcribe_audio_file(file_path: str) -> str:
    """Транскрибировать аудио файл, пробуя Whisper, затем SpeechRecognition."""
    # Попробуем Whisper, если он доступен
    try:
        model = _get_whisper_model()
        # fp16 имеет смысл только на видеокарте; на CPU он не поддерживается и
        # whisper иначе сыплет предупреждением на каждое распознавание.
        result = model.transcribe(file_path, language="ru", fp16=(_whisper_device == "cuda"))
        text = result.get("text", "").strip()
        if text:
            print(f"✅ Whisper распознал: {text}")
        return text
    except Exception as whisper_error:
        import traceback
        print(f"⚠️ Whisper ошибка: {whisper_error}")
        traceback.print_exc()

    # Фолбэк на speech_recognition
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(file_path) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="ru-RU").strip()
            if text:
                print(f"✅ SpeechRecognition распознал: {text}")
            return text
    except Exception as sr_error:
        import traceback
        print(f"⚠️ SpeechRecognition ошибка: {sr_error}")
        traceback.print_exc()
        return ""


@app.post("/speech_to_text")
async def speech_to_text(file: UploadFile = File(...)):
    """
    Распознать речь из загруженного аудио файла
    
    Совместимый эндпоинт для Electron фронтенда
    """
    temp_file = None
    # Быстрая проверка доступности библиотек для распознавания речи
    try:
        import importlib
        has_whisper = importlib.util.find_spec('whisper') is not None
        has_sr = importlib.util.find_spec('speech_recognition') is not None
    except Exception:
        has_whisper = False
        has_sr = False

    if not has_whisper and not has_sr:
        return JSONResponse(
            status_code=501,
            content={
                "success": False,
                "error": "speech_modules_missing",
                "message": "Отсутствуют библиотеки для распознавания речи. Установите 'whisper' или 'SpeechRecognition' и необходимые зависимости (ffmpeg, pydub).",
                "install_hint": "\\.venv\\Scripts\\python.exe -m pip install -U openai-whisper SpeechRecognition pydub"
            }
        )

    try:
        # Сохранить файл временно
        contents = await file.read()
        temp_file = f"temp_audio_{file.filename}"

        with open(temp_file, "wb") as f:
            f.write(contents)

        # Предварительная проверка качества аудио: длительность и уровень громкости
        try:
            from pydub import AudioSegment
            with timing_stage("01.распознавание.подготовка_аудио"):
                seg = AudioSegment.from_file(temp_file)
            duration_ms = len(seg)
            loudness = seg.dBFS if hasattr(seg, 'dBFS') else None
            print(f"🔎 Audio duration_ms={duration_ms}, dBFS={loudness}")

            # Если аудио слишком короткое или слишком тихое — вернуть развернутое сообщение
            if duration_ms < 400:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "text": "",
                        "filename": file.filename,
                        "message": "audio_too_short: Аудио слишком короткое (меньше 400ms). Попробуйте говорить дольше."
                    }
                )
            if loudness is not None and loudness < -50:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "text": "",
                        "filename": file.filename,
                        "message": "audio_too_quiet: Уровень звука слишком низкий. Проверьте микрофон/громкость."
                    }
                )

            # Усилить тихие (но не безнадёжно тихие — те уже отсеяны выше)
            # клипы до целевой громкости перед распознаванием. На практике
            # многие голосовые команды приходят в районе -34..-48 dBFS —
            # Whisper на таких либо не распознаёт ничего (текст пустой,
            # 400 Bad Request), либо галлюцинирует случайный текст. Простое
            # усиление громкости заметно снижает долю таких промахов.
            TARGET_DBFS = -20.0
            MAX_GAIN_DB = 25.0
            if loudness is not None and loudness < TARGET_DBFS:
                gain = min(TARGET_DBFS - loudness, MAX_GAIN_DB)
                with timing_stage("01.распознавание.усиление_звука"):
                    seg = seg.apply_gain(gain)
                    seg.export(temp_file, format="wav")
                print(f"🔊 Тихое аудио ({loudness:.1f} dBFS) усилено на {gain:.1f} дБ перед распознаванием")
        except Exception as audio_check_err:
            print(f"⚠️ Audio pre-check failed: {audio_check_err}")

        # Whisper — тяжёлая CPU-операция (секунды на клип); вызванная синхронно
        # внутри async-хендлера она замораживает ВЕСЬ event loop, включая
        # /health — из-за этого фронтенд (особенно в hands-free режиме, где
        # запросы идут часто) периодически показывал "backend недоступен".
        with timing_stage("01.распознавание.whisper"):
            text = await asyncio.to_thread(_transcribe_audio_file, temp_file)
        return JSONResponse(
            status_code=200 if text else 400,
            content={
                "success": bool(text),
                "text": text,
                "filename": file.filename,
                "message": f"✅ Распознано: {text}" if text else "❌ Не удалось распознать речь",
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "text": "",
                "error": str(e),
                "message": f"❌ Ошибка: {e}"
            }
        )
    finally:
        import os
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)


@app.post("/ask")
async def ask_question(request: Dict):
    """Обработка вопросов и команд с сохранением в историю"""
    question = request.get("question", "").strip()
    context = request.get("context", "")
    quiet_mode = request.get("quiet_mode", False)
    user_name = request.get("user_name", "User")
    
    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Вопрос не предоставлен", "data": {}}
        )
    
    try:
        result = await scott_ai.process_command(question, quiet_mode=quiet_mode, user_name=user_name)
        
        response_text = result.get("response", "")
        response_payload = {
            "success": True,
            "question": question,
            "data": {
                "answer": response_text,
                "question": question,
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "type": result.get("type", "command"),
                "command": result.get("command")
            }
        }
        
        try:
            memory_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'memory.jsonl')
            os.makedirs(os.path.dirname(memory_path), exist_ok=True)
            
            with open(memory_path, 'a', encoding='utf-8') as f:
                history_entry = {
                    "question": question,
                    "answer": response_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat(),
                    "context": context,
                    "type": result.get("type", "command")
                }
                f.write(json.dumps(history_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"⚠️ Ошибка сохранения истории: {e}")
        
        return response_payload
        
    except Exception as e:
        print(f"❌ Ошибка при обработке вопроса: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "data": {}}
        )


@app.post("/speak")
async def speak_text(text: str = Form("")):
    """Озвучить текст голосом Scott"""
    text = text.strip()
    
    if not text:
        return {"success": False, "message": "❌ Текст не предоставлен"}
    
    try:
        if scott_voice:
            # scott_voice.speak() синхронный и занимает ~2с (генерация + проигрывание).
            # Вызванный напрямую внутри async-хендлера он замораживал весь event loop:
            # на это время переставал отвечать даже /health, и лаунчер мигал статусом
            # "offline" каждый раз, когда Scott что-то озвучивал. Тот же приём, что уже
            # применён для Whisper в /speech_to_text и для psutil в /metrics.
            with timing_stage("02.синтез_речи.speak"):
                await asyncio.to_thread(scott_voice.speak, text)
            print(f"🔊 Озвучено: {text[:50]}...")
            return {"success": True, "message": "✅ Текст озвучен"}
        else:
            print(f"⚠️ Scott Voice недоступен")
            return {"success": False, "message": "⚠️ Озвучивание недоступно"}
    except Exception as e:
        print(f"❌ Ошибка озвучивания: {e}")
        return {"success": False, "error": str(e)}


# ===== УПРАВЛЕНИЕ ФАЙЛАМИ И ПРОГРАММАМИ =====

@app.post("/open-program")
async def open_program(request: dict):
    """Открыть программу по имени"""
    from file_system_manager import file_manager
    
    program_name = request.get("program", "").strip()
    print(f"🔍 [open-program] Получен запрос: program_name='{program_name}'")
    
    if not program_name:
        return {"success": False, "message": "❌ Имя программы не указано"}
    
    try:
        # Найти программу
        program_path = file_manager.find_program(program_name)
        print(f"🔍 [open-program] Найденный путь: {program_path}")
        
        if not program_path:
            return {"success": False, "message": f"❌ Программа не найдена: {program_name}"}
        
        # Открыть программу
        result = file_manager.open_program(program_path)
        print(f"✅ [open-program] Результат: {result}")
        return result
    except Exception as e:
        print(f"❌ [open-program] Ошибка: {str(e)}")
        return {"success": False, "message": f"❌ Ошибка: {str(e)}"}


@app.post("/file-action")
async def file_action(request: dict):
    """Выполнить действие с файлом"""
    from file_system_manager import file_manager
    
    try:
        action = request.get("action", "").lower()  # open, delete, rename, move
        file_path = request.get("file", "").strip()
        extra = request.get("extra", "")  # для rename - новое имя, для move - путь назначения
        
        if not file_path:
            return {"success": False, "message": "❌ Путь файла не указан"}
        
        if action == "open":
            return file_manager.open_file(file_path)
        elif action == "delete":
            return file_manager.delete_file(file_path)
        elif action == "rename":
            if not extra:
                return {"success": False, "message": "❌ Новое имя не указано"}
            return file_manager.rename_file(file_path, extra)
        elif action == "move":
            if not extra:
                return {"success": False, "message": "❌ Путь назначения не указан"}
            return file_manager.move_file(file_path, extra)
        else:
            return {"success": False, "message": f"❌ Неизвестное действие: {action}"}
    except Exception as e:
        return {"success": False, "message": f"❌ Ошибка при выполнении действия: {str(e)}"}


@app.get("/desktop-files")
async def get_desktop_files():
    """Получить список файлов на рабочем столе"""
    from file_system_manager import file_manager
    
    files = file_manager.list_desktop_files()
    return {"success": True, "files": files}


@app.post("/search-files")
async def search_files(request: dict):
    """Поиск файлов по имени или расширению"""
    from file_system_manager import file_manager
    
    pattern = request.get("pattern", "").strip()
    folder = request.get("folder")
    
    if not pattern:
        return {"success": False, "message": "❌ Паттерн поиска не указан"}
    
    try:
        results = file_manager.search_files(pattern, folder)
        return {"success": True, "count": len(results), "files": results[:20]}
    except Exception as e:
        return {"success": False, "message": f"❌ Ошибка поиска: {str(e)}"}


@app.post("/search-content")
async def search_content(request: dict):
    """Поиск текста в содержимом файлов"""
    from file_system_manager import file_manager
    
    text = request.get("text", "").strip()
    folder = request.get("folder")
    
    if not text:
        return {"success": False, "message": "❌ Текст для поиска не указан"}
    
    try:
        results = file_manager.find_in_file_content(text, folder)
        return {"success": True, "count": len(results), "results": results}
    except Exception as e:
        return {"success": False, "message": f"❌ Ошибка поиска: {str(e)}"}


@app.get("/list-processes")
async def list_processes():
    """Получить список работающих процессов"""
    try:
        import psutil
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
            try:
                processes.append({
                    "pid": proc.pid,
                    "name": proc.name(),
                    "memory_mb": round(proc.info['memory_percent'], 2),
                    "cpu_percent": round(proc.info['cpu_percent'], 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return {"success": True, "count": len(processes), "processes": processes[:50]}
    except ImportError:
        return {
            "success": False, 
            "message": "❌ psutil не установлен. Используйте: pip install psutil"
        }
    except Exception as e:
        return {"success": False, "message": f"❌ Ошибка: {str(e)}"}


@app.post("/kill-process", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def kill_process(request: dict):
    """Завершить процесс по PID или имени"""
    try:
        import psutil
        
        pid = request.get("pid")
        name = request.get("name", "").lower()
        force = request.get("force", False)
        
        if not pid and not name:
            return {"success": False, "message": "❌ Укажите PID или имя процесса"}
        
        killed = []
        failed = []
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if (pid and proc.pid == pid) or (name and name in proc.name().lower()):
                    try:
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        killed.append({"pid": proc.pid, "name": proc.name()})
                    except Exception as e:
                        failed.append({"pid": proc.pid, "error": str(e)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if killed:
            return {
                "success": True,
                "message": f"✅ Процессы завершены: {len(killed)}",
                "killed": killed
            }
        else:
            return {"success": False, "message": "❌ Процессы не найдены"}
            
    except ImportError:
        return {"success": False, "message": "❌ psutil не установлен"}
    except Exception as e:
        return {"success": False, "message": f"❌ Ошибка: {str(e)}"}


@app.post("/chat")
async def chat(message: Dict):
    """Чат с Scott"""
    text = message.get("message", "")
    
    if not text:
        return {"error": "Сообщение не предоставлено"}
    
    result = await scott_ai.process_command(text)
    return result


@app.get("/voice/available")
async def list_available_voices(gender: str = ""):
    """
    Список доступных голосов для выбора в Настройках — и локальных (Silero),
    и облачных (Edge TTS).

    ?gender=male|female фильтрует список: лаунчер показывает только мужские,
    не зашивая в интерфейс знание о конкретных именах голосов.
    """
    from scott_voice import AVAILABLE_VOICES, VOICE_GENDERS, get_current_voice
    import silero_tts as _silero

    wanted = gender.strip().lower()
    voices = []
    for vid, label in AVAILABLE_VOICES.items():
        voice_gender = VOICE_GENDERS.get(vid, "unknown")
        if wanted and voice_gender != wanted:
            continue
        voices.append({
            "id": vid,
            "label": label,
            "gender": voice_gender,
            # Локальный движок работает офлайн и заметно быстрее — это стоит
            # показать в интерфейсе, чтобы выбор был осознанным.
            "engine": "silero" if vid in _silero.SILERO_VOICES else "edge",
            "local": vid in _silero.SILERO_VOICES,
        })

    return {
        "voices": voices,
        "default": get_current_voice(),
        "current": get_current_voice(),
    }


@app.post("/voice/select")
async def select_voice(request: Dict):
    """
    Переключить голос Scott на лету — без правки .env и перезапуска backend.
    Действует до перезапуска процесса.
    """
    from scott_voice import set_current_voice, get_current_voice, AVAILABLE_VOICES

    voice = (request.get("voice") or "").strip()
    if not voice:
        return JSONResponse(status_code=400, content={"success": False, "message": "Голос не указан"})

    if not set_current_voice(voice):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Неизвестный голос «{voice}»",
                "available": list(AVAILABLE_VOICES.keys()),
            },
        )

    return {
        "success": True,
        "voice": get_current_voice(),
        "label": AVAILABLE_VOICES.get(voice, voice),
        "message": f"Голос переключён на {AVAILABLE_VOICES.get(voice, voice)}",
    }


@app.post("/text_to_speech")
async def text_to_speech(request: Dict):
    """Преобразование текста в речь"""
    text = request.get("text", "")
    voice_name = request.get("voice")  # опционально: 'ru-RU-DmitryNeural' / 'ru-RU-SvetlanaNeural'

    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "Текст не предоставлен"}
        )

    try:
        voice = getattr(scott_ai, "scott_voice", None)
        if voice is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Voice engine не инициализирован"}
            )

        loop = asyncio.get_running_loop()
        with timing_stage("02.синтез_речи.в_файл"):
            audio_file = await asyncio.wait_for(
                loop.run_in_executor(tts_executor, lambda: voice.speak_to_file(text, voice=voice_name)),
                timeout=45
            )
        logging.debug(f"/text_to_speech generated file: {audio_file}")

        if audio_file and os.path.exists(audio_file):
            with open(audio_file, 'rb') as f:
                audio_data = f.read()

            # Локальный Silero отдаёт WAV, облачный edge-tts — MP3. Тип содержимого
            # определяем по фактическому файлу: иначе WAV уезжал бы клиенту с
            # заголовком audio/mpeg, и плеер на нём спотыкался.
            is_wav = audio_file.lower().endswith(".wav")
            return Response(
                content=audio_data,
                media_type="audio/wav" if is_wav else "audio/mpeg",
                headers={
                    "Content-Disposition": f"attachment; filename=audio.{'wav' if is_wav else 'mp3'}"
                }
            )

        logging.error(f"/text_to_speech failed: audio_file={audio_file}")
        return JSONResponse(
            status_code=500,
            content={"error": "Не удалось сгенерировать аудио", "audio_file": audio_file}
        )
    except asyncio.TimeoutError:
        logging.warning("/text_to_speech timed out while generating audio")
        return JSONResponse(
            status_code=504,
            content={"error": "Таймаут генерации аудио"}
        )
    except Exception as e:
        logging.exception("Ошибка в /text_to_speech")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


# ============= WEBSOCKET ENDPOINT =============

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket для реал-тайм чата"""
    await websocket.accept()
    
    try:
        while True:
            # Получаем сообщение от клиента
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                text = message.get("text", "") or message.get("command", "")
                
                if text:
                    # Обрабатываем команду
                    result = await scott_ai.process_command(text)
                    
                    # Отправляем результат обратно
                    await websocket.send_json({
                        "status": "success",
                        "data": result
                    })
                else:
                    await websocket.send_json({
                        "status": "error",
                        "message": "Текст команды не предоставлен"
                    })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "status": "error",
                    "message": "Некорректный формат JSON"
                })
    
    except Exception as e:
        print(f"❌ WebSocket ошибка: {e}")
        await websocket.close(code=1011)


# ============= ВЕБ-ИНТЕГРАЦИИ (YouTube, GitHub) =============


@app.post("/web/youtube/search")
async def youtube_search(data: Dict):
    """Найти видео на YouTube (через YouTube Data API v3) и открыть его в браузере"""
    query = data.get('query', '').strip()
    return web_integrations.search_youtube_video(query)


@app.post("/web/github/search")
async def github_search(data: Dict):
    """Найти репозиторий на GitHub (через GitHub Search API) и открыть его в браузере"""
    query = data.get('query', '').strip()
    return web_integrations.search_github_repo(query)


# ============= МАКРОСЫ (v3.3) =============


@app.post("/macros/cancel-recording")
async def cancel_recording():
    """Отменить запись"""
    if not HAS_V33_FEATURES:
        return {"error": "Компоненты v3.3 не доступны"}
    return macro_recorder.cancel_recording()


# ============= ВЕРСИОНИРОВАНИЕ (v3.3) =============


@app.get("/versions/current")
async def get_current_version(item_id: str):
    """Получить текущую версию"""
    if not HAS_V33_FEATURES:
        return {"error": "Компоненты v3.3 не доступны"}
    version = version_manager.get_current_version(item_id)
    if version:
        return version
    return {"error": f'Текущая версия для "{item_id}" не найдена'}


@app.post("/versions/compare")
async def compare_versions(data: Dict):
    """Сравнить две версии"""
    if not HAS_V33_FEATURES:
        return {"error": "Компоненты v3.3 не доступны"}
    return version_manager.compare_versions(
        item_id=data.get('item_id', ''),
        v1=data.get('v1', 1),
        v2=data.get('v2', 2)
    )


# ============= ГОЛОСОВОЕ СОЗДАНИЕ ПРАВИЛ (v3.3) =============


@app.post("/voice/parse-macro-action")
async def voice_parse_macro_action(data: Dict):
    """Парсить голосовую инструкцию для макроса"""
    if not HAS_V33_FEATURES:
        return {"error": "Компоненты v3.3 не доступны"}
    
    text = data.get('text', '')
    return voice_rule_builder.parse_macro_instruction(text)


# ============= SHUTDOWN HANDLING =============
# Примечание: использование lifespan context manager выше вместо @app.on_event()


# ============= ГЛАВНАЯ ФУНКЦИЯ =============

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🤖 SCOTT AI ASSISTANT - Backend Server v2.0")
    print("="*80)
    
    # По умолчанию — только петлевой адрес. Scott выполняет команды на этой
    # машине: открывает приложения, читает файлы, управляет питанием. На
    # 0.0.0.0 он был доступен всей локальной сети, причём /command токена не
    # требует — сосед по Wi-Fi мог открывать программы и смотреть, что лежит на
    # рабочем столе. Лаунчер работает на том же компьютере, так что снаружи
    # backend видеть незачем.
    #
    # Если доступ по сети всё же нужен (например, лаунчер на другом
    # устройстве), BACKEND_HOST задаётся явно — но тогда ОБЯЗАТЕЛЬНО закройте
    # порт брандмауэром или поставьте перед ним обратный прокси с проверкой.
    backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port = int(os.getenv("BACKEND_PORT", "8000"))
    backend_reload = os.getenv("BACKEND_RELOAD", "false").lower() in ("1", "true", "yes")

    # uvicorn требует передавать приложение как import-строку, если включён reload
    uvicorn.run(
        "main:app" if backend_reload else app,
        host=backend_host,
        port=backend_port,
        reload=backend_reload,
        log_level="info"
    )
