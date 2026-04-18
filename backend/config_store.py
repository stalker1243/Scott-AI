"""
Простой конфиг проекта (json) для управления Скоттом из панели.

Хранит настройки, которые удобно менять без правок кода:
- голос (voice_preset)
- настройки ASR (whisper model_size/language)
- настройки LLM (provider/model)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any, Dict
import json


DEFAULT_CONFIG_PATH = Path("./config.json")


@dataclass
class AppConfig:
    user_name: str = ""
    user_title: str = "сэр"
    preferred_voice_gender: str = "male"
    voice_preset: str = "scott_brutal_ru"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 160
    asr_model_size: str = "tiny"
    asr_language: str = "ru"
    asr_device: str = "cpu"
    input_device_id: int = -1
    memory_path: str = "./data/memory.jsonl"
    offline_game_limit_minutes: int = 90
    activity_advice_cooldown_minutes: int = 20
    enable_power_confirmation: bool = True
    assistant_memory_path: str = "./data/assistant_profile.json"
    # UI/launcher theme
    ui_font_family: str = "Segoe UI"
    ui_font_size: int = 14
    ui_accent_color: str = "#72A0FF"  # neon blue
    ui_text_color: str = "#EAF0FF"
    ui_panel_opacity_left: int = 75   # 0..100
    ui_panel_opacity_right: int = 80  # 0..100


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()
    try:
        data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        cfg = AppConfig()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")


