"""
Подсказка распознаванию: что Scott ожидает услышать.

ЗАЧЕМ ОНА. Именно на этом голос и проигрывал чату. В чате человек пишет
«Google Chrome» — Scott находит программу и открывает. Голосом получалось
«открой кукол хром» — так записано в журнале услышанного, — и найти по такому
названию было нечего. Возможности при этом одинаковые: разбор у голоса и чата
общий, вся разница была в тексте, который до него доходил.

Замер на живой проверке: «открой вижуал студио код» без подсказки
распознаётся как «визуал студия у кода», с подсказкой — «Visual Studio Code».
"""

import pytest

pytestmark = pytest.mark.unit

try:
    import speech_hints
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import speech_hints


@pytest.fixture(autouse=True)
def без_кэша():
    """Подсказка собирается один раз — в проверках это мешает."""
    speech_hints.reset()
    yield
    speech_hints.reset()


def подсунуть_каталог(monkeypatch, названия):
    """Каталог установленных программ — свой, а не настоящий с этой машины."""
    try:
        import app_resolver
    except ImportError:  # pragma: no cover
        from backend import app_resolver

    индекс = {и.lower(): "" for и in названия}
    monkeypatch.setattr(app_resolver, "_get_startapps_index", lambda: индекс)
    monkeypatch.setattr(app_resolver, "_get_shortcut_index", lambda: {})


def test_имя_всегда_в_подсказке(monkeypatch):
    """
    Без имени «Скотт, какая погода» распознаётся как «Скот, какая погода», а
    непрочитанное имя означает, что человека не услышали вовсе.
    """
    подсунуть_каталог(monkeypatch, [])

    assert "Скотт" in speech_hints.prompt()


def test_в_подсказку_идут_только_установленные(monkeypatch):
    """
    Подсказывать модели то, чего на машине нет, — значит учить её слышать
    несуществующее: «открой блокнот» превратится в название чужой программы.
    """
    подсунуть_каталог(monkeypatch, ["google chrome", "discord"])

    подсказка = speech_hints.prompt()

    assert "Google Chrome" in подсказка
    assert "Discord" in подсказка
    assert "Photoshop" not in подсказка


def test_длина_подсказки_ограничена(monkeypatch):
    """
    Длинная подсказка сбивает распознавание остального: модель начинает
    подгонять услышанное под неё, и обычная фраза превращается в набор
    названий.
    """
    подсунуть_каталог(monkeypatch, [и.lower() for и in speech_hints.KNOWN_APPS])

    программы = speech_hints.installed_known_apps()

    assert len(программы) <= speech_hints.MAX_APPS


def test_без_каталога_остаётся_обращение(monkeypatch):
    """
    Каталог не собрался — подсказка теряет названия, но не имя. Работать без
    неё хуже, чем с ней, но лучше, чем со сбитым распознаванием.
    """
    try:
        import app_resolver
    except ImportError:  # pragma: no cover
        from backend import app_resolver

    def падает():
        raise RuntimeError("каталог программ недоступен")

    monkeypatch.setattr(app_resolver, "_get_startapps_index", падает)
    monkeypatch.setattr(app_resolver, "_get_shortcut_index", падает)

    assert speech_hints.installed_known_apps() == []
    assert "Скотт" in speech_hints.prompt()


def test_подсказка_собирается_один_раз(monkeypatch):
    """Каталог программ стоит почти секунду — собирать его на каждую фразу нельзя."""
    вызовов = {"n": 0}

    try:
        import app_resolver
    except ImportError:  # pragma: no cover
        from backend import app_resolver

    def каталог():
        вызовов["n"] += 1
        return {"discord": ""}

    monkeypatch.setattr(app_resolver, "_get_startapps_index", каталог)
    monkeypatch.setattr(app_resolver, "_get_shortcut_index", lambda: {})

    speech_hints.prompt()
    speech_hints.prompt()
    speech_hints.prompt()

    assert вызовов["n"] == 1
