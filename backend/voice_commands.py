"""Explicit commands for Scott's speech, with no system-volume changes."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceCommand:
    action: str
    value: object = None


ALIASES = {
    "скотт войс": "scott-voice", "скоттвойс": "scott-voice", "scott voice": "scott-voice",
    "айдар": "aidar", "айдара": "aidar", "aidar": "aidar",
    "айдера": "aidar", "эйдара": "aidar",
    "пайдара": "aidar",
    "евгений": "eugene", "евгения": "eugene", "eugene": "eugene",
    "бая": "baya", "баи": "baya", "байя": "baya", "baya": "baya",
    "ксения": "kseniya", "ксении": "kseniya", "kseniya": "kseniya",
    "ксения икс": "xenia", "ксении икс": "xenia", "xenia": "xenia",
    "дмитрий": "ru-RU-DmitryNeural", "дмитрия": "ru-RU-DmitryNeural",
    "светлана": "ru-RU-SvetlanaNeural", "светланы": "ru-RU-SvetlanaNeural",
    "эндрю": "en-US-AndrewMultilingualNeural", "брайан": "en-US-BrianMultilingualNeural",
    "брайана": "en-US-BrianMultilingualNeural",
    "уильям": "en-AU-WilliamMultilingualNeural", "уильяма": "en-AU-WilliamMultilingualNeural",
    "вильям": "en-AU-WilliamMultilingualNeural", "вильяма": "en-AU-WilliamMultilingualNeural",
    "у ильяма": "en-AU-WilliamMultilingualNeural", "у илима": "en-AU-WilliamMultilingualNeural",
    "флориан": "de-DE-FlorianMultilingualNeural", "флориана": "de-DE-FlorianMultilingualNeural",
    "флорианы": "de-DE-FlorianMultilingualNeural",
}


def _spoken_number(text):
    if text.isdecimal() and len(text) <= 3:
        return int(text)
    small = dict(zip(('ноль', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь',
        'восемь', 'девять', 'десять', 'одиннадцать', 'двенадцать', 'тринадцать',
        'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать'), range(20)))
    tens = dict(zip(('двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят',
                    'семьдесят', 'восемьдесят', 'девяносто'), range(20, 100, 10)))
    if text == 'сто':
        return 100
    words = text.replace('-', ' ').split()
    if len(words) == 1:
        return small.get(text, tens.get(text))
    if len(words) == 2 and words[0] in tens and words[1] in small and 1 <= small[words[1]] <= 9:
        return tens[words[0]] + small[words[1]]
    return None


def resolve_voice(value, voices):
    value = str(value).casefold().strip()
    value = ALIASES.get(value, value)
    matches = [name for name, label in voices.items() if name.casefold() == value.casefold()
               or label.split('(')[0].strip().casefold() == value.casefold()]
    return matches[0] if len(matches) == 1 else None


def parse(text: str):
    # STT adds commas between command words. Keep punctuation inside numbers
    # so a malformed decimal does not silently become an integer percentage.
    lower = re.sub(r"(?<=[^\W\d_])[,;:]\s*", " ", text.casefold().replace("ё", "е"))
    lower = re.sub(r"\s+", " ", lower).strip(" .,!?;:")
    if lower in {"выключи озвучку", "отключи озвучку", "выключи голос", "помолчи", "молчи", "включи тихий режим",
                 "выключу звучку", "выключаю звучку", "выключаю озвучку"}:
        return VoiceCommand("quiet", True)
    if lower in {"включи озвучку", "включи голос", "выключи тихий режим", "говори вслух", "можешь говорить", "ключи озвучку"}:
        return VoiceCommand("quiet", False)
    if lower in {"говори громче", "говори погромче"}:
        return VoiceCommand("volume_delta", 10)
    if lower in {"говори тише", "говори потише"}:
        return VoiceCommand("volume_delta", -10)
    if lower in {"какой голос выбран", "каким голосом ты говоришь", "настройки голоса", "покажи настройки голоса"}:
        return VoiceCommand("status")
    if lower in {'какие голоса есть', 'покажи голоса', 'список голосов', 'какие голоса доступны'}:
        return VoiceCommand('catalog')
    match = re.fullmatch(r"(?:выбери|выпери|смени|измени|переключи|поставь|включи) (?:свой )?голос(?: на)? (.+)", lower)
    if match:
        value = match[1].strip()
        return VoiceCommand("select", ALIASES.get(value, value))
    match = re.fullmatch(r"(?:поставь |установи |сделай )?громкость (?:твоего )?голоса(?: на)? (.+?)(?:\s*%| процентов| процента| процент)?", lower)
    if match:
        volume = _spoken_number(match[1].strip())
        if volume is not None:
            return VoiceCommand("volume", volume)
        return VoiceCommand('invalid_volume')
    match = re.fullmatch(r"(?:выбери|смени|измени|поставь) (?:характеры?|стиль) (?:своего )?(?:голоса|озвучки)(?: на)? (.+)", lower)
    if match:
        characters = {"обычный": "natural", "естественный": "natural", "четкий": "clear",
                      "исходный": "natural", "сдержанный": "restrained", "скотт": "scott",
                      "цифровой": "digital",
                      "спокойный": "calm", "мягкий": "calm", "мягкий и четкий": "calm",
                      "синтетический": "synthetic", "робот": "synthetic", "из динамика": "speaker"}
        return VoiceCommand("character", characters.get(match[1], match[1]))
    return None


def execute(action, value=None) -> str:
    try:
        from . import audio_settings, audio_endpoints, scott_voice
        from .voice_character import CHARACTERS
    except ImportError:
        import audio_settings, audio_endpoints, scott_voice
        from voice_character import CHARACTERS
    try:
        if action == "select":
            voice = resolve_voice(value, scott_voice.AVAILABLE_VOICES)
            if voice == 'scott-voice':
                info = scott_voice.scott_voice_engine.get_engine().describe()
                if not info['available']:
                    return '❌ ' + info['reason']
            if not voice or not scott_voice.set_current_voice(voice):
                return '❌ Не знаю такого голоса. ' + execute('catalog')
            return f"Теперь говорю голосом {scott_voice.AVAILABLE_VOICES[voice]}. Выбор сохранён."
        if action == "quiet":
            audio_settings.set_quiet(value)
            if value:
                audio_endpoints._stop_current_speech()
            return "Озвучка выключена." if value else "Озвучка включена."
        if action in ("volume", "volume_delta"):
            if action == "volume" and not 0 <= value <= 100:
                return "❌ Громкость голоса должна быть от 0 до 100 процентов."
            settings = (audio_settings.update(volume=value) if action == 'volume'
                        else audio_settings.adjust_volume(value))
            return f"Громкость моего голоса: {settings['volume']} процентов."
        if action == 'invalid_volume':
            return '❌ Назовите громкость голоса числом от 0 до 100, например: «громкость голоса пятьдесят процентов».'
        if action == "character":
            if scott_voice.get_current_voice() == 'scott-voice':
                profiles = scott_voice.scott_voice_engine.PROFILES
                if value not in profiles:
                    return "❌ Для Scott Voice выберите исходный, сдержанный, Scott или цифровой характер."
                if not scott_voice.set_current_voice('scott-voice', value):
                    return '❌ ' + scott_voice.scott_voice_engine.get_engine().describe()['reason']
                audio_endpoints._stop_current_speech()
                return f"Характер Scott Voice: {profiles[value]}."
            if value not in CHARACTERS:
                return "❌ Не знаю такого характера голоса. Выберите его в настройках."
            audio_settings.update(character=value)
            return f"Характер голоса: {CHARACTERS[value]}."
        if action == "status":
            voice = scott_voice.get_current_voice()
            settings = audio_settings.get_settings()
            return f"Голос: {scott_voice.AVAILABLE_VOICES[voice]}. Громкость: {settings['volume']} процентов. Озвучка {'выключена' if settings['quiet'] else 'включена'}."
        if action == 'catalog':
            names = ', '.join(label.split('(')[0].strip() for label in scott_voice.AVAILABLE_VOICES.values())
            return f'Доступные голоса: {names}. Скажите, например: «выбери голос Айдара».'
    except OSError:
        return "❌ Не удалось сохранить настройки голоса. Проверьте доступ к папке данных."
    return "❌ Неизвестная настройка голоса."
