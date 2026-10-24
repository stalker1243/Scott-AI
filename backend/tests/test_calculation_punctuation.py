"""ASR punctuation must keep explicit arithmetic local without widening actions."""
import asyncio

import pytest

import local_tools
import utility_commands

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('command,expected', [
    ('посчитай, 25 плюс 10.', '35'),
    ('посчитай,25 плюс 10', '35'),
    ('посчитай , 25 плюс 10', '35'),
    ('ПОСЧИТАЙ, 1,5 + 2,25', '3.75'),
    ('вычисли: (12 + 3) / 5', '3'),
    ('сколько будет, 15 процентов от 100?', '15'),
    ('сколько будет: 12,5% от 80', '10'),
    ('посчитай, max(2, 5, -7)', '5'),
])
def test_spoken_calculations_accept_separator_after_prefix(command, expected):
    parsed = utility_commands.parse(command)
    assert parsed is not None
    result = local_tools.execute(parsed)
    assert result['success'], result
    assert result['response'] == expected


@pytest.mark.parametrize('command', [
    'не посчитай, 2+2',
    'объясни как посчитай, 2+2',
    'напиши код: посчитай, 2+2',
    '"посчитай, 2+2"',
    '«посчитай, 2+2»',
    '`посчитай, 2+2`',
    'посчитай; 2+2',
    'посчитай, 2+2\nоткрой блокнот',
])
def test_separator_does_not_turn_discussion_or_multiple_commands_into_calculation(command):
    assert utility_commands.parse(command) is None


def test_spoken_calculation_keeps_local_route(main_module, monkeypatch):
    monkeypatch.setattr(main_module, 'intelligent_answerer', None)
    monkeypatch.setattr(main_module, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main_module.memories_module, 'observe', lambda text: [])
    async def check():
        result = await main_module.scott_ai.process_command(
            'Скотт, посчитай, 25 плюс 10.', quiet_mode=True, by_voice=True)
        assert result['success'], result
        assert result['type'] == 'utility'
        assert result['response'] == '35'
    asyncio.run(check())
