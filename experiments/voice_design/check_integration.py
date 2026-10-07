"""Verify the optional engine, cancellation and TTS/STT API without playback or commands."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import shutil
import sys
import threading
import time
import urllib.request
import wave

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from backend.scott_voice_engine import ScottVoiceEngine, PROFILES
from backend.scott_voice_process import VoiceProcessError
from benchmark_base import Backend
from trial_utils import save_json


def main():
    output = ROOT/'reports/voice-integration'
    output.mkdir(parents=True, exist_ok=True)
    backend = Backend('http://127.0.0.1:8000')
    before, _ = backend.get('/voice/available', timeout=25)
    result = dict(results=[], health_errors=[], profiles=PROFILES,
                  app_voice_before=before['current'])
    available = next(v for v in before['voices'] if v['id'] == 'scott-voice')
    assert available['available'], available['reason']
    stopped = threading.Event()
    health = []
    def monitor():
        while not stopped.is_set():
            try:
                _, elapsed = backend.get('/health', timeout=2)
                health.append(elapsed)
            except Exception as error:
                result['health_errors'].append(type(error).__name__)
            stopped.wait(.2)
    checker = threading.Thread(target=monitor, daemon=True)
    checker.start()
    engine = ScottVoiceEngine()
    try:
        assert engine.describe()['available']
        for phrase in ['Готово.', 'Слушаю.', 'Соединение восстановлено.']:
            for profile in PROFILES:
                started = time.perf_counter()
                path = Path(engine.synthesize(phrase, profile))
                first = time.perf_counter()-started
                started = time.perf_counter()
                assert engine.synthesize(phrase, profile) == str(path)
                cached = time.perf_counter()-started
                row = dict(text=phrase, profile=profile,
                    audio=str(path.relative_to(ROOT)).replace('\\', '/'),
                    first_seconds=round(first, 4), cache_seconds=round(cached, 6),
                    recognition=backend.transcribe(path, phrase))
                assert row['recognition']['success'] and row['recognition']['word_error_rate'] == 0, row
                result['results'].append(row)
                print(json.dumps(row, ensure_ascii=True), flush=True)
        # Interrupt the warmed model during a new generation, not a cache hit.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(engine.synthesize,
                'Это отдельная проверка отмены подготовки речи. Никаких действий выполнять не требуется. Проверяем освобождение процесса.', 'natural')
            time.sleep(.8)
            client = engine._client
            status = client.status()
            assert status['active'] and status['running']
            owner = psutil.Process(status['pid'])
            owned = [owner, *owner.children(recursive=True)]
            started = time.perf_counter()
            engine.cancel()
            result['cancel_seconds'] = round(time.perf_counter()-started, 4)
            try:
                pending.result(timeout=5)
            except VoiceProcessError as error:
                assert error.code == 'cancelled'
            else:
                raise AssertionError('Cancelled generation returned audio')
            result['cancelled_process_tree_stopped'] = all(not process.is_running() for process in owned)
            assert result['cancelled_process_tree_stopped']
        engine.close()  # Release its GPU before testing the API's own worker.
        phrase = 'Проверка завершена.'
        request = urllib.request.Request(backend.url+'/text_to_speech',
            data=json.dumps(dict(text=phrase, voice='scott-voice')).encode('utf-8'),
            headers={'Content-Type':'application/json'})
        started = time.perf_counter()
        with backend.opener.open(request, timeout=90) as response:
            assert response.headers['Content-Type'].startswith('audio/wav')
            api_path = output/'api.wav'
            api_path.write_bytes(response.read())
        result['api_synthesis_seconds'] = round(time.perf_counter()-started, 4)
        with wave.open(str(api_path), 'rb') as audio:
            assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
        result['api_recognition'] = backend.transcribe(api_path, phrase)
        assert result['api_recognition']['success'] and result['api_recognition']['word_error_rate'] == 0
        after, _ = backend.get('/voice/available')
        result['app_voice_unchanged'] = after['current'] == before['current']
        result['parent_without_torch'] = 'torch' not in sys.modules
        result['parent_without_qwen'] = 'qwen_tts' not in sys.modules
        assert result['app_voice_unchanged'] and result['parent_without_torch'] and result['parent_without_qwen']
    finally:
        engine.close()
        stopped.set()
        checker.join(timeout=3)
    result['health_requests'] = len(health)
    result['health_max_seconds'] = round(max(health), 4) if health else None
    assert not result['health_errors']
    for source in (ROOT/'ScottAI_qt/build-voice/screenshots/voice').glob('*.png'):
        shutil.copy2(source, output/source.name)
    save_json(output/'integration.json', result)
    print(json.dumps({key:value for key,value in result.items() if key != 'results'}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
