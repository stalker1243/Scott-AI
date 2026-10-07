"""Apply three original robotic colourings to the approved, synthetic Base clips."""
from pathlib import Path
import argparse
import hashlib
import json
import time

from trial_utils import ROOT, HERE, save_json, write_audio


def colour_voice(audio, rate, profile):
    """Modulate the voice's low body while retaining its upper consonant band."""
    import numpy as np
    from scipy.signal import butter, sosfilt
    values = np.asarray(audio, dtype=np.float64)
    if values.ndim != 1 or not values.size or rate < 16000 or not np.isfinite(values).all():
        raise ValueError('Expected finite mono speech at 16 kHz or higher')
    clean = sosfilt(butter(2, [65, min(7200, rate*.45)], btype='bandpass', fs=rate, output='sos'), values)
    body = sosfilt(butter(2, 1400, btype='lowpass', fs=rate, output='sos'), clean)
    consonants = clean-body
    carrier = np.cos(2*np.pi*profile['carrier_hz']*np.arange(len(values))/rate)
    metallic = body*carrier
    delay = max(1, round(rate*profile['delay_ms']/1000))
    delayed = np.zeros_like(body)
    delayed[delay:] = metallic[:-delay]
    return (clean + profile['body_mix']*(metallic-body)
            + profile['presence']*consonants + profile['resonance']*delayed).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'reports/voice-base')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/scott-voice')
    parser.add_argument('--check-stt', action='store_true', help='Use only the local transcription endpoint')
    parser.add_argument('--backend-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    import soundfile as sf
    profiles = json.loads((HERE/'robotic_profiles.json').read_text(encoding='utf-8'))
    base = json.loads((args.source/'base.json').read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    backend = None
    if args.check_stt:
        from benchmark_base import Backend
        backend = Backend(args.backend_url)
        backend.get('/health')
    result = dict(name='Scott Voice', processor_version=1, profiles=profiles,
                  reference_sha256=base['reference_sha256'], source_model=base['model'], results=[],
                  note='Colouring only: no pitch shifting or time stretching. Frame count is preserved; human listening is required.')
    selected = ('status', 'reference', 'technical')
    source_rows = {row['id']: row for row in base['results']}
    for case_id in selected:
        source = source_rows[case_id]
        source_path = args.source/source['audio']
        audio, rate = sf.read(source_path, dtype='float32')
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        for profile in profiles:
            started = time.perf_counter()
            processed = colour_voice(audio, rate, profile)
            elapsed = time.perf_counter()-started
            target = args.output/f'{profile["id"]}-{case_id}.wav'
            metrics = write_audio(processed, rate, target)
            if len(processed) != len(audio):
                raise ValueError('Processing changed the frame count')
            row = dict(id=case_id, title=source['title'], text=source['text'], profile=profile['id'],
                       source_audio=str(source_path.relative_to(ROOT)).replace('\\','/'), source_sha256=digest,
                       source_frames=len(audio), processing_seconds=round(elapsed, 6), **metrics)
            if backend:
                row['recognition'] = backend.transcribe(target, source['text'])
            result['results'].append(row)
            save_json(args.output/'scott-voice.json', result)
            print(json.dumps(dict(case=case_id, profile=profile['id'], processing_seconds=row['processing_seconds'],
                                 recognition=row.get('recognition')), ensure_ascii=True), flush=True)
    if backend:
        health, seconds = backend.get('/health')
        result['health'] = dict(response=health, seconds=round(seconds, 3))
    result['summary'] = dict(clips=len(result['results']),
         zero_wer=sum(row.get('recognition',{}).get('success',False) and row['recognition']['word_error_rate']==0
                      for row in result['results']),
         worst_processing_seconds=max(row['processing_seconds'] for row in result['results']))
    save_json(args.output/'scott-voice.json', result)


if __name__ == '__main__':
    main()
