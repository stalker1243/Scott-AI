"""
Пауза, после которой фраза считается законченной, подстраивается под человека.

Была жёсткая: 0.8 секунды на каждой фразе. Число выбрано как компромисс, и оно
плохо для обеих сторон. Кто говорит слитно, ждёт лишнюю треть секунды всегда, а
кому свойственно задумываться посреди фразы — того Scott обрывает на вдохе и
выполняет половину сказанного: «открой…» вместо «открой блокнот и сверни окно».

Подстраиваться есть по чему. Если человека оборвали, он почти сразу продолжает
говорить — новая фраза начинается через считанные миллисекунды после того, как
предыдущую закрыли. Если же после фразы наступает настоящая тишина, значит
паузу можно было и не выжидать так долго.
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
    samples = int(module.SAMPLE_RATE * seconds)
    tone = np.sin(np.linspace(0, seconds * 220 * 2 * np.pi, samples))
    return (tone * level).astype(np.float32)


def прогнать(module, stream, config=None, wait=3.0):
    instance = module.VoiceListener(
        transcribe=lambda audio: "Скотт, открой блокнот",
        handle_command=lambda text: None,
        check_trigger=None,
        config=config,
    )
    instance._running = True
    поток = threading.Thread(target=instance._segment_loop, daemon=True)
    поток.start()

    instance.feed(stream)
    time.sleep(wait)
    instance._running = False
    return instance


# ==================== Сама подстройка ====================

def test_starts_from_configured_value(listener_module):
    """Начинается подстройка с настроенного значения, а не с чужого."""
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "",
        handle_command=lambda t: None,
    )
    assert instance._silence_to_end == instance.config.silence_to_end
    assert instance.stats.silence_to_end == instance.config.silence_to_end


def test_cut_off_lengthens_the_pause(listener_module):
    """
    Обрыв удлиняет паузу — и сразу заметно.

    Худший исход здесь не задержка, а выполненная половина команды: Scott
    слышит «открой…», не дожидается «блокнот» и делает неизвестно что.
    """
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None,
    )
    было = instance._silence_to_end
    instance._adjust_silence(cut=True)

    assert instance._silence_to_end > было
    assert instance._silence_to_end == pytest.approx(было + instance.config.silence_step_up)


def test_clean_ending_shortens_the_pause(listener_module):
    """Спокойное окончание фразы позволяет ждать меньше."""
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None,
    )
    было = instance._silence_to_end
    instance._adjust_silence(cut=False)

    assert instance._silence_to_end < было


def test_reaction_to_cut_is_faster_than_creep_down(listener_module):
    """
    Вверх пауза идёт резко, вниз — медленно.

    Это не симметричная настройка: обрыв означает выполненную половину
    команды, а лишнее ожидание всего лишь неприятно. Один обрыв должен
    перекрывать несколько спокойных окончаний.
    """
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None,
    )
    assert instance.config.silence_step_up > instance.config.silence_step_down * 3


@pytest.mark.parametrize("cut,повторов", [(True, 30), (False, 60)])
def test_pause_stays_within_bounds(listener_module, cut, повторов):
    """
    Пауза не уходит за границы, сколько бы сигналов ни пришло.

    Ниже нижней границы Scott начнёт рубить обычную речь, выше верхней —
    ощутимо тормозить на каждой фразе. Подстройка не должна доводить ни до
    того, ни до другого.
    """
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None,
    )
    for _ in range(повторов):
        instance._adjust_silence(cut=cut)

    assert instance.config.min_silence_to_end <= instance._silence_to_end
    assert instance._silence_to_end <= instance.config.max_silence_to_end


def test_adaptation_can_be_switched_off(listener_module):
    """
    Подстройку можно выключить.

    Нужно для проверок и для тех, кто подобрал паузу руками: молча менять
    настройку, выставленную человеком, нельзя.
    """
    config = listener_module.ListenerConfig(adaptive_silence=False)
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None, config=config,
    )
    было = instance._silence_to_end
    instance._adjust_silence(cut=True)

    assert instance._silence_to_end == было


# ==================== На живом потоке ====================

def test_quick_resume_counts_as_cut_off(listener_module):
    """
    Речь, возобновившаяся сразу после закрытия фразы, считается обрывом.

    Так это и звучит в жизни: человек говорит «открой», задумывается на
    полсекунды и добавляет «блокнот». Scott закрывает фразу в паузе, а
    продолжение приходит как новая — по этому и видно, что оборвали.
    """
    # Пауза короткая, чтобы фраза закрылась в задумчивости говорящего.
    config = listener_module.ListenerConfig(silence_to_end=0.3)
    поток = np.concatenate([
        silence(listener_module, 0.4),
        speech(listener_module, 0.8),
        silence(listener_module, 0.45),   # задумался — но фраза уже закрыта
        speech(listener_module, 0.8),
        silence(listener_module, 0.6),
    ])

    instance = прогнать(listener_module, поток, config=config)

    assert instance.stats.cutoffs >= 1, "обрыв не замечен"
    assert instance._silence_to_end > 0.3, "пауза не удлинилась"


def test_long_silence_does_not_count_as_cut_off(listener_module):
    """
    Пара к тесту выше: настоящая тишина между фразами обрывом не считается.

    Иначе обычный разговор с паузами постоянно удлинял бы ожидание, и Scott
    делался бы всё медлительнее без всякой причины.
    """
    config = listener_module.ListenerConfig(silence_to_end=0.8)
    поток = np.concatenate([
        silence(listener_module, 0.4),
        speech(listener_module, 0.8),
        silence(listener_module, 2.6),    # закончил и молчит
        speech(listener_module, 0.8),
        silence(listener_module, 0.6),
    ])

    instance = прогнать(listener_module, поток, config=config, wait=5.0)

    assert instance.stats.cutoffs == 0, "спокойная пауза принята за обрыв"
    assert instance._silence_to_end < 0.8, "пауза не сократилась после тишины"


def test_pause_is_visible_in_diagnostics(listener_module):
    """
    Текущая пауза видна снаружи.

    Настройка, которая меняется сама, обязана быть на виду: иначе разбираться,
    почему Scott стал медлительнее, будет негде.
    """
    instance = listener_module.VoiceListener(
        transcribe=lambda a: "", handle_command=lambda t: None,
    )
    instance._adjust_silence(cut=True)

    assert instance.stats.silence_to_end == instance._silence_to_end


def test_clean_gap_counts_from_the_end_of_speech(listener_module):
    """
    Спокойное окончание отсчитывается от последнего звука, а не от закрытия фразы.

    Эти два признака легко спутать, и я спутал: к моменту закрытия пауза
    ожидания уже прошла, поэтому при пороге в две секунды и паузе 0.8
    требовалось почти три секунды настоящей тишины. Человек, говорящий слитно
    с паузами по 2.6 секунды, не получал ни одного сокращения — подстройка вниз
    просто не работала.
    """
    config = listener_module.ListenerConfig(silence_to_end=0.8, clean_gap=2.0)
    поток = [silence(listener_module, 0.4)]
    for _ in range(4):
        поток += [speech(listener_module, 0.8), silence(listener_module, 2.6)]

    instance = прогнать(listener_module, np.concatenate(поток), config=config, wait=14.0)

    # Четыре спокойных окончания подряд — пауза должна ощутимо сползти вниз.
    assert instance._silence_to_end <= 0.8 - 2 * config.silence_step_down,         f"пауза почти не сдвинулась: {instance._silence_to_end}"
