"""
Дежурный режим Скотта (always-listening) с активацией по слову.

Как работает:
1) Скотт "слушает" микрофон и ждёт фразу-активатор (wake word): "скотт" / "scott"
2) После активации:
   - пытается выполнить команду ОС через SystemController
   - если это не системная команда — отвечает через LLM
3) Ответ всегда озвучивается.

Запуск:
    cd backend
    python voice_assistant_daemon.py

Выход:
    Ctrl+C
"""

from __future__ import annotations

import os
import re
import time
import traceback
from difflib import SequenceMatcher
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import sounddevice as sd
import soundfile as sf

try:
    from .chatbot import ChatBot, ChatBotConfig  # noqa: E402
    from .llm_core import LlmEngine, LlmConfig  # noqa: E402
    from .knowledge_base import KnowledgeBase  # noqa: E402
    from .tts_core import TtsEngine, TtsConfig  # noqa: E402
    from .system_control import SystemController  # noqa: E402
    from .asr_core import AsrEngine, AsrConfig  # noqa: E402
    from .config_store import load_config  # noqa: E402
    from .audio_playback import play_audio  # noqa: E402
except ImportError:
    from chatbot import ChatBot, ChatBotConfig  # noqa: E402
    from llm_core import LlmEngine, LlmConfig  # noqa: E402
    from knowledge_base import KnowledgeBase  # noqa: E402
    from tts_core import TtsEngine, TtsConfig  # noqa: E402
    from system_control import SystemController  # noqa: E402
    from asr_core import AsrEngine, AsrConfig  # noqa: E402
    from config_store import load_config  # noqa: E402
    from audio_playback import play_audio  # noqa: E402


@dataclass
class ListenConfig:
    sample_rate: int = 16000
    channels: int = 1
    ambient_seconds: float = 1.0
    max_utterance_seconds: float = 6.0
    start_threshold_mult: float = 1.6   # ещё мягче старт, чтобы не срезать начало команды
    min_threshold: float = 0.006        # понижен, чтобы ловить тихую речь/гарнитуры
    stop_silence_seconds: float = 0.45  # быстрее завершаем фразу -> быстрее реакция
    pre_roll_seconds: float = 0.25      # чуть захватываем до начала речи
    input_device: Optional[int] = None  # если None — авто выбор
    fallback_chunk_seconds: float = 2.2


WAKE_WORDS = ("скотт", "scott")


def _append_daemon_log(text: str) -> None:
    log_path = Path(__file__).resolve().parent / "data" / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as f:
        f.write(text + "\n")


def _is_bad_input_name(name: str) -> bool:
    n = (name or "").lower()
    bad_tokens = (
        "headphones",
        "науш",
        "гарнит",
        "gaming",
        "loopback",
        "stereo mix",
        "переназнач",
        "remap",
        "virtual",
        "vb-audio",
        "primary sound capture",
        "первичный драйвер записи",
        "wave mapper",
        "переназначение звуковых",
    )
    return any(tok in n for tok in bad_tokens)


def _normalize_token(token: str) -> str:
    return "".join(ch for ch in token.lower() if ch.isalpha())


def _best_match_ratio(word: str, candidates: tuple[str, ...]) -> tuple[float, str]:
    best_ratio = 0.0
    best_word = ""
    for cand in candidates:
        r = SequenceMatcher(None, word, cand).ratio()
        if r > best_ratio:
            best_ratio = r
            best_word = cand
    return best_ratio, best_word


def _normalize_command_text(cmd: str) -> str:
    """
    Исправляет частые искажения ASR в командных словах.
    Пример: "отклогал" -> "открой", "аткрой" -> "открой".
    """
    t = (cmd or "").strip().lower()
    if not t:
        return t
    words = [w.strip(" ,.!?:;—-") for w in t.split() if w.strip(" ,.!?:;—-")]
    if not words:
        return t

    verbs = (
        "открой",
        "закрой",
        "запусти",
        "включи",
        "выключи",
        "найди",
        "покажи",
        "перейди",
        "заблокируй",
    )
    keywords = (
        "гугл",
        "google",
        "chrome",
        "хром",
        "браузер",
        "ютуб",
        "youtube",
        "дискорд",
        "discord",
        "телеграм",
        "telegram",
        "стим",
        "steam",
        "вк",
        "вконтакте",
        "новости",
        "погода",
        "курс",
        "доллара",
        "евро",
        "github",
        "гитхаб",
    )
    first_raw = words[0]
    # Нормализуем типичные формы/ошибки глагола команды.
    manual_verb_fixes = {
        "откроет": "открой",
        "открои": "открой",
        "открою": "открой",
        "открыл": "открой",
        "заблокирует": "заблокируй",
        "заблокируеть": "заблокируй",
        "создайте": "создай",
        "создать": "создай",
    }
    words[0] = manual_verb_fixes.get(words[0], words[0])
    first_norm = _normalize_token(first_raw)
    if first_norm:
        ratio, repl = _best_match_ratio(first_norm, verbs)
        if ratio >= 0.62:
            words[0] = repl

    # Корректируем ключевые слова команды (названия приложений/сайтов/запросов).
    for i in range(1, len(words)):
        w_norm = _normalize_token(words[i])
        if not w_norm:
            continue
        ratio, repl = _best_match_ratio(w_norm, keywords)
        if ratio >= 0.68:
            words[i] = repl

    # Частые "съеденные" конструкции
    joined = " ".join(words).strip()
    if joined.startswith("открой google"):
        return "открой google chrome"
    if joined.startswith("открой гугл"):
        return "открой google chrome"
    if joined.startswith("открой хром"):
        return "открой google chrome"
    if joined.startswith("открой ютуб"):
        return "открой youtube"
    if joined.startswith("открой гитхаб") or joined.startswith("открой github"):
        return "открой сайт github"
    return joined


def _looks_immediate_system_command(cmd: str) -> bool:
    c = (cmd or "").strip().lower()
    if not c:
        return False
    prefixes = ("открой", "закрой", "запусти", "включи", "выключи", "перейди", "найди", "заблокируй", "создай")
    return c.startswith(prefixes)


def _should_voice_system_result(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    # Для ошибок/подтверждений/советов озвучка важна.
    important_markers = ("не удалось", "ошибка", "уточн", "подтверд", "отмен", "совет", "рекомендац")
    return any(m in t for m in important_markers)


def _looks_like_asr_noise(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    # Явные маркеры "мусорного" распознавания (субтитры, фоновая музыка, повторы).
    noise_markers = (
        "редактор субтитров",
        "корректор",
        "музыка",
        "я не знаю, что это было",
    )
    if any(m in t for m in noise_markers):
        return True
    # Длинные "тааааа", "аааа" и прочие растянутые гласные.
    if re.search(r"(.)\1{10,}", t):
        return True
    # Слишком длинный повтор одного и того же фрагмента.
    words = [w for w in t.split() if w]
    if len(words) >= 16:
        uniq = len(set(words))
        if uniq <= max(4, len(words) // 8):
            return True
    return False



def _print_input_devices() -> None:
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"⚠️  Не удалось получить список аудиоустройств: {e}")
        return

    print("\n🎙️  Доступные устройства ввода (микрофоны):")
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            name = d.get("name", "Unknown")
            hostapi = d.get("hostapi", None)
            print(f"- id={i}  channels={d.get('max_input_channels')}  name={name}  hostapi={hostapi}")


def _pick_input_device(cfg: ListenConfig) -> Optional[int]:
    """
    Возвращает корректный id устройства ввода или None (пусть sounddevice выберет сам).
    Исправляет ситуацию, когда default device == -1.
    """
    env = os.getenv("MALTRUAND_INPUT_DEVICE")
    if env is not None and env.strip().isdigit():
        cfg.input_device = int(env.strip())

    if cfg.input_device is not None:
        try:
            devices = sd.query_devices()
            if 0 <= int(cfg.input_device) < len(devices):
                d = devices[int(cfg.input_device)]
                if d.get("max_input_channels", 0) > 0:
                    return int(cfg.input_device)
        except Exception:
            pass
        # Невалидный id — сбрасываем и ищем корректный автоматически.
        cfg.input_device = None

    try:
        default_in, _ = sd.default.device  # type: ignore[attr-defined]
    except Exception:
        default_in = None

    # Иногда default в Windows указывает на "тихий" вход (гарнитура/loopback).
    # Поэтому если пользователь явно не выбрал устройство, оцениваем кандидатов
    # и выбираем самый "живой" микрофонный вариант.
    try:
        devices = sd.query_devices()
        best_id: Optional[int] = None
        best_score = -10_000.0
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) <= 0:
                continue
            name = str(d.get("name", "")).lower()
            if _is_bad_input_name(name):
                continue
            score = float(d.get("max_input_channels", 1))
            if any(k in name for k in ("mic", "microphone", "микрофон")):
                score += 6.0
            if any(k in name for k in ("array", "массив", "realtek", "usb")):
                score += 1.5
            if score > best_score:
                best_score = score
                best_id = i
        if best_id is not None:
            cfg.input_device = int(best_id)
            os.environ["MALTRUAND_INPUT_DEVICE"] = str(best_id)
            return best_id
        if isinstance(default_in, int) and default_in >= 0:
            return default_in
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0:
                return i
    except Exception:
        return None

    return None


def _input_device_candidates() -> List[int]:
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    result: List[int] = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0 and not _is_bad_input_name(str(d.get("name", ""))):
            result.append(i)
    if result:
        return result
    # fallback: если все устройства отфильтрованы, возвращаем любой input.
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            result.append(i)
    return result


def _probe_device_rms(device_id: int, sample_rate: int, seconds: float = 0.35) -> float:
    try:
        samples = max(1, int(sample_rate * seconds))
        audio = sd.rec(
            samples,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device_id,
        )
        sd.wait()
        return _rms(audio.reshape(-1))
    except Exception:
        return 0.0


def _autofix_input_device(cfg: ListenConfig, current_threshold: float) -> bool:
    """Пытается найти вход, где есть реальный сигнал, и переключиться на него."""
    candidates = _input_device_candidates()
    if not candidates:
        return False
    min_signal = max(cfg.min_threshold * 0.25, current_threshold * 0.2, 0.0005)
    best_id: Optional[int] = None
    best_rms = 0.0
    for dev_id in candidates:
        rms = _probe_device_rms(dev_id, cfg.sample_rate)
        try:
            info = sd.query_devices(dev_id)
            name = str(info.get("name", "")).lower()
        except Exception:
            name = ""
        # Поднимаем приоритет "реальных" микрофонов и понижаем "headphones" входы.
        if any(k in name for k in ("микрофон", "microphone", "mic")):
            rms *= 1.35
        if _is_bad_input_name(name):
            rms *= 0.75
        if rms > best_rms:
            best_rms = rms
            best_id = dev_id
    if best_id is not None and best_rms >= min_signal:
        cfg.input_device = int(best_id)
        os.environ["MALTRUAND_INPUT_DEVICE"] = str(best_id)
        try:
            info = sd.query_devices(best_id)
            print(f"🎤 Автопереключение микрофона: id={best_id} ({info.get('name', 'Unknown')})")
        except Exception:
            print(f"🎤 Автопереключение микрофона: id={best_id}")
        return True
    return False


def init_bot() -> ChatBot:
    app_cfg = load_config()
    kb = KnowledgeBase()
    llm = LlmEngine(
        LlmConfig(
            provider=app_cfg.llm_provider,
            model=app_cfg.llm_model,
            temperature=float(getattr(app_cfg, "llm_temperature", 0.4)),
            max_tokens=int(getattr(app_cfg, "llm_max_tokens", 160)),
        ),
        knowledge_base=kb,
    )
    voice_by_gender = {
        "male": "scott_brutal_ru",
        "female": "robot_light_female",
    }
    selected_voice = app_cfg.voice_preset or voice_by_gender.get(app_cfg.preferred_voice_gender, "scott_brutal_ru")
    tts = TtsEngine(TtsConfig(voice_preset=selected_voice))
    # Быстрый ASR под цель ~2 секунды: tiny + фиксированный язык ru
    daemon_asr_model = os.getenv("MALTRUAND_DAEMON_ASR_MODEL", "base").strip() or app_cfg.asr_model_size
    asr = AsrEngine(AsrConfig(model_size=daemon_asr_model, language=app_cfg.asr_language, device=app_cfg.asr_device))
    bot = ChatBot(
        ChatBotConfig(
            language="ru",
            asr_engine=asr,
            llm_engine=llm,
            tts_engine=tts,
            memory_path=Path(app_cfg.memory_path),
        )
    )
    bot.system_controller = SystemController(
        offline_game_limit_minutes=app_cfg.offline_game_limit_minutes,
        advice_cooldown_minutes=app_cfg.activity_advice_cooldown_minutes,
        enable_power_confirmation=app_cfg.enable_power_confirmation,
        memory_path=Path(app_cfg.assistant_memory_path),
        user_name=app_cfg.user_name,
        user_title=app_cfg.user_title,
    )
    return bot


def _rms(x: np.ndarray) -> float:
    x = x.astype(np.float32, copy=False).reshape(-1)
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def calibrate_threshold(cfg: ListenConfig) -> float:
    print(f"🎛️  Калибровка шума ({cfg.ambient_seconds:.1f}s)... молчи секунду.")
    device = _pick_input_device(cfg)
    try:
        audio = sd.rec(
            int(cfg.ambient_seconds * cfg.sample_rate),
            samplerate=cfg.sample_rate,
            channels=cfg.channels,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except Exception as e:
        print(f"❌ Ошибка доступа к микрофону: {e}")
        _print_input_devices()
        print("\n💡 Можно явно выбрать микрофон так:")
        print("   setx MALTRUAND_INPUT_DEVICE 1")
        print("   (подставь id нужного устройства)")
        raise
    noise = _rms(audio)
    if noise <= 1e-6:
        # Типичный кейс: выбрано "мертвое" устройство.
        switched = _autofix_input_device(cfg, cfg.min_threshold)
        if switched:
            try:
                device = _pick_input_device(cfg)
                audio = sd.rec(
                    int(cfg.ambient_seconds * cfg.sample_rate),
                    samplerate=cfg.sample_rate,
                    channels=cfg.channels,
                    dtype="float32",
                    device=device,
                )
                sd.wait()
                noise = _rms(audio)
            except Exception:
                pass
    thr = max(cfg.min_threshold, min(0.045, noise * cfg.start_threshold_mult))
    print(f"✅ Шум: {noise:.4f} → порог старта: {thr:.4f}")
    return thr


def record_utterance(cfg: ListenConfig, start_threshold: float) -> Optional[np.ndarray]:
    """
    Ждёт речь и записывает одну фразу, завершая по тишине.
    Возвращает mono float32 массив или None, если ничего не записали.
    """
    sr = cfg.sample_rate
    block = int(0.03 * sr)  # 30ms
    max_samples = int(cfg.max_utterance_seconds * sr)
    stop_silence = int(cfg.stop_silence_seconds * sr)
    pre_roll = int(cfg.pre_roll_seconds * sr)

    ring: List[np.ndarray] = []
    captured: List[np.ndarray] = []
    started = False
    silent = 0
    total = 0

    device = _pick_input_device(cfg)
    with sd.InputStream(
        samplerate=sr,
        channels=cfg.channels,
        dtype="float32",
        blocksize=block,
        device=device,
    ) as stream:
        # ждём начала речи
        while True:
            data, _ = stream.read(block)
            mono = data.reshape(-1)
            ring.append(mono.copy())
            # ограничиваем буфер
            ring_samples = sum(len(x) for x in ring)
            while ring_samples > pre_roll and ring:
                ring_samples -= len(ring[0])
                ring.pop(0)

            energy = _rms(mono)
            if not started:
                if energy > start_threshold:
                    started = True
                    captured.extend(ring)
                    ring.clear()
                    silent = 0
                    total = sum(len(x) for x in captured)
                    break

        # записываем до конца фразы
        while started:
            data, _ = stream.read(block)
            mono = data.reshape(-1).copy()
            captured.append(mono)
            total += len(mono)

            energy = _rms(mono)
            if energy < (start_threshold * 0.65):
                silent += len(mono)
            else:
                silent = 0

            if silent >= stop_silence:
                break
            if total >= max_samples:
                break

    if not captured:
        return None

    audio = np.concatenate(captured).astype(np.float32, copy=False)
    # лёгкая защита от пустоты
    if _rms(audio) < cfg.min_threshold * 0.5:
        return None
    return audio


def record_chunk(cfg: ListenConfig) -> Optional[np.ndarray]:
    """Фиксированная запись чанка как fallback при проблемах VAD."""
    try:
        device = _pick_input_device(cfg)
        samples = int(cfg.fallback_chunk_seconds * cfg.sample_rate)
        audio = sd.rec(
            samples,
            samplerate=cfg.sample_rate,
            channels=cfg.channels,
            dtype="float32",
            device=device,
        )
        sd.wait()
        mono = audio.reshape(-1).astype(np.float32, copy=False)
        # Отсекаем почти нулевые чанки, иначе Whisper начинает "галлюцинировать" текст.
        if mono.size == 0:
            return None
        if _rms(mono) < max(0.0035, cfg.min_threshold * 0.9):
            return None
        return mono
    except Exception:
        return None


def extract_after_wake(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    if not t:
        return None
    # Опциональный режим без wake-word (по умолчанию выключен).
    if os.getenv("MALTRUAND_VOICE_NO_WAKE", "0") == "1":
        return t
    for w in WAKE_WORDS:
        if w in t:
            # если wake word не в начале — всё равно берём часть после первого появления
            idx = t.find(w)
            rest = t[idx + len(w):].strip(" ,.!?:;—-")
            return _normalize_command_text(rest) if rest else ""
    # Нечеткое совпадение wake-word (частая ошибка tiny-whisper: "мэйфтруан", "мальтруан").
    words = [w.strip(" ,.!?:;—-") for w in t.split() if w.strip(" ,.!?:;—-")]
    for i, word in enumerate(words):
        score = max(SequenceMatcher(None, word, wake).ratio() for wake in WAKE_WORDS)
        if score >= 0.72:
            rest = " ".join(words[i + 1 :]).strip()
            return _normalize_command_text(rest) if rest else ""
    # Компромисс: если wake не распознан, но фраза явно командная — обрабатываем.
    # Это помогает при ошибках tiny-whisper на слове "мальтруант".
    if os.getenv("MALTRUAND_ALLOW_DIRECT_COMMANDS", "0") == "1":
        direct_prefixes = (
            "открой",
            "запусти",
            "включи",
            "выключи",
            "найди",
            "покажи",
            "перейди",
            "какой",
            "какая",
            "какие",
            "сколько",
            "когда",
            "где",
            "кто",
            "что",
            "сделай",
            "поставь",
            "пауза",
            "громче",
            "тише",
            "заблокируй",
        )
        # Для direct-режима требуем хотя бы 2 слова, чтобы не реагировать на шум.
        if t.startswith(direct_prefixes) and len([w for w in t.split() if w]) >= 2:
            return _normalize_command_text(t)
    return None


def speak(bot: ChatBot, text: str, out_path: Path) -> bool:
    """Синтез + воспроизведение с диагностикой результата."""
    try:
        bot.tts.synthesize_to_file(text=text, language="ru", speaker=None, out_path=out_path)
        print(f"🔊 TTS файл: {out_path}")
    except Exception as e:
        print(f"❌ Ошибка синтеза речи: {e}")
        return False

    ok = False
    try:
        ok = play_audio(out_path)
    except Exception as e:
        print(f"❌ Ошибка воспроизведения: {e}")
        ok = False
    if not ok:
        print("⚠️ Не удалось запустить воспроизведение аудио.")
    return ok


def main():
    cfg = ListenConfig()
    bot = init_bot()

    tmp_dir = Path("./voice_sessions")
    tmp_dir.mkdir(exist_ok=True)
    fast_ack_path = tmp_dir / "__fast_ack.wav"

    print("🟢 Скотт в дежурном режиме.")
    print("Скажи: «Скотт, открой google chrome» или «Scott, ...».")
    print("Выход: Ctrl+C\n")
    # Покажем выбранный микрофон, если удалось определить
    dev = _pick_input_device(cfg)
    if dev is not None:
        try:
            info = sd.query_devices(dev)
            print(f"🎤 Используется микрофон id={dev}: {info.get('name','Unknown')}\n")
        except Exception:
            pass
    else:
        print("⚠️ Микрофон по умолчанию не найден. Скотт останется в дежурном режиме и будет ждать появления микрофона.")

    # Калибровка порога. Если микрофона нет или нет доступа — не вылетаем, а ждём.
    try:
        start_thr = calibrate_threshold(cfg)
    except Exception:
        print("⚠️ Не удалось получить доступ к микрофону. "
              "Дежурный режим активен, будет периодически проверять наличие микрофона.")
        start_thr = cfg.min_threshold
        while True:
            try:
                time.sleep(5.0)
                dev = _pick_input_device(cfg)
                if dev is None:
                    continue
                start_thr = calibrate_threshold(cfg)
                print("✅ Микрофон найден, голосовой дежурный режим активирован.")
                break
            except KeyboardInterrupt:
                raise
            except Exception:
                continue
    # Короткая фраза для мгновенного подтверждения перед быстрыми системными действиями.
    if not fast_ack_path.exists():
        try:
            bot.tts.synthesize_to_file(text="Есть, сэр.", language="ru", speaker=None, out_path=fast_ack_path)
        except Exception:
            pass
    counter = 0
    none_streak = 0
    empty_asr_streak = 0
    last_thr_adjust = 0.0
    force_chunk_mode = os.getenv("MALTRUAND_FORCE_CHUNK_LISTEN", "0") == "1"
    rotate_index = 0
    deaf_until = 0.0
    last_asr_text = ""
    same_asr_streak = 0

    try:
        while True:
            if time.time() < deaf_until:
                time.sleep(0.05)
                continue
            sys_controller = getattr(bot, "system_controller", None)
            if sys_controller is not None:
                coach = sys_controller.poll_activity()
                if coach and coach.message:
                    counter += 1
                    coach_path = tmp_dir / f"daemon_coach_{counter}.wav"
                    print(f"🎙️  Скотт: {coach.message}")
                    speak(bot, coach.message, coach_path)

            try:
                if force_chunk_mode or none_streak >= 10:
                    audio = record_chunk(cfg)
                else:
                    audio = record_utterance(cfg, start_thr)
            except Exception as e:
                print(f"❌ Ошибка чтения с микрофона: {e}")
                time.sleep(1.0)
                continue
            if audio is None:
                none_streak += 1
                # Если долго ничего не ловим, чуть снижаем порог старта (частая причина “не реагирует”).
                if none_streak >= 10 and (time.time() - last_thr_adjust) > 5.0:
                    start_thr = max(cfg.min_threshold, min(0.045, start_thr * 0.85))
                    last_thr_adjust = time.time()
                # Если очень долго тишина, значит часто выбран не тот input device.
                if none_streak >= 40:
                    switched = _autofix_input_device(cfg, start_thr)
                    if switched:
                        try:
                            start_thr = calibrate_threshold(cfg)
                        except Exception:
                            pass
                    none_streak = 0
                continue
            none_streak = 0
            audio_rms = _rms(audio)
            if audio_rms < max(0.0035, cfg.min_threshold * 0.9):
                # Тихий/ложный захват — трактуем как пустоту.
                none_streak += 1
                if none_streak >= 8:
                    _autofix_input_device(cfg, start_thr)
                continue

            counter += 1
            q_path = tmp_dir / f"daemon_q_{counter}.wav"
            a_path = tmp_dir / f"daemon_a_{counter}.wav"
            sf.write(str(q_path), audio, cfg.sample_rate)

            # ASR: передаём массив напрямую, чтобы Whisper не вызывал ffmpeg subprocess на каждый запрос.
            question_text = bot.asr.transcribe(audio)
            if not (question_text or "").strip():
                empty_asr_streak += 1
                # В chunk-режиме это главный индикатор "слушаем не тот микрофон".
                if empty_asr_streak >= 6:
                    switched = _autofix_input_device(cfg, start_thr)
                    if not switched:
                        # Принудительная ротация микрофонов: на некоторых системах RMS ничего не показывает,
                        # но ASR начинает работать после ручного переключения устройства.
                        cands = _input_device_candidates()
                        if cands:
                            rotate_index = (rotate_index + 1) % len(cands)
                            cfg.input_device = int(cands[rotate_index])
                            os.environ["MALTRUAND_INPUT_DEVICE"] = str(cfg.input_device)
                            switched = True
                            try:
                                info = sd.query_devices(cfg.input_device)
                                print(f"🎤 Ротация микрофона: id={cfg.input_device} ({info.get('name', 'Unknown')})")
                            except Exception:
                                print(f"🎤 Ротация микрофона: id={cfg.input_device}")
                    if switched:
                        try:
                            start_thr = calibrate_threshold(cfg)
                        except Exception:
                            pass
                    empty_asr_streak = 0
                continue
            if _looks_like_asr_noise(question_text):
                continue
            q_norm = (question_text or "").strip().lower()
            if q_norm == last_asr_text:
                same_asr_streak += 1
            else:
                same_asr_streak = 0
                last_asr_text = q_norm
            if same_asr_streak >= 2 and audio_rms < 0.01:
                switched = _autofix_input_device(cfg, start_thr)
                if switched:
                    try:
                        start_thr = calibrate_threshold(cfg)
                    except Exception:
                        pass
                continue
            empty_asr_streak = 0
            print(f"\n📝 ASR: {question_text}")

            # Wake word gating
            cmd = extract_after_wake(question_text)
            if cmd is None:
                # не активировали — игнорируем, чтобы ассистент не мешал
                continue

            if cmd == "":
                answer = "Да, сэр. Чем могу помочь?"
                print(f"🎙️  Скотт: {answer}")
                speak(bot, answer, a_path)
                # Короткая "глухая" пауза, чтобы не подхватить собственный TTS.
                deaf_until = time.time() + 1.8
                continue
            if cmd in {"открой", "закрой", "запусти", "включи", "выключи", "перейди", "найди"}:
                answer = "Уточните команду, сэр. Что именно открыть или запустить?"
                print(f"🎙️  Скотт: {answer}")
                speak(bot, answer, a_path)
                deaf_until = time.time() + 1.8
                continue
            if len(cmd.strip(" .,!?:;—-")) < 3:
                answer = "Повторите команду, сэр. Я расслышал не полностью."
                print(f"🎙️  Скотт: {answer}")
                speak(bot, answer, a_path)
                deaf_until = time.time() + 1.6
                continue

            # Системные команды приоритетнее LLM
            sys_controller = getattr(bot, "system_controller", None)
            if sys_controller is not None:
                if _looks_immediate_system_command(cmd):
                    try:
                        play_audio(fast_ack_path)
                        deaf_until = max(deaf_until, time.time() + 0.7)
                    except Exception:
                        pass
                sys_result = sys_controller.handle_command(cmd)
                if sys_result.handled:
                    answer = sys_result.message or "К вашим услугам, сэр."
                    print(f"🖥️  Система: {answer}")
                    if _should_voice_system_result(answer):
                        speak(bot, answer, a_path)
                        deaf_until = time.time() + min(8.0, 1.2 + len(answer) * 0.025)
                    else:
                        # Для быстрых системных команд ограничиваемся мгновенным ack.
                        deaf_until = max(deaf_until, time.time() + 0.7)
                    # сохраняем в историю
                    bot._remember_turn(cmd, answer)  # noqa: SLF001 (простое сохранение памяти)
                    continue

            # LLM
            print("🤖 LLM...")
            res = bot.process_text_question(cmd, output_audio_path=a_path)
            print(f"🎙️  Скотт: {res['answer_text']}")
            try:
                played = play_audio(a_path)
                if not played:
                    print("⚠️ LLM-ответ сгенерирован, но воспроизведение не запустилось.")
            except Exception as e:
                print(f"❌ Ошибка воспроизведения LLM-ответа: {e}")
            ans = str(res.get("answer_text", ""))
            deaf_until = time.time() + min(8.0, 1.6 + len(ans) * 0.03)

    except KeyboardInterrupt:
        print("\n👋 Скотт: Дежурный режим остановлен.")


if __name__ == "__main__":
    try:
        _append_daemon_log("=== daemon start ===")
        main()
    except Exception:
        _append_daemon_log("=== daemon crash ===")
        _append_daemon_log(traceback.format_exc())
        raise


