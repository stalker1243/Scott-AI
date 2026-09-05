"""
Подготовка машины к работе Scott.

Главная проверка здесь одна: правильно ли выбирается сборка torch. Ошибка в
этом месте не ломает установку — она делает Scott впятеро медленнее без
единого сообщения. Обычная команда `pip install torch` ставит сборку для
процессора, молча игнорируя видеокарту; именно так когда-то Whisper молотил
6.6 секунды на фразу, пока RTX 3060 простаивала.

Ничего не устанавливается: подменяется наличие nvidia-smi и проверяется, что
именно Scott собирается запустить.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def boot():
    import bootstrap

    return bootstrap


def with_gpu(boot, monkeypatch, present: bool):
    """Притвориться машиной с видеокартой или без неё."""
    monkeypatch.setattr(boot, "has_nvidia_gpu", lambda: present)
    monkeypatch.setattr(boot, "gpu_name", lambda: "NVIDIA GeForce RTX 3060" if present else None)


def test_gpu_machine_gets_cuda_build(boot, monkeypatch):
    """
    На машине с видеокартой ставится сборка с CUDA.

    Её нет на обычном PyPI, поэтому обязателен отдельный индекс — без него pip
    молча поставит версию для процессора.
    """
    with_gpu(boot, monkeypatch, True)

    args, explanation = boot.torch_requirement()

    assert "--index-url" in args
    assert boot.CUDA_INDEX in args
    assert any("+cu" in a for a in args), "поставится сборка без поддержки видеокарты"
    assert "RTX 3060" in explanation


def test_cpu_machine_gets_plain_build(boot, monkeypatch):
    """Без видеокарты ставится обычная сборка — и человеку говорят, чем это обернётся."""
    with_gpu(boot, monkeypatch, False)

    args, explanation = boot.torch_requirement()

    assert "--index-url" not in args
    assert args == [boot.TORCH_CPU]
    assert "процессор" in explanation.lower()


def test_explanation_is_honest_about_speed(boot, monkeypatch):
    """
    Человеку объясняют разницу до установки, а не после.

    Четыре гигабайта загрузки — это выбор, который стоит сделать осознанно;
    равно как и согласие на шесть секунд ожидания каждой фразы.
    """
    with_gpu(boot, monkeypatch, True)
    _, gpu_text = boot.torch_requirement()

    with_gpu(boot, monkeypatch, False)
    _, cpu_text = boot.torch_requirement()

    assert "гб" in gpu_text.lower(), "не сказано, сколько весит загрузка"
    assert "секунд" in cpu_text.lower(), "не сказано, чем обернётся работа на процессоре"


def test_gpu_detection_without_nvidia_smi(boot, monkeypatch):
    """
    Без nvidia-smi считаем, что видеокарты нет.

    Спросить у torch нельзя — его ещё не установили, и вся суть в том, чтобы
    выбрать правильную сборку ДО установки. nvidia-smi ставится вместе с
    драйвером, поэтому его наличие — надёжный признак живой карты.
    """
    monkeypatch.setattr(boot.shutil, "which", lambda name: None)

    assert boot.has_nvidia_gpu() is False


def test_ready_check_requires_all_pieces(boot, monkeypatch):
    """
    Готовность проверяется по всем трём частям сразу.

    Установка могла оборваться посередине: torch скачался, а whisper нет —
    и тогда подготовку нужно продолжить, а не считать законченной.
    """
    calls = []

    class FakeResult:
        returncode = 1
        stdout = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeResult()

    monkeypatch.setattr(boot.subprocess, "run", fake_run)

    assert boot.is_ready("python") is False
    assert "import torch, whisper, fastapi" in " ".join(calls[0])


def test_prepare_skips_when_ready(boot, monkeypatch):
    """Если всё стоит, подготовка не повторяется: качать 4 ГБ заново незачем."""
    monkeypatch.setattr(boot, "is_ready", lambda python=None: True)

    messages = []
    step = boot.prepare(progress=lambda msg, frac: messages.append(msg))

    assert step.done
    assert any("уже установлено" in m for m in messages)


def test_failure_is_reported_not_swallowed(boot, monkeypatch):
    """
    Неудачная установка возвращает причину.

    Молчаливый провал здесь означал бы, что человек запускает Scott и получает
    непонятную ошибку вместо «не удалось скачать torch, проверьте интернет».
    """
    monkeypatch.setattr(boot, "is_ready", lambda python=None: False)

    class FakeResult:
        returncode = 1
        stderr = "нет соединения с download.pytorch.org"
        stdout = ""

    monkeypatch.setattr(boot.subprocess, "run", lambda cmd, **kw: FakeResult())

    step = boot.prepare()

    assert not step.done
    assert "torch" in step.error
