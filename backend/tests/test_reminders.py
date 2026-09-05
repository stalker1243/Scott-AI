"""
Напоминания: разбор времени и срабатывание в срок.

Прежний планировщик в проекте не работал вовсе: задачи складывались в список,
поток вызывал `schedule.run_pending()` — а сами задачи в библиотеку никто не
регистрировал. Команда принималась, появлялась в списке и не выполнялась
никогда. Проверено практикой: запланированная на минуту вперёд команда так и
не сработала.

Поэтому здесь две группы проверок. Первая — что сказанное человеком
превращается в правильное время. Вторая — что дело действительно срабатывает и
переживает перезапуск.
"""

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 14, 0)


@pytest.fixture
def rem():
    import reminders

    return reminders


@pytest.fixture
def service(rem, tmp_path, monkeypatch):
    """Служба с отдельным файлом хранения — чтобы не трогать настоящие дела."""
    monkeypatch.setattr(rem, "STORE_PATH", tmp_path / "reminders.json")
    return rem.ReminderService()


# ==================== Разбор времени ====================

@pytest.mark.parametrize("phrase,expected", [
    ("напомни через 10 минут выключить плиту", NOW + timedelta(minutes=10)),
    ("напомни через 2 часа позвонить", NOW + timedelta(hours=2)),
    ("напомни через 3 дня оплатить счёт", NOW + timedelta(days=3)),
])
def test_relative_time(rem, phrase, expected):
    assert rem.parse_time(phrase, NOW) == expected


@pytest.mark.parametrize("phrase,expected", [
    ("напомни через час позвонить маме", NOW + timedelta(hours=1)),
    ("напомни через полчаса про встречу", NOW + timedelta(minutes=30)),
    ("напомни через полтора часа проверить почту", NOW + timedelta(minutes=90)),
    ("напомни через минуту", NOW + timedelta(minutes=1)),
])
def test_fixed_expressions(rem, phrase, expected):
    """
    Устойчивые выражения без числа.

    Они проверяются раньше общего образца не случайно: тот разбирает «через
    полчаса» как число «пол» плюс единицу «часа» и отказывается, не найдя
    такого числа. Так «через полчаса» и «через час» вообще не работали.
    """
    assert rem.parse_time(phrase, NOW) == expected


def test_absolute_time_today(rem):
    """Время, которое ещё не наступило, — сегодня."""
    assert rem.parse_time("напомни в 15:30 забрать заказ", NOW) == NOW.replace(hour=15, minute=30)


def test_absolute_time_moves_to_tomorrow(rem):
    """
    Время, которое сегодня уже прошло, переносится на завтра.

    Иначе напоминание «в 9:00», поставленное вечером, сработало бы мгновенно —
    и человек решил бы, что Scott сломался.
    """
    evening = datetime(2026, 9, 5, 22, 0)

    result = rem.parse_time("напомни в 9:00 про врача", evening)

    assert result == datetime(2026, 9, 6, 9, 0)


def test_tomorrow_is_respected(rem):
    assert rem.parse_time("напомни завтра в 9:00", NOW) == datetime(2026, 9, 6, 9, 0)


@pytest.mark.parametrize("phrase", [
    "напомни просто что-нибудь",
    "напомни",
    "открой блокнот",
])
def test_unparseable_time_is_rejected(rem, phrase):
    """
    Непонятое время честно отклоняется.

    Поставить напоминание наугад хуже, чем переспросить: человек будет ждать
    сигнала, которого не будет, или получит его посреди ночи.
    """
    assert rem.parse_time(phrase, NOW) is None


@pytest.mark.parametrize("phrase,expected", [
    ("напомни через 10 минут выключить плиту", "выключить плиту"),
    ("напомни в 15:30 забрать заказ", "забрать заказ"),
    ("напомни о том что нужно купить хлеб через 20 минут", "купить хлеб"),
    ("напомни в 9 часов утра принять лекарство", "принять лекарство"),
])
def test_subject_extraction(rem, phrase, expected):
    """
    Из фразы вынимается то, что Scott произнесёт вслух.

    Служебные слова убираются: «напомню: что выключить плиту» звучит
    косноязычно, а слушать это придётся человеку.
    """
    assert rem.extract_subject(phrase) == expected


# ==================== Срабатывание ====================

def test_due_reminder_fires(service):
    """
    Дело, которому пришёл срок, выполняется.

    Ровно это и не работало раньше — напоминание принималось и молчало.
    """
    fired = []
    service.on_fire = fired.append
    service.add("выключить плиту", datetime.now() - timedelta(seconds=1))

    service._fire_due()

    assert len(fired) == 1
    assert fired[0].text == "выключить плиту"


def test_future_reminder_waits(service):
    """Дело на будущее раньше срока не трогают."""
    fired = []
    service.on_fire = fired.append
    service.add("позвонить", datetime.now() + timedelta(hours=1))

    service._fire_due()

    assert fired == []
    assert len(service.pending()) == 1


def test_reminder_fires_once(service):
    """Сработавшее дело не повторяется при каждой проверке."""
    fired = []
    service.on_fire = fired.append
    service.add("проверить", datetime.now() - timedelta(seconds=1))

    service._fire_due()
    service._fire_due()

    assert len(fired) == 1


def test_reminders_survive_restart(rem, tmp_path, monkeypatch):
    """
    Дела переживают перезапуск.

    Scott работает в фоне, и перезапуск для человека незаметен — а «напомни
    через час» обязано пережить его без потерь.
    """
    store = tmp_path / "reminders.json"
    monkeypatch.setattr(rem, "STORE_PATH", store)

    first = rem.ReminderService()
    first.add("купить хлеб", datetime.now() + timedelta(hours=2))

    second = rem.ReminderService()

    assert len(second.pending()) == 1
    assert second.pending()[0].text == "купить хлеб"


def test_cancel_removes(service):
    item = service.add("отменить это", datetime.now() + timedelta(hours=1))

    assert service.cancel(item.id)
    assert service.pending() == []
    assert not service.cancel("такого-нет")


def test_broken_store_does_not_break_startup(rem, tmp_path, monkeypatch):
    """Испорченный файл не мешает запуску: дела теряются, Scott — нет."""
    store = tmp_path / "reminders.json"
    store.write_text("{это не json", encoding="utf-8")
    monkeypatch.setattr(rem, "STORE_PATH", store)

    service = rem.ReminderService()

    assert service.all() == []


def test_failing_callback_does_not_break_loop(service):
    """
    Сбой при озвучивании не должен ронять службу.

    Одно неудачное напоминание — не повод перестать напоминать обо всём
    остальном.
    """
    def explode(item):
        raise RuntimeError("голос недоступен")

    service.on_fire = explode
    service.add("первое", datetime.now() - timedelta(seconds=2))

    service._fire_due()

    # Служба пережила исключение и пометила дело выполненным.
    assert all(item.done for item in service.all())

# ==================== Случаи из живого разговора ====================
#
# Всё в этом блоке подсмотрено в логах: человек говорил фразу голосом, Whisper
# передавал её со своими искажениями, и Scott делал не то. Формулировки взяты
# ровно в том виде, в каком они дошли до разбора.

def test_swallowed_preposition_still_parses(rem):
    """
    «Напомни мне в 18:00 …» Whisper передал как «напомним мне 18.00, …».

    Пропал предлог и двоеточие стало точкой — время не находилось, фраза
    уходила в открытие приложений, и Scott запустил Discord вместо того чтобы
    поставить напоминание на вечер.
    """
    now = datetime(2026, 9, 5, 12, 0)
    assert rem.parse_time("напомним мне 18.00, зайти в discord", now=now) == datetime(2026, 9, 5, 18, 0)


@pytest.mark.parametrize("phrase", [
    "напомним мне 18.00, зайти в discord",
    "напомните вечером позвонить маме",
    "напомнить завтра про встречу",
])
def test_verb_forms_stripped_from_subject(rem, phrase):
    """
    Форма глагола убирается целиком, а не по первым буквам.

    Порядок альтернатив в регулярном выражении решает всё: со списком
    «и|им|ите» движок съедал «напомни» и оставлял в тексте напоминания хвост
    «м мне …», который Scott потом зачитывал вслух.
    """
    subject = rem.extract_subject(phrase)
    assert not subject.lower().startswith(("м ", "те ", "ть ", "напомн"))


@pytest.mark.parametrize("phrase,expected_hour", [
    ("напомни в 9 утра про встречу", 9),
    ("напомни в 9 вечера позвонить маме", 21),
    ("напомни в 3 дня забрать посылку", 15),
    ("напомни в 12 ночи выключить компьютер", 0),
])
def test_daypart_shifts_hour(rem, phrase, expected_hour):
    """
    «Семь вечера» — это 19:00.

    Время суток раньше просто вырезалось из текста, поэтому «в 9 вечера»
    ставило напоминание на девять утра следующего дня.
    """
    now = datetime(2026, 9, 5, 12, 0)
    parsed = rem.parse_time(phrase, now=now)
    assert parsed is not None, f"«{phrase}» не разобрана"
    assert parsed.hour == expected_hour
