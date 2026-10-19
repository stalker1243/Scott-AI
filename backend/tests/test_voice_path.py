"""Whole listener-to-reply route with synthetic input and isolated side effects."""
import asyncio
from types import SimpleNamespace
import time

import pytest

pytestmark = pytest.mark.unit

@pytest.mark.parametrize('text', [
    'посчитай 2+2', 'переведи 2 километра в метры', 'запусти секундомер',
    'поставь секундомер на паузу', 'сколько на секундомере',
    'какая сегодня дата', 'брось кубик', 'покажи системную громкость',
])
def test_new_tools_are_followup_commands(main_module, text):
    assert main_module._похоже_на_команду(text)

@pytest.mark.parametrize('text', [
    'расскажи о погоде', 'не запускай секундомер', 'как работает калькулятор',
    'мой скотт вычислил результат',
])
def test_conversation_is_not_a_followup_command(main_module, text):
    assert not main_module._похоже_на_команду(text)

def test_browser_followup_uses_enabled_browser_route(main_module, monkeypatch):
    import browser_control_jobs
    monkeypatch.setattr(browser_control_jobs, 'jobs', SimpleNamespace(enabled=True))
    assert main_module._похоже_на_команду('поставь на паузу ютуб')
    assert not main_module._похоже_на_команду('объясни как поставить видео на паузу')

@pytest.fixture(scope='module')
def engines():
    from command_parser import CommandParser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    return dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())

@pytest.mark.parametrize('spoken,heard', [
    ('посчитай двадцать пять плюс десять', 'Посчитай 25 плюс 10.'),
    ('переведи два километра в метры', 'Переведи 2 км в метры.'),
    ('двадцать процентов от ста', '20 процентов от 100'),
    ('запусти секундомер', 'Запусти секундомер.'),
    ('увеличь громкость на десять процентов', 'Увеличь громкость на 10 процентов.'),
])
def test_accuracy_compares_effective_local_payload_without_execution(spoken, heard, engines, monkeypatch):
    import accuracy_voice
    import understanding
    import local_tools
    import system_volume
    monkeypatch.setattr(local_tools, 'execute', lambda *args: pytest.fail('Accuracy must not execute commands'))
    monkeypatch.setattr(system_volume, 'execute', lambda *args: pytest.fail('Must not change output device'))
    first = understanding.understand(spoken, **engines)
    last = understanding.understand(heard, **engines)
    assert accuracy_voice._same_decision(first, last)

@pytest.mark.parametrize('first,last', [
    ('посчитай 15+1', 'посчитай 50+1'),
    ('переведи 2 километра в метры', 'переведи 2 сантиметра в метры'),
    ('запусти секундомер', 'останови секундомер'),
    ('установи системную громкость на 15 процентов', 'установи системную громкость на 50 процентов'),
    ('15 процентов от 200', '50 процентов от 200'),
])
def test_changed_local_payload_is_an_accuracy_miss(first, last, engines):
    import accuracy_voice
    import understanding
    assert not accuracy_voice._same_decision(understanding.understand(first, **engines), understanding.understand(last, **engines))

def test_listener_command_reply_followup_and_expiry(main_module, monkeypatch, tmp_path):
    import listener
    import audio_settings
    import scott_voice
    import local_tools
    from voice_name_trigger import check_voice_trigger
    main = main_module
    voiced = []
    futures = []
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: False)
    monkeypatch.setattr(scott_voice, 'get_current_voice', lambda: 'eugene')
    monkeypatch.setattr(main, 'THINKING_CUE_AFTER_SECONDS', 10)
    monkeypatch.setattr(main.memories_module, 'observe', lambda text: [])
    monkeypatch.setattr(local_tools, 'stopwatch', local_tools.Stopwatch(lambda: 1.))
    voice = SimpleNamespace(speak_to_file=lambda text: text, play_audio=lambda text: voiced.append(text))
    listening = listener.VoiceListener(transcribe=lambda audio: '',
        handle_command=lambda text: futures.append(main._listener_handle(text)),
        check_trigger=check_voice_trigger, looks_like_command=main._похоже_на_команду)
    monkeypatch.setattr(listening, '_записать_услышанное', lambda *args: None)
    monkeypatch.setattr(main.scott_runtime, 'listener', listening)
    monkeypatch.setattr(main.scott_runtime, 'scott_voice', voice)
    async def check():
        monkeypatch.setattr(main, '_main_loop', asyncio.get_running_loop())
        listening._dispatch('Скотт, посчитай 2+2')
        await asyncio.wrap_future(futures[-1])
        assert voiced[-1] == '4'
        listening._dispatch('запусти секундомер')
        assert len(futures) == 2
        await asyncio.wrap_future(futures[-1])
        assert 'Секундомер работает' in voiced[-1]
        listening._dispatch('не запускай секундомер')
        assert len(futures) == 2
        listening._answered_at = time.time()-60
        listening._dispatch('посчитай 2+2')
        assert len(futures) == 2
        assert listening.stats.ignored == 2
    asyncio.run(check())


def test_listener_introduction_speaks_offer_and_accepts_yes_without_wake_name(main_module, monkeypatch):
    import listener
    import scott_voice
    from assistant_identity import VoiceIntroduction, INTRODUCTION, CREATOR, HOW_IT_WORKS, DECLINED
    from voice_name_trigger import check_voice_trigger
    main = main_module
    voiced, futures = [], []
    monkeypatch.setattr(scott_voice, 'get_current_voice', lambda: 'eugene')
    monkeypatch.setattr(main.scott_ai, '_identity_dialogue', VoiceIntroduction())
    monkeypatch.setattr(main.scott_ai, '_browser_decision', lambda *a: None)
    async def speak(text, generation=None):
        voiced.append(text)
        return True
    monkeypatch.setattr(main, '_play_voice_response', speak)
    listening = listener.VoiceListener(transcribe=lambda audio: '',
        handle_command=lambda text: futures.append(main._listener_handle(text)),
        check_trigger=check_voice_trigger, looks_like_command=main._похоже_на_команду)
    monkeypatch.setattr(listening, '_записать_услышанное', lambda *args: None)
    monkeypatch.setattr(main.scott_runtime, 'listener', listening)
    async def check():
        monkeypatch.setattr(main, '_main_loop', asyncio.get_running_loop())
        for text in ('Скотт, кто ты?', 'Да, расскажи подробнее',
                     'Скотт, кто твой создатель?', 'Нет, спасибо'):
            count = len(futures)
            listening._dispatch(text)
            assert len(futures) == count + 1
            await asyncio.wrap_future(futures[-1])
        assert voiced == [INTRODUCTION, HOW_IT_WORKS, CREATOR, DECLINED]
        listening._dispatch('Да')
        assert len(futures) == 4
        # The listener's normal ten-second wake-name window still applies.
        listening._dispatch('Скотт, кто ты?')
        await asyncio.wrap_future(futures[-1])
        listening._answered_at = time.time() - 60
        listening._dispatch('Да')
        assert len(futures) == 5
    asyncio.run(check())

@pytest.mark.parametrize('stop', ['Скотт стоп', 'Скотт, хватит!', 'Scott замолчи', 'Скотт достаточно'])
def test_named_stop_cancels_pending_reply_without_a_new_model_request(main_module, monkeypatch, stop):
    import listener
    import scott_voice
    import scott_voice_engine
    import speech_player
    from voice_name_trigger import check_voice_trigger
    main = main_module
    requests, futures, stopped, spoken = [], [], [], []
    monkeypatch.setattr(scott_voice, 'get_current_voice', lambda: 'eugene')
    monkeypatch.setattr(scott_voice_engine, 'cancel', lambda: stopped.append('synthesis'))
    monkeypatch.setattr(speech_player, 'PLAYBACK_AVAILABLE', True)
    monkeypatch.setattr(speech_player, 'get_player', lambda: SimpleNamespace(stop=lambda: stopped.append('playback')))
    monkeypatch.setattr(main, 'THINKING_CUE_AFTER_SECONDS', 10)
    listening = listener.VoiceListener(transcribe=lambda audio: '',
        handle_command=lambda text: futures.append(main._listener_handle(text)),
        check_trigger=check_voice_trigger, looks_like_command=main._похоже_на_команду,
        on_interrupt=main._listener_interrupted)
    monkeypatch.setattr(listening, '_записать_услышанное', lambda *args: None)
    monkeypatch.setattr(main.scott_runtime, 'listener', listening)
    async def check():
        monkeypatch.setattr(main, '_main_loop', asyncio.get_running_loop())
        begin, release = asyncio.Event(), asyncio.Event()
        async def command(text, **options):
            requests.append(text); begin.set(); await release.wait()
            return {'response': 'Ответ после ожидания'}
        async def reply(text, generation=None): spoken.append(text); return True
        monkeypatch.setattr(main.scott_ai, 'process_command', command)
        monkeypatch.setattr(main, '_play_voice_response', reply)
        listening._dispatch('Скотт расскажи про космос')
        await begin.wait()
        try:
            listening._dispatch(stop)
        finally:
            release.set()
            for future in futures: await asyncio.wrap_future(future)
        assert requests == ['расскажи про космос']
        assert stopped == ['synthesis', 'playback']
        assert spoken == []
    asyncio.run(check())

@pytest.mark.parametrize('phrase', ['Скотт скажи слово стоп', 'Скотт не говори стоп', 'Спасибо Скотт'])
def test_named_stop_mention_keeps_normal_dispatch(phrase, monkeypatch):
    import listener
    from voice_name_trigger import check_voice_trigger
    called, interrupted = [], []
    instance = listener.VoiceListener(transcribe=lambda audio: '', handle_command=called.append,
        check_trigger=check_voice_trigger, on_interrupt=interrupted.append)
    monkeypatch.setattr(instance, '_записать_услышанное', lambda *args: None)
    instance._dispatch(phrase)
    assert called and not interrupted


def test_unnamed_stop_outside_speech_window_is_ignored(monkeypatch):
    import listener
    from voice_name_trigger import check_voice_trigger
    called, interrupted = [], []
    instance = listener.VoiceListener(transcribe=lambda audio: '', handle_command=called.append,
        check_trigger=check_voice_trigger, on_interrupt=interrupted.append)
    monkeypatch.setattr(instance, '_записать_услышанное', lambda *args: None)
    instance._dispatch('стоп')
    assert not called and not interrupted
    assert instance.stats.ignored == 1
