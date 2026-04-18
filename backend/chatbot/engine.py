"""Чат-бот, объединяющий ASR + LLM + TTS."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import re

try:
    # Режим пакетного запуска: `python -m backend...`
    from ..asr_core import AsrEngine, get_default_asr_engine
    from ..llm_core import LlmEngine, get_default_llm_engine
    from ..tts_core import TtsEngine, get_default_engine, get_jarvis_voice
    from ..memory_store import MemoryStore, MemoryConfig
except ImportError:
    # Режим прямого запуска из папки backend
    from asr_core import AsrEngine, get_default_asr_engine
    from llm_core import LlmEngine, get_default_llm_engine
    from tts_core import TtsEngine, get_default_engine, get_jarvis_voice
    from memory_store import MemoryStore, MemoryConfig


@dataclass
class ChatBotConfig:
    """Конфигурация чат-бота."""
    language: str = "ru"
    asr_engine: Optional[AsrEngine] = None
    llm_engine: Optional[LlmEngine] = None
    tts_engine: Optional[TtsEngine] = None
    memory_path: Optional[Path] = None  # если задан — история сохраняется на диск


class ChatBot:
    """
    Чат-бот, который:
    1. Распознаёт речь из аудио (ASR)
    2. Обрабатывает вопрос через LLM
    3. Озвучивает ответ (TTS)
    """

    def __init__(self, config: Optional[ChatBotConfig] = None):
        self.config = config or ChatBotConfig()
        
        # Инициализация движков
        self.asr = self.config.asr_engine or get_default_asr_engine()
        self.llm = self.config.llm_engine or get_default_llm_engine()
        self.tts = self.config.tts_engine or get_default_engine()

        # Память диалога: список пар (вопрос, ответ)
        self.history: List[Tuple[str, str]] = []
        self.max_history_turns: int = 6  # сколько последних реплик учитывать

        # Постоянная память (между запусками)
        self._memory_store: Optional[MemoryStore] = None
        if self.config.memory_path is not None:
            self._memory_store = MemoryStore(MemoryConfig(path=self.config.memory_path))
            # Подгружаем немного истории, чтобы сохранялся контекст
            self.history.extend(self._memory_store.load_last_turns(limit=30))

    @staticmethod
    def _normalize_for_tts(text: str) -> str:
        """
        Подготавливает текст для TTS, чтобы он звучал естественно:
        - убирает эмодзи и нестандартные символы
        - убирает markdown-разметку (#, *, ` и т.п.)
        - сглаживает «лишние» знаки (кавычки, скобки и т.п.), чтобы голос
          не пытался их проговаривать
        """
        # Быстрые нормализации для русской озвучки (сокращения и символы)
        # Важно: это только для TTS. Печатный текст остаётся оригинальным.
        replacements = {
            "и т.д.": "и так далее",
            "и т.п.": "и тому подобное",
            "т.д.": "так далее",
            "т.п.": "тому подобное",
            "т.е.": "то есть",
            "т. е.": "то есть",
            "т.к.": "так как",
            "№": "номер ",
        }
        lowered = text
        for k, v in replacements.items():
            lowered = re.sub(re.escape(k), v, lowered, flags=re.IGNORECASE)
        text = lowered

        # Убираем ссылки (для голоса они бесполезны)
        text = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"www\.\S+", " ", text, flags=re.IGNORECASE)

        # Сглаживаем повторяющиеся знаки
        text = re.sub(r"[!?]{2,}", ".", text)
        text = re.sub(r"\.{3,}", "…", text)

        # Удаляем эмодзи и прочие символы вне базового диапазона
        text = re.sub(r"[^\w\s.,!?;:\-—()\"'«»…]", " ", text, flags=re.UNICODE)
        # Убираем лишние служебные знаки, которые могут портить озвучку
        # (кавычки, скобки, двоеточия и точки с запятой)
        text = re.sub(r"[\"'«»()\\[\\];:]", " ", text, flags=re.UNICODE)

        # Локальные правки для более естественной речи
        text = re.sub(r"\s*-\s*", " — ", text)  # дефисы -> тире в речи
        text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()

        # Минимальный финальный контроль
        if len(text) > 0 and text[-1] not in ".!?…":
            text += "."
        return text

    @staticmethod
    def _format_for_screen(text: str) -> str:
        """
        Форматирование ответа для экрана (читаемость).
        Ничего "агрессивно" не удаляем — только делаем аккуратнее.
        """
        t = (text or "").strip()
        if not t:
            return t
        # Убираем хвостовые пробелы, немного нормализуем пустые строки
        t = re.sub(r"\r\n", "\n", t)
        t = re.sub(r"[ \t]+\n", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    @staticmethod
    def _detect_language(text: str) -> str:
        """
        Простейшее определение языка текста.
        Возвращает 'ru' если есть кириллица, 'en' если только латиница, иначе 'ru' по умолчанию.
        """
        has_cyrillic = any("а" <= ch.lower() <= "я" for ch in text)
        has_latin = any("a" <= ch.lower() <= "z" for ch in text)

        if has_cyrillic and not has_latin:
            return "ru"
        if has_latin and not has_cyrillic:
            return "en"
        return "ru"

    def _build_context_from_history(self) -> str:
        """
        Формирует текстовый контекст из истории диалога для LLM.
        Берём несколько последних пар вопрос/ответ.
        """
        if not self.history:
            return ""

        # Берём последние N реплик
        turns = self.history[-self.max_history_turns :]
        lines: list[str] = ["Предыдущий диалог:"]
        for i, (q, a) in enumerate(turns, 1):
            lines.append(f"{i}. Пользователь: {q}")
            lines.append(f"   Скотт: {a}")
        return "\n".join(lines)

    def _remember_turn(self, question: str, answer: str) -> None:
        """Добавляет новую реплику в историю диалога."""
        self.history.append((question, answer))
        if self._memory_store is not None:
            try:
                self._memory_store.append_turn(question, answer)
            except Exception:
                pass

    def process_audio_question(self, audio_path: Path, output_audio_path: Optional[Path] = None) -> dict:
        """
        Обработать вопрос из аудиофайла и вернуть ответ в виде аудио.
        
        Args:
            audio_path: Путь к аудиофайлу с вопросом
            output_audio_path: Путь для сохранения ответа (опционально)
            
        Returns:
            Словарь с результатами:
            {
                "question_text": распознанный текст вопроса,
                "answer_text": текст ответа,
                "answer_audio": путь к аудиофайлу с ответом
            }
        """
        print(f"🎤 Распознавание речи из {audio_path}...")
        question_text = self.asr.transcribe(audio_path)
        print(f"📝 Распознанный вопрос: {question_text}")

        print("🤖 Обработка вопроса через LLM...")
        # Формируем контекст из истории
        ctx = self._build_context_from_history()
        answer_text_raw = self.llm.answer(question_text, context=ctx)
        answer_text = self._format_for_screen(answer_text_raw)
        print(f"💬 Ответ: {answer_text}")

        # Подготовка текста для TTS
        tts_text = self._normalize_for_tts(answer_text_raw)

        # Определяем язык и голос
        lang = self._detect_language(question_text or answer_text)
        jarvis_preset = get_jarvis_voice("ru" if lang == "ru" else "en")

        # Генерируем аудио ответа
        if output_audio_path is None:
            output_audio_path = audio_path.parent / "answer.wav"
        
        # Запоминаем реплику в истории
        self._remember_turn(question_text, answer_text_raw)

        print(f"🔊 Генерация аудио ответа...")
        self.tts.synthesize_to_file(
            text=tts_text,
            language=lang,
            speaker=jarvis_preset.voice,
            out_path=output_audio_path
        )
        print(f"✅ Аудио сохранено: {output_audio_path}")

        return {
            "question_text": question_text,
            "answer_text": answer_text,
            "answer_audio": str(output_audio_path)
        }

    def process_text_question(self, question_text: str, output_audio_path: Optional[Path] = None) -> dict:
        """
        Обработать текстовый вопрос и вернуть ответ в виде аудио.
        
        Args:
            question_text: Текст вопроса
            output_audio_path: Путь для сохранения ответа (опционально)
            
        Returns:
            Словарь с результатами
        """
        print(f"💬 Вопрос: {question_text}")

        print("🤖 Обработка вопроса через LLM...")
        # Формируем контекст из истории
        ctx = self._build_context_from_history()
        answer_text_raw = self.llm.answer(question_text, context=ctx)
        answer_text = self._format_for_screen(answer_text_raw)
        print(f"💬 Ответ: {answer_text}")

        # Подготовка текста для TTS
        tts_text = self._normalize_for_tts(answer_text_raw)

        # Определяем язык и голос
        lang = self._detect_language(question_text or answer_text)
        jarvis_preset = get_jarvis_voice("ru" if lang == "ru" else "en")

        # Генерируем аудио ответа
        if output_audio_path is None:
            from tempfile import gettempdir
            output_audio_path = Path(gettempdir()) / "answer.wav"
        
        # Запоминаем реплику в истории
        self._remember_turn(question_text, answer_text_raw)

        print(f"🔊 Генерация аудио ответа...")
        self.tts.synthesize_to_file(
            text=tts_text,
            language=lang,
            speaker=jarvis_preset.voice,
            out_path=output_audio_path
        )
        print(f"✅ Аудио сохранено: {output_audio_path}")

        return {
            "question_text": question_text,
            "answer_text": answer_text,
            "answer_audio": str(output_audio_path)
        }


def get_default_chatbot() -> ChatBot:
    """Фабрика для получения чат-бота по умолчанию."""
    return ChatBot()

