"""Optional voice integration: no models, microphone, playback or personal data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from types import SimpleNamespace
import wave
import json
import hashlib

import httpx
import pytest

import audio_settings
import scott_voice
import scott_voice_engine as engine_module
from scott_voice_process import VoiceProcessError
import voice_config

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('device,expected',[('cuda',2),('cpu',4)])
@pytest.mark.parametrize('value',[None,'auto',' AUTO ','','0','17','-1','2.5','invalid'])
def test_worker_thread_defaults_and_invalid_override_are_bounded(tmp_path,monkeypatch,device,expected,value):
    monkeypatch.setenv('SCOTT_VOICE_DEVICE',device)
    if value is None:monkeypatch.delenv('SCOTT_VOICE_CPU_THREADS',raising=False)
    else:monkeypatch.setenv('SCOTT_VOICE_CPU_THREADS',value)
    config=engine_module.default_config(tmp_path)
    assert config.device==device and config.cpu_threads==expected
    assert config.wire()['cpu_threads']==expected
    assert not config.rms_norm


@pytest.mark.parametrize('value',[1,4,16])
def test_explicit_thread_override_survives_acceleration_changes(tmp_path,monkeypatch,value):
    monkeypatch.setenv('SCOTT_VOICE_DEVICE','cuda')
    monkeypatch.setenv('SCOTT_VOICE_CPU_THREADS',str(value))
    engine=engine_module.ScottVoiceEngine(engine_module.default_config(tmp_path))
    for accelerated in (True,False):
        engine.set_acceleration(accelerated)
        assert engine.config.cpu_threads==value and engine.config.rms_norm is accelerated
        assert engine_module.VoiceProcessConfig.from_wire(engine.config.wire()).cpu_threads==value


@pytest.mark.parametrize('setting,ordinary,accelerated',[('auto',2,4),('',2,4),('1',1,1),('4',4,4),('16',16,16)])
def test_application_switch_uses_mode_defaults_or_explicit_override(tmp_path,monkeypatch,setting,ordinary,accelerated):
    monkeypatch.setenv('SCOTT_VOICE_DEVICE','cuda')
    monkeypatch.setenv('SCOTT_VOICE_CPU_THREADS',setting)
    monkeypatch.setattr(engine_module,'preferred_config',lambda:engine_module.config_at(tmp_path))
    engine=engine_module.ScottVoiceEngine()
    assert engine.config.cpu_threads==ordinary
    engine.set_acceleration(True)
    assert engine.config.rms_norm and engine.config.cpu_threads==accelerated
    engine.set_acceleration(False)
    assert not engine.config.rms_norm and engine.config.cpu_threads==ordinary


def test_saved_rms_preference_keeps_four_threads_without_rewriting_settings(tmp_path,monkeypatch):
    monkeypatch.setenv('SCOTT_VOICE_DEVICE','cuda')
    monkeypatch.setenv('SCOTT_VOICE_CPU_THREADS','auto')
    monkeypatch.setattr(engine_module,'default_config',lambda:engine_module.config_at(tmp_path))
    voice_config.save_voice('scott-voice',profile='digital',acceleration=True)
    original=voice_config.CONFIG_PATH.read_bytes()
    config=engine_module.preferred_config()
    assert config.rms_norm and config.cpu_threads==4
    assert engine_module.default_config().cpu_threads==2 and not engine_module.default_config().rms_norm
    assert voice_config.CONFIG_PATH.read_bytes()==original


@pytest.fixture
def installed_assets(tmp_path, monkeypatch):
    config = engine_module.default_config(tmp_path)
    required = ['config.json', 'generation_config.json', 'merges.txt', 'model.safetensors',
                'preprocessor_config.json', 'tokenizer_config.json', 'vocab.json',
                'speech_tokenizer/config.json', 'speech_tokenizer/configuration.json',
                'speech_tokenizer/model.safetensors', 'speech_tokenizer/preprocessor_config.json']
    for path in [config.python, config.worker, config.profiles_json, *[config.model_dir/name for name in required]]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}', encoding='utf-8')
    (config.model_dir/'scott-model.json').write_text(json.dumps(dict(model='fixture', revision='fixture', files=required+['.gitattributes', 'README.md'])))
    config.reference_json.parent.mkdir(parents=True)
    reference = config.reference_json.with_name('scott-reference.wav')
    wav(reference)
    config.reference_json.write_text(json.dumps(dict(sha256=hashlib.sha256(reference.read_bytes()).hexdigest())))
    monkeypatch.setattr(engine_module, '_probe_runtime', lambda *args: '')
    return config


def wav(path):
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b'\x01\x00'*240)
    return str(path)


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, 'inspect_installation', lambda _: '')
    calls = []
    class Client:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.failure = None
            self.started = threading.Event()
            self.release = threading.Event()
            self.block = False
        def synthesize(self, text, profile):
            calls.append((text, profile))
            self.started.set()
            if self.block:
                assert self.release.wait(3)
            if self.closed:
                raise VoiceProcessError('cancelled')
            if self.failure:
                raise VoiceProcessError(self.failure)
            return SimpleNamespace(path=wav(tmp_path/'optional.wav'))
        def close(self):
            self.closed = True
            self.release.set()
    clients = []
    def factory(*args, **kwargs):
        client = Client()
        clients.append(client)
        return client
    engine = engine_module.ScottVoiceEngine(engine_module.default_config(tmp_path), factory)
    monkeypatch.setattr(engine_module, '_engine', engine)
    voice = scott_voice.ScottVoice.__new__(scott_voice.ScottVoice)
    voice.audio_dir = tmp_path/'cache'
    voice.audio_dir.mkdir()
    voice.engine = None
    monkeypatch.setattr(audio_settings, 'get_character', lambda: 'natural')
    yield SimpleNamespace(engine=engine, voice=voice, clients=clients, calls=calls)
    engine.close()


def test_uninstalled_engine_remains_default_without_starting_worker(tmp_path, monkeypatch):
    engine = engine_module.ScottVoiceEngine(engine_module.default_config(tmp_path))
    monkeypatch.setattr(engine_module, '_engine', engine)
    original = b'{"voice":"ru-RU-DmitryNeural"}'
    voice_config.CONFIG_PATH.write_bytes(original)
    info = next(v for v in scott_voice.describe_voices()['voices'] if v['id'] == 'scott-voice')
    assert (info['available'], info['local'], info['engine']) == (False, True, 'qwen')
    assert info['reason'] and info['state'] == 'unavailable'
    assert not scott_voice.set_current_voice('scott-voice')
    assert scott_voice.get_current_voice() == 'scott-voice'
    assert voice_config.CONFIG_PATH.read_bytes() == original
    assert engine._client is None


def test_installation_requires_runtime_files_but_not_hub_metadata(installed_assets):
    assert engine_module.inspect_installation(installed_assets) == ''
    assert not (installed_assets.model_dir/'.gitattributes').exists()


def test_missing_weights_fail_before_runtime_probe(installed_assets, monkeypatch):
    (installed_assets.model_dir/'model.safetensors').unlink()
    monkeypatch.setattr(engine_module, '_probe_runtime', lambda *args: pytest.fail('Incomplete weights probed'))
    assert engine_module.inspect_installation(installed_assets) == 'invalid_assets'


def test_manifest_cannot_reference_files_outside_model(installed_assets):
    path = installed_assets.model_dir/'scott-model.json'
    value = json.loads(path.read_text())
    value['files'].append('../outside.safetensors')
    path.write_text(json.dumps(value))
    assert engine_module.inspect_installation(installed_assets) == 'invalid_assets'


def test_profile_survives_reselection_and_removes_legacy_fallback_on_save(integrated):
    voice_config.CONFIG_PATH.write_text('{"voice":"eugene","fallback_voice":"aidar"}',encoding='utf-8')
    assert scott_voice.set_current_voice('scott-voice', 'restrained')
    assert voice_config.get_scott_profile() == 'restrained'
    assert 'fallback_voice' not in json.loads(voice_config.CONFIG_PATH.read_text())
    assert not scott_voice.set_current_voice('ru-RU-DmitryNeural')
    scott_voice.set_current_voice('scott-voice')
    assert voice_config.get_scott_profile() == 'restrained'
    assert 'fallback_voice' not in json.loads(voice_config.CONFIG_PATH.read_text())
    assert integrated.clients == []  # Saving/selecting never synthesizes speech.


@pytest.mark.parametrize('value', ['unknown', None, 7, ['scott']])
def test_invalid_saved_profile_uses_approved_original(value):
    import json
    voice_config.CONFIG_PATH.write_text(json.dumps({'scott_profile': value}), encoding='utf-8')
    assert voice_config.get_scott_profile() == 'scott'


def test_optional_voice_uses_its_profile_and_keeps_legacy_processing_out(integrated):
    voice_config.save_voice('scott-voice', 'digital')
    integrated.voice._придать_характер = lambda *args: pytest.fail('Unexpected legacy processing')
    path = integrated.voice.speak_to_file('Тест')
    assert path and integrated.calls == [('Тест', 'digital')]
    assert integrated.engine.describe()['state'] == 'ready'


def test_runtime_failure_keeps_scott_choice_and_cooldown_without_fallback(integrated, monkeypatch):
    scott_voice.set_current_voice('scott-voice')
    integrated.engine.synthesize('init')
    integrated.clients[0].failure = 'timeout'
    assert integrated.voice.speak_to_file('Проверка') is None
    assert scott_voice.get_current_voice() == 'scott-voice'
    assert integrated.engine.describe()['state'] == 'error'
    info = next(v for v in scott_voice.describe_voices()['voices'] if v['id'] == 'scott-voice')
    assert info['error'] == 'timeout' and info['reason']
    assert 'fallback_id' not in info
    before = len(integrated.calls)
    assert integrated.voice.speak_to_file('Ещё одна проверка') is None
    assert len(integrated.calls) == before  # Cooldown prevents repeated slow failures.


def test_missing_runtime_after_restart_does_not_use_saved_fallback(integrated, monkeypatch):
    original=b'{"voice":"scott-voice","fallback_voice":"eugene"}'
    voice_config.CONFIG_PATH.write_bytes(original)
    monkeypatch.setattr(engine_module, 'inspect_installation', lambda _: 'not_installed')
    assert integrated.voice.speak_to_file('Тест') is None
    assert integrated.clients == []
    assert voice_config.CONFIG_PATH.read_bytes() == original
    assert scott_voice.get_current_voice() == 'scott-voice'


def test_cancelled_and_queued_old_requests_never_fall_back(integrated, monkeypatch):
    voice_config.save_voice('scott-voice')
    integrated.engine.synthesize('init')
    client = integrated.clients[0]
    client.block = True
    client.started.clear()
    waiting = threading.Event()
    lock = threading.RLock()
    class ObservedLock:
        def __enter__(self):
            if not lock.acquire(blocking=False):
                waiting.set()
                lock.acquire()
        def __exit__(self, *args):
            lock.release()
    integrated.voice._synthesis_lock = ObservedLock()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(integrated.voice.speak_to_file, 'old')
        assert client.started.wait(1)
        second = pool.submit(integrated.voice.speak_to_file, 'queued')
        assert waiting.wait(1)
        integrated.engine.cancel()
        assert first.result() is None
        assert second.result() is None
    assert client.closed and len(integrated.clients) == 1
    assert integrated.voice.speak_to_file('new')
    assert len(integrated.clients) == 2


def test_quiet_control_cancels_optional_synthesis(integrated):
    import audio_endpoints
    integrated.engine.synthesize('init')
    client = integrated.clients[0]
    audio_endpoints._stop_current_speech()
    assert client.closed and integrated.engine._client is None


def test_factory_failure_has_safe_status_and_can_retry(integrated):
    def broken(*args, **kwargs):
        raise ValueError('private filesystem detail')
    integrated.engine.factory = broken
    with pytest.raises(VoiceProcessError, match='synthesis_failed'):
        integrated.engine.synthesize('Тест')
    info = integrated.engine.describe()
    assert info['state'] == 'error' and 'private' not in str(info)


def test_voice_routes_validate_profile_and_preserve_selection(main_module, integrated, monkeypatch):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            catalog = (await client.get('/voice/available?gender=male')).json()
            assert catalog['scott_profile'] == 'scott'
            assert all(v['gender'] == 'male' for v in catalog['voices'])
            response = await client.post('/voice/select', json={'voice':'scott-voice', 'profile':'restrained'})
            assert response.json()['success']
            assert voice_config.get_scott_profile() == 'restrained'
            for body in ({'voice':'scott-voice', 'profile':'unknown'}, {'voice':'eugene', 'profile':'scott'}, {'voice':'scott-voice', 'profile':[]}):
                assert (await client.post('/voice/select', json=body)).status_code == 400
            monkeypatch.setattr(engine_module, 'inspect_installation', lambda _: 'not_installed')
            response = await client.post('/voice/select', json={'voice':'scott-voice'})
            assert response.status_code == 503 and response.json()['message']
            assert scott_voice.get_current_voice() == 'scott-voice'
    asyncio.run(run())


def test_catalog_probe_does_not_block_health(main_module, integrated, monkeypatch):
    import time
    entered = threading.Event()
    def probe(_):
        entered.set()
        time.sleep(.15)
        return ''
    monkeypatch.setattr(engine_module, 'inspect_installation', probe)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            pending = asyncio.create_task(client.get('/voice/available'))
            assert await asyncio.to_thread(entered.wait, 1)
            health = await client.get('/health')
            assert health.status_code == 200 and not pending.done()
            assert (await pending).status_code == 200
    asyncio.run(run())


def test_long_optional_answer_is_split_without_losing_words():
    text = 'Это достаточно длинное предложение без точки ' * 35
    chunks = engine_module.speech_chunks(text)
    assert len(chunks) > 5 and all(len(chunk) <= 180 for chunk in chunks)
    assert ' '.join(chunks).split() == text.split()


def test_long_first_sentence_starts_at_a_clause_boundary():
    first = 'Проверка завершена, все необходимые настройки сохранены,'
    continuation = 'соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью.'
    assert engine_module.speech_chunks(first+' '+continuation) == [first, continuation]


@pytest.mark.parametrize('text', [
    'Соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью ' * 3,
    'Сначала проверим подключение и сохранённые настройки: после завершения проверки можно продолжить работу с выбранной моделью.',
    'Сначала проверим подключение и сохранённые настройки — после завершения проверки можно продолжить работу с выбранной моделью.',
    'Уровень заряда 37 процентов, громкость 40 процентов и свободно 256 мегабайт; все необходимые настройки приложения сохранены.',
])
def test_first_fragment_is_bounded_and_preserves_prepared_words(text):
    from speech_text import prepare_for_speech
    expected = prepare_for_speech(text, accents=False)
    chunks = engine_module.speech_chunks(text)
    assert 40 <= len(chunks[0]) <= 90
    assert all(chunk and len(chunk) <= 180 for chunk in chunks)
    assert ' '.join(chunks).split() == expected.split()


@pytest.mark.parametrize('text', [
    'Готово.', 'Слушаю.', 'Соединение восстановлено.',
    'Соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью.',
])
def test_short_optional_answers_remain_whole(text):
    assert len(text) <= 110
    assert engine_module.speech_chunks(text) == [text]


def test_short_first_does_not_break_a_long_word_or_add_an_empty_chunk():
    word = 'длинноеслово'*10
    text = word+' сохранены все необходимые настройки приложения.'
    chunks = engine_module.speech_chunks(text)
    assert all(chunks) and ' '.join(chunks) == text
    assert chunks[0] == word
    assert engine_module.speech_chunks(word+'длинноеслово') == [word+'длинноеслово']


def test_stop_after_first_fragment_does_not_synthesize_continuation(integrated, monkeypatch):
    import speech_player
    voice_config.save_voice('scott-voice')
    player = SimpleNamespace(generation=0)
    monkeypatch.setattr(speech_player, 'get_player', lambda: player)
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: False)
    text = ('Проверка завершена, все необходимые настройки сохранены, '
            'соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью.')
    spoken, played = [], []
    monkeypatch.setattr(integrated.voice, 'speak_to_file', lambda chunk: spoken.append(chunk) or 'first.wav')
    def play(path, **options):
        played.append((path, options['wait']))
        player.generation += 1
    monkeypatch.setattr(integrated.voice, 'play_audio', play)
    assert integrated.voice.speak(text) is None
    assert spoken == [engine_module.speech_chunks(text)[0]]
    assert played == [('first.wav', False)]


def test_optional_reply_accepts_stop_during_preparation(main_module, integrated, monkeypatch):
    import runtime
    voice_config.save_voice('scott-voice')
    started = threading.Event()
    release = threading.Event()
    played, expectations = [], []
    def synthesize(text):
        started.set()
        assert release.wait(2)
        return 'not-played.wav'
    monkeypatch.setattr(runtime, 'scott_voice', SimpleNamespace(speak_to_file=synthesize, play_audio=lambda *args, **kwargs: played.append(args)))
    monkeypatch.setattr(runtime, 'listener', SimpleNamespace(expect_interruption=expectations.append, stop_expecting=lambda: None))
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: False)
    async def run():
        generation = main_module._next_voice_response()
        reply = asyncio.create_task(main_module._play_voice_response('Проверочный ответ.', generation))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            assert expectations == ['Проверочный ответ.']
            main_module._listener_interrupted('стоп')
        finally:
            release.set()
        assert not await reply and played == []
    asyncio.run(run())


def test_optional_long_reply_preserves_playback_order(main_module, integrated, monkeypatch):
    import runtime
    voice_config.save_voice('scott-voice')
    text = 'Проверочное длинное предложение без точки ' * 15
    spoken, played = [], []
    def synthesize(chunk):
        spoken.append(chunk)
        return chunk
    monkeypatch.setattr(runtime, 'scott_voice', SimpleNamespace(speak_to_file=synthesize, play_audio=lambda path, **kwargs: played.append((path, kwargs['wait']))))
    monkeypatch.setattr(runtime, 'listener', None)
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: False)
    assert asyncio.run(main_module._play_voice_response(text))
    assert ' '.join(spoken).split() == text.split()
    assert [path for path, wait in played] == spoken
    assert [wait for path, wait in played] == [False]*(len(played)-1)+[True]


def test_optional_reply_discards_continuation_after_first_playback(main_module, integrated, monkeypatch):
    import runtime
    voice_config.save_voice('scott-voice')
    text = ('Проверка завершена, все необходимые настройки сохранены, '
            'соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью.')
    spoken, played, echo = [], [], []
    def synthesize(chunk):
        spoken.append(chunk)
        return 'first.wav'
    def play(path, **options):
        played.append((path, options['wait']))
        main_module._next_voice_response()
    monkeypatch.setattr(runtime, 'scott_voice', SimpleNamespace(speak_to_file=synthesize, play_audio=play))
    monkeypatch.setattr(runtime, 'listener', SimpleNamespace(expect_interruption=lambda _: echo.append('start'),
        stop_expecting=lambda: echo.append('stop')))
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: False)
    generation = main_module._next_voice_response()
    assert not asyncio.run(main_module._play_voice_response(text, generation))
    assert spoken == [engine_module.speech_chunks(text)[0]]
    assert played == [('first.wav', False)] and echo == ['start', 'stop']


@pytest.mark.parametrize('name', ['скотт войс', 'скоттвойс', 'Scott Voice'])
def test_optional_voice_can_be_selected_by_name(integrated, name):
    import voice_commands
    command = voice_commands.parse('выбери голос '+name)
    assert (command.action, command.value) == ('select', 'scott-voice')
    assert voice_commands.execute(command.action, command.value).startswith('Теперь')
    assert scott_voice.get_current_voice() == 'scott-voice'


@pytest.mark.parametrize('name,profile', [('исходный','natural'), ('сдержанный','restrained'), ('скотт','scott'), ('цифровой','digital')])
def test_optional_character_command_changes_the_actual_profile(integrated, name, profile):
    import voice_commands
    voice_config.save_voice('scott-voice')
    command = voice_commands.parse('выбери стиль голоса '+name)
    assert command.action == 'character' and command.value == profile
    assert voice_commands.execute(command.action, command.value).startswith('Характер Scott Voice')
    assert voice_config.get_scott_profile() == profile


def test_optional_character_does_not_acknowledge_unused_legacy_effect(integrated):
    import voice_commands
    voice_config.save_voice('scott-voice', 'digital')
    assert voice_commands.execute('character', 'speaker').startswith('❌')
    assert voice_config.get_scott_profile() == 'digital'
