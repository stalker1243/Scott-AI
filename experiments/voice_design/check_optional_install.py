"""Verify a fresh optional runtime through synthetic WAV/STT, never commands or playback."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import wave

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from scott_voice_engine import ScottVoiceEngine, config_at
from scott_voice_install import REFERENCE_SHA, check, home_path
from benchmark_base import Backend

def main():
    output = ROOT/'reports/voice-setup'
    output.mkdir(parents=True, exist_ok=True)
    home = home_path(ROOT)
    before_reference = hashlib.sha256((ROOT/'assets/scott-voice/reference/scott-reference.wav').read_bytes()).hexdigest()
    assert before_reference == REFERENCE_SHA
    result = dict(installation=check(home, deep=True), samples=[], health_errors=[])
    assert result['installation']['available']
    backend = Backend('http://127.0.0.1:8000')
    catalog, _ = backend.get('/voice/available', timeout=25)
    selected = catalog['current']
    job, _ = backend.get('/voice/install')
    assert job['installed']
    result['api_installation_detected'] = True
    stopped, health = threading.Event(), []
    def monitor():
        while not stopped.is_set():
            try:
                _, elapsed = backend.get('/health', timeout=2)
                health.append(elapsed)
            except Exception as error:
                result['health_errors'].append(type(error).__name__)
            stopped.wait(.2)
    thread = threading.Thread(target=monitor, daemon=True); thread.start()
    config = replace(config_at(home), cache_dir=output/'cache')
    engine = ScottVoiceEngine(config)
    try:
        for profile, phrase in [('natural','Скотт на связи. Проверка голоса завершена.'),
                                ('scott','Говорю чётко и спокойно. Соединение восстановлено.')]:
            start = time.perf_counter()
            path = Path(engine.synthesize(phrase, profile))
            duration = time.perf_counter()-start
            wav = output/(profile+'.wav')
            wav.write_bytes(path.read_bytes())
            with wave.open(str(wav), 'rb') as audio:
                assert (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) == (1,2,24000)
                seconds = audio.getnframes()/audio.getframerate()
            start = time.perf_counter()
            assert engine.synthesize(phrase, profile) == str(path)
            cached = time.perf_counter()-start
            recognition = backend.transcribe(wav, phrase)
            assert recognition['success'] and recognition['word_error_rate'] == 0, recognition
            result['samples'].append(dict(profile=profile, text=phrase, audio=wav.name,
                synthesis_seconds=round(duration,3), audio_seconds=round(seconds,3),
                cache_seconds=round(cached,6), recognition=recognition))
        catalog, _ = backend.get('/voice/available')
        assert catalog['current'] == selected
        result['chosen_voice_unchanged'] = True
        result['reference_unchanged'] = hashlib.sha256(config.reference_json.with_name('scott-reference.wav').read_bytes()).hexdigest() == REFERENCE_SHA
        assert result['reference_unchanged']
        result['torch_absent_from_parent'] = 'torch' not in sys.modules
        assert result['torch_absent_from_parent']
    finally:
        engine.close(); stopped.set(); thread.join(timeout=3)
    result.update(health_requests=len(health), health_max_seconds=round(max(health),4),
                  no_microphone=True, no_playback=True, no_commands=True)
    assert not result['health_errors']
    (output/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))

if __name__ == '__main__':
    main()
