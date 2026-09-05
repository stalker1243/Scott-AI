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
    # pip на месте — иначе установка остановится раньше, на нём.
    monkeypatch.setattr(boot, "ensure_pip", lambda *a, **kw: None)
    monkeypatch.setattr(
        boot, "_run_pip",
        lambda *a, **kw: (False, "нет соединения с download.pytorch.org"),
    )

    step = boot.prepare()

    assert not step.done
    assert "torch" in step.error
    assert "download.pytorch.org" in step.error, "причина потерялась по дороге"

# ==================== Прогресс установки ====================
#
# pip без терминала печатает прогресс-бар ОДНОЙ строкой, когда всё уже
# скачано, — по его выводу полосу не построить. Единственное надёжное число в
# его выводе появляется до загрузки: «Downloading torch-….whl (3.9 GB)».

@pytest.mark.parametrize("line,expected_mb", [
    ("Downloading torch-2.9.1-cp313-win_amd64.whl (110.9 MB)", 110.9),
    ("  Downloading numpy-2.1.0.whl (12.6 MB)", 12.6),
    ("Downloading torch-2.9.1+cu126-cp313-win_amd64.whl (3.9 GB)", 3.9 * 1024),
    ("Downloading tiny-1.0.whl (59 kB)", 59 / 1024),
])
def test_download_size_parsed(boot, line, expected_mb):
    """Размер файла достаётся из строки pip — на нём строится вся полоса."""
    size = boot._parse_download_size(line)
    assert size is not None, f"не разобрана строка: {line}"
    assert abs(size / 1024 ** 2 - expected_mb) < 0.1


@pytest.mark.parametrize("line", [
    "Collecting torch==2.9.1",
    "Installing collected packages: torch",
    "   ---------------------------------------- 12.6/12.6 MB 5.2 MB/s",
    "",
])
def test_not_a_size_line(boot, line):
    """
    Пара к тесту выше: прочие строки размером не считаются.

    Строка с прогресс-баром сюда попадать не должна намеренно — она приходит
    уже после загрузки и сбила бы отсчёт.
    """
    assert boot._parse_download_size(line) is None


@pytest.mark.parametrize("size,text", [
    (110.9 * 1024 ** 2, "111 МБ"),
    (3.9 * 1024 ** 3, "3.9 ГБ"),
    (512 * 1024 ** 2, "512 МБ"),
])
def test_human_readable_size(boot, size, text):
    """Объём показывается человеку, а не в байтах."""
    assert boot._human(size) == text


def test_models_counted_as_readiness(boot, monkeypatch, tmp_path):
    """
    Установленные библиотеки без моделей — ещё не готовность.

    Иначе мастер отчитается «всё готово», а первая же голосовая команда уйдёт
    качать 700 МБ, и человек будет ждать молча, не понимая, что происходит.
    """
    monkeypatch.setattr(boot.os.path, "expanduser", lambda _: str(tmp_path))
    assert boot.models_ready() is False

    (tmp_path / ".cache" / "whisper").mkdir(parents=True)
    (tmp_path / ".cache" / "whisper" / "small.pt").write_bytes(b"x")
    assert boot.models_ready() is False, "одной модели мало"

    (tmp_path / ".cache" / "torch" / "hub" / "snakers4_silero-models_master").mkdir(parents=True)
    assert boot.models_ready() is True


def test_check_mode_reports_readiness(boot, monkeypatch, capsys):
    """
    Режим --check отвечает лаунчеру, нужен ли мастер: кодом возврата и строкой
    JSON. Текст разбирать лаунчеру нечем, а код возврата однозначен.
    """
    monkeypatch.setattr(boot, "is_ready", lambda: False)
    monkeypatch.setattr(boot, "gpu_name", lambda: "NVIDIA GeForce RTX 3060")

    code = boot.main(["--check", "--json"])
    out = capsys.readouterr().out

    assert code == 2, "неготовность должна отличаться кодом возврата"
    assert '"ready": false' in out.lower()
    assert "RTX 3060" in out


def test_check_mode_when_ready(boot, monkeypatch, capsys):
    """Пара к предыдущему: на готовой машине мастер не нужен."""
    monkeypatch.setattr(boot, "is_ready", lambda: True)
    monkeypatch.setattr(boot, "gpu_name", lambda: None)

    assert boot.main(["--check", "--json"]) == 0
    assert '"ready": true' in capsys.readouterr().out.lower()


def test_json_mode_emits_progress_and_result(boot, monkeypatch, capsys):
    """
    В режиме --json каждое событие — отдельная строка JSON.

    Лаунчеру нужен не текст, а доля выполнения: без неё полосу прогресса
    нарисовать нечем.
    """
    import json

    def fake_prepare(python=None, progress=None):
        progress("Скачиваю torch: 1.2 ГБ из 3.9 ГБ", 0.3)
        progress("Модели загружены", 0.95)
        return boot.Step(title="Готово", done=True)

    monkeypatch.setattr(boot, "prepare", fake_prepare)

    assert boot.main(["--json"]) == 0

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [e["type"] for e in events] == ["progress", "progress", "done"]
    assert events[0]["fraction"] == 0.3
    assert "3.9 ГБ" in events[0]["message"]


def test_json_mode_reports_failure(boot, monkeypatch, capsys):
    """
    Сбой доходит до лаунчера как событие, а не молчанием.

    Установка идёт минутами, и оборвавшаяся сеть — обычное дело; человек
    должен увидеть, что именно не вышло.
    """
    import json

    monkeypatch.setattr(
        boot, "prepare",
        lambda python=None, progress=None: boot.Step(title="Установка", error="оборвалась сеть"),
    )

    assert boot.main(["--json"]) == 1

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert events[-1]["type"] == "error"
    assert "сеть" in events[-1]["message"]

# ==================== pip во встроенном Python ====================
#
# Найдено живой проверкой установщика: в embeddable-сборке Python нет pip
# вовсе, и мастер первого запуска на чужой машине падал на первом же шаге с
# «No module named pip». Рядом с python.exe установщик кладёт get-pip.py.

def test_pip_installed_from_bundled_script(boot, monkeypatch, tmp_path):
    """Когда pip нет, он ставится из лежащего рядом get-pip.py."""
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    (tmp_path / "get-pip.py").write_text("# заглушка", encoding="utf-8")

    calls = []
    states = iter([False, True])  # до установки нет, после — есть

    monkeypatch.setattr(boot, "has_pip", lambda _: next(states))
    monkeypatch.setattr(
        boot.subprocess, "run",
        lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    assert boot.ensure_pip(str(python)) is None
    assert any("get-pip.py" in str(part) for part in calls[0]), "get-pip.py не запускался"


def test_missing_get_pip_reported_clearly(boot, monkeypatch, tmp_path):
    """
    Пара к тесту выше: если и pip нет, и get-pip.py рядом не лежит, человек
    должен увидеть, чего именно не хватает, а не «No module named pip» из
    недр вывода pip.
    """
    python = tmp_path / "python.exe"
    python.write_bytes(b"")

    monkeypatch.setattr(boot, "has_pip", lambda _: False)

    error = boot.ensure_pip(str(python))
    assert error is not None
    assert "get-pip.py" in error


def test_existing_pip_left_alone(boot, monkeypatch, tmp_path):
    """На обычном Python с pip ничего не запускается — ставить нечего."""
    monkeypatch.setattr(boot, "has_pip", lambda _: True)
    monkeypatch.setattr(
        boot.subprocess, "run",
        lambda *a, **kw: pytest.fail("pip уже есть, а установка всё равно запустилась"),
    )

    assert boot.ensure_pip("python") is None


def test_install_stops_without_pip(boot, monkeypatch):
    """
    Установка зависимостей не начинается, пока нет pip.

    Иначе первым же сообщением человек получал бы «не удалось поставить
    torch» — с настоящей причиной, спрятанной внутри.
    """
    monkeypatch.setattr(boot, "ensure_pip", lambda *a, **kw: "нет pip и нет get-pip.py")
    monkeypatch.setattr(
        boot, "_run_pip",
        lambda *a, **kw: pytest.fail("pip запустили, хотя его нет"),
    )

    step = boot.install_dependencies("python")
    assert not step.done
    assert "get-pip" in step.error
