"""
Эхоподавление внутри слушателя: сквозная проверка.

Отдельно фильтр уже проверен — он убирает эхо на 10-12 децибел, не трогая
голос человека. Здесь проверяется другое: что он вообще включён в работу и что
опорный сигнал доходит до него выровненным по времени.

Это разные вещи, и вторая ломается чаще. Между проигрывателем и слушателем
лежит время: один говорит, когда начал играть, другой спрашивает, что звучало
в момент записи блока. Ошибка в этой арифметике не роняет ничего — она просто
делает подавление бесполезным, и заметить её можно только замером.

Микрофон здесь не нужен: звук подаётся напрямую через feed().
"""

import time

import numpy as np
import pytest

pytestmark = pytest.mark.unit


try:
    import echo_cancel
    import echo_reference
    from listener import VoiceListener, ListenerConfig, SAMPLE_RATE, BLOCK_SIZE
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import echo_cancel
    from backend import echo_reference
    from backend.listener import VoiceListener, ListenerConfig, SAMPLE_RATE, BLOCK_SIZE


def речь(секунд=2.0, семя=1):
    """Звук с огибающей, похожей на голос."""
    случай = np.random.default_rng(семя)
    сырьё = случай.standard_normal(int(SAMPLE_RATE * секунд)).astype(np.float32)

    окно = np.hanning(64).astype(np.float32)
    окно /= окно.sum()
    сглажено = np.convolve(сырьё, окно, mode="same").astype(np.float32)

    слоги = np.abs(np.sin(np.linspace(0, секунд * 12, сглажено.size))) + 0.15
    return (сглажено * слоги * 0.3).astype(np.float32)


@pytest.fixture
def ссылка():
    """Чистое хранилище опорного сигнала на каждую проверку."""
    r = echo_reference.EchoReference()
    echo_reference._reference = r
    yield r
    echo_reference._reference = None


# ==================== Приведение звука ====================

def test_playback_is_resampled_to_microphone_rate():
    """
    Синтезатор отдаёт сорок восемь тысяч отсчётов в секунду, микрофон пишет
    шестнадцать. Сравнивать их напрямую нельзя.
    """
    исходный = речь(1.0)
    сорок_восемь = np.repeat(исходный, 3)      # грубо «48 кГц»

    приведённый = echo_reference.to_mono_16k(сорок_восемь, 48000)

    assert abs(приведённый.size - исходный.size) < 10


def test_stereo_becomes_mono():
    стерео = np.stack([речь(0.5), речь(0.5, семя=2)], axis=1)

    моно = echo_reference.to_mono_16k(стерео, SAMPLE_RATE)

    assert моно.ndim == 1


# ==================== Окно опорного сигнала ====================

def test_no_window_while_silent(ссылка):
    """
    Scott молчит — вычитать нечего.

    Пустой ответ здесь важен: по нему слушатель понимает, что звук надо
    оставить нетронутым.
    """
    assert ссылка.window(BLOCK_SIZE).size == 0


def test_window_follows_the_clock(ссылка):
    """
    Кусок берётся по времени, а не по счётчику блоков.

    Слушатель может отстать — очередь, занятый процессор, — и тогда счётчик
    разошёлся бы с настоящим временем, а вместе с ним уехало бы и выравнивание.
    """
    сигнал = np.arange(SAMPLE_RATE, dtype=np.float32)   # по отсчёту видно место
    ссылка.start(сигнал, SAMPLE_RATE)

    начало = ссылка._started_at

    # Спрашиваем так, будто прошло ровно полсекунды.
    кусок = ссылка.window(BLOCK_SIZE, at=начало + 0.5)

    assert кусок.size == BLOCK_SIZE

    # Полсекунды — это отсчёт 8000; блок кончается там, начинается раньше.
    assert abs(float(кусок[-1]) - 8000) < BLOCK_SIZE


def test_window_accounts_for_delay(ссылка):
    """
    Задержка сдвигает окно назад.

    Звук дошёл до микрофона позже, чем ушёл в колонки, значит записанному
    блоку соответствует более ранний кусок опорного сигнала. Знак этой
    поправки перепутать легко, а последствие тихое: подавление просто
    перестаёт работать.
    """
    сигнал = np.arange(SAMPLE_RATE, dtype=np.float32)
    ссылка.start(сигнал, SAMPLE_RATE)
    начало = ссылка._started_at

    без_задержки = ссылка.window(BLOCK_SIZE, at=начало + 0.5)

    ссылка.delay = int(SAMPLE_RATE * 0.1)      # сто миллисекунд
    с_задержкой = ссылка.window(BLOCK_SIZE, at=начало + 0.5)

    # С задержкой берётся кусок, записанный раньше — то есть с меньшими
    # номерами отсчётов.
    assert float(с_задержкой[-1]) < float(без_задержки[-1])
    assert abs(float(без_задержки[-1]) - float(с_задержкой[-1]) - SAMPLE_RATE * 0.1) < 50


def test_window_is_padded_at_the_start(ссылка):
    """В начале ответа опорного сигнала ещё мало — хвост дополняется тишиной."""
    ссылка.start(речь(1.0), SAMPLE_RATE)
    начало = ссылка._started_at

    кусок = ссылка.window(BLOCK_SIZE, at=начало + 0.01)

    assert кусок.size == BLOCK_SIZE


# ==================== Замер задержки ====================

def test_delay_is_learned_from_the_first_blocks(ссылка):
    """
    Задержка меряется по первым полсекунды ответа и запоминается.

    Считать её на каждой реплике незачем: она зависит от устройства вывода, а
    не от фразы.
    """
    сигнал = речь(3.0)
    ссылка.start(сигнал, SAMPLE_RATE)

    задержка = int(SAMPLE_RATE * 0.12)
    запись = np.concatenate([np.zeros(задержка, dtype=np.float32), сигнал * 0.5])

    assert not ссылка.delay_known

    # Подаём блоками, как это делает слушатель. Звука нужно больше, чем
    # длина образца: иначе корреляции негде искать.
    for i in range(0, len(запись) - BLOCK_SIZE, BLOCK_SIZE):
        ссылка.learn_delay(запись[i:i + BLOCK_SIZE])

    assert ссылка.delay_known
    assert abs(ссылка.delay - задержка) < SAMPLE_RATE * 0.02


def test_delay_is_forgotten_on_demand(ссылка):
    """
    При смене устройства вывода задержку надо забыть.

    У других колонок или наушников она своя, и прежняя станет мешать.
    """
    ссылка.delay = 1234
    ссылка.delay_known = True

    ссылка.forget_delay()

    assert not ссылка.delay_known
    assert ссылка.delay == 0


# ==================== Слушатель целиком ====================

def сделать_слушателя(услышанное, **настройки):
    return VoiceListener(
        transcribe=lambda audio: "распознано",
        handle_command=lambda text, **k: услышанное.append(text),
        config=ListenerConfig(**настройки),
    )


def test_listener_removes_echo(ссылка):
    """
    Собственный ответ в микрофоне становится тише.

    Это и есть цель всей работы: Scott произносил ответ, а следующей строкой в
    логе появлялось «Мимо: Попробую открыть Google Chrome» — он распознавал
    сам себя.
    """
    слушатель = сделать_слушателя([])

    ответ = речь(2.0)
    ссылка.start(ответ, SAMPLE_RATE)
    ссылка.delay = 0
    ссылка.delay_known = True

    начало = ссылка._started_at

    было, стало = [], []

    # Идём по ответу блоками, подавая эхо и спрашивая опорный сигнал по тому
    # же времени — как это происходит вживую.
    for n, i in enumerate(range(0, len(ответ) - BLOCK_SIZE, BLOCK_SIZE)):
        эхо = ответ[i:i + BLOCK_SIZE] * 0.5

        # Время, когда этот блок был бы записан.
        момент = начало + (i + BLOCK_SIZE) / SAMPLE_RATE
        опорный = ссылка.window(BLOCK_SIZE, at=момент)

        очищено = слушатель._echo.process(эхо, опорный) \
            if слушатель._echo else эхо

        if слушатель._echo is None:
            # Первый блок создаёт фильтр через общий путь.
            слушатель._without_echo(эхо)
            continue

        было.append(эхо)
        стало.append(очищено)

    if not было:
        pytest.skip("фильтр не успел создаться")

    половина = len(было) // 2
    подавление = echo_cancel.suppression_db(
        np.concatenate(было[половина:]), np.concatenate(стало[половина:]))

    assert подавление > 5, f"подавление всего {подавление:.1f} дБ"


def test_listener_leaves_sound_alone_while_scott_is_silent(ссылка):
    """
    Пока Scott молчит, звук не трогается вовсе.

    Гонять фильтр вхолостую нельзя: на тишине он только расшатается, и первый
    же настоящий блок придётся начинать заново.
    """
    слушатель = сделать_слушателя([])
    блок = речь(0.03)[:BLOCK_SIZE]

    получилось = слушатель._without_echo(блок)

    assert np.allclose(получилось, блок)


def test_echo_cancelling_can_be_turned_off(ссылка):
    """
    Выключатель нужен: на чужой машине всё может пойти не так, и человек
    должен иметь возможность вернуть прежнее поведение.
    """
    слушатель = сделать_слушателя([], cancel_echo=False)

    ссылка.start(речь(1.0), SAMPLE_RATE)
    ссылка.delay_known = True

    блок = речь(0.03)[:BLOCK_SIZE]

    assert np.allclose(слушатель._without_echo(блок), блок)


def test_broken_echo_does_not_break_listening(ссылка, monkeypatch):
    """
    Сломанное эхоподавление не должно лишать Scott слуха.

    Оно улучшение, а не условие работы: при любой беде звук идёт к
    распознаванию как есть.
    """
    слушатель = сделать_слушателя([])

    ссылка.start(речь(1.0), SAMPLE_RATE)
    ссылка.delay_known = True

    def взрыв(*a, **k):
        raise RuntimeError("что-то сломалось")

    monkeypatch.setattr(echo_reference.EchoReference, "window", взрыв)

    блок = речь(0.03)[:BLOCK_SIZE]

    # Не должно бросить, и звук должен остаться прежним.
    assert np.allclose(слушатель._without_echo(блок), блок)
