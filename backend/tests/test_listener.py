"""
Прослушивание микрофона и активация по имени.

Микрофон здесь не нужен: звук подаётся в модуль напрямую через `feed`, а
распознавание подменяется функцией, возвращающей заранее известный текст. Так
проверяется вся логика — где начинается фраза, где заканчивается, обращались
ли к Scott — без единого произнесённого слова.

Чего это не покрывает: как поведёт себя реальный микрофон в шумной комнате.
Порог там подстраивается под фон, и подобрать его окончательно можно только на
живой машине.
"""

import threading
import time

import numpy as np
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def listener_module():
    import listener

    return listener


def silence(module, seconds: float) -> np.ndarray:
    """Тишина — не абсолютный ноль, а слабый шум: так ведёт себя живой микрофон."""
    return np.random.normal(0, 0.0005, int(module.SAMPLE_RATE * seconds)).astype(np.float32)


def speech(module, seconds: float, level: float = 0.15) -> np.ndarray:
    """Условная «речь» — достаточно громкий сигнал, чтобы преодолеть порог."""
    samples = int(module.SAMPLE_RATE * seconds)
    tone = np.sin(np.linspace(0, seconds * 220 * 2 * np.pi, samples))
    return (tone * level).astype(np.float32)


def run_stream(module, stream, transcribe=None, check_trigger=None, wait=2.5, config=None):
    """Прогнать поток через слушателя и вернуть его вместе со списком команд."""
    executed = []
    heard = []

    def default_transcribe(audio):
        heard.append(len(audio) / module.SAMPLE_RATE)
        return "Скотт, открой блокнот"

    instance = module.VoiceListener(
        transcribe=transcribe or default_transcribe,
        handle_command=lambda text: executed.append(text),
        check_trigger=check_trigger,
        config=config,
    )
    instance._running = True
    threads = [
        threading.Thread(target=instance._segment_loop, daemon=True),
        threading.Thread(target=instance._process_loop, daemon=True),
    ]
    for thread in threads:
        thread.start()

    instance.feed(stream)
    time.sleep(wait)
    instance._running = False

    return instance, executed, heard


# ==================== Разбор потока на фразы ====================

def test_speech_between_silence_becomes_one_phrase(listener_module):
    """Одна фраза в тишине выделяется как одна фраза."""
    stream = np.concatenate([
        silence(listener_module, 0.6),
        speech(listener_module, 1.2),
        silence(listener_module, 1.2),
    ])

    _, _, heard = run_stream(listener_module, stream)

    assert len(heard) == 1


def test_pause_splits_phrases(listener_module):
    """
    Пауза разделяет реплики.

    Иначе Scott склеил бы отдельные обращения в одно и попытался выполнить
    команду, которой никто не давал.
    """
    stream = np.concatenate([
        silence(listener_module, 0.5),
        speech(listener_module, 1.0),
        silence(listener_module, 1.5),
        speech(listener_module, 1.0),
        silence(listener_module, 1.2),
    ])

    _, _, heard = run_stream(listener_module, stream, wait=3.0)

    assert len(heard) == 2


def test_short_noise_is_ignored(listener_module):
    """
    Щелчок или стук не должен запускать распознавание.

    Иначе Whisper будет просыпаться от каждого удара по клавиатуре — а это
    сотни миллисекунд работы видеокарты на пустом месте.
    """
    stream = np.concatenate([
        silence(listener_module, 0.5),
        speech(listener_module, 0.05),
        silence(listener_module, 1.5),
    ])

    _, _, heard = run_stream(listener_module, stream)

    assert heard == []


def test_silence_alone_produces_nothing(listener_module):
    """В тишине Scott молчит и ничего не распознаёт."""
    _, executed, heard = run_stream(listener_module, silence(listener_module, 3.0))

    assert heard == []
    assert executed == []


def test_long_speech_is_cut(listener_module):
    """
    Слишком длинная речь обрезается по верхней границе.

    Разговор рядом с компьютером не должен копиться в памяти бесконечно.
    """
    config = listener_module.ListenerConfig(max_phrase=1.0)
    stream = np.concatenate([
        silence(listener_module, 0.4),
        speech(listener_module, 4.0),
        silence(listener_module, 1.2),
    ])

    _, _, heard = run_stream(listener_module, stream, wait=3.0, config=config)

    assert heard, "фраза не выделена вовсе"
    assert max(heard) <= 1.6, f"фраза не обрезана: {heard}"


def test_preroll_keeps_beginning(listener_module):
    """
    В начало фразы попадает запас до превышения порога.

    Человек начинает говорить тише, чем середину фразы, и без запаса теряется
    первый слог — тот самый, в котором звучит имя.
    """
    stream = np.concatenate([
        silence(listener_module, 0.8),
        speech(listener_module, 1.0),
        silence(listener_module, 1.2),
    ])

    _, _, heard = run_stream(listener_module, stream)

    assert heard and heard[0] > 1.0, f"фраза короче самой речи: {heard}"


# ==================== Активация по имени ====================

class FakeTrigger:
    def __init__(self, has_trigger, command_text=""):
        self.has_trigger = has_trigger
        self.command_text = command_text


def test_command_runs_only_after_name(listener_module):
    """Обращение по имени — команда выполняется."""
    stream = np.concatenate([
        silence(listener_module, 0.5), speech(listener_module, 1.0), silence(listener_module, 1.2),
    ])

    _, executed, _ = run_stream(
        listener_module, stream,
        transcribe=lambda audio: "Скотт, открой блокнот",
        check_trigger=lambda text: FakeTrigger(True, "открой блокнот"),
    )

    assert executed == ["открой блокнот"]


def test_speech_without_name_is_ignored(listener_module):
    """
    Без имени команда не выполняется.

    Главное свойство всей затеи: Scott слышит комнату целиком, и реагировать на
    любой разговор рядом — худшее, что он может делать.
    """
    stream = np.concatenate([
        silence(listener_module, 0.5), speech(listener_module, 1.0), silence(listener_module, 1.2),
    ])

    instance, executed, _ = run_stream(
        listener_module, stream,
        transcribe=lambda audio: "Какая сегодня погода",
        check_trigger=lambda text: FakeTrigger(False),
    )

    assert executed == []
    assert instance.stats.ignored == 1


def test_name_without_command_does_nothing(listener_module):
    """Позвали по имени, но ничего не попросили — выполнять нечего."""
    stream = np.concatenate([
        silence(listener_module, 0.5), speech(listener_module, 1.0), silence(listener_module, 1.2),
    ])

    instance, executed, _ = run_stream(
        listener_module, stream,
        transcribe=lambda audio: "Скотт",
        check_trigger=lambda text: FakeTrigger(True, ""),
    )

    assert executed == []
    assert instance.stats.triggered == 1


def test_recognition_failure_does_not_stop_listening(listener_module):
    """
    Сбой распознавания не должен ронять прослушивание.

    Одна неудачная фраза — не повод оглохнуть до перезапуска backend.
    """
    stream = np.concatenate([
        silence(listener_module, 0.4), speech(listener_module, 1.0), silence(listener_module, 1.2),
        speech(listener_module, 1.0), silence(listener_module, 1.2),
    ])

    attempts = []

    def flaky(audio):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("модель не отозвалась")
        return "Скотт, сделай громче"

    instance, executed, _ = run_stream(
        listener_module, stream,
        transcribe=flaky,
        check_trigger=lambda text: FakeTrigger(True, "сделай громче"),
        wait=3.0,
    )

    assert len(attempts) == 2, "после сбоя слушатель перестал разбирать фразы"
    assert executed == ["сделай громче"]
    assert "не удалось" in instance.stats.last_error.lower()


# ==================== Состояние ====================

def test_status_reports_state(listener_module):
    """Состояние показывает, слушает ли Scott и что успел услышать."""
    instance = listener_module.VoiceListener(
        transcribe=lambda audio: "",
        handle_command=lambda text: None,
    )

    status = instance.status()

    assert status["listening"] is False
    assert "noise_floor" in status
    assert status["phrases_heard"] == 0


def test_stop_without_start_is_safe(listener_module):
    """Остановить не начатое прослушивание — не ошибка."""
    instance = listener_module.VoiceListener(
        transcribe=lambda audio: "",
        handle_command=lambda text: None,
    )

    assert instance.stop()["success"]
