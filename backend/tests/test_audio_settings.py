"""
Звук: громкость, устройства и тихий режим.

Тихий режим — не косметика. Просьба «помолчи» нужна ночью, в наушниках у
соседа по комнате, на созвоне; до сих пор единственным способом заткнуть Scott
было выключить весь backend. Поэтому здесь проверяется не только то, что
настройка сохраняется, но и что она действительно доходит до звука — включая
запасной путь на машинах без sounddevice.

Настройки при этом обязаны переживать перезапуск: первая же жалоба живого
пользователя была именно о том, что всё сбрасывается при закрытии программы.
"""

import json

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def audio(tmp_path, monkeypatch):
    """Настройки в своей папке: настоящий файл пользователя трогать нельзя."""
    try:
        import audio_settings as module
    except ImportError:
        from backend import audio_settings as module

    monkeypatch.setattr(module, "CONFIG_PATH", tmp_path / "audio_config.json")
    return module


# ==================== Хранение ====================

def test_defaults_when_nothing_saved(audio):
    """Без файла настроек Scott говорит в полный голос через системный выход."""
    settings = audio.get_settings()
    assert settings["volume"] == 100
    assert settings["quiet"] is False
    assert settings["output_device"] == ""


def test_settings_survive_restart(audio):
    """
    Настройки читаются с диска, а не живут в памяти процесса.

    Живая жалоба первого пользователя: после закрытия программы всё
    сбрасывалось. Выбирать наушники каждое утро заново — ровно та мелочь, из-за
    которой перестают пользоваться.
    """
    audio.update(volume=40, quiet=True, output_device="Наушники")

    stored = json.loads(audio.CONFIG_PATH.read_text(encoding="utf-8"))
    assert stored["volume"] == 40
    assert stored["quiet"] is True
    assert stored["output_device"] == "Наушники"


def test_partial_update_keeps_the_rest(audio):
    """Меняя громкость, человек не должен терять выбранное устройство."""
    audio.update(output_device="Наушники", volume=50)
    audio.update(volume=80)

    settings = audio.get_settings()
    assert settings["volume"] == 80
    assert settings["output_device"] == "Наушники"


def test_broken_file_does_not_silence_scott(audio):
    """
    Испорченный файл настроек — не повод замолчать или упасть при старте.

    Худший исход тут не ошибка, а немой ассистент без объяснения причины.
    """
    audio.CONFIG_PATH.write_text("{ это не json", encoding="utf-8")

    settings = audio.get_settings()
    assert settings["volume"] == 100
    assert settings["quiet"] is False


# ==================== Границы громкости ====================

@pytest.mark.parametrize("given,expected", [
    (999, 100),
    (-5, 0),
    ("70", 70),
    (None, 100),
    ("громко", 100),
])
def test_volume_stays_in_range(audio, given, expected):
    """
    Громкость выше сотни не делает звук громче — она делает его хрипом.

    Умножение волны выводит значения за отрезок, который принимает звуковая
    карта, и края срезаются. Поэтому предел жёсткий, что бы ни лежало в файле
    и что бы ни прислал интерфейс.
    """
    audio.CONFIG_PATH.write_text(
        json.dumps({"volume": given}), encoding="utf-8"
    )
    assert audio.get_settings()["volume"] == expected


def test_volume_becomes_multiplier(audio):
    """Проигрыватель ждёт множитель, а человек думает в процентах."""
    audio.update(volume=50)
    assert audio.get_volume() == 0.5


# ==================== Устройства по имени ====================

def test_missing_device_falls_back_to_system(audio):
    """
    Исчезнувшее устройство означает системное, а не молчание.

    Наушники отключают, и это обычное дело: Scott должен продолжить говорить
    через динамики, а не замолчать до похода в настройки.
    """
    audio.update(output_device="Устройства с таким именем нет")
    assert audio.get_output_device() is None


def test_device_remembered_by_name_not_number(audio):
    """
    Запоминается имя устройства, а не его номер.

    Номера в системе не постоянны: достаточно включить телевизор по HDMI, и
    то, что вчера было третьим устройством, сегодня станет четвёртым — Scott
    заговорил бы не туда.
    """
    audio.update(output_device="Наушники")
    stored = json.loads(audio.CONFIG_PATH.read_text(encoding="utf-8"))
    assert stored["output_device"] == "Наушники"
    assert "index" not in stored


# ==================== Тихий режим ====================

def test_quiet_mode_toggles(audio):
    assert audio.set_quiet(True)["quiet"] is True
    assert audio.is_quiet() is True
    assert audio.set_quiet(False)["quiet"] is False
    assert audio.is_quiet() is False


def test_quiet_skips_playback(audio, monkeypatch):
    """
    В тихом режиме звук не доходит до звуковой карты.

    Проверяется сам проигрыватель, а не намерение: именно он — то единственное
    место, через которое проходит вся речь Scott.
    """
    try:
        import speech_player as player_module
    except ImportError:
        from backend import speech_player as player_module

    monkeypatch.setattr(player_module, "PLAYBACK_AVAILABLE", True)
    monkeypatch.setattr(player_module, "_muted", lambda: True)

    played = []
    player = player_module.SpeechPlayer()
    monkeypatch.setattr(player, "_play_file", lambda path: played.append(path))

    player.play_and_wait("phrase.wav", timeout=1.0)
    assert played == [], "в тихом режиме что-то прозвучало"


def test_quiet_does_not_block_the_listener(audio, monkeypatch):
    """
    Ожидание речи в тихом режиме заканчивается сразу.

    На этом ожидании слушатель держит микрофон приостановленным, чтобы Scott не
    услышал сам себя. Молчание с ожиданием обернулось бы глухотой на пустом
    месте — на две минуты, до истечения таймаута.
    """
    import time

    try:
        import speech_player as player_module
    except ImportError:
        from backend import speech_player as player_module

    monkeypatch.setattr(player_module, "PLAYBACK_AVAILABLE", True)
    monkeypatch.setattr(player_module, "_muted", lambda: True)

    started = time.time()
    player_module.SpeechPlayer().play_and_wait("phrase.wav", timeout=30.0)
    assert time.time() - started < 1.0, "ожидание не оборвалось"


def test_preview_ignores_quiet_mode(audio, monkeypatch):
    """
    Кнопка «Прослушать» в настройках звучит всегда.

    Человек нажал её сам и ждёт звука именно сейчас: молчание в ответ он
    примет за поломку, а не за соблюдение тихого режима.
    """
    try:
        import speech_player as player_module
    except ImportError:
        from backend import speech_player as player_module

    monkeypatch.setattr(player_module, "PLAYBACK_AVAILABLE", True)
    monkeypatch.setattr(player_module, "_muted", lambda: True)

    played = []
    player = player_module.SpeechPlayer()
    monkeypatch.setattr(player, "_play_file", lambda path: played.append(path))

    player.play_and_wait("preview.wav", timeout=5.0, force=True)
    assert played == ["preview.wav"]

# ==================== Список устройств ====================

def test_truncated_duplicates_are_dropped(audio):
    """
    Одно устройство не должно стоять в списке дважды.

    Живой список на машине разработчика — двенадцать строк там, где физически
    пять устройств: Windows показывает каждое через несколько звуковых
    подсистем, и старейшая (MME) обрезает имя до 31 знака. Человек видит два
    одинаковых пункта и выбирает, как правило, первый — обрезанный.
    """
    devices = [
        {"index": 0, "name": "Динамики (High Definition Audio", "channels": 2, "default": False},
        {"index": 5, "name": "Динамики (High Definition Audio Device)", "channels": 2, "default": False},
        {"index": 7, "name": "Line Out (Wave Speaker)", "channels": 2, "default": False},
    ]

    kept = [d["name"] for d in audio._drop_truncated(devices)]
    assert kept == ["Динамики (High Definition Audio Device)", "Line Out (Wave Speaker)"]


def test_default_mark_moves_to_full_name(audio):
    """
    Пометка «по умолчанию» не теряется вместе с обрезанной строкой.

    Системным Windows называет как раз её — и, отбросив строку молча, мы
    оставили бы список вовсе без отметки о том, что звучит сейчас.
    """
    devices = [
        {"index": 0, "name": "Динамики (High Definition Audio", "channels": 2, "default": True},
        {"index": 5, "name": "Динамики (High Definition Audio Device)", "channels": 2, "default": False},
    ]

    kept = audio._drop_truncated(devices)
    assert len(kept) == 1
    assert kept[0]["default"] is True


def test_different_devices_are_kept(audio):
    """
    Пара к тестам выше: разные устройства схлопывать нельзя.

    Правило смотрит на начало строки, и легко было бы потерять настоящее
    устройство с похожим именем.
    """
    devices = [
        {"index": 0, "name": "Микрофон (Headphones)", "channels": 1, "default": False},
        {"index": 1, "name": "Микрофон (Webcam)", "channels": 1, "default": False},
    ]

    assert len(audio._drop_truncated(devices)) == 2
