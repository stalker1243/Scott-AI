"""
Проверки на живом backend: то, что нельзя увидеть по одному только коду.

Требуют запущенного сервера (`cd backend && python main.py`); если его нет,
тесты пропускаются, а не падают — на машине без поднятого backend это не
поломка, а просто нечего проверять.

Запуск только этих:      python -m pytest -m integration
Запуск всего, кроме них: python -m pytest -m "not integration"
"""

import io
import wave

import pytest
import requests

pytestmark = pytest.mark.integration

BASE = "http://127.0.0.1:8000"
TIMEOUT = 90


@pytest.fixture(scope="module", autouse=True)
def require_backend():
    try:
        requests.get(f"{BASE}/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend не запущен на порту 8000")


def test_health_reports_online():
    data = requests.get(f"{BASE}/health", timeout=TIMEOUT).json()
    assert data["status"] == "online"


def test_synthesis_returns_real_audio():
    """
    Синтез отдаёт настоящий звук, а не пустышку.

    Проверяется длительность: движок может «успешно» вернуть файл на ноль
    секунд, и по коду ответа это неотличимо от нормальной работы. Фраза взята
    редкая, чтобы не попасть в кэш audio_cache и заставить движок отработать.
    """
    text = "Проверка синтеза номер восемьсот тринадцать"
    response = requests.post(f"{BASE}/text_to_speech", json={"text": text}, timeout=TIMEOUT)
    assert response.status_code == 200

    audio = response.content
    assert len(audio) > 1000, "Аудио подозрительно маленькое"

    with wave.open(io.BytesIO(audio)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds > 0.5, f"Речь длиной {seconds:.2f} с — движок отдал тишину"


def test_voice_round_trip():
    """
    Сквозная проверка голосового цикла: Scott произносит фразу и сам её узнаёт.

    Это единственный тест, где синтез и распознавание работают вместе, — то
    есть ровно то, что происходит при живом разговоре. Сверяются слова, а не
    строка целиком: Whisper вправе иначе расставить знаки препинания и
    заглавные буквы, и придираться к этому смысла нет.
    """
    phrase = "Скотт, открой калькулятор и покажи загрузку процессора"

    spoken = requests.post(f"{BASE}/text_to_speech", json={"text": phrase}, timeout=TIMEOUT)
    assert spoken.status_code == 200

    recognised = requests.post(
        f"{BASE}/speech_to_text",
        files={"file": ("phrase.wav", spoken.content, "audio/wav")},
        timeout=TIMEOUT,
    )
    assert recognised.status_code == 200, recognised.text

    heard = recognised.json()["text"]
    expected_words = [w.strip(",.!?").lower() for w in phrase.split()]
    heard_words = [w.strip(",.!?").lower() for w in heard.split()]
    assert heard_words == expected_words, f"Услышано иначе: {heard!r}"


def test_command_answers():
    """Ассистент отвечает на обращение — значит цепочка разбора команды жива."""
    data = requests.post(f"{BASE}/command", json={"text": "привет"}, timeout=TIMEOUT).json()
    assert data.get("response"), f"Пустой ответ: {data}"


def test_dangerous_endpoint_rejects_anonymous():
    """
    Без токена опасная операция не выполняется.

    Парная к статической проверке зависимостей: там видно, что защита
    объявлена, здесь — что она действительно срабатывает.
    """
    response = requests.post(
        f"{BASE}/extended/powershell",
        json={"command": "Write-Output проверка"},
        timeout=TIMEOUT,
    )
    assert response.status_code in (401, 403), f"Ожидался отказ, получено {response.status_code}"
