"""
Проверка обновлений через GitHub Releases.

До этого она была фикцией: эндпоинт сравнивал версию из локального VERSION.json
с ней же самой и всегда отвечал «обновлений нет», никуда не обращаясь. Поэтому
здесь проверяется в первую очередь то, что проверка действительно ходит наружу
и честно отчитывается, когда сходить не удалось.

Сеть в тестах не трогается: ответ GitHub подменяется.
"""

import json
import time

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def upd():
    try:
        import updates
    except ImportError:
        from backend import updates

    return updates


@pytest.fixture
def no_cache(upd, tmp_path, monkeypatch):
    """Увести кэш во временную папку, чтобы тесты не мешали друг другу."""
    monkeypatch.setattr(upd, "CACHE_FILE", tmp_path / "update_check.json")
    return tmp_path / "update_check.json"


# ==================== Сравнение версий ====================

@pytest.mark.parametrize("candidate,current,expected", [
    ("1.0.1", "1.0.0", True),
    ("v1.1.0", "1.0.0", True),
    ("2.0.0", "1.9.9", True),
    ("1.10.0", "1.9.0", True),      # числами, а не строками: «10» больше «9»
    ("1.0.0", "1.0.0", False),
    ("0.9.9", "1.0.0", False),
    ("1.0", "1.0.0", False),        # «1.0» и «1.0.0» — одно и то же
    ("1.0.0", "1.0.0-beta", True),  # выпуск новее своего предрелиза
    ("1.0.0-beta", "1.0.0", False), # а предрелиз тому, у кого выпуск, не нужен
])
def test_version_comparison(upd, candidate, current, expected):
    """Теги на GitHub пишут по-разному — «v» перед номером ломать ничего не должна."""
    assert upd.is_newer(candidate, current) is expected


# ==================== Выбор установщика ====================

def test_picks_setup_exe(upd):
    """Из вложений выбирается установщик, а не архив с исходниками."""
    assets = [
        {"name": "Source code.zip"},
        {"name": "ScottAI-1.1.0-setup.exe"},
        {"name": "checksums.txt"},
    ]
    assert upd._pick_installer(assets)["name"] == "ScottAI-1.1.0-setup.exe"


def test_skips_arm64(upd):
    """
    Установщик под другую архитектуру не предлагается.

    Найдено на живом релизе PowerToys: arm64-файл лежит в списке первым, и
    без этой проверки человеку с обычным компьютером предлагали именно его.
    """
    assets = [
        {"name": "AppSetup-1.0.0-arm64.exe"},
        {"name": "AppSetup-1.0.0-x64.exe"},
    ]
    assert upd._pick_installer(assets)["name"] == "AppSetup-1.0.0-x64.exe"


def test_no_installer_is_not_a_crash(upd):
    """Релиз без .exe — не повод падать: обновление покажется со ссылкой на страницу."""
    assert upd._pick_installer([{"name": "Source code.tar.gz"}]) is None
    assert upd._pick_installer([]) is None


# ==================== Ответ GitHub ====================

def _release(tag, asset_name="ScottAI-9.9.9-setup.exe"):
    return {
        "tag_name": tag,
        "body": "Что нового: Scott научился варить кофе",
        "html_url": f"https://github.com/stalker1243/Scott-AI/releases/tag/{tag}",
        "published_at": "2026-09-10T12:00:00Z",
        "assets": [{
            "name": asset_name,
            "browser_download_url": f"https://github.com/.../{asset_name}",
            "size": 64 * 1024 * 1024,
        }],
    }


def test_new_version_offered(upd, no_cache, monkeypatch):
    """Вышедшая версия предлагается — со ссылкой на установщик и заметками."""
    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", lambda repo=None: (_release("v9.9.9"), ""))

    info = upd.check(force=True)

    assert info.update_available is True
    assert info.latest_version == "9.9.9"
    assert info.asset_name.endswith(".exe")
    assert "кофе" in info.release_notes
    assert info.error == ""


def test_same_version_not_offered(upd, no_cache, monkeypatch):
    """Пара к тесту выше: своя же версия обновлением не считается."""
    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", lambda repo=None: (_release("v1.0.0"), ""))

    assert upd.check(force=True).update_available is False


def test_network_failure_reported_not_swallowed(upd, no_cache, monkeypatch):
    """
    Недоступный GitHub — обычное дело, но молчать об этом нельзя.

    Иначе человек видит «обновлений нет» и там, где их не искали вовсе.
    """
    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(
        upd, "fetch_latest_release",
        lambda repo=None: (None, "не удалось связаться с GitHub: таймаут"),
    )

    info = upd.check(force=True)

    assert info.update_available is False
    assert "GitHub" in info.error


# ==================== Кэш ====================

def test_cache_saves_github_requests(upd, no_cache, monkeypatch):
    """
    Второй запрос подряд идёт из кэша.

    GitHub без токена разрешает 60 обращений в час, а выпуски выходят куда
    реже — ходить туда при каждом запуске лаунчера незачем.
    """
    calls = []

    def counted(repo=None):
        calls.append(repo)
        return _release("v9.9.9"), ""

    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", counted)

    upd.check(force=True)
    upd.check()   # должен взять из кэша
    upd.check()

    assert len(calls) == 1, f"ходили на GitHub {len(calls)} раза вместо одного"


def test_stale_cache_refreshed(upd, no_cache, monkeypatch):
    """Кэш старше суток не годится — идём на GitHub заново."""
    calls = []

    def counted(repo=None):
        calls.append(repo)
        return _release("v9.9.9"), ""

    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", counted)

    upd.check(force=True)

    stale = json.loads(no_cache.read_text(encoding="utf-8"))
    stale["checked_at"] = time.time() - upd.CHECK_INTERVAL_SECONDS - 60
    no_cache.write_text(json.dumps(stale), encoding="utf-8")

    upd.check()
    assert len(calls) == 2, "устаревший кэш не обновился"


def test_cache_respects_new_current_version(upd, no_cache, monkeypatch):
    """
    После обновления программы старый кэш не должен предлагать то, что уже
    стоит: сравнение делается заново, по текущей версии.
    """
    monkeypatch.setattr(upd, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", lambda repo=None: (_release("v9.9.9"), ""))
    assert upd.check(force=True).update_available is True

    # Человек поставил обновление — кэш прежний, но предлагать больше нечего.
    monkeypatch.setattr(upd, "current_version", lambda: "9.9.9")
    assert upd.check().update_available is False

def test_unknown_own_version_offers_nothing(upd, no_cache, monkeypatch):
    """
    Пока своя версия неизвестна, обновление не предлагается.

    Найдено живым пользователем: VERSION.json не попал в дистрибутив, программа
    считала свою версию нулевой — и предложила поставить ту самую версию,
    которая у человека уже стояла.
    """
    monkeypatch.setattr(upd, "current_version", lambda: "0.0.0")
    monkeypatch.setattr(upd, "fetch_latest_release", lambda repo=None: (_release("v1.0.2"), ""))

    info = upd.check(force=True)

    assert info.update_available is False
    assert "VERSION.json" in info.error
