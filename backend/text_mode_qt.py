"""Текстовый режим Скотта (Qt) без терминала, в стиле лаунчера."""
from __future__ import annotations

from pathlib import Path
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from config_store import load_config
from knowledge_base import KnowledgeBase
from llm_core import LlmConfig, LlmEngine
from tts_core import TtsConfig, TtsEngine
from chatbot import ChatBot, ChatBotConfig
from system_control import SystemController
from audio_playback import play_audio


class TextModeWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scott • Текстовый режим")
        self.setMinimumSize(920, 640)

        self.cfg = load_config()
        self.bot = self._build_bot()
        self.counter = 0

        self._build_ui()
        self._apply_style()
        self._fade_in()

    def _build_bot(self) -> ChatBot:
        kb = KnowledgeBase()
        llm = LlmEngine(
            LlmConfig(
                provider=self.cfg.llm_provider,
                model=self.cfg.llm_model,
                temperature=float(getattr(self.cfg, "llm_temperature", 0.4)),
                max_tokens=int(getattr(self.cfg, "llm_max_tokens", 160)),
            ),
            knowledge_base=kb,
        )
        tts = TtsEngine(TtsConfig(voice_preset=self.cfg.voice_preset))
        bot = ChatBot(
            ChatBotConfig(
                language="ru",
                llm_engine=llm,
                tts_engine=tts,
                memory_path=Path(self.cfg.memory_path),
            )
        )
        bot.system_controller = SystemController(
            offline_game_limit_minutes=self.cfg.offline_game_limit_minutes,
            advice_cooldown_minutes=self.cfg.activity_advice_cooldown_minutes,
            enable_power_confirmation=self.cfg.enable_power_confirmation,
            memory_path=Path(self.cfg.assistant_memory_path),
            user_name=self.cfg.user_name,
            user_title=self.cfg.user_title,
        )
        return bot

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("TEXT MODE")
        title.setObjectName("title")
        subtitle = QtWidgets.QLabel("Быстрый чат • команды системы • озвучка")
        subtitle.setObjectName("subtitle")
        header_left = QtWidgets.QVBoxLayout()
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header.addLayout(header_left)
        header.addStretch(1)

        self.badge = QtWidgets.QLabel("● READY")
        self.badge.setObjectName("badge")
        header.addWidget(self.badge)
        root.addLayout(header)

        self.chat = QtWidgets.QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setObjectName("chat")
        self.chat.appendPlainText("Скотт: Текстовый режим активирован. Чем помочь?\n")
        root.addWidget(self.chat, 1)

        bottom = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("Введите сообщение или команду…")
        self.input.returnPressed.connect(self.send)
        bottom.addWidget(self.input, 1)

        self.btn_send = QtWidgets.QPushButton("ОТПРАВИТЬ")
        self.btn_send.setObjectName("sendButton")
        self.btn_send.clicked.connect(self.send)
        bottom.addWidget(self.btn_send)
        root.addLayout(bottom)

        hint = QtWidgets.QLabel("Подсказка: можно писать ‘открой сайт github’, ‘выключи звук’, ‘дай совет’.")
        hint.setObjectName("hint")
        root.addWidget(hint)

    def _apply_style(self) -> None:
        accent = QtGui.QColor(getattr(self.cfg, "ui_accent_color", "#3FAF6B"))
        if not accent.isValid():
            accent = QtGui.QColor("#3FAF6B")
        r, g, b = accent.red(), accent.green(), accent.blue()

        text_c = QtGui.QColor(getattr(self.cfg, "ui_text_color", "#C8D3CC"))
        if not text_c.isValid():
            text_c = QtGui.QColor("#C8D3CC")
        tr, tg, tb = text_c.red(), text_c.green(), text_c.blue()

        self.setStyleSheet(
            f"""
            QWidget {{
              color: rgb({tr},{tg},{tb});
              font-family: Segoe UI;
              background: rgba(10,16,14,0.94);
            }}
            #title {{
              font-size: 30px;
              font-weight: 900;
              letter-spacing: 3px;
            }}
            #subtitle {{
              color: rgba({tr},{tg},{tb},0.62);
              font-size: 12px;
            }}
            #badge {{
              padding: 6px 12px;
              border-radius: 999px;
              background: rgba({r},{g},{b},0.12);
              border: 1px solid rgba({r},{g},{b},0.40);
              font-weight: 800;
              letter-spacing: 1px;
            }}
            #chat {{
              background: rgba(0,0,0,0.28);
              border: 1px solid rgba({r},{g},{b},0.22);
              border-radius: 12px;
              padding: 10px;
              font-size: 13px;
            }}
            QLineEdit {{
              background: rgba(0,0,0,0.35);
              border: 1px solid rgba({r},{g},{b},0.25);
              border-radius: 10px;
              padding: 10px 12px;
              font-size: 13px;
            }}
            #sendButton {{
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(46,56,50,0.95), stop:1 rgba(26,34,30,0.95));
              border: 1px solid rgba({r},{g},{b},0.55);
              border-radius: 10px;
              padding: 10px 18px;
              font-weight: 900;
              letter-spacing: 1px;
            }}
            #sendButton:hover {{
              border: 1px solid rgba({r},{g},{b},0.85);
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(62,76,66,0.98), stop:1 rgba(34,44,38,0.98));
            }}
            #hint {{
              color: rgba({tr},{tg},{tb},0.55);
              font-size: 12px;
            }}
            """
        )

    def _fade_in(self) -> None:
        self.setWindowOpacity(0.0)
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _append(self, who: str, text: str) -> None:
        self.chat.appendPlainText(f"{who}: {text}\n")
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _typing_badge(self, on: bool) -> None:
        self.badge.setText("● THINKING" if on else "● READY")

    def send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append("Вы", text)

        self._typing_badge(True)
        QtWidgets.QApplication.processEvents()

        sys_controller = getattr(self.bot, "system_controller", None)
        if sys_controller is not None:
            sys_result = sys_controller.handle_command(text)
            if sys_result.handled:
                answer = sys_result.message or "Команда выполнена."
                self._append("Скотт", answer)
                self._speak(answer)
                self._typing_badge(False)
                return

        self.counter += 1
        out = Path("voice_sessions") / f"text_qt_answer_{self.counter}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        result = self.bot.process_text_question(text, output_audio_path=out)
        answer = result.get("answer_text", "")
        self._append("Скотт", answer)
        play_audio(out)
        self._typing_badge(False)

    def _speak(self, text: str) -> None:
        self.counter += 1
        out = Path("voice_sessions") / f"text_qt_sys_{self.counter}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.bot.tts.synthesize_to_file(text=text, language="ru", speaker=None, out_path=out)
        play_audio(out)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    w = TextModeWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

