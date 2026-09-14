"""
Список умений: что Scott может и как его об этом просить.

До сих пор узнать это было негде — четыре случайных примера на главной
создавали впечатление, что он умеет ровно четыре вещи. Голосовой помощник,
возможности которого угадывают, используется на десятую часть.

Две вещи, ради которых написаны проверки.

Первая: список обещает. Умение, отмеченное доступным там, где его нет, хуже
отсутствия списка — человек решит, что у него сломалось. Поэтому каждое умение
отвечает, доступно ли оно ЗДЕСЬ, и упавшая проверка не должна уносить весь
список.

Вторая: примеры фраз должны работать. Показанное «сделай громче» обязано быть
той самой формулировкой, которую Scott понимает, — иначе раздел учит человека
неправильному.
"""

import pytest

pytestmark = pytest.mark.unit

try:
    import abilities
    import understanding
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import abilities, understanding


# ==================== Устройство списка ====================

def test_список_не_пуст():
    итог = abilities.describe()

    assert итог["groups"], "список умений оказался пустым"
    assert итог["total"] > 0


def test_у_каждого_умения_есть_название_и_объяснение():
    for группа in abilities.describe()["groups"]:
        assert группа["group"], "у группы нет названия"

        for умение in группа["items"]:
            assert умение["title"], f"у умения {умение['id']} нет названия"
            assert умение["detail"], f"умение {умение['id']} ничего не объясняет"


def test_у_каждого_умения_есть_примеры():
    """
    Примеры — единственный способ показать, КАК просить: Scott понимает «сделай
    громче», но не «увеличь звук на 20 процентов».
    """
    for группа in abilities.describe()["groups"]:
        for умение in группа["items"]:
            assert умение["examples"], f"у умения {умение['id']} нет ни одного примера"


def test_упавшая_проверка_не_уносит_список(monkeypatch):
    """
    Человек, у которого отвалился микрофон, имеет право узнать про остальные
    умения — а увидел бы пустую страницу.
    """
    def взрыв():
        raise RuntimeError("что-то сломалось")

    сломанное = [{
        "group": "Проверочная",
        "items": [{
            "id": "взрыв", "title": "Взрывное", "detail": "падает",
            "examples": ["раз"], "check": взрыв,
        }],
    }]

    monkeypatch.setattr(abilities, "ABILITIES", сломанное + abilities.ABILITIES)

    итог = abilities.describe()

    первое = итог["groups"][0]["items"][0]
    assert первое["state"] == abilities.UNAVAILABLE
    assert "не удалось" in первое["reason"]
    assert len(итог["groups"]) > 1, "остальные группы пропали"


def test_недоступное_объясняется_словами(monkeypatch):
    """
    «Недоступно» без причины оставляет человека в тупике: он не знает, чинить
    это или так и должно быть.
    """
    monkeypatch.setattr(abilities, "ABILITIES", [{
        "group": "Проверочная",
        "items": [{
            "id": "нет", "title": "Отсутствующее", "detail": "—",
            "examples": ["раз"], "check": lambda: "нет нужной программы",
        }],
    }])

    умение = abilities.describe()["groups"][0]["items"][0]

    assert умение["state"] == abilities.UNAVAILABLE
    assert умение["reason"] == "нет нужной программы"


def test_счётчик_доступного_считает_верно(monkeypatch):
    monkeypatch.setattr(abilities, "ABILITIES", [{
        "group": "Проверочная",
        "items": [
            {"id": "a", "title": "Есть", "detail": "—", "examples": ["раз"]},
            {"id": "b", "title": "Нет", "detail": "—", "examples": ["два"],
             "check": lambda: "недоступно"},
        ],
    }])

    итог = abilities.describe()

    assert итог["total"] == 2
    assert итог["ready"] == 1


# ==================== Примеры действительно работают ====================
#
# Раздел учит человека, как просить. Показанная фраза, которую Scott не
# понимает, — это не подсказка, а ловушка.

def test_пример_про_память_разбирается_как_просьба_запомнить():
    пример = _пример("remember")

    assert understanding.extract_memory(пример) is not None


def test_пример_про_проект_разбирается_как_просьба_открыть_проект():
    пример = _пример("projects")

    assert understanding.extract_project(пример) is not None


def _пример(ability_id: str, содержит: str = "") -> str:
    """Первый пример указанного умения — тот самый, что видит человек."""
    for группа in abilities.ABILITIES:
        for умение in группа["items"]:
            if умение["id"] != ability_id:
                continue

            for пример in умение["examples"]:
                if not содержит or содержит in пример:
                    return пример

    raise AssertionError(f"не нашлось примера для умения {ability_id}")
