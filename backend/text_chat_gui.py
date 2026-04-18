"""Текстовый GUI-режим Мальтруанта без терминала."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from config_store import load_config
from knowledge_base import KnowledgeBase
from llm_core import LlmConfig, LlmEngine
from tts_core import TtsConfig, TtsEngine
from chatbot import ChatBot, ChatBotConfig
from system_control import SystemController
from audio_playback import play_audio


def build_bot():
    cfg = load_config()
    kb = KnowledgeBase()
    llm = LlmEngine(LlmConfig(provider=cfg.llm_provider, model=cfg.llm_model), knowledge_base=kb)
    tts = TtsEngine(TtsConfig(voice_preset=cfg.voice_preset))
    bot = ChatBot(
        ChatBotConfig(
            language="ru",
            llm_engine=llm,
            tts_engine=tts,
            memory_path=Path(cfg.memory_path),
        )
    )
    bot.system_controller = SystemController(
        offline_game_limit_minutes=cfg.offline_game_limit_minutes,
        advice_cooldown_minutes=cfg.activity_advice_cooldown_minutes,
        enable_power_confirmation=cfg.enable_power_confirmation,
        memory_path=Path(cfg.assistant_memory_path),
        user_name=cfg.user_name,
        user_title=cfg.user_title,
    )
    return bot


class TextModeApp:
    def __init__(self) -> None:
        self.bot = build_bot()
        self.counter = 0
        self.root = tk.Tk()
        self.root.title("Maltruand - Текстовый режим")
        self.root.geometry("860x620")

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.BOTH, expand=True)

        self.chat = ScrolledText(top, wrap=tk.WORD, font=("Segoe UI", 11))
        self.chat.pack(fill=tk.BOTH, expand=True)
        self.chat.insert(tk.END, "Мальтруант: Текстовый режим активирован. Чем помочь?\n\n")
        self.chat.configure(state=tk.DISABLED)

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill=tk.X)
        self.entry = ttk.Entry(bottom)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _e: self.send())
        ttk.Button(bottom, text="Отправить", command=self.send).pack(side=tk.LEFT, padx=8)

    def append(self, line: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, line + "\n")
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def send(self) -> None:
        text = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        if not text:
            return
        self.append(f"Вы: {text}")

        sys_controller = getattr(self.bot, "system_controller", None)
        if sys_controller is not None:
            sys_result = sys_controller.handle_command(text)
            if sys_result.handled:
                answer = sys_result.message or "Команда выполнена."
                self.append(f"Мальтруант: {answer}\n")
                self._speak(answer)
                return

        self.counter += 1
        out = Path("voice_sessions") / f"text_gui_answer_{self.counter}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = self.bot.process_text_question(text, output_audio_path=out)
        answer = result.get("answer_text", "")
        self.append(f"Мальтруант: {answer}\n")
        self._speak(answer, out)

    def _speak(self, text: str, audio_path: Path | None = None) -> None:
        if audio_path is None:
            self.counter += 1
            audio_path = Path("voice_sessions") / f"text_gui_sys_{self.counter}.wav"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            self.bot.tts.synthesize_to_file(text=text, language="ru", speaker=None, out_path=audio_path)
        play_audio(audio_path)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    TextModeApp().run()
