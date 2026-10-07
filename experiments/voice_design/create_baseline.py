"""Create a same-text reference with Scott's current Eugene/Calm voice."""
from pathlib import Path
import argparse
import json
import sys
import time

from generate_samples import ROOT, REFERENCE, prepare_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-design')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT/'backend'))
    import numpy as np
    import soundfile as sf
    import silero_tts
    import speech_text
    import voice_character
    path = args.output/'scott-current.wav'
    started = time.perf_counter()
    if not silero_tts.synthesize(speech_text.prepare_for_speech(REFERENCE), str(path), 'eugene'):
        raise RuntimeError('Local reference synthesis failed')
    audio, rate = sf.read(path, dtype='float32')
    audio = voice_character.apply(audio, rate, 'calm')
    rms = float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
    peak = float(np.max(np.abs(audio)))
    if not np.isfinite(audio).all() or peak < 1e-5:
        raise ValueError('Invalid reference audio')
    gain = min(4.0, .065/max(rms, 1e-6), .95/peak)
    audio *= gain
    sf.write(path, audio, rate, subtype='PCM_16')
    row = dict(profile='current', title='Текущий голос',
               description='Евгений, спокойная подача. Образец для сравнения.',
               audio=path.name, seconds=round(len(audio)/rate, 3), sample_rate=rate,
               generation_with_load_seconds=round(time.perf_counter()-started, 3),
               gain=round(gain, 4), peak=round(float(np.max(np.abs(audio))), 4),
               rms=round(float(np.sqrt(np.mean(audio.astype(np.float64)**2))), 4))
    (args.output/'baseline.json').write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    main()
