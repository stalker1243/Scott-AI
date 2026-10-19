"""Offline conversions with explicit dimensions and decimal/binary data units."""
from decimal import Decimal

UNITS = {}
def add(dimension, scale, label, aliases, offset='0'):
    for alias in aliases.split('|'):
        UNITS[alias] = (dimension, Decimal(str(scale)), Decimal(offset), label)

def aliases(existing, extra):
    for alias in extra.split('|'):
        UNITS[alias] = UNITS[existing]

add('length', 1, 'м', 'м|метр|метры|метра|метров|m')
add('length', 1000, 'км', 'км|километр|километра|километры|километров|km')
add('length', '.01', 'см', 'см|сантиметр|сантиметра|сантиметры|сантиметров|cm')
add('length', '.001', 'мм', 'мм|миллиметр|миллиметра|миллиметров|mm')
add('length', '.0254', 'дюйм', 'дюйм|дюйма|дюймов|inch|inches')
add('length', '.3048', 'фут', 'фут|фута|футов|foot|feet')
add('length', '1609.344', 'миля', 'миля|мили|миль|mile|miles')
add('mass', 1, 'кг', 'кг|килограмм|килограмма|килограммов|kg')
add('mass', '.001', 'г', 'г|грамм|грамма|граммов|g')
add('mass', '.000001', 'мг', 'мг|миллиграмм|миллиграммов|mg')
add('mass', 1000, 'т', 'т|тонна|тонны|тонн|tonne')
add('mass', '.45359237', 'фунт', 'фунт|фунта|фунтов|lb|pound|pounds')
add('mass', '.028349523125', 'унция', 'унция|унции|унций|ounce|ounces')
add('time', 1, 'с', 'с|секунда|секунды|секунд|s|second|seconds')
add('time', 60, 'мин', 'мин|минута|минуты|минут|minute|minutes')
add('time', 3600, 'ч', 'ч|час|часа|часов|hour|hours')
add('time', 86400, 'день', 'день|дня|дней|сутки|суток|day|days')
add('time', 604800, 'неделя', 'неделя|недели|недель|week|weeks')
add('volume', 1, 'л', 'л|литр|литра|литров|l|liter|liters')
add('volume', '.001', 'мл', 'мл|миллилитр|миллилитров|ml')
add('volume', 1000, 'м³', 'м³|м3|кубометр|кубометра|кубометров')
add('area', 1, 'м²', 'м²|м2|квадратный метр|квадратные метры|квадратных метров')
add('area', 1000000, 'км²', 'км²|км2|квадратные километры|квадратных километров')
add('area', 10000, 'га', 'га|гектар|гектара|гектаров')
add('area', 100, 'сотка', 'сотка|сотки|соток')
add('speed', 1, 'м/с', 'м/с|метров в секунду')
add('speed', Decimal(1)/Decimal('3.6'), 'км/ч', 'км/ч|километров в час')
add('speed', '.44704', 'миль/ч', 'миль/ч|mph|миль в час')
add('data', 1, 'Б', 'б|байт|байта|байтов|byte|bytes')
add('data', '.125', 'бит', 'бит|бита|битов|bit|bits')
for power, prefix, ru in ((1, 'k', 'кило'), (2, 'm', 'мега'), (3, 'g', 'гига'), (4, 't', 'тера')):
    add('data', 1000**power, prefix.upper()+'B', f'{prefix}b|{prefix}б|{ru}байт|{ru}байта|{ru}байтов')
for power, prefix, ru in ((1, 'ki', 'киби'), (2, 'mi', 'меби'), (3, 'gi', 'гиби'), (4, 'ti', 'теби')):
    add('data', 1024**power, prefix.capitalize()+'B', f'{prefix}b|{prefix}б|{ru}байт|{ru}байта|{ru}байтов')
add('temperature', 1, '°C', '°c|c|цельсий|цельсия|градусов цельсия|градусы цельсия')
add('temperature', Decimal(5)/9, '°F', '°f|f|фаренгейт|фаренгейта|градусов фаренгейта', '-32')
add('temperature', 1, 'K', 'k|кельвин|кельвина|кельвинов', '-273.15')
for existing, extra in (
        ('мм', 'миллиметры'), ('дюйм', 'дюймы'), ('фут', 'футы'),
        ('кг', 'килограммы'), ('г', 'граммы'), ('мг', 'миллиграммы|миллиграмма'),
        ('фунт', 'фунты'), ('ч', 'часы'), ('день', 'дни'),
        ('л', 'литры'), ('мл', 'миллилитры|миллилитра'), ('м3', 'кубометры'),
        ('га', 'гектары'), ('б', 'байты'), ('бит', 'биты'), ('k', 'кельвины')):
    aliases(existing, extra)
for prefix, ru in (('k', 'кило'), ('m', 'мега'), ('g', 'гига'), ('t', 'тера')):
    aliases(prefix+'b', ru[0]+'б|'+ru+'байты')
for prefix, ru in (('ki', 'киби'), ('mi', 'меби'), ('gi', 'гиби'), ('ti', 'теби')):
    aliases(prefix+'b', ru[:2]+'б|'+ru+'байты')

def split_conversion(body):
    # Try all separators because a speed unit itself contains "в".
    import re
    for separator in reversed(list(re.finditer(r'\s+(?:в|to)\s+', body, re.I))):
        left, target = body[:separator.start()].casefold().strip(), body[separator.end():].casefold().strip(' .?!')
        if target not in UNITS:
            continue
        for alias in sorted(UNITS, key=len, reverse=True):
            if left.endswith(' '+alias):
                return left[:-len(alias)].strip(), alias, target
    return None

def convert(value, source, target):
    first, last = UNITS[source], UNITS[target]
    if first[0] != last[0]:
        raise ValueError('Эти единицы измеряют разные величины.')
    base = (value + first[2]) * first[1]
    if first[0] == 'temperature' and base < Decimal('-273.15'):
        raise ValueError('Температура ниже абсолютного нуля.')
    return base / last[1] - last[2], last[3]
