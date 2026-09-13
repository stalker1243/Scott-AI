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

    # ---- загрузка ----

    def load(self) -> str:
        """Поднять модель. Возвращает название выбранной реализации."""
        if ENGINE_CHOICE in ("auto", "faster") and self._try_fast():
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

        try:
            self._model = whisper.load_model(self.model_name, device=self.device)
        except Exception as e:
            # Не хватило видеопамяти, битый драйвер — распознавание не должно
            # отваливаться целиком, спокойно откатываемся на процессор.
            if self.device != "cpu":
                print(f"⚠️ Не удалось загрузить модель на {self.device.upper()} "
                      f"({e}); откатываюсь на CPU")
                self._model = whisper.load_model(self.model_name, device="cpu")
                self.device = "cpu"
            else:
                raise

        self.engine = "openai-whisper"
        print(f"✅ Whisper «{self.model_name}» загружен на {self.device.upper()}")

    # ---- распознавание ----

    def transcribe(self, audio: Any, language: str = "ru") -> str:
        """
        Превратить звук в текст.

        Принимается и путь к файлу, и готовый массив: слушатель микрофона
        отдаёт массив, а загруженная запись приходит файлом.
        """
        if self._model is None:
            self.load()

        if self.engine == "faster-whisper":
            куски, _ = self._model.transcribe(audio, language=language)
            return "".join(кусок.text for кусок in куски).strip()

        # fp16 имеет смысл только на видеокарте: на процессоре он не
        # поддерживается, и whisper иначе предупреждает об этом на каждую фразу.
        итог = self._model.transcribe(audio, language=language,
                                      fp16=(self.device == "cuda"))
        return (итог.get("text") or "").strip()

    def warmup(self, seconds: float = 1.0) -> None:
        """
        Прогнать через модель тишину.

        Первая настоящая фраза иначе ждёт, пока видеокарта дотянет ядра под
        реальную работу, — и человек видит задержку ровно там, где ждёт
        отзывчивости.
        """
        import numpy as np

        тишина = np.zeros(int(16000 * seconds), dtype=np.float32)
        self.transcribe(тишина)


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
