"""Модуль чат-бота, объединяющий ASR + LLM + TTS."""
from .engine import ChatBot, ChatBotConfig, get_default_chatbot

__all__ = ["ChatBot", "ChatBotConfig", "get_default_chatbot"]

