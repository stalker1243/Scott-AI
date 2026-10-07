"""
Распознавание речи: две реализации Whisper за одним окошком.

ЧТО ЗАМЕРЕНО. faster-whisper обещает четырёхкратное ускорение, и проверять это
пришлось самому. На видеокарте RTX 3060 с моделью small четыре фразы общей
длиной двенадцать секунд распознавались так:

    openai-whisper   1.39 с
    faster-whisper   0.68–1.14 с

То есть быстрее в полтора-два раза, а не вчетверо. На процессоре разрыв ещё
скромнее: 3.1 против 2.5 секунды на двух фразах. Обещанные четыре раза
относятся к другим связкам — к большим моделям и к сравнению с исходной
реализацией без видеокарты.

Полтора-два раза — это всё равно заметно: полсекунды на каждой фразе человек
чувствует. Плюс на float16 точность оказалась чуть выше: «фотосинтис» против
«фотосимтис» — оба неверны, но второе дальше от истины.

ПОЧЕМУ ОБЕ. Быстрая реализация тянет за собой CTranslate2 и скачивает модель в
собственном формате — это лишние полторы сотни мегабайт и две минуты при
первом запуске. Если её нет или она не завелась, Scott должен продолжать
слышать, а не умолкать. Поэтому выбор движка спрятан здесь, и остальной код о
нём не знает.

УСТРОЙСТВО. Обе реализации принимают и путь к файлу, и готовый массив звука:
слушатель микрофона отдаёт массив, а загруженная запись приходит файлом.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

# Какую реализацию брать: auto — быструю, если она есть, иначе обычную.
ENGINE_CHOICE = os.getenv("WHISPER_ENGINE", "auto").strip().lower()

# Точность вычислений для быстрой реализации.
#
# float16 замерен как самый быстрый и самый точный из трёх: int8_float16 не
# быстрее, а int8 медленнее почти вдвое и теряет в разборчивости. На видеокарте
# без поддержки float16 CTranslate2 сам откатится на что умеет.
FAST_COMPUTE_GPU = os.getenv("WHISPER_COMPUTE", "float16")
FAST_COMPUTE_CPU = "int8"


# Сколько попыток делать, если распознавание вышло неуверенным.
#
# Whisper, не набрав нужной уверенности, повторяет распознавание с растущей
# «температурой»: по умолчанию пять заходов — 0.0, 0.2, 0.4, 0.6, 0.8, — и
# каждый стоит 200–350 мс. На записи без внятной речи неуверенными выходят все
# пять, и пятнадцатисекундный кусок фона обрабатывается полторы секунды вместо
# трёхсот миллисекунд. В живом журнале таких переборов набралось 749 — это и
# есть тот самый хвост, из-за которого Scott временами «подвисал» на пять и
# более секунд.
#
# Две попытки вместо пяти: первая ловит обычную речь, вторая помогает на
# трудной записи. Дальше перебирать незачем — на фоне и шуме уверенности всё
# равно не будет, а человеку лучше быстро услышать «не понял», чем ждать.
TEMPERATURES = [0.0, 0.2]

# Search several candidates instead of committing to the first token. Keep
# the same policy in both implementations. This is not an accuracy score.
try:
    BEAM_SIZE = max(1, min(8, int(os.getenv('WHISPER_BEAM_SIZE', '5'))))
except ValueError:
    BEAM_SIZE = 5


def prepare_audio(audio: Any) -> Any:
    """Decode real uploads once; microphone arrays are already mono at 16 kHz."""
    import numpy as np
    if isinstance(audio, (str, os.PathLike)) and Path(audio).is_file():
        try:
            from faster_whisper.audio import decode_audio
        except ImportError:
            from whisper import load_audio
            audio = load_audio(str(audio))
        else:
            audio = decode_audio(str(audio), sampling_rate=16000)
    if not isinstance(audio, np.ndarray):
        return audio
    if audio.ndim != 1:
        raise ValueError('Whisper expects mono audio at 16000 Hz')
    if not np.isfinite(audio).all():
        raise ValueError('Audio contains non-finite samples')
    return np.ascontiguousarray(audio, dtype=np.float32)


def normalize_quiet_audio(audio: Any) -> Any:
    """Lift quiet recordings with bounded gain; never amplify normal speech."""
    import numpy as np
    if not isinstance(audio, np.ndarray) or not audio.size:
        return audio
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if peak <= 1e-7 or rms >= .015:
        return audio
    gain = min(8.0, .03 / max(rms, 1e-10), .90 / peak)
    return (audio * gain).astype(np.float32) if gain > 1 else audio


# С какой длины записи проверять, есть ли в ней речь вообще.
#
# Проверка стоит около ста миллисекунд — для команды в полторы секунды это
# заметная прибавка ни за что: человек говорил, речь там есть. А вот запись,
# дошедшая до пятнадцатисекундного предела, почти всегда оказывается фоном:
# музыкой, разговором в комнате, шумом. Тишина после речи в таких случаях не
# наступает, слушатель пишет до упора, и Whisper потом добросовестно ищет
# слова там, где их нет.
#
# Из 715 записей в живом журнале 429 были ровно пятнадцатисекундными.
SPEECH_CHECK_FROM_SECONDS = 2.0


def _подсказка() -> str:
    """
    Что Scott ожидает услышать: своё имя и названия установленных программ.

    Собирается в speech_hints — там же объяснено, почему список короткий.
    Не собралась — работаем без неё: подсказка улучшает распознавание, но не
    является условием работы.
    """
    try:
        try:
            from . import speech_hints
        except ImportError:
            import speech_hints

        return speech_hints.prompt()
    except Exception:
        return "Скотт. Компьютер, браузер, папка, голос."


# Что Whisper выдумывает, когда речи нет.
#
# Это не случайный набор слов, а обрывки титров из обучающих данных: модель
# обучалась на видео с субтитрами и на тишине выдаёт то, чем такие видео
# заканчиваются. В журнале услышанного эта фраза встретилась дословно —
# «Редактор субтитров О.Голубкина», — и Scott честно попытался счесть её
# командой.
#
# Опознаются по началу фразы, а не по вхождению: «открой субтитры» — законная
# просьба, и отбрасывать её нельзя.
HALLUCINATION_STARTS = (
    "редактор субтитров",
    "корректор ",
    "субтитры сделал",
    "субтитры создавал",
    "субтитры делал",
    "продолжение следует",
    "подписывайтесь на канал",
    "спасибо за просмотр",
    "спасибо за внимание",
    "субтитры и перевод",
)


def looks_like_hallucination(text: str) -> bool:
    """
    Похоже ли распознанное на выдумку модели, а не на сказанное человеком.

    Whisper на тишине и шуме выдаёт обрывки титров — это известная его черта, а
    не сбой. Для Scott такая строка опаснее пустой: он принимает её за фразу,
    ищет в ней своё имя, а при неудачном стечении мог бы и найти.
    """
    прибранный = (text or "").strip().lower().strip(".!?…,")

    if not прибранный:
        return False

    return any(прибранный.startswith(начало) for начало in HALLUCINATION_STARTS)


class Recognizer:
    """
    Распознаватель речи с выбранной реализацией.

    Модель загружается один раз и живёт до смены устройства: раньше она
    поднималась заново на каждое голосовое сообщение, и это стоило секунд на
    каждую фразу.
    """

    def __init__(self, model_name: str, device: str):
        self.model_name = model_name
        self.device = device
        self.engine = ""
        self._model: Any = None
        self._model_lock = threading.RLock()

    # ---- загрузка ----

    def load(self) -> str:
        with self._model_lock:
            if self._model is None:
                self._load()
            return self.engine

    def _load(self) -> str:
        """Поднять модель. Возвращает название выбранной реализации."""
        try:
            from . import device_settings
        except ImportError:
            import device_settings
        hip_gpu = self.device == 'cuda' and device_settings.rocm_build()
        if hip_gpu:
            print('🔊 AMD ROCm/HIP: использую PyTorch Whisper вместо CUDA-сборки CTranslate2')
        if not hip_gpu and ENGINE_CHOICE in ("auto", "faster") and self._try_fast():
            return self.engine

        if ENGINE_CHOICE == "faster":
            print("⚠️ Быстрая реализация не завелась — беру обычную")

        self._load_openai()
        return self.engine

    def _try_fast(self) -> bool:
        """Попробовать поднять faster-whisper. Неудача здесь не беда."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            if ENGINE_CHOICE == "faster":
                print("⚠️ faster-whisper не установлен")
            return False

        compute = FAST_COMPUTE_GPU if self.device == "cuda" else FAST_COMPUTE_CPU

        try:
            print(f"🔊 Загружаю faster-whisper «{self.model_name}» "
                  f"на {self.device.upper()} ({compute})...")
            self._model = WhisperModel(self.model_name, device=self.device,
                                       compute_type=compute)
            self.engine = "faster-whisper"
            print(f"✅ faster-whisper «{self.model_name}» готов на {self.device.upper()}")
            return True
        except Exception as e:
            # Не хватило видеопамяти, нет cuDNN, битый кэш модели — всё это не
            # повод остаться без слуха: ниже поднимется обычная реализация.
            print(f"⚠️ faster-whisper не поднялся ({str(e)[:120]})")
            self._model = None
            return False

    def _load_openai(self) -> None:
        import whisper

        print(f"🔊 Загружаю Whisper «{self.model_name}» на {self.device.upper()}...")

        # The comparison/downloader can keep large checkpoints beside Scott's
        # other local models. Reuse that checkpoint instead of downloading a
        # second copy into the user profile.
        checkpoint = Path(__file__).resolve().parent / 'data/models/whisper' / f'{self.model_name}.pt'
        if self.model_name == 'turbo':
            checkpoint = checkpoint.with_name('large-v3-turbo.pt')
        # load by model name so Whisper still validates the official SHA-256
        # checksum (also detects an interrupted download).
        cache_options = {'download_root': str(checkpoint.parent)} if checkpoint.is_file() else {}
        try:
            self._model = whisper.load_model(self.model_name, device=self.device, **cache_options)
        except Exception as e:
            # Не хватило видеопамяти, битый драйвер — распознавание не должно
            # отваливаться целиком, спокойно откатываемся на процессор.
            if self.device != "cpu":
                print(f"⚠️ Не удалось загрузить модель на {self.device.upper()} "
                      f"({e}); откатываюсь на CPU")
                self._model = whisper.load_model(self.model_name, device="cpu", **cache_options)
                self.device = "cpu"
            else:
                raise

        self.engine = "openai-whisper"
        print(f"✅ Whisper «{self.model_name}» загружен на {self.device.upper()}")

    # ---- распознавание ----

    def transcribe(self, audio: Any, language: str = "ru") -> str:
        # Whisper's decoder and its hooks belong to this shared model. File
        # uploads, microphone phrases and warmup must use it one at a time.
        with self._model_lock:
            try:
                return self._transcribe(audio, language)
            except RuntimeError as error:
                message = str(error).casefold()
                if self.device != 'cuda' or not any(word in message for word in (
                        'cuda', 'cudnn', 'cublas', 'hip', 'hsa', 'miopen', 'rocblas',
                        'invalid device function', 'out of memory')):
                    raise
                # A failed GPU must not fail every following microphone clip.
                # Retry once on CPU and keep that working model for this run.
                print(f'⚠️ Whisper: ошибка GPU ({str(error)[:120]}), переключаюсь на CPU')
                self._model = None
                self.device = 'cpu'
                self.engine = ''
                self._load()
                return self._transcribe(audio, language)

    def _transcribe(self, audio: Any, language: str = "ru") -> str:
        """
        Превратить звук в текст.

        Принимается и путь к файлу, и готовый массив: слушатель микрофона
        отдаёт массив, а загруженная запись приходит файлом.
        """
        import numpy as np
        audio = prepare_audio(audio)
        # Short silence must also be rejected, before loading a large model.
        if isinstance(audio, np.ndarray) and (not audio.size or np.max(np.abs(audio)) <= 1e-7):
            return ''
        if self._model is None:
            self.load()

        if not self._есть_речь(audio):
            return ''

        audio = normalize_quiet_audio(audio)
        options = dict(beam_size=BEAM_SIZE, best_of=5, condition_on_previous_text=False)

        if self.engine == "faster-whisper":
            куски, _ = self._model.transcribe(audio, language=language,
                                              temperature=TEMPERATURES,
                                              initial_prompt=_подсказка(), **options)
            текст = "".join(кусок.text for кусок in куски).strip()

            if looks_like_hallucination(текст):
                print(f"🔇 Пропускаю выдумку модели: «{текст[:60]}»")
                return ""

            return текст

        # fp16 имеет смысл только на видеокарте: на процессоре он не
        # поддерживается, и whisper иначе предупреждает об этом на каждую фразу.
        итог = self._model.transcribe(audio, language=language,
                                      fp16=(self.device == "cuda"),
                                      initial_prompt=_подсказка(), temperature=TEMPERATURES,
                                      **options)
        text = (итог.get("text") or "").strip()
        if looks_like_hallucination(text):
            print(f'🔇 Пропускаю выдумку модели: «{text[:60]}»')
            return ''
        return text

    def _есть_речь(self, audio: Any) -> bool:
        """
        Есть ли в длинной записи речь вообще.

        Проверяется только длинное — короткую команду человек произнёс сам, и
        тратить на неё сто миллисекунд незачем. Длинная запись почти всегда
        означает, что тишина после речи не наступила: играла музыка, шёл
        разговор в комнате. Искать слова там, где их нет, дорого — Whisper на
        таком материале уходит в перебор попыток.

        Проверка бережная: она находит речь даже на −57 dBFS, то есть сказанное
        шёпотом из другого конца комнаты не потеряется. При любом сомнении —
        при ошибке, при отсутствии модуля — отвечаем «речь есть»: пропустить
        команду хуже, чем лишний раз её поискать.
        """
        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            return True

        if not isinstance(audio, np.ndarray):
            # Путь к файлу: длину дёшево не узнать, да и приходят так
            # загруженные записи, а не фон из комнаты.
            return True

        if len(audio) < 16000 * SPEECH_CHECK_FROM_SECONDS:
            return True

        try:
            from faster_whisper import vad

            отрезки = vad.get_speech_timestamps(audio, vad.VadOptions())
            return bool(отрезки)
        except Exception:
            return True

    def warmup(self, seconds: float = 15.0) -> None:
        """
        Прогнать через модель шум той длины, какая приходит с микрофона.

        Первая настоящая фраза иначе ждёт, пока видеокарта дотянет ядра под
        реальную работу, — и человек видит задержку ровно там, где ждёт
        отзывчивости.

        ПОЧЕМУ ШУМ, А НЕ ТИШИНА. Прогрев тишиной не прогревал ничего: замер
        показал 2 миллисекунды на секунду тишины — Whisper отбрасывает её
        сразу, не считая. Прогрев выглядел сделанным, а первая фраза всё равно
        шла по холодному пути.

        ПОЧЕМУ ПЯТНАДЦАТЬ СЕКУНД. Столько длится запись с микрофона в
        большинстве случаев: из 715 записей в живом журнале 429 оказались ровно
        пятнадцатисекундными — это предел длины фразы у слушателя. Прогрев на
        секунде не покрывает такой вход: видеокарта дотягивает ядра под
        КАЖДЫЙ новый размер, и на Silero это уже проверено — там прогрев
        коротким входом снимал лишь половину платы.
        """
        import numpy as np

        # Слабый шум, а не тишина: ноль Whisper распознаёт как пустоту и
        # выходит сразу. Амплитуда мала, чтобы не тратить время на настоящий
        # разбор слов — важно прогнать вычисления, а не что-то распознать.
        генератор = np.random.default_rng(seed=1)
        шум = (генератор.standard_normal(int(16000 * seconds)) * 0.01).astype(np.float32)

        self.transcribe(шум)


def available_engines() -> dict:
    """
    Какие реализации есть на этой машине — для раздела диагностики.

    Человеку, у которого распознавание работает медленно, полезно видеть, что
    быстрая реализация просто не установлена.
    """
    есть = {}

    try:
        import faster_whisper
        есть["faster-whisper"] = getattr(faster_whisper, "__version__", "есть")
    except ImportError:
        есть["faster-whisper"] = ""

    try:
        import whisper
        есть["openai-whisper"] = getattr(whisper, "__version__", "есть")
    except ImportError:
        есть["openai-whisper"] = ""

    return есть
