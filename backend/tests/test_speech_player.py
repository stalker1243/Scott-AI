"""
Очередь воспроизведения речи.

Написано после жалобы с живого созвона: если задать Scott несколько вопросов
подряд, ответы начинали звучать одновременно — «набор случайных слов, сотни за
секунду». Причина была в устройстве: каждый ответ проигрывался сам по себе, в
своём потоке, и о существовании других не знал.

Звук здесь не воспроизводится: проверяется сама очередь — что фразы идут по
одной, что обрыв работает и что устаревшие ответы не звучат вовсе.
"""

import threading
import time

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def player(monkeypatch):
    """
    Проигрыватель с подменённым выводом звука.

    Вместо динамика — список сыгранного и небольшая задержка: без неё
    невозможно поймать наложение, ради которого всё и затевалось.
    """
    try:
        import speech_player
    except ImportError:
        from backend import speech_player

    monkeypatch.setattr(speech_player, "PLAYBACK_AVAILABLE", True)

    played = []
    playing_now = []
    overlaps = []

    def fake_play(self, path):
        # Если в этот момент уже что-то играет — это ровно тот дефект,
        # который чинили.
        if playing_now:
            overlaps.append(path)
        playing_now.append(path)
        time.sleep(0.05)
        playing_now.remove(path)
        played.append(path)

    monkeypatch.setattr(speech_player.SpeechPlayer, "_play_file", fake_play)

    instance = speech_player.SpeechPlayer()
    instance.played = played
    instance.overlaps = overlaps

    yield instance

    # Поток проигрывателя — демон и живёт дальше сам по себе. Если его не
    # остановить, он продолжит разбирать очередь уже во время следующего теста
    # и допишет туда чужие фразы: первая версия этих проверок так и падала.
    instance.stop()
    instance._queue.put(None)


def test_phrases_play_one_after_another(player):
    """
    Три фразы, поставленные разом, звучат по очереди.

    Это главное: раньше они начинали звучать одновременно.
    """
    for name in ("a.wav", "b.wav", "c.wav"):
        player.play(name)

    deadline = time.time() + 5
    while len(player.played) < 3 and time.time() < deadline:
        time.sleep(0.02)

    assert player.played == ["a.wav", "b.wav", "c.wav"]
    assert player.overlaps == [], f"фразы наложились: {player.overlaps}"


def test_play_returns_immediately(player):
    """
    Постановка в очередь не блокирует вызывающего.

    Обработчик команды не должен ждать, пока Scott договорит: пока он ждёт,
    backend не отвечает ни на что другое.
    """
    start = time.time()
    for _ in range(5):
        player.play("x.wav")
    assert time.time() - start < 0.1


def test_stop_drops_pending(player):
    """
    Обрыв выбрасывает всё, что не успело зазвучать.

    Человек задал новый вопрос — старые ответы ему уже не нужны.
    """
    for index in range(5):
        player.play(f"{index}.wav")

    time.sleep(0.06)
    player.stop()
    time.sleep(0.3)

    assert len(player.played) < 5, "после обрыва доиграли все фразы"


def test_waiting_caller_released_on_stop(player):
    """
    Тот, кто ждал окончания фразы, не должен зависнуть после обрыва.

    Слушатель приостанавливает микрофон на время речи и ждёт её конца; если
    обрыв оставит его ждать, Scott оглохнет до истечения таймаута.
    """
    released = threading.Event()

    def waiter():
        player.play_and_wait("long.wav", timeout=5)
        released.set()

    thread = threading.Thread(target=waiter, daemon=True)
    thread.start()
    time.sleep(0.02)

    player.stop()

    assert released.wait(2), "ожидающий не был отпущен после обрыва"


def test_stale_phrases_never_play(player):
    """
    Фразы, поставленные до обрыва, не звучат и потом.

    Иначе оборванный ответ всплывал бы посреди следующего разговора.
    """
    player.play("old-1.wav")
    player.play("old-2.wav")
    player.stop()

    player.play("fresh.wav")

    deadline = time.time() + 3
    while "fresh.wav" not in player.played and time.time() < deadline:
        time.sleep(0.02)

    assert "fresh.wav" in player.played
    assert "old-2.wav" not in player.played
