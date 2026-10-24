"""Parse explicit local tools; discussion and model questions keep their route."""
import re
import utility_units

def parse(text):
    request = text.strip().rstrip('.!?').strip()
    if not request or len(request) > 600 or '\n' in request or '`' in request:
        return None
    # ASR can put a separator after the explicit arithmetic prefix. Keep
    # commas inside numbers/functions intact for the bounded calculator.
    request = re.sub(r'^(посчитай|вычисли|сколько будет)[ \t]*[,:][ \t]*',
                     r'\1 ', request, flags=re.I)
    lower = request.casefold()
    infinitives = {'посчитать': 'посчитай', 'вычислить': 'вычисли', 'перевести': 'переведи',
                   'пересчитать': 'пересчитай', 'конвертировать': 'конвертируй',
                   'запустить': 'запусти', 'остановить': 'останови', 'сбросить': 'сбрось',
                   'продолжить': 'продолжи', 'возобновить': 'возобнови', 'поставить': 'поставь',
                   'установить': 'установи', 'увеличить': 'увеличь', 'уменьшить': 'уменьши',
                   'выключить': 'выключи', 'включить': 'включи', 'бросить': 'брось', 'подбросить': 'подбрось'}
    first, separator, rest = lower.partition(' ')
    if first in infinitives:
        lower = request = infinitives[first] + separator + rest
    if lower in ('какая системная громкость', 'покажи системную громкость', 'какая громкость системы'):
        return {'action': 'system_volume', 'operation': 'status'}
    if lower in ('выключи системный звук', 'выключи звук системы', 'включи системный звук', 'включи звук системы'):
        return {'action': 'system_volume', 'operation': 'mute', 'value': int(lower.startswith('выключи'))}
    volume = re.fullmatch(r'(?:(?:установи|поставь|сделай)\s+)?(?:системную громкость|громкость системы|громкость)\s+(?:на\s+)?(.+?)(?:\s*(?:%|процент(?:а|ов)?))?', lower)
    delta = re.fullmatch(r'(увеличь|уменьши|прибавь|убавь)\s+(?:системную громкость|громкость системы|звук|громкость)\s+на\s+(.+?)(?:\s*(?:%|процент(?:а|ов)?))?', lower)
    if volume or delta:
        from voice_commands import _spoken_number
        raw = delta[2] if delta else volume[1]
        value = int(raw) if re.fullmatch(r'[+-]?\d{1,12}', raw) else _spoken_number(raw)
        if value is not None and delta and delta[1] in ('уменьши', 'убавь'):
            value = -value
        # Recognized invalid input must not fall through to legacy volume-up.
        return {'action': 'system_volume', 'operation': 'delta' if delta else 'set', 'value': value}
    stopwatch = {
        'запусти секундомер': 'start', 'начни секундомер': 'start',
        'поставь секундомер на паузу': 'pause', 'приостанови секундомер': 'pause',
        'продолжи секундомер': 'resume', 'возобнови секундомер': 'resume',
        'останови секундомер': 'stop', 'сбрось секундомер': 'reset',
        'сколько на секундомере': 'status', 'покажи секундомер': 'status',
        'засеки круг': 'lap', 'круг секундомера': 'lap',
    }
    if lower in stopwatch:
        return {'action': 'stopwatch', 'operation': stopwatch[lower]}
    if lower in ('брось кубик', 'кинь кубик'):
        return {'action': 'random', 'minimum': 1, 'maximum': 6}
    if lower in ('подбрось монету', 'брось монету'):
        return {'action': 'coin'}
    if lower in ('какой сегодня день недели', 'какой завтра день недели', 'какая сегодня дата', 'какая завтра дата'):
        return {'action': 'date', 'offset': int('завтра' in lower)}
    match = re.fullmatch(r'(?:случайное число|выбери случайное число) от (-?\d{1,12}) до (-?\d{1,12})', lower)
    if match:
        return {'action': 'random', 'minimum': int(match[1]), 'maximum': int(match[2])}
    match = re.fullmatch(r'(?:сколько дней до|дней до) (\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})', lower)
    if match:
        return {'action': 'days_until', 'date': match[1]}
    match = re.fullmatch(r'сколько дней между (\S+) и (\S+)', lower)
    if match:
        return {'action': 'days_between', 'first': match[1], 'last': match[2]}
    match = re.fullmatch(r'(?:(?:сколько будет|посчитай|вычисли)\s+)?(.+?)\s*(?:%|процент(?:а|ов)?)\s+(?:от|из)\s+(.+)', lower)
    if match:
        return {'action': 'percent', 'percent': match[1], 'value': match[2]}
    match = re.fullmatch(r'(?:посчитай|вычисли|сколько будет)\s+(.+)', request, re.I)
    if match:
        return {'action': 'calculate', 'expression': match[1]}
    match = re.fullmatch(r'(?:переведи|пересчитай|конвертируй)\s+(.+)', request, re.I)
    if match:
        parts = utility_units.split_conversion(match[1])
        if parts:
            return dict(action='convert', value=parts[0], source=parts[1], target=parts[2])
    return None
