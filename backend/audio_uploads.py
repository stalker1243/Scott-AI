"""Prepare and transcribe an upload in one worker with its own temporary files."""

import tempfile
from pathlib import Path

try:
    from .timing import stage
except ImportError:
    from timing import stage


def transcribe_upload(contents: bytes, filename: str, transcribe):
    filename = filename or 'audio.wav'
    empty = {'success': False, 'text': '', 'filename': filename}
    if not contents:
        return 400, {**empty, 'message': 'Аудиофайл пуст'}
    # The client name is response metadata. It never becomes a filesystem path.
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.wav', '.mp3', '.m4a', '.ogg', '.webm', '.flac', '.aac', '.mp4'}:
        suffix = '.audio'
    try:
        # This worker owns cleanup even if the HTTP request is cancelled.
        with tempfile.TemporaryDirectory(prefix='scott-stt-') as directory:
            path = Path(directory) / ('input' + suffix)
            path.write_bytes(contents)
            try:
                from pydub import AudioSegment
                with stage('01.распознавание.подготовка_аудио'):
                    segment = AudioSegment.from_file(str(path))
                duration, loudness = len(segment), segment.dBFS
                if duration < 400:
                    return 400, {**empty, 'message': 'audio_too_short: Аудио слишком короткое (меньше 400ms). Попробуйте говорить дольше.'}
                # Keep very quiet speech for Whisper's VAD and bounded gain.
                # A fixed -50 dB cutoff used to reject a real whisper outright.
                if loudness is not None and loudness < -75:
                    return 400, {**empty, 'message': 'audio_too_quiet: Уровень звука слишком низкий. Проверьте микрофон/громкость.'}
                # Gain now belongs to the shared recognizer. Re-encoding here
                # amplified files twice and could clip transients before VAD.
            except Exception as error:
                # Preserve support for machines without pydub/ffmpeg: the
                # recognizer may be able to read the original format itself.
                print(f'⚠️ Audio pre-check failed: {error}')
            with stage('01.распознавание.файл', meta={'байт': path.stat().st_size}):
                text = transcribe(str(path))
            return (200 if text else 400), {'success': bool(text), 'text': text,
                'filename': filename, 'message': f'✅ Распознано: {text}' if text else '❌ Не удалось распознать речь'}
    except Exception as error:
        return 500, {**empty, 'error': str(error), 'message': f'❌ Ошибка: {error}'}
