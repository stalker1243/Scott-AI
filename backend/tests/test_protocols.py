"""
Протоколы: именованная последовательность шагов.

Проверяется то, ради чего модуль и написан, и то, на чём такие вещи обычно
ломаются: имя, названное обычным словом, не должно перехватывать обычные
фразы, а протокол, зовущий сам себя, не должен вешать Scott.

Шаги здесь никогда не исполняются по-настоящему: исполнитель передаётся
снаружи, и в проверках он просто записывает, что его позвали. Ради этого
разделение решения и последствий и сделано — протокол из шести шагов
проверяется за миллисекунды, не открывая ни одной программы.
"""

import pytest

pytestmark = pytest.mark.unit


try:
    import protocols
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import protocols


@pytest.fixture
def хранилище(tmp_path):
    """Хранилище во временном файле: настоящие протоколы трогать нельзя."""
    return protocols.ProtocolStore(path=tmp_path / "protocols.json")


@pytest.fixture
def рабочий_день(хранилище):
    хранилище.add(
        "рабочий день",
        ["открой браузер", "открой редактор кода", "приглуши звук"],
        phrases=["за работу", "начали"],
    )
    return хранилище.get("рабочий день")


class Исполнитель:
    """Запоминает, что его просили сделать, вместо того чтобы делать."""

    def __init__(self, ошибка_на=None, бросать=False):
        self.шаги = []
        self.ошибка_на = ошибка_на
        self.бросать = бросать

    def __call__(self, text):
        self.шаги.append(text)

        if text == self.ошибка_на:
            if self.бросать:
                raise RuntimeError("не вышло")
            return {"type": "error", "response": "не вышло"}

        return f"сделал: {text}"


# ==================== Хранение ====================

def test_protocol_survives_restart(tmp_path):
    """
    Протокол переживает перезапуск.

    Scott работает в фоне и может быть перезапущен незаметно для человека, а
    протоколы он составляет один раз и надолго.
    """
    путь = tmp_path / "protocols.json"

    первый = protocols.ProtocolStore(path=путь)
    первый.add("вечер", ["закрой браузер", "приглуши звук"])

    второй = protocols.ProtocolStore(path=путь)
    найденный = второй.get("вечер")

    assert найденный is not None
    assert [шаг.text for шаг in найденный.steps] == ["закрой браузер", "приглуши звук"]


def test_protocol_written_by_hand_is_read(tmp_path):
    """
    Протокол, записанный руками простым списком фраз, читается.

    Полная запись со словарями и паузами нужна программе, а человеку, который
    правит файл в блокноте, удобнее список строк. Отказываться его читать
    незачем.
    """
    путь = tmp_path / "protocols.json"
    путь.write_text(
        '[{"name": "утро", "steps": ["открой почту", "прочитай новости"]}]',
        encoding="utf-8",
    )

    склад = protocols.ProtocolStore(path=путь)
    протокол = склад.get("утро")

    assert протокол is not None
    assert len(протокол.steps) == 2
    assert протокол.steps[0].pause == 0


def test_empty_protocol_is_refused(хранилище):
    """Протокол без шагов не нужен никому: он ничего не делает."""
    итог = хранилище.add("пустой", [])

    assert итог["success"] is False
    assert хранилище.get("пустой") is None


def test_name_must_be_unique(хранилище, рабочий_день):
    итог = хранилище.add("Рабочий День", ["открой браузер"])

    assert итог["success"] is False


def test_too_many_steps_is_refused(хранилище):
    """
    Предел на длину — защита не от злого умысла, а от опечатки.

    Протокол на тысячу шагов человек не пишет; такое число берётся из ошибки, и
    выполнять его целиком значит заморозить Scott надолго.
    """
    итог = хранилище.add("длинный", ["шаг"] * (protocols.MAX_STEPS + 1))

    assert итог["success"] is False


# ==================== Как протокол зовут ====================

def test_called_by_name_with_wrapper(хранилище, рабочий_день):
    for фраза in [
        "протокол рабочий день",
        "запусти протокол рабочий день",
        "выполни сценарий рабочий день",
        "включи режим рабочий день",
        "Протокол Рабочий День!",
    ]:
        assert хранилище.match(фраза) is рабочий_день, фраза


def test_called_by_own_phrase(хранилище, рабочий_день):
    """Человек редко зовёт вещь одним и тем же словом."""
    assert хранилище.match("за работу") is рабочий_день
    assert хранилище.match("начали") is рабочий_день


def test_ordinary_phrase_does_not_launch_protocol(хранилище):
    """
    Протокол с обычным именем не перехватывает обычные фразы.

    Ровно та ловушка, ради которой совпадение здесь только точное: протокол,
    названный «браузер», при поиске по вхождению слов начал бы срабатывать на
    «открой браузер», и открыть браузер стало бы нельзя.
    """
    хранилище.add("браузер", ["открой хром", "открой почту"])

    assert хранилище.match("открой браузер") is None
    assert хранилище.match("закрой браузер") is None
    assert хранилище.match("что такое браузер") is None

    # А позванный прямо — срабатывает.
    assert хранилище.match("протокол браузер") is not None


def test_disabled_protocol_is_not_matched(хранилище, рабочий_день):
    хранилище.update("рабочий день", enabled=False)

    assert хранилище.match("протокол рабочий день") is None


def test_unknown_phrase_matches_nothing(хранилище, рабочий_день):
    assert хранилище.match("протокол которого нет") is None
    assert хранилище.match("") is None


# ==================== Выполнение ====================

def test_steps_run_in_order(рабочий_день):
    исполнитель = Исполнитель()
    итог = protocols.run(рабочий_день, исполнитель)

    assert итог.ok
    assert исполнитель.шаги == ["открой браузер", "открой редактор кода", "приглуши звук"]


def test_run_stops_at_failed_step(рабочий_день):
    """
    После сбоя протокол останавливается.

    Шаги в последовательности опираются друг на друга: открыть файл в
    редакторе, который не открылся, бессмысленно.
    """
    исполнитель = Исполнитель(ошибка_на="открой редактор кода")
    итог = protocols.run(рабочий_день, исполнитель)

    assert not итог.ok
    assert итог.stopped_at == 1
    assert исполнитель.шаги == ["открой браузер", "открой редактор кода"]
    assert "остановлен" in итог.summary()
    assert "открой редактор кода" in итог.summary()


def test_thrown_error_is_the_same_as_returned(рабочий_день):
    """
    Исполнитель может и вернуть ошибку, и бросить её.

    В проекте есть и такие, и такие: заставлять их вести себя одинаково ради
    протоколов значило бы переписывать половину исполнения.
    """
    исполнитель = Исполнитель(ошибка_на="открой браузер", бросать=True)
    итог = protocols.run(рабочий_день, исполнитель)

    assert итог.stopped_at == 0
    assert "не вышло" in итог.steps[0].response


def test_run_can_continue_after_error(рабочий_день):
    исполнитель = Исполнитель(ошибка_на="открой браузер")
    итог = protocols.run(рабочий_день, исполнитель, stop_on_error=False)

    assert len(исполнитель.шаги) == 3
    assert итог.steps[0].ok is False
    assert итог.steps[1].ok is True


def test_pause_is_waited_between_steps(хранилище):
    """
    Пауза после шага соблюдается.

    Программа, которую только что попросили открыться, не готова принять
    следующую команду сразу.
    """
    хранилище.add("медленный", [
        {"text": "открой браузер", "pause": 2},
        {"text": "введи в поиск браузера погода"},
    ])

    ожидания = []
    protocols.run(хранилище.get("медленный"), Исполнитель(), sleep=ожидания.append)

    assert ожидания == [2.0]


def test_pause_is_capped(хранилище):
    """
    Слишком долгая пауза обрезается.

    Опечатка в числе не должна оставлять Scott висеть час.
    """
    хранилище.add("опечатка", [{"text": "открой браузер", "pause": 9999}])

    ожидания = []
    protocols.run(хранилище.get("опечатка"), Исполнитель(), sleep=ожидания.append)

    assert ожидания == [60.0]


def test_recursion_is_stopped(рабочий_день):
    """
    Протокол, зовущий сам себя, не вешает Scott.

    Шаг протокола — обычная фраза, и ничто не мешает написать в ней «запусти
    протокол рабочий день». Без предела на глубину это бесконечный цикл.
    """
    итог = protocols.run(рабочий_день, Исполнитель(), depth=protocols.MAX_DEPTH)

    assert not итог.ok
    assert "сам себя" in итог.error


def test_disabled_protocol_does_not_run(хранилище, рабочий_день):
    хранилище.update("рабочий день", enabled=False)
    исполнитель = Исполнитель()

    итог = protocols.run(рабочий_день, исполнитель)

    assert not итог.ok
    assert исполнитель.шаги == []


def test_run_is_counted(хранилище, рабочий_день):
    хранилище.mark_run(рабочий_день)
    хранилище.mark_run(рабочий_день)

    assert хранилище.get("рабочий день").runs == 2
    assert хранилище.get("рабочий день").last_run is not None


# ==================== Правка и удаление ====================

def test_steps_can_be_replaced(хранилище, рабочий_день):
    хранилище.update("рабочий день", steps=["открой почту"])

    assert [шаг.text for шаг in хранилище.get("рабочий день").steps] == ["открой почту"]


def test_update_cannot_empty_the_protocol(хранилище, рабочий_день):
    итог = хранилище.update("рабочий день", steps=[])

    assert итог["success"] is False
    assert len(хранилище.get("рабочий день").steps) == 3


def test_delete_removes_protocol(хранилище, рабочий_день):
    assert хранилище.delete("рабочий день")["success"] is True
    assert хранилище.get("рабочий день") is None
    assert хранилище.delete("рабочий день")["success"] is False


# ==================== Разбор ====================

class ЗаглушкаНамерения:
    """Движок намерений, который ни на что не претендует."""

    class Итог:
        intent_type = "unknown"
        main_param = ""
        is_command = False

    def detect(self, text):
        return self.Итог()


class ЗаглушкаРазборщика:
    class Итог:
        command_type = "unknown"
        main_param = ""
        confidence = 0.0

    def parse(self, text):
        return self.Итог()


class ЗаглушкаОтвечающего:
    def is_question(self, text):
        return False


def _решение(text, склад):
    try:
        import understanding
    except ImportError:  # pragma: no cover
        from backend import understanding

    return understanding.understand(
        text,
        intent_engine=ЗаглушкаНамерения(),
        parser=ЗаглушкаРазборщика(),
        answerer=ЗаглушкаОтвечающего(),
        find_protocol=склад.match,
    )


def test_decision_says_protocol(хранилище, рабочий_день):
    """
    Разбор узнаёт протокол и объясняет, почему решил так.

    Решение принимается в одном месте — иначе протоколы стали бы четвёртым
    механизмом, спорящим с остальными за смысл фразы. Ровно от этого спора
    когда-то и завели understanding.
    """
    решение = _решение("протокол рабочий день", хранилище)

    assert решение.kind == "protocol"
    assert решение.protocol is рабочий_день
    assert "рабочий день" in решение.reason


def test_protocol_beats_built_in_rules(хранилище):
    """
    Протокол сильнее встроенных правил.

    Человек составил его сам и назвал сам; если встроенное поведение будет
    перебивать его настройку, протокол с обычным именем позвать станет нельзя.
    """
    хранилище.add("ютуб", ["открой браузер", "открой почту"])

    решение = _решение("протокол ютуб", хранилище)

    assert решение.kind == "protocol"


def test_ordinary_phrase_is_not_a_protocol(хранилище, рабочий_день):
    """Обычная фраза не должна превращаться в протокол."""
    решение = _решение("открой браузер", хранилище)

    assert решение.kind != "protocol"


def test_parsing_works_without_protocols():
    """
    Без протоколов разбор работает как раньше.

    Хранилище может не подняться — файл повреждён, прав нет, — и это не повод
    ронять разбор всех остальных фраз.
    """
    try:
        import understanding
    except ImportError:  # pragma: no cover
        from backend import understanding

    решение = understanding.understand(
        "открой браузер",
        intent_engine=ЗаглушкаНамерения(),
        parser=ЗаглушкаРазборщика(),
        answerer=ЗаглушкаОтвечающего(),
        find_protocol=None,
    )

    assert решение.kind != "protocol"


# ==================== Выполнение через корутину ====================

@pytest.mark.asyncio
async def test_async_run_keeps_order(рабочий_день):
    """
    Асинхронное выполнение делает то же, что и обычное.

    Настоящее исполнение в проекте асинхронное — шаг уходит в обработчик
    команд, — а проверять протоколы удобнее синхронно. Два цикла обязаны вести
    себя одинаково, иначе проверки перестают что-либо значить.
    """
    шаги = []

    async def выполнить(text):
        шаги.append(text)
        return f"сделал: {text}"

    итог = await protocols.run_async(рабочий_день, выполнить)

    assert итог.ok
    assert шаги == ["открой браузер", "открой редактор кода", "приглуши звук"]


@pytest.mark.asyncio
async def test_async_run_stops_at_failed_step(рабочий_день):
    шаги = []

    async def выполнить(text):
        шаги.append(text)
        if text == "открой редактор кода":
            return {"type": "error", "response": "не вышло"}
        return "готово"

    итог = await protocols.run_async(рабочий_день, выполнить)

    assert итог.stopped_at == 1
    assert len(шаги) == 2


@pytest.mark.asyncio
async def test_async_recursion_is_stopped(рабочий_день):
    """Предел вложенности работает и в асинхронном пути."""
    async def выполнить(text):
        return "готово"

    итог = await protocols.run_async(рабочий_день, выполнить, depth=protocols.MAX_DEPTH)

    assert not итог.ok
    assert "сам себя" in итог.error
