#!/usr/bin/env python3
"""
Быстрая самопроверка Скотта перед сборкой/установкой.

Запуск из папки backend:
    python self_check.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


MODULES = [
    "config_store",
    "tts_core",
    "tts_core.voices",
    "llm_core.engine",
    "chatbot.engine",
    "system_control.engine",
    "system_control.app_discovery",
    "voice_assistant_daemon",
    "maltruand",
    "launcher.launcher_qt",
    "video_dubbing.engine",
]


def main() -> int:
    print("🔍 Самопроверка модулей Скотта...\n")
    ok = True

    for name in MODULES:
        try:
            importlib.import_module(name)
            print(f"✅ import {name}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"❌ import {name} — ошибка: {e}")

    if ok:
        print("\n🎉 Всё основное импортируется без ошибок. Можно собирать EXE/установщик.")
        return 0

    print("\n⚠️ Есть ошибки импортов. Сначала исправь их, затем повтори проверку.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


