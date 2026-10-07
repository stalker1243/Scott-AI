"""Compare effective reminder payloads without executing or saving anything."""
from types import SimpleNamespace
import pytest
from accuracy_voice import _same_decision
import scheduled
import understanding

pytestmark = pytest.mark.unit


def reminder(text):
    return understanding.Decision(kind='action', action='reminder',
        parsed=SimpleNamespace(main_param=text, context={}))


def test_reminder_punctuation_and_spelled_hour_keep_same_payload():
    assert _same_decision(reminder('напомни завтра в девять позвонить маме'),
                          reminder('Напомни, завтра в 9 позвонить маме.'))
    assert _same_decision(reminder('напомни через двадцать минут проверить почту'),
                          reminder('Напомни, через 20 минут проверить почту.'))


@pytest.mark.parametrize('text', [
    'напомни завтра в 10 позвонить маме',
    'напомни завтра в девять вечера позвонить маме',
    'напомни завтра в 9 позвонить врачу',
    'напомни позвонить маме',
])
def test_different_due_or_subject_is_still_a_miss(text):
    assert not _same_decision(reminder('напомни завтра в девять позвонить маме'), reminder(text))


def test_first_person_reminder_never_becomes_deferred_command():
    assert scheduled.is_reminder('Напомню через час про созвон.')
    assert understanding.extract_schedule('Напомню через час про созвон.') is None
