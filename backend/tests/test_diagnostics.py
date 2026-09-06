"""
Диагностика и, главное, отсутствие секретов в том, что уходит наружу.

Отчёт об ошибке пользователь отправляет постороннему человеку — разработчику,
в чат, в issue. API-ключ внутри такого архива означал бы, что утечку устроили
мы сами, своими руками и одной кнопкой. Поэтому проверок на секреты здесь
больше, чем на всё остальное вместе взятое.
"""

import json
import zipfile

import pytest

pytestmark = pytest.mark.unit

FAKE_SECRETS = {
    "GROQ_API_KEY": "gsk_ZZtestZZ1234567890abcdefghijklmnop",
    "EXECUTE_TOKEN": "совершенно-произвольный-токен-пользователя-9182",
    "GITHUB_TOKEN": "github_pat_11TESTTESTTEST1234567890abcdefgh",
}


@pytest.fixture
def diag(monkeypatch):
    import diagnostics

    for name, value in FAKE_SECRETS.items():
        monkeypatch.setenv(name, value)
    return diagnostics


# ==================== Маскировка ====================

@pytest.mark.parametrize("name", list(FAKE_SECRETS))
def test_env_secrets_are_masked(diag, name):
    """
    Значение секретной переменной вырезается из текста дословно.

    Работает даже для EXECUTE_TOKEN, который пользователь придумывает сам и
    который не подходит ни под один шаблон известных сервисов — его значение
    берётся прямо из окружения.
    """
    value = FAKE_SECRETS[name]
    masked = diag.mask_secrets(f"строка лога, в ней {value} посреди текста")
    assert value not in masked
    assert "***СКРЫТО***" in masked


@pytest.mark.parametrize("secret", [
    "sk-abcdefghijklmnopqrstuvwxyz012345",
    "gsk_abcdefghijklmnopqrstuvwxyz01234",
    "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz01234",
    "ghp_abcdefghijklmnopqrstuvwxyz012345",
    "Bearer abcdefghijklmnopqrstuvwxyz0123",
])
def test_known_key_shapes_are_masked(diag, secret):
    """Чужие ключи узнаются по форме — на случай, если в лог попал не наш."""
    assert secret not in diag.mask_secrets(f"заголовок: {secret}")


def test_ordinary_text_survives(diag):
    """Маскировка не должна съедать обычные строки — иначе логи бесполезны."""
    text = "2026-09-04 ERROR Не нашёл приложение «калькулятор»"
    assert diag.mask_secrets(text) == text


# ==================== Сведения о системе ====================

def test_system_info_hides_secret_values(diag):
    """
    В сведениях о машине секретные переменные показаны как «задано», не значением.

    Иначе отчёт раздавал бы ключи ещё до того, как дело дошло до логов.
    """
    info = diag.collect_system_info()
    settings = info["настройки"]

    for name, value in FAKE_SECRETS.items():
        assert settings.get(name) in ("задано", "пусто"), f"{name} раскрыт"
        assert value not in json.dumps(info, ensure_ascii=False)


def test_gpu_info_reports_device(diag):
    """Сведения о видеокарте отвечают на первый вопрос при жалобе на медленную работу."""
    gpu = diag.collect_gpu_info()
    assert "cuda_доступна" in gpu
    assert "torch" in gpu


# ==================== Отчёт ====================

def test_report_contains_no_secrets(diag, tmp_path, monkeypatch):
    """
    Собранный архив не содержит ни одного секрета — ни в логах, ни в описании.

    Самая важная проверка файла: всё остальное здесь про удобство, а это про
    то, что мы не устроим пользователю утечку.
    """
    monkeypatch.setattr(diag, "REPORTS_DIR", tmp_path / "reports")

    # лог, куда секреты уже попали — именно так и бывает в жизни
    log = tmp_path / "backend_errors.log"
    log.write_text(
        f"ERROR запрос отклонён\nAuthorization: Bearer {FAKE_SECRETS['GROQ_API_KEY']}\n"
        f"токен={FAKE_SECRETS['EXECUTE_TOKEN']}\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(diag.LOG_FILES, "backend_errors.log", log)

    result = diag.build_report(note="Scott не открывает калькулятор")
    assert result["success"], result

    with zipfile.ZipFile(result["path"]) as archive:
        names = archive.namelist()
        assert "system_info.json" in names
        assert "описание_проблемы.txt" in names

        for name in names:
            blob = archive.read(name).decode("utf-8", errors="replace")
            for secret in FAKE_SECRETS.values():
                assert secret not in blob, f"{name} содержит секрет"


def test_report_keeps_user_note(diag, tmp_path, monkeypatch):
    """Описание своими словами попадает в архив: обычно оно полезнее логов."""
    monkeypatch.setattr(diag, "REPORTS_DIR", tmp_path / "reports")
    result = diag.build_report(note="Звук пропал после перезапуска")

    with zipfile.ZipFile(result["path"]) as archive:
        assert "Звук пропал" in archive.read("описание_проблемы.txt").decode("utf-8")


def test_tail_log_masks_and_limits(diag, tmp_path, monkeypatch):
    """Хвост лога ограничен по длине и тоже проходит через маскировку."""
    log = tmp_path / "backend_errors.log"
    log.write_text("\n".join(f"строка {i} {FAKE_SECRETS['GROQ_API_KEY']}" for i in range(100)), encoding="utf-8")
    monkeypatch.setitem(diag.LOG_FILES, "backend_errors.log", log)

    result = diag.tail_log("backend_errors.log", lines=10)

    assert result["success"]
    assert len(result["lines"]) == 10
    assert all(FAKE_SECRETS["GROQ_API_KEY"] not in line for line in result["lines"])


def test_unknown_log_is_rejected(diag):
    """
    Читать можно только известные логи.

    Имя файла приходит от клиента, и без белого списка параметром `name` можно
    было бы попросить любой файл на диске.
    """
    assert not diag.tail_log("../../.env")["success"]

# ==================== Список ошибок ====================
#
# Раньше каждая строка с ERROR или Traceback шла в список отдельной записью, и
# человек видел шесть одинаковых «Traceback (most recent call last):» — по ним
# нельзя понять ровно ничего: сама ошибка стоит в последней строке блока.

TRACEBACK_LOG = """2026-09-06 10:00:00,000 DEBUG httpx: всё в порядке
Traceback (most recent call last):
  File "main.py", line 10, in speak
    voice.save_wav(text)
  File "silero.py", line 51, in save_wav
    raise ValueError("не найден голос eugene")
ValueError: не найден голос eugene
2026-09-06 10:00:05,000 DEBUG что-то обычное
"""


def _errors_from(tmp_path, monkeypatch, text):
    """Подсунуть diagnostics временный лог и прочитать, что он из него достал."""
    import diagnostics

    log = tmp_path / "backend_errors.log"
    log.write_text(text, encoding="utf-8")
    monkeypatch.setitem(diagnostics.LOG_FILES, "backend_errors.log", log)
    return diagnostics.recent_errors(50)


def test_traceback_collapsed_to_its_message(tmp_path, monkeypatch):
    """Трейсбек — одна запись, и в ней сама ошибка, а не слово «Traceback»."""
    errors = _errors_from(tmp_path, monkeypatch, TRACEBACK_LOG)

    assert len(errors) == 1, f"ожидалась одна запись, получено {len(errors)}"
    assert errors[0]["text"] == "ValueError: не найден голос eugene"
    assert "Traceback" not in errors[0]["text"]


def test_traceback_details_kept(tmp_path, monkeypatch):
    """
    Подробности не теряются: они нужны при разборе, просто не в списке.
    """
    errors = _errors_from(tmp_path, monkeypatch, TRACEBACK_LOG)

    assert "silero.py" in errors[0]["details"]
    assert "Traceback" in errors[0]["details"]


def test_repeated_errors_collapsed(tmp_path, monkeypatch):
    """
    Одинаковые ошибки подряд схлопываются со счётчиком.

    В живом логе один и тот же отказ повторяется десятками — списка на десять
    строк не хватит даже на одну настоящую причину.
    """
    errors = _errors_from(tmp_path, monkeypatch, TRACEBACK_LOG * 3)

    assert len(errors) == 1
    assert errors[0]["count"] == 3


def test_plain_error_lines_kept(tmp_path, monkeypatch):
    """
    Пара к тестам выше: обычные строки ERROR никуда не деваются.

    Не всякая ошибка приходит трейсбеком — многое пишется одной строкой.
    """
    errors = _errors_from(
        tmp_path, monkeypatch,
        "2026-09-06 10:00:00,000 ERROR main: не удалось открыть микрофон\n",
    )

    assert len(errors) == 1
    assert "микрофон" in errors[0]["text"]
    assert errors[0]["count"] == 1


def test_debug_noise_ignored(tmp_path, monkeypatch):
    """Отладочные строки в список не попадают — их в логе тысячи."""
    errors = _errors_from(
        tmp_path, monkeypatch,
        "2026-09-06 10:00:00,000 DEBUG comtypes: Release POINTER\n" * 5,
    )

    assert errors == []

def test_launcher_log_collected():
    """
    Журнал лаунчера попадает в отчёт.

    Именно в нём видно падения при запуске — случаи, когда человек нажимает
    ярлык и не происходит ничего. Без этого файла причина такого молчания в
    отчёт не попадала вовсе.
    """
    import diagnostics

    assert "launcher.log" in diagnostics.LOG_FILES
    assert "ScottAI" in str(diagnostics.LOG_FILES["launcher.log"])
