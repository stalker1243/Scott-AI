"""Names from the actual catalog work, and simultaneous changes are preserved."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
import audio_settings
import scott_voice
import voice_commands
import understanding
from command_parser import CommandParser
from fast_intent import get_fast_intent_engine
from question_answerer import get_question_answerer
from speech_text import prepare_for_speech

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_settings, 'CONFIG_PATH', tmp_path / 'audio.json')


@pytest.mark.parametrize('text,expected', [('пятьдесят пять', 55), ('сто', 100), ('ноль', 0),
    ('один', 1), ('двадцать один', 21), ('девяносто девять', 99), ('50', 50), ('50%', 50)])
def test_spoken_volume_numbers(text, expected):
    command = voice_commands.parse('громкость голоса ' + text)
    assert (command.action, command.value) == ('volume', expected)
    voice_commands.execute(command.action, command.value)
    assert audio_settings.get_settings()['volume'] == expected


@pytest.mark.parametrize('value', ['сто пять', 'пятьдесят одиннадцать', '50,5', '²', '9' * 5000])
def test_invalid_own_voice_volume_cannot_turn_into_system_volume(value):
    command = voice_commands.parse('громкость голоса ' + value)
    assert command.action == 'invalid_volume'
    assert voice_commands.execute(command.action).startswith('❌')
    assert not audio_settings.CONFIG_PATH.exists()


@pytest.mark.parametrize('name,label', list(scott_voice.AVAILABLE_VOICES.items()))
def test_every_catalog_name_can_be_selected(name, label):
    spoken = label.split('(')[0].strip()
    if name == 'scott-voice' and not scott_voice.scott_voice_engine.get_engine().describe()['available']:
        assert voice_commands.execute('select', spoken).startswith('❌')
        return
    assert voice_commands.execute('select', spoken).startswith('Теперь')
    assert scott_voice.get_current_voice() == name


@pytest.mark.parametrize('spoken,expected', [('Флориана', 'de-DE-FlorianMultilingualNeural'),
    ('Уильяма', 'en-AU-WilliamMultilingualNeural'), ('Брайана', 'en-US-BrianMultilingualNeural')])
def test_russian_cloud_voice_names(spoken, expected):
    command = voice_commands.parse('выбери голос ' + spoken)
    voice_commands.execute(command.action, command.value)
    assert scott_voice.get_current_voice() == expected


def test_catalog_command_uses_actual_available_names():
    command = understanding.understand('Скотт, какие голоса есть?', intent_engine=get_fast_intent_engine(),
        parser=CommandParser(), answerer=get_question_answerer())
    assert command.action == 'voice_settings' and command.parsed.main_param == 'catalog'
    response = voice_commands.execute('catalog')
    for label in scott_voice.AVAILABLE_VOICES.values():
        assert label.split('(')[0].strip() in response


def test_ambiguous_label_does_not_choose_a_voice_by_order():
    assert voice_commands.resolve_voice('Demo', {'a': 'Demo (local)', 'b': 'Demo (cloud)'}) is None
    assert voice_commands.resolve_voice('a', {'a': 'Demo (local)', 'b': 'Demo (cloud)'}) == 'a'


def test_simultaneous_relative_volume_commands_are_not_lost():
    audio_settings.update(volume=20)
    barrier = threading.Barrier(4)
    def change(_):
        barrier.wait(timeout=2)
        for i in range(5):
            voice_commands.execute('volume_delta', 1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(change, range(4)))
    assert audio_settings.get_settings()['volume'] == 40


def test_pc_is_pronounced_as_a_word():
    assert 'компьютер' in prepare_for_speech('выключи пк').casefold()
    assert 'компьютер' in prepare_for_speech('состояние PC').casefold()
