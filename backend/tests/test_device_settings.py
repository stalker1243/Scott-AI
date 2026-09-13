"""
Выбор устройства для распознавания и синтеза речи.

Разница между видеокартой и процессором для этого проекта принципиальная:
замеры на живом backend дали 1.0 с против 4.5 с на одной и той же фразе.
Поэтому автоматика должна брать видеокарту всегда, когда та доступна, а ручной
выбор существует как аварийный выход — на случай занятой видеокарты или
сбойного драйвера.

Отдельная забота — приоритеты. Переменная в .env сильнее кнопки в интерфейсе:
если человек прописал устройство руками, значит на то была причина, и
интерфейс не должен это молча переигрывать.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def devices(tmp_path, monkeypatch):
    """Модуль настроек с изолированным файлом конфигурации и без влияния .env."""
    import device_settings

    monkeypatch.setattr(device_settings, "CONFIG_PATH", tmp_path / "device_config.json")
    for var in device_settings.ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)
    return device_settings


def test_auto_prefers_gpu_when_available(devices, monkeypatch):
    """Автоматика берёт видеокарту: ради этого всё и затевалось."""
    monkeypatch.setattr(devices, "cuda_available", lambda: True)

    assert devices.get_choice("whisper") == "auto"
    assert devices.resolve_device("whisper") == "cuda"


def test_auto_falls_back_to_cpu(devices, monkeypatch):
    """Без видеокарты автоматика молча уходит на процессор."""
    monkeypatch.setattr(devices, "cuda_available", lambda: False)

    assert devices.resolve_device("whisper") == "cpu"


def test_manual_choice_is_saved_and_applied(devices, monkeypatch):
    """Выбор пользователя сохраняется и действует."""
    monkeypatch.setattr(devices, "cuda_available", lambda: True)

    result = devices.set_choice("whisper", "cpu")

    assert result["success"]
    assert devices.get_choice("whisper") == "cpu"
    assert devices.resolve_device("whisper") == "cpu"


def test_choice_survives_reload(devices, monkeypatch):
    """Выбор переживает перезапуск: он лежит в файле, а не в памяти процесса."""
    monkeypatch.setattr(devices, "cuda_available", lambda: True)
    devices.set_choice("silero", "cpu")

    assert devices.CONFIG_PATH.exists()
    assert devices.get_choice("silero") == "cpu"
    # whisper при этом не задет — движки хранятся раздельно
    assert devices.get_choice("whisper") == "auto"


def test_env_wins_over_interface(devices, monkeypatch):
    """
    Переменная в .env сильнее кнопки.

    И не просто сильнее: попытка сменить устройство через интерфейс отклоняется
    с объяснением, а не делает вид, что сработала. Молчаливое расхождение между
    тем, что показано в настройках, и тем, что происходит на деле, — худший из
    исходов.
    """
    monkeypatch.setattr(devices, "cuda_available", lambda: True)
    devices.set_choice("whisper", "cpu")

    monkeypatch.setenv("WHISPER_DEVICE", "cuda")

    assert devices.get_choice("whisper") == "cuda"
    assert devices.is_locked_by_env("whisper")

    result = devices.set_choice("whisper", "cpu")
    assert not result["success"]
    assert "WHISPER_DEVICE" in result["message"]


def test_cannot_choose_missing_gpu(devices, monkeypatch):
    """Видеокарту, которой нет, выбрать нельзя — с внятным отказом."""
    monkeypatch.setattr(devices, "cuda_available", lambda: False)

    result = devices.set_choice("whisper", "cuda")

    assert not result["success"]
    assert "недоступна" in result["message"]


def test_stale_gpu_choice_degrades_quietly(devices, monkeypatch):
    """
    Сохранённый выбор видеокарты на машине без неё приводит к процессору, а не к падению.

    Настройка могла переехать вместе с конфигом на другой компьютер — падать
    из-за этого при старте неправильно.
    """
    monkeypatch.setattr(devices, "cuda_available", lambda: True)
    devices.set_choice("whisper", "cuda")

    monkeypatch.setattr(devices, "cuda_available", lambda: False)
    assert devices.resolve_device("whisper") == "cpu"


def test_invalid_input_is_rejected(devices):
    """Чужой движок или несуществующее устройство отклоняются."""
    assert not devices.set_choice("whisper", "tpu")["success"]
    assert not devices.set_choice("нет-такого-движка", "cpu")["success"]


def test_switch_unloads_models(devices, monkeypatch):
    """
    Смена устройства выгружает модели.

    Без этого переключение вступало бы в силу только после перезапуска
    backend — и пользователь решил бы, что кнопка не работает.
    """
    monkeypatch.setattr(devices, "cuda_available", lambda: True)

    unloaded = []
    devices.register_reset_hook(lambda: unloaded.append(True))

    devices.set_choice("whisper", "cpu")

    assert unloaded, "модели не были выгружены при смене устройства"


def test_broken_config_falls_back_to_auto(devices):
    """Испорченный файл настроек не мешает запуску — возвращаемся к автоматике."""
    devices.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    devices.CONFIG_PATH.write_text("{это не json", encoding="utf-8")

    assert devices.get_choice("whisper") == "auto"


# ==================== Графика Apple ====================
#
# На Mac видеокарты NVIDIA нет, а считать на процессоре медленно. Metal
# доступен всем машинам с процессорами Apple — с 2020 года это все новые Mac,
# и не пользоваться им значило бы без причины отдать человеку худшую работу.
#
# Но доступен он не всем движкам: faster-whisper построен на CTranslate2,
# который Metal не поддерживает вовсе.

def test_auto_takes_apple_gpu_for_synthesis(devices, monkeypatch):
    monkeypatch.setattr(devices, "cuda_available", lambda: False)
    monkeypatch.setattr(devices, "mps_available", lambda: True)

    assert devices.resolve_device("silero") == "mps"


def test_recognition_stays_on_cpu_even_with_apple_gpu(devices, monkeypatch):
    """
    Распознавание на Metal не считается — и просить его бесполезно.

    Молчаливая попытка кончилась бы не ошибкой, а падением при загрузке модели:
    CTranslate2 о таком устройстве не знает.
    """
    monkeypatch.setattr(devices, "cuda_available", lambda: False)
    monkeypatch.setattr(devices, "mps_available", lambda: True)

    assert devices.resolve_device("whisper") == "cpu"


def test_apple_gpu_cannot_be_chosen_for_recognition(devices, monkeypatch):
    monkeypatch.setattr(devices, "mps_available", lambda: True)

    ответ = devices.set_choice("whisper", "mps")

    assert not ответ["success"]
    assert "процессор" in ответ["message"]


def test_apple_gpu_can_be_chosen_for_synthesis(devices, monkeypatch):
    monkeypatch.setattr(devices, "mps_available", lambda: True)

    assert devices.set_choice("silero", "mps")["success"]
    assert devices.resolve_device("silero") == "mps"


def test_stale_apple_choice_degrades_quietly(devices, monkeypatch):
    """
    Выбор мог достаться от другой машины: настройки переживают переустановку и
    переезд. Падать из-за этого нельзя — уходим на процессор.
    """
    monkeypatch.setattr(devices, "mps_available", lambda: True)
    devices.set_choice("silero", "mps")

    monkeypatch.setattr(devices, "mps_available", lambda: False)

    assert devices.resolve_device("silero") == "cpu"


def test_nvidia_still_wins_where_it_exists(devices, monkeypatch):
    """
    Порядок не спорный — обе видеокарты на одной машине не встречаются, — но
    записан явно: перепутать его значит на Windows тихо уйти на процессор.
    """
    monkeypatch.setattr(devices, "cuda_available", lambda: True)
    monkeypatch.setattr(devices, "mps_available", lambda: True)

    assert devices.resolve_device("silero") == "cuda"
