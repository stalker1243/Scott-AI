"""
Панель управления Скоттом (GUI, Tkinter).

Позволяет:
- запускать/останавливать режимы (CLI, voice live, daemon)
- менять голосовой пресет
- менять настройки ASR/LLM
- сохранять настройки в config.json

Запуск:
    cd backend
    python control_panel.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from config_store import AppConfig, load_config, save_config
from tts_core import list_available_voices


BACKEND_DIR = Path(__file__).parent


class ControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Scott Control Panel")
        self.geometry("620x420")

        self.cfg = load_config()
        self.process: subprocess.Popen | None = None

        voices = list_available_voices()
        self.voice_keys = sorted(voices.keys())

        # UI vars
        self.var_voice = tk.StringVar(value=self.cfg.voice_preset)
        self.var_llm_provider = tk.StringVar(value=self.cfg.llm_provider)
        self.var_llm_model = tk.StringVar(value=self.cfg.llm_model)
        self.var_asr_size = tk.StringVar(value=self.cfg.asr_model_size)
        self.var_asr_lang = tk.StringVar(value=self.cfg.asr_language)
        self.var_asr_device = tk.StringVar(value=self.cfg.asr_device)

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **pad)

        # Config section
        cfg_box = ttk.LabelFrame(frm, text="Настройки")
        cfg_box.pack(fill="x", **pad)

        row = 0
        ttk.Label(cfg_box, text="Голос (preset):").grid(row=row, column=0, sticky="w", **pad)
        cmb_voice = ttk.Combobox(cfg_box, textvariable=self.var_voice, values=self.voice_keys, state="readonly", width=35)
        cmb_voice.grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(cfg_box, text="LLM provider:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Combobox(cfg_box, textvariable=self.var_llm_provider, values=["ollama", "dummy", "openai"], state="readonly", width=35).grid(
            row=row, column=1, sticky="w", **pad
        )

        row += 1
        ttk.Label(cfg_box, text="LLM model:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(cfg_box, textvariable=self.var_llm_model, width=38).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(cfg_box, text="Whisper model:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Combobox(cfg_box, textvariable=self.var_asr_size, values=["tiny", "base", "small", "medium", "large"], state="readonly", width=35).grid(
            row=row, column=1, sticky="w", **pad
        )

        row += 1
        ttk.Label(cfg_box, text="ASR language:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Combobox(cfg_box, textvariable=self.var_asr_lang, values=["ru", "en", ""], state="readonly", width=35).grid(
            row=row, column=1, sticky="w", **pad
        )

        row += 1
        ttk.Label(cfg_box, text="ASR device:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Combobox(cfg_box, textvariable=self.var_asr_device, values=["cpu", "cuda"], state="readonly", width=35).grid(
            row=row, column=1, sticky="w", **pad
        )

        btn_row = ttk.Frame(cfg_box)
        btn_row.grid(row=row + 1, column=0, columnspan=2, sticky="w", **pad)
        ttk.Button(btn_row, text="💾 Сохранить настройки", command=self.save).pack(side="left", padx=6)
        ttk.Button(btn_row, text="↩ Сбросить из файла", command=self.reload).pack(side="left", padx=6)

        # Run section
        run_box = ttk.LabelFrame(frm, text="Запуск режимов")
        run_box.pack(fill="x", **pad)

        run_row = ttk.Frame(run_box)
        run_row.pack(fill="x", **pad)
        ttk.Button(run_row, text="▶ Текстовый режим Scott (maltruand.py)", command=lambda: self.start("maltruand.py")).pack(side="left", padx=6)
        ttk.Button(run_row, text="▶ Голос live (voice_chat_live.py)", command=lambda: self.start("voice_chat_live.py")).pack(side="left", padx=6)
        ttk.Button(run_row, text="▶ Дежурный режим (daemon)", command=lambda: self.start("voice_assistant_daemon.py")).pack(side="left", padx=6)
        ttk.Button(run_row, text="⏹ Стоп", command=self.stop).pack(side="left", padx=6)

        # Status
        self.status = tk.StringVar(value="Готово.")
        ttk.Label(frm, textvariable=self.status).pack(fill="x", **pad)

        hint = (
            "Подсказка: если нет микрофона, запускай текстовый режим.\n"
            "Голосовые режимы требуют работающего устройства ввода."
        )
        ttk.Label(frm, text=hint).pack(fill="x", **pad)

    def save(self) -> None:
        cfg = AppConfig(
            voice_preset=self.var_voice.get(),
            llm_provider=self.var_llm_provider.get(),
            llm_model=self.var_llm_model.get().strip(),
            asr_model_size=self.var_asr_size.get(),
            asr_language=self.var_asr_lang.get().strip() or "ru",
            asr_device=self.var_asr_device.get(),
            memory_path=str(self.cfg.memory_path),
        )
        save_config(cfg)
        self.cfg = cfg
        self.status.set("✅ Настройки сохранены в backend/config.json")

    def reload(self) -> None:
        self.cfg = load_config()
        self.var_voice.set(self.cfg.voice_preset)
        self.var_llm_provider.set(self.cfg.llm_provider)
        self.var_llm_model.set(self.cfg.llm_model)
        self.var_asr_size.set(self.cfg.asr_model_size)
        self.var_asr_lang.set(self.cfg.asr_language)
        self.var_asr_device.set(self.cfg.asr_device)
        self.status.set("✅ Настройки загружены из backend/config.json")

    def start(self, script: str) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Scott", "Сначала останови текущий режим (Стоп).")
            return

        # Сохраним настройки перед запуском
        self.save()

        script_path = BACKEND_DIR / script
        if not script_path.exists():
            messagebox.showerror("Scott", f"Файл не найден: {script_path}")
            return

        # Открываем в новом окне консоли, чтобы было удобно взаимодействовать (ввод/вывод)
        cmd = [sys.executable, str(script_path)]
        try:
            self.process = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.status.set(f"▶ Запущено: {script}")
        except Exception as e:
            messagebox.showerror("Scott", f"Не удалось запустить: {e}")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.status.set("Нет запущенного процесса.")
            return
        try:
            self.process.terminate()
            self.status.set("⏹ Процесс остановлен.")
        except Exception as e:
            self.status.set(f"⚠️ Не удалось остановить: {e}")


if __name__ == "__main__":
    ControlPanel().mainloop()


