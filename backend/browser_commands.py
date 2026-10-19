"""Small, explicit browser requests. Page text never becomes an instruction."""
import re
try:
    from .understanding import strip_command_wrapper
except ImportError:
    from understanding import strip_command_wrapper

SITE = r'(?:ютуб(?:е|а)?|youtube)'


def parse(text):
    request = strip_command_wrapper(text).strip()
    if '\n' in request or '`' in request:
        return None
    request = re.sub(r'(?i)^давай\s+', '', request)
    management = {
        'install': r'(?:подготовь|подготовить|установи|установить) (?:управляемый браузер|браузер(?: скотта| scott)?)',
        'enable': r'включи управление браузером',
        'disable': r'отключи управление браузером',
        'cancel': r'(?:отмени|останови) (?:действие|задачу|подготовку) (?:в браузере|браузера)',
        'status': r'(?:покажи )?(?:статус браузера|результаты поиска (?:на|в) (?:ютубе|youtube))',
    }
    for action, pattern in management.items():
        if re.fullmatch('(?i)' + pattern + r'[.!?]?', request):
            return {'action': action}
    if re.fullmatch(rf'(?i)(?:открой|открыть|зайди на)\s+{SITE}[.!]?', request):
        return {'action': 'home'}
    controls = [('pause', r'(?:пауза|приостанови|поставь на паузу|останови)'),
                ('resume', r'(?:продолжи|возобнови)'), ('close', r'(?:закрой|закрыть)')]
    for action, verb in controls:
        if re.fullmatch(rf'(?i){verb}\s+(?:(?:видео|воспроизведение)\s+)?(?:(?:на|в)\s+)?{SITE}[.!]?', request):
            return {'action': action}
    choice = re.fullmatch(r'(?i)(?:включи|открой|покажи)\s+(?:видео\s+)?(первое|первый|второе|второй|третье|третий|четвёртое|четвертое|четвёртый|пятое|пятый|[1-5])(?:\s+(?:видео|из найденных|из результатов))?[.!]?', request)
    if choice:
        words = ['перв', 'втор', 'трет', 'четв', 'пят']
        value = choice[1].lower()
        index = int(value) - 1 if value.isdigit() else next(i for i, word in enumerate(words) if value.startswith(word))
        return {'action': 'select', 'index': index}
    request = re.sub(rf'(?i)^(?:открой|открыть)\s+{SITE}\s*(?:,|и)\s*', '', request)
    match = re.fullmatch(rf'(?i)(найди|найти|поищи|включи|включить|посмотри)\s+(?:(?:видео|музыку|песню|ролик)\s+)?(?:на|в)\s+{SITE}\s+(.+)', request)
    if not match:
        # After "open YouTube and ...", the second part may omit the service.
        if re.match(rf'(?i)^(?:открой|открыть)\s+{SITE}\s*(?:,|и)\s*', strip_command_wrapper(text)):
            match = re.fullmatch(r'(?i)(найди|найти|поищи|включи|включить)\s+(.+)', request)
        if not match:
            return None
    query = match[match.lastindex].strip(' "«»').rstrip('.!')
    autoplay = bool(re.search(r'(?i)\s+и\s+включи\s+(?:первое|первый)(?:\s+видео)?$', query))
    query = re.sub(r'(?i)\s+и\s+включи\s+(?:первое|первый)(?:\s+видео)?$', '', query).strip()
    if not query or len(query) > 500:
        return None
    return {'action': 'play' if autoplay or match[1].lower().startswith('включ') else 'search', 'query': query}
