"""
Scott можно перебить словом.

Пока он говорит, микрофон был приглушён наглухо — иначе Scott слышит себя из
колонок и принимает собственный ответ за новую команду. На живой проверке так
и вышло: он произнёс ответ, а следующей строкой в логе появилось «Мимо», и
дальше его же фраза. Стоило бы ему сказать «Скотт» — и он заговорил бы сам с
собой без остановки.

Цена глухоты высока. Ответ длится десять секунд, и всё это время человек не
может остановить Scott, даже поняв ответ с первых слов.

Надёжность держится на трёх условиях сразу, а не на одном: громкость выше
уровня колонок, короткая фраза и слово из короткого списка. Плюс четвёртая
проверка — если услышанное встречается в том, что Scott произносит, это эхо.

Здесь проверяются все четыре, причём с обеих сторон: и что перебивание
срабатывает, и что собственный голос Scott его не вызывает.
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
    return np.random.normal(0, 0.0005, int(module.SAMPLE_RATE * seconds)).astype(np.float32)


def через_микрофон(instance, module, samples: np.ndarray) -> None:
    """
    Подать звук так, как его подаёт звуковой поток.

    Не через `feed`: тот кладёт блоки в очередь напрямую, минуя проверку
    приглушения, — и проверка приглушения на нём ничего не значила бы.
    """
    for start in range(0, len(samples), module.BLOCK_SIZE):
        block = samples[start:start + module.BLOCK_SIZE]
        if len(block) < module.BLOCK_SIZE:
            block = np.pad(block, (0, module.BLOCK_SIZE - len(block)))
        instance._on_audio(block.reshape(-1, 1), len(block), None, None)


def speech(module, seconds: float, level: float = 0.15) -> np.ndarray:
    samples = int(module.SAMPLE_RATE * seconds)
    tone = np.sin(np.linspace(0, seconds * 220 * 2 * np.pi, samples))
    return (tone * level).astype(np.float32)


def слушатель(module, услышано="стоп", speaking_text="", config=None):
    """Слушатель с заглушкой распознавания и записью перебиваний."""
    перебили = []

    instance = module.VoiceListener(
        transcribe=lambda audio: услышано,
        handle_command=lambda text: None,
        check_trigger=None,
        config=config,
        on_interrupt=lambda text: перебили.append(text),
    )
    if speaking_text:
        instance.expect_interruption(speaking_text)
    return instance, перебили


# ==================== Слово из списка ====================

@pytest.mark.parametrize("слово", ["стоп", "хватит", "замолчи", "Спасибо!", "достаточно"])
def test_stop_words_interrupt(listener_module, слово):
    """Просьба замолчать останавливает речь."""
    instance, перебили = слушатель(listener_module, speaking_text="я рассказываю про фотосинтез")
    instance._handle_interruption(слово)

    assert перебили == [слово], f"«{слово}» не перебило"
    assert instance.stats.interruptions == 1


@pytest.mark.parametrize("фраза", [
    "открой браузер",
    "а что там дальше",
    "и ещё вопрос про космос",
])
def test_other_phrases_do_not_interrupt(listener_module, фраза):
    """
    Пара к тесту выше: обычная реплика речь не обрывает.

    Услышанное во время речи — либо просьба замолчать, либо эхо. Обычной
    командой оно быть не может, и выполнять её посреди ответа нельзя.
    """
    instance, перебили = слушатель(listener_module, speaking_text="рассказываю")
    instance._handle_interruption(фраза)

    assert перебили == []
    assert instance.stats.interruptions == 0


# ==================== Своё эхо ====================

def test_own_voice_is_recognised_as_echo(listener_module):
    """
    Услышанное внутри собственной речи — эхо, а не человек.

    Главная опасность: в ответе Scott может встретиться и слово из списка.
    «Этого достаточно, чтобы растение выжило» — здесь есть «достаточно», и без
    этой проверки Scott оборвал бы себя сам.
    """
    ответ = "этого достаточно, чтобы растение выжило"
    instance, перебили = слушатель(listener_module, speaking_text=ответ)

    instance._handle_interruption("достаточно")

    assert перебили == [], "Scott оборвал сам себя"
    assert instance.stats.echo_ignored == 1


def test_same_word_interrupts_when_not_in_speech(listener_module):
    """
    Пара к тесту выше: то же слово перебивает, если Scott его не говорил.

    Иначе проверка на эхо запретила бы перебивание вообще — достаточно было бы
    одного совпадения, чтобы слово перестало работать навсегда.
    """
    instance, перебили = слушатель(
        listener_module, speaking_text="растения поглощают углекислый газ"
    )
    instance._handle_interruption("достаточно")

    assert перебили == ["достаточно"]


# ==================== Громкость ====================

def test_threshold_follows_playback_level(listener_module):
    """
    Порог считается от громкости самого Scott, а не от тишины.

    Иначе всё зависело бы от того, насколько выкручены колонки: при громком
    ответе Scott перебивал бы себя сам, при тихом — человека было бы не
    слышно.
    """
    instance, _ = слушатель(listener_module, speaking_text="говорю")

    instance._playback_level = 0.05
    порог = instance._playback_level * instance.config.interrupt_threshold

    assert порог > 0.05, "порог не поднялся выше уровня колонок"


def test_expecting_mode_lets_audio_through(listener_module):
    """
    В режиме ожидания перебивания звук доходит до разбора.

    До этого блоки отбрасывались в самом начале — приглушение было полным, и
    перебить Scott было нечем в принципе.
    """
    instance, _ = слушатель(listener_module)
    instance._suspended = True
    instance.expect_interruption("говорю")

    assert instance.is_expecting_interruption is True

    через_микрофон(instance, listener_module, speech(listener_module, 0.2))
    assert not instance._blocks.empty(), "звук не дошёл до разбора"


def test_full_suspend_still_blocks_audio(listener_module):
    """
    Пара к тесту выше: обычное приглушение по-прежнему глухое.

    Им пользуется короткая реплика «секунду» — там перебивать нечего, и
    открывать щель незачем.
    """
    instance, _ = слушатель(listener_module)
    instance.suspend()

    через_микрофон(instance, listener_module, speech(listener_module, 0.2))
    assert instance._blocks.empty()


# ==================== Выход из режима ====================

def test_stop_expecting_clears_the_queue(listener_module):
    """
    После речи очередь чистится.

    В ней осталась вторая половина собственного ответа: разбирать её теперь
    незачем, а принять за команду — вполне возможно.
    """
    instance, _ = слушатель(listener_module, speaking_text="говорю")
    instance.feed(speech(listener_module, 0.5))
    assert not instance._blocks.empty()

    instance.stop_expecting()

    assert instance._blocks.empty()
    assert instance.is_expecting_interruption is False
    assert instance._speaking_text == ""


# ==================== На живом потоке ====================

def test_loud_stop_word_interrupts_through_the_stream(listener_module):
    """
    Перебивание проходит весь путь: звук, нарезка, распознавание, остановка.

    Проверка не по частям, а целиком — громкое слово поверх тихой речи Scott.
    """
    instance, перебили = слушатель(
        listener_module, услышано="стоп", speaking_text="я рассказываю про фотосинтез"
    )
    instance._running = True
    потоки = [
        threading.Thread(target=instance._segment_loop, daemon=True),
        threading.Thread(target=instance._process_loop, daemon=True),
    ]
    for поток in потоки:
        поток.start()

    instance.feed(np.concatenate([
        speech(listener_module, 0.6, level=0.02),   # Scott говорит
        speech(listener_module, 0.5, level=0.30),   # человек перебивает
        silence(listener_module, 0.6),
    ]))
    time.sleep(2.5)
    instance._running = False

    assert перебили, "перебивание не дошло до остановки речи"


def test_state_is_visible(listener_module):
    """
    Перебивания и отвергнутое эхо видны снаружи.

    Второе важно не меньше первого: по нему видно, что щель работает узко, а
    не пропускает всё подряд.
    """
    instance, _ = слушатель(listener_module, speaking_text="говорю")
    instance._handle_interruption("стоп")
    instance._handle_interruption("открой браузер")

    состояние = instance.status()
    assert состояние["interruptions"] == 1
    assert состояние["echo_ignored"] == 1


# ==================== Разная громкость колонок ====================

def перебивание_на_потоке(module, колонки, человек, услышано="стоп",
                          текст="я рассказываю про фотосинтез"):
    """Прогнать ответ Scott с голосом человека посередине."""
    instance, перебили = слушатель(module, услышано=услышано, speaking_text=текст)
    instance._running = True
    for цель in (instance._segment_loop, instance._process_loop):
        threading.Thread(target=цель, daemon=True).start()

    куски = [speech(module, 0.8, level=колонки)]
    if человек:
        куски.append(speech(module, 0.5, level=человек))
    куски += [speech(module, 0.8, level=колонки), silence(module, 0.5)]

    instance.feed(np.concatenate(куски))
    time.sleep(2.5)
    instance._running = False
    return instance, перебили


@pytest.mark.parametrize("колонки,человек", [
    (0.02, 0.30),   # тихие колонки
    (0.10, 0.35),   # обычная громкость
    (0.20, 0.60),   # выкручены на максимум
])
def test_interruption_works_at_any_playback_volume(listener_module, колонки, человек):
    """
    Громкость колонок не должна ничего решать.

    Порог считается от неё же, поэтому перебить можно и тихого, и громкого
    Scott. Это выяснялось трудно: сначала планку задирал фоновый шум, который
    подстраивался под голос Scott, потом — переходный блок между его речью и
    голосом человека.
    """
    _, перебили = перебивание_на_потоке(listener_module, колонки, человек)
    assert перебили, f"колонки {колонки}, человек {человек} — не перебило"


@pytest.mark.parametrize("колонки", [0.02, 0.15])
def test_own_voice_never_interrupts(listener_module, колонки):
    """
    Пара к тесту выше, и она важнее.

    Собственный голос Scott не должен обрывать его самого — ни на тихой
    громкости, ни на громкой. Ровно это и случилось на живой проверке, когда
    микрофон был открыт: Scott распознал сам себя.
    """
    instance, перебили = перебивание_на_потоке(listener_module, колонки, None)
    assert перебили == [], f"на громкости {колонки} Scott оборвал сам себя"


def test_quiet_human_does_not_interrupt_loud_playback(listener_module):
    """
    Человек тише колонок перебить не может — и это честно.

    Отличить его от собственного голоса Scott в такой записи нечем. Признаться
    в этом лучше, чем обрывать ответ по любому шуму.
    """
    _, перебили = перебивание_на_потоке(listener_module, 0.20, 0.22)
    assert перебили == []


def test_noise_floor_not_polluted_by_playback(listener_module):
    """
    Фон комнаты не подстраивается под голос Scott.

    Тонкое место, и раньше его не было видно: во время речи блоки
    отбрасывались целиком. Щель для перебивания её и открыла — фон уехал
    вверх до громкости Scott, порог поднялся до 0.286 при голосе человека
    0.247, и человека стало не слышно вовсе. А после ответа завышенный фон
    сделал бы Scott глухим и к следующей команде.
    """
    instance, _ = слушатель(listener_module, speaking_text="говорю")
    instance._running = True
    threading.Thread(target=instance._segment_loop, daemon=True).start()

    было = instance._noise_floor
    instance.feed(speech(listener_module, 1.0, level=0.10))
    time.sleep(1.5)
    instance._running = False

    assert instance._noise_floor == pytest.approx(было, abs=0.002), \
        "фон комнаты впитал голос Scott"
