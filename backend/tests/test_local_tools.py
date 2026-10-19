"""Offline tools through real routing, bounded execution and synthetic device state."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import json
import subprocess

import pytest

import local_tools as tools
import utility_commands as commands
import utility_units as units
import system_volume as volume

pytestmark = pytest.mark.unit

@pytest.mark.parametrize('expression,expected', [
    ('0.1 + 0.2', '0.3'), ('1,5 + 2,25', '3.75'), ('(12 + 3) / 5', '3'),
    ('двадцать пять плюс десять', '35'), ('шесть умножить на семь', '42'),
    ('сто разделить на четыре', '25'), ('2 в степени 10', '1024'),
    ('корень из 81', '9'), ('sqrt(144)', '12'), ('abs(-4)', '4'),
    ('round(2.675, 2)', '2.68'), ('round(1250, -2)', '1200'),
    ('max(2, 5, -7)', '5'), ('min(2, 5, -7)', '-7'),
    ('-7 // 3', '-3'), ('-7 % 3', '2'), ('7 % -3', '-2'),
    ('2×3 + 8÷4', '8'), ('2^3', '8'), ('2 х 3', '6'),
    ('1e-20', '1e-20'), ('1e100', '1e+100'), ('2**-3', '0.125'),
])
def test_calculations(expression, expected):
    result = tools.execute({'action': 'calculate', 'expression': expression})
    assert result['success'], result
    assert Decimal(result['response']) == Decimal(expected)

@pytest.mark.parametrize('expression', [
    '1/0', 'sqrt(-1)', '2**101', '2**0.5', '1e101', '1e-101',
    '__import__("os").system("echo bad")', 'open("secret")',
    '(1).__class__', '[1,2]', '{1:2}', 'True', 'lambda: 1',
    'min()', 'round(2, 13)', 'round(2, 1.5)', 'sqrt(1, 2)',
    'min(1,2,3,4,5,6,7,8,9)', '2 & 3', '1;2', '1+'*80+'1',
    '-'*30+'1', '('*300+'1'+')'*300,
])
def test_invalid_calculations_are_bounded_errors(expression):
    result = tools.execute({'action': 'calculate', 'expression': expression})
    assert result['success'] is False
    assert result['response']

@pytest.mark.parametrize('command,expected', [
    ('посчитай 15 процентов от 200', '30'), ('сколько будет 12,5% от 80', '10'),
    ('двадцать процентов от ста', '20'),
    ('переведи 2 километра в метры', '2000 м'),
    ('переведи 1 ГБ в мегабайты', '1000 MB'),
    ('переведи 1 ГиБ в мебибайты', '1024 MiB'),
    ('переведи 8 бит в байты', '1 Б'),
    ('переведи 2 килограммы в граммы', '2000 г'),
    ('переведи 2 литры в миллилитры', '2000 мл'),
    ('переведи 2 часы в минуты', '120 мин'),
    ('переведи 1 гектар в сотки', '100 сотка'),
    ('переведи 36 километров в час в метров в секунду', '10 м/с'),
    ('переведи 32 °F в °C', '0 °C'),
    ('переведи 273,15 K в °C', '0 °C'),
    ('переведи 0 °C в °F', '32 °F'),
    ('переведи -40 °F в °C', '-40 °C'),
])
def test_commands_execute(command, expected):
    result = tools.execute(commands.parse(command))
    assert result['success'], result
    assert result['response'] == expected

@pytest.mark.parametrize('command', [
    'переведи 1 метр в килограммы', 'переведи -274 °C в K',
    'переведи -1 K в °C', 'переведи -460 °F в °C',
    'сколько дней до 2026-02-30', 'сколько дней между вчера и завтра',
    'случайное число от 10 до 1', 'посчитай один миллиард',
])
def test_invalid_tool_requests(command):
    parsed = commands.parse(command)
    assert parsed
    assert tools.execute(parsed)['success'] is False

@pytest.mark.parametrize('command', [
    'объясни как посчитать проценты', 'переведи текст на английский',
    'переведи 30 долларов в рубли', 'посчитай 1 + 1\nоткрой блокнот',
    '`посчитай 2+2`', 'напиши калькулятор', 'x'*601,
])
def test_unknown_requests_keep_existing_routes(command):
    assert commands.parse(command) is None

def test_dates_leap_year_and_past():
    def call(command): return tools.execute(commands.parse(command), today=date(2026, 10, 9))
    assert call('какая сегодня дата')['response'] == '09.10.2026, пятница'
    assert call('какой завтра день недели')['response'] == '10.10.2026, суббота'
    assert call('сколько дней до 01.01.2027')['data']['days'] == 84
    assert call('сколько дней до 2026-10-08')['response'] == '1 день назад'
    assert call('сколько дней между 28.02.2024 и 01.03.2024')['data']['days'] == 2
    assert call('сколько дней между 2024-03-01 и 2024-02-28')['data']['days'] == -2

@pytest.mark.parametrize('when,expected', [
    ('2026-10-10', '1 день'), ('2026-10-11', '2 дня'), ('2026-10-14', '5 дней'),
    ('2026-10-20', '11 дней'), ('2026-10-30', '21 день'),
])
def test_calendar_day_labels(when, expected):
    assert tools.execute(dict(action='days_until', date=when), today=date(2026, 10, 9))['response'] == expected

def test_random_ranges_and_coin(monkeypatch):
    bounds = []
    def randbelow(bound): bounds.append(bound); return bound-1
    monkeypatch.setattr(tools.secrets, 'randbelow', randbelow)
    assert tools.execute(commands.parse('случайное число от -10 до 10'))['response'] == '10'
    assert tools.execute(commands.parse('брось кубик'))['response'] == '6'
    assert tools.execute(commands.parse('подбрось монету'))['response'] == 'Орёл'
    assert tools.execute(commands.parse('случайное число от 4 до 4'))['response'] == '4'
    assert bounds == [21, 6, 2, 1]

def test_stopwatch_lifecycle_and_no_pause_time():
    clock = [0.]
    watch = tools.Stopwatch(lambda: clock[0])
    assert watch.run('status')[1]['state'] == 'idle'
    watch.run('start')
    clock[0] = 1.25
    assert watch.run('lap')[1]['laps'] == [1.25]
    watch.run('start')  # Already running: retain the original start.
    clock[0] = 2.
    assert watch.run('pause')[1]['elapsed_seconds'] == 2
    clock[0] = 100.
    assert watch.run('status')[1]['elapsed_seconds'] == 2
    watch.run('resume')
    clock[0] = 101.5
    text, state = watch.run('stop')
    assert '00:00:03.500' in text and state['elapsed_seconds'] == 3.5
    clock[0] = 500.
    assert watch.run('status')[1]['elapsed_seconds'] == 3.5
    watch.run('start')
    assert watch.run('status')[1]['laps'] == []
    assert watch.run('reset')[1] == {'state': 'idle', 'elapsed_seconds': 0., 'laps': []}
    with pytest.raises(ValueError): watch.run('lap')

def test_stopwatch_concurrent_laps_and_limit():
    watch = tools.Stopwatch(lambda: 5.)
    watch.run('start')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: watch.run('lap'), range(100)))
    assert len(results[-1][1]['laps']) <= 100
    assert len(watch.run('status')[1]['laps']) == 100
    with pytest.raises(ValueError): watch.run('lap')

@pytest.fixture(scope='module')
def engines():
    from command_parser import CommandParser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    return dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())

@pytest.mark.parametrize('text', [
    'Скотт, посчитай 2+2', 'можешь перевести 2 километра в метры?',
    'запусти секундомер', 'сколько дней до 31.12.2026', 'брось кубик',
    'установи системную громкость на тридцать процентов',
    'увеличь громкость системы на десять процентов',
])
def test_real_chat_and_voice_routing(text, engines):
    import understanding
    assert understanding.chat_action(text, **engines).kind == 'utility'
    assert understanding.understand(text, **engines).kind == 'utility'

@pytest.mark.parametrize('text', [
    'не запускай секундомер', 'как работает команда «запусти секундомер»?',
    'напиши код: посчитай 2+2', '"выключи системный звук"',
    'расскажи как установить системную громкость на 30 процентов',
    'посчитай 2+2\nвыключи системный звук',
])
def test_chat_discussion_never_executes(text, engines):
    import understanding
    assert understanding.chat_action(text, **engines) is None

def test_custom_protocol_and_voice_settings_keep_priority(engines):
    import understanding
    custom = object()
    assert understanding.understand('запусти секундомер', find_protocol=lambda text: custom, **engines).protocol is custom
    result = understanding.understand('громкость голоса тридцать процентов', **engines)
    assert result.kind == 'action' and result.action == 'voice_settings'

@pytest.mark.parametrize('text', [
    'громкость -1', 'громкость 101', 'громкость 999999999', 'громкость много',
    'увеличь громкость на 101 процентов',
])
def test_invalid_volume_cannot_become_legacy_volume_up(text, engines, monkeypatch):
    import understanding
    decision = understanding.chat_action(text, **engines)
    assert decision.kind == 'utility'
    monkeypatch.setattr(volume, '_native', lambda *args: pytest.fail('Must reject before OS call'))
    assert tools.execute(decision.parsed)['success'] is False

@pytest.mark.parametrize('tool,status,expected', [
    ('wpctl', 'Volume: 0.45 [MUTED]', (45, True)),
    ('pactl', 'Volume: front-left: 29491 / 45% / -20.0 dB', (45, False)),
    ('amixer', 'Front Left: Playback 45 [45%] [on]', (45, False)),
    ('osascript', '45,true', (45, True)),
])
def test_read_platform_volume(tool, status, expected, monkeypatch):
    monkeypatch.setattr(volume, '_run', lambda cmd: 'Mute: no' if 'get-sink-mute' in cmd else status)
    assert volume._status(tool) == expected

@pytest.mark.parametrize('tool', ['wpctl', 'pactl', 'amixer', 'osascript'])
@pytest.mark.parametrize('operation,value', [('set', 30), ('delta', 80), ('delta', -80), ('mute', 1)])
def test_platform_writes_fixed_argv_and_verify(tool, operation, value, monkeypatch):
    import os_actions
    monkeypatch.setattr(os_actions, 'is_windows', lambda: False)
    monkeypatch.setattr(os_actions, 'current_os', lambda: os_actions.MACOS if tool == 'osascript' else os_actions.LINUX)
    monkeypatch.setattr(os_actions, 'find_tool', lambda *names: tool)
    calls = []
    monkeypatch.setattr(volume, '_run', lambda cmd: calls.append(cmd) or '')
    readings = []
    monkeypatch.setattr(volume, '_status', lambda selected: readings.append(selected) or (40, False))
    result = volume.execute(operation, value)
    assert result['success'] and result['data'] == {'volume': 40, 'muted': False}
    assert calls[0][0] == tool and len(calls) == 1
    assert len(readings) == (2 if operation == 'delta' else 1)
    if operation != 'mute':
        target = min(100, max(0, 40+value)) if operation == 'delta' else value
        assert any(str(target) in arg for arg in calls[0])
    if tool == 'wpctl' and operation != 'mute': assert calls[0][-2:] == ['--limit', '1.0']

@pytest.mark.parametrize('payload', [
    '{}', 'null', 'oops', '{"protocol":2,"success":true,"volume":30,"muted":false}',
    '{"protocol":true,"success":true,"volume":30,"muted":false}',
    '{"protocol":1,"success":true,"volume":true,"muted":false}',
    '{"protocol":1,"success":true,"volume":101,"muted":false}',
    '{"protocol":1,"success":true,"volume":30,"muted":0}',
])
def test_native_contract_rejects_bad_results(payload, monkeypatch):
    monkeypatch.setattr(volume, 'native_path', lambda: 'ScottSystem.exe')
    monkeypatch.setattr(volume, '_run', lambda cmd: payload)
    with pytest.raises(ValueError): volume._native('status', None)

def test_native_fixed_args_and_failure(monkeypatch):
    import os_actions
    monkeypatch.setattr(os_actions, 'is_windows', lambda: True)
    monkeypatch.setattr(volume, 'native_path', lambda: 'ScottSystem.exe')
    calls = []
    monkeypatch.setattr(volume, '_run', lambda cmd: calls.append(cmd) or json.dumps(dict(protocol=1, success=True, volume=30, muted=False)))
    assert volume.execute('set', 30)['success']
    assert calls == [['ScottSystem.exe', 'volume', '30']]
    monkeypatch.setattr(volume, '_run', lambda cmd: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd, 4)))
    assert volume.execute('status')['success'] is False

def test_catalog_examples_route_to_local_tools(engines):
    import abilities
    import understanding
    catalog = abilities.describe()
    for group in catalog['groups']:
        if group['group'] == 'Локальные инструменты':
            for item in group['items']:
                for example in item['examples']:
                    assert understanding.chat_action(example, **engines).kind == 'utility', example

def test_real_api_chat_command_voice_and_fresh_results(main_module, tmp_path, monkeypatch):
    import httpx
    from chat_store import ChatStore
    database = ChatStore(tmp_path/'chats')
    monkeypatch.setattr(main_module.chat_api, 'store', lambda: database)
    monkeypatch.setattr(main_module.chat_api, 'get_intelligent_answerer', lambda: None)
    monkeypatch.setattr(main_module, 'intelligent_answerer', None)
    monkeypatch.setattr(main_module, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main_module.memories_module, 'observe', lambda text: [])
    watch = tools.Stopwatch(lambda: 1.)
    monkeypatch.setattr(tools, 'stopwatch', watch)
    counts = iter([0, 1])
    monkeypatch.setattr(tools.secrets, 'randbelow', lambda bound: next(counts))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            ident = (await client.post('/chats')).json()['chat']['id']
            response = await client.post(f'/chats/{ident}/messages', data={'question': 'посчитай 0.1+0.2'})
            assert response.status_code == 200
            assert response.json()['chat']['messages'][-1]['text'] == '0.3'
            for expected in ('1', '2'):
                result = await main_module.scott_ai.process_command('брось кубик', quiet_mode=True, by_voice=True)
                assert result['success'] and result['response'] == expected
            result = await main_module.scott_ai.process_command('запусти секундомер', quiet_mode=True, by_voice=True)
            assert result['success'] and result['data']['state'] == 'running'
            result = await main_module.scott_ai.process_command('посчитай 1/0', quiet_mode=True)
            assert not result['success'] and result['type'] == 'utility_error'
    asyncio.run(check())
