"""
Поиск и закрытие запущенных программ.

Написано после жалобы: Scott не мог закрыть приложение, когда его просили.
Причин было три, и каждая по отдельности ломала команду — имя процесса
угадывалось из фразы («дискорд» → `дискорд.exe`), русские названия не
переводились, а результат не проверялся вовсе: ответ «закрыл» приходил и
тогда, когда закрывать было нечего.

Настоящие процессы здесь не трогаются: список системы подменяется.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def finder():
    try:
        import process_finder
    except ImportError:
        from backend import process_finder

    return process_finder


@pytest.mark.parametrize("query,process,expected", [
    ("дискорд", "Discord.exe", True),      # транслитерация неточна: diskord/discord
    ("discord", "Discord.exe", True),
    ("хром", "chrome.exe", True),          # короткое слово — выручает список псевдонимов
    ("блокнот", "notepad.exe", True),
    ("телеграм", "Telegram.exe", True),
    ("спотифай", "Spotify.exe", True),
    ("дискорд", "Spotify.exe", False),     # чужую программу закрывать нельзя
    ("блокнот", "chrome.exe", False),
])
def test_name_matching(finder, query, process, expected):
    """Как человек называет программу и как она называется в системе."""
    try:
        from app_resolver import ALIASES, transliterate, _normalize
    except ImportError:
        from backend.app_resolver import ALIASES, transliterate, _normalize

    normalized = _normalize(query)
    variants = {normalized, transliterate(normalized)}
    if ALIASES.get(normalized):
        variants.add(ALIASES[normalized])

    score = max(finder._match_score(v, process, "") for v in variants)
    assert (score >= 0.6) is expected, f"«{query}» против {process}: {score:.2f}"


def test_empty_process_name_matches_nothing(finder):
    """
    Процесс без имени не должен совпадать ни с чем.

    Найдено на живой системе: пустое имя проходило проверку «запрос начинается
    с имени» — пустая строка начинает любую, — и «закрой хром» находило
    безымянный системный процесс.
    """
    assert finder._match_score("хром", "", "") == 0.0


def test_window_title_used(finder):
    """
    Название на экране тоже считается: его человек и произносит.

    «Яндекс Браузер» — это browser.exe, и по имени файла его не найти.
    """
    assert finder._match_score("яндекс", "browser.exe", "Яндекс Браузер") > 0.6


class FakeProcess:
    """Процесс, который можно «закрыть», ничего не трогая в системе."""

    def __init__(self, pid, name, closed, denied=False):
        self.info = {"pid": pid, "name": name}
        self._closed = closed
        self._denied = denied

    def terminate(self):
        if self._denied:
            import psutil
            raise psutil.AccessDenied(self.info["pid"])
        self._closed.append(self.info["name"])


def test_closes_every_process_of_the_app(finder, monkeypatch):
    """
    Закрываются все процессы программы, а не один.

    У браузеров и мессенджеров их десятки: убить первый попавшийся — значит
    оставить окно на месте и соврать, что закрыл.
    """
    closed = []
    processes = [
        FakeProcess(1, "Discord.exe", closed),
        FakeProcess(2, "Discord.exe", closed),
        FakeProcess(3, "Discord.exe", closed),
        FakeProcess(4, "Code.exe", closed),
    ]

    monkeypatch.setattr(finder.psutil, "process_iter", lambda *a, **kw: list(processes))
    monkeypatch.setattr(finder, "_window_titles", lambda: {})

    result = finder.close_running("дискорд")

    assert result["success"] is True
    assert closed.count("Discord.exe") == 3
    assert "Code.exe" not in closed, "закрыта посторонняя программа"


def test_missing_app_reported_honestly(finder, monkeypatch):
    """
    Если программа не запущена — так и сказано.

    Прежний код отвечал «✅ Закрыл приложение» независимо ни от чего.
    """
    monkeypatch.setattr(finder.psutil, "process_iter", lambda *a, **kw: [])
    monkeypatch.setattr(finder, "_window_titles", lambda: {})

    result = finder.close_running("дискорд")

    assert result["success"] is False
    assert "Не нашёл" in result["message"]


def test_access_denied_reported(finder, monkeypatch):
    """
    Отказ системы — это не успех.

    Процесс с большими правами Scott закрыть не может, и человек должен знать
    об этом, а не гадать, почему окно на месте.
    """
    closed = []
    processes = [FakeProcess(1, "Guard.exe", closed, denied=True)]

    monkeypatch.setattr(finder.psutil, "process_iter", lambda *a, **kw: list(processes))
    monkeypatch.setattr(finder, "_window_titles", lambda: {})

    result = finder.close_running("guard")

    assert result["success"] is False
    assert "не дала система" in result["message"]


def test_system_processes_protected(finder, monkeypatch):
    """
    Служебные процессы не закрываются по голосу.

    «Закрой проводник» не должно оставлять человека без панели задач, а
    попытка закрыть svchost — обрушить систему.
    """
    closed = []
    processes = [
        FakeProcess(1, "explorer.exe", closed),
        FakeProcess(2, "svchost.exe", closed),
    ]

    monkeypatch.setattr(finder.psutil, "process_iter", lambda *a, **kw: list(processes))
    monkeypatch.setattr(finder, "_window_titles", lambda: {})

    assert finder.find_running("проводник") == []
    assert finder.close_running("проводник")["success"] is False
    assert closed == []


def test_scott_does_not_close_itself(finder, monkeypatch):
    """Пара к предыдущему: «закрой скотт» не должно обрывать сам разговор."""
    closed = []
    processes = [FakeProcess(1, "ScottAI.exe", closed)]

    monkeypatch.setattr(finder.psutil, "process_iter", lambda *a, **kw: list(processes))
    monkeypatch.setattr(finder, "_window_titles", lambda: {})

    assert finder.find_running("scottai") == []
    assert closed == []
