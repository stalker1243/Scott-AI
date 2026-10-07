"""Shared formatting and output checks for the local voice experiment."""
from pathlib import Path
import json
import re

from generate_samples import ROOT, HERE, prepare_text
from evaluate_samples import word_error_rate


def cases():
    return json.loads((HERE/'trial_cases.json').read_text(encoding='utf-8'))


def save_json(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def write_audio(audio, rate, path):
    import numpy as np
    import soundfile as sf
    values = np.asarray(audio, dtype=np.float32)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise ValueError('Invalid synthesized audio')
    peak = float(np.abs(values).max())
    rms = float(np.sqrt(np.mean(values.astype(np.float64)**2)))
    if peak < 1e-5:
        raise ValueError('Silent synthesized audio')
    gain = min(4.0, .065/max(rms, 1e-6), .95/peak)
    values = values*gain
    sf.write(path, values, rate, subtype='PCM_16')
    return dict(audio=Path(path).name, seconds=round(len(values)/rate, 3), sample_rate=rate,
                gain=round(gain, 4), peak=round(float(np.abs(values).max()), 4),
                rms=round(float(np.sqrt(np.mean(values.astype(np.float64)**2))), 4))


def recognition_check(reference, heard):
    def words(text):
        return re.findall(r'[а-яa-z]+|\d+(?:[.,]\d+)?', prepare_text(text).casefold().replace('ё', 'е'))
    return dict(heard=heard, word_error_rate=round(word_error_rate(words(reference), words(heard)), 4))
