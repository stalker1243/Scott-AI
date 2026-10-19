"""Only male choices can reach synthesis, including old settings and system fallback."""
import asyncio
import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
import httpx
import pytest
import scott_voice as tts
import silero_tts
import voice_commands
import voice_config

pytestmark=pytest.mark.unit
RETIRED=('ru-RU-SvetlanaNeural','baya','kseniya','xenia')


def test_catalog_and_spoken_catalog_only_contain_male_voices():
    assert set(silero_tts.SILERO_VOICES)=={'aidar','eugene'}
    assert set(tts.VOICE_GENDERS.values())=={'male'}
    assert not set(RETIRED)&set(tts.AVAILABLE_VOICES)
    assert not set(RETIRED)&set(voice_commands.ALIASES.values())
    assert tts.describe_voices('female')['voices']==[]


@pytest.mark.parametrize('retired',RETIRED)
def test_old_choice_and_scott_fallback_resolve_to_male_without_rewriting_settings(tmp_path,monkeypatch,retired):
    path=tmp_path/'voice.json';monkeypatch.setattr(voice_config,'CONFIG_PATH',path)
    original=json.dumps({'voice':retired,'fallback_voice':retired,'scott_profile':'scott'}).encode()
    path.write_bytes(original)
    current=tts.get_current_voice()
    assert current in tts.AVAILABLE_VOICES and tts.VOICE_GENDERS[current]=='male'
    assert voice_config.get_fallback_voice('aidar',tts.AVAILABLE_VOICES)=='aidar'
    assert not tts.set_current_voice(retired)
    assert path.read_bytes()==original


@pytest.mark.parametrize('value',['baya','kseniya','xenia','unknown'])
def test_retired_environment_defaults_cannot_select_female(value,monkeypatch):
    monkeypatch.setenv('SILERO_VOICE',value);monkeypatch.setenv('TTS_VOICE','ru-RU-SvetlanaNeural')
    data=runpy.run_path(str(Path(silero_tts.__file__)))
    assert data['DEFAULT_SILERO_VOICE']=='aidar'
    data=runpy.run_path(str(Path(tts.__file__)))
    assert data['DEFAULT_VOICE'] in tts.AVAILABLE_VOICES
    assert tts.VOICE_GENDERS[data['DEFAULT_VOICE']]=='male'


@pytest.mark.parametrize('value',RETIRED)
def test_retired_voice_cannot_reach_provider_or_return_old_audio(tmp_path,monkeypatch,value):
    voice=tts.ScottVoice.__new__(tts.ScottVoice);voice.audio_dir=tmp_path;voice.engine=None
    monkeypatch.setattr(voice,'_save_edge_tts',lambda *args:pytest.fail('Retired voice reached provider'))
    assert voice.speak_to_file('Синтетическая проверка.',voice=value) is None


def test_system_voice_prefers_verified_male_russian_and_handles_byte_languages():
    find=tts.ScottVoice.__new__(tts.ScottVoice)._find_russian_voice
    female=SimpleNamespace(name='Microsoft Irina',gender='Female',languages=[b'\x05ru'])
    unknown=SimpleNamespace(name='Unknown Russian',languages=['ru'])
    david=SimpleNamespace(name='Microsoft David',gender='Male',languages=['en_US'])
    pavel=SimpleNamespace(name='Microsoft Pavel Desktop',languages=[b'\x05ru-RU'])
    assert find([female,unknown,david,pavel]) is pavel
    assert find([female,unknown,david]) is david
    assert find([female,unknown]) is None
    assert find([SimpleNamespace(name='Dmitry',gender='Female',languages=['ru'])]) is None
    assert find([]) is None


def test_only_female_system_installation_does_not_keep_default_engine(tmp_path,monkeypatch):
    import storage_paths
    selected=[]
    female=SimpleNamespace(name='Microsoft Irina',gender='Female',languages=['ru'])
    engine=SimpleNamespace(getProperty=lambda key:[female],
        setProperty=lambda key,value:selected.append((key,value)),stop=lambda:None)
    monkeypatch.setattr(tts.pyttsx3,'init',lambda:engine)
    monkeypatch.setattr(storage_paths,'audio_cache',lambda:tmp_path)
    monkeypatch.setattr(tts.ScottVoice,'_start_tts_worker',lambda self:None)
    instance=tts.ScottVoice()
    assert instance.engine is None
    assert not any(key=='voice' for key,value in selected)


def test_system_worker_rejects_female_only_inventory(tmp_path,monkeypatch):
    import queue
    engine=SimpleNamespace(getProperty=lambda key:[SimpleNamespace(name='Irina',gender='Female',languages=['ru'])],
        setProperty=lambda *args:None,stop=lambda:None,
        save_to_file=lambda *args:pytest.fail('Female default reached system synthesis'))
    monkeypatch.setattr(tts.pyttsx3,'init',lambda:engine)
    instance=tts.ScottVoice.__new__(tts.ScottVoice);instance.tts_queue=queue.Queue()
    result=queue.Queue();instance.tts_queue.put(('Fixture',str(tmp_path/'audio.wav'),result));instance.tts_queue.put(None)
    instance._tts_worker()
    assert result.get_nowait() is None


@pytest.mark.parametrize('value',(*RETIRED,[],123,''))
def test_api_rejects_retired_or_invalid_explicit_voice_before_synthesis(main_module,monkeypatch,value):
    fake=SimpleNamespace(speak_to_file=lambda *args,**kwargs:pytest.fail('Invalid voice reached synthesis'))
    monkeypatch.setattr(main_module.scott_ai,'scott_voice',fake)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),base_url='http://localhost') as client:
            for path in ('/voice/select','/text_to_speech'):
                response=await client.post(path,json={'voice':value,'text':'Синтетическая проверка.'})
                assert response.status_code==400
    asyncio.run(check())


def test_system_fallback_does_not_reuse_pre_policy_cache(tmp_path,monkeypatch):
    voice=tts.ScottVoice.__new__(tts.ScottVoice);voice.audio_dir=tmp_path;voice.engine=True
    text='Синтетическая проверка.'
    old=tmp_path/('scott_'+hashlib.sha256(f'pyttsx3:{text}'.encode()).hexdigest()[:24]+'.wav')
    old.write_bytes(b'old potentially female audio')
    monkeypatch.setattr(tts,'HAS_EDGE_TTS',False);monkeypatch.setattr(tts,'HAS_SILERO',False)
    monkeypatch.setattr(voice,'_cache_synthesis',lambda path,*args:str(path))
    result=voice.speak_to_file(text,voice='ru-RU-DmitryNeural')
    assert result and Path(result)!=old and old.read_bytes()==b'old potentially female audio'
