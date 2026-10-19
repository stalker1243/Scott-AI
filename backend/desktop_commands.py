"""Explicit desktop requests; app/control names are data, never shell commands."""
import re


def _name(value):
    return value.strip().strip('«»“”\"\'').strip()


def parse(text):
    if not isinstance(text, str) or len(text) > 1200 or '\n' in text or '`' in text:
        return None
    value = text.strip().rstrip(' .!?').replace('ё', 'е')
    value = re.sub(r'^(?:пожалуйста[,]?\s+)', '', value, flags=re.I)
    value = re.sub(r'[,]?\s+пожалуйста$', '', value, flags=re.I)
    for pattern, operation in (
        (r'(?:закрой|закрыть)\s+все\s+(?:открытые\s+)?окна', 'close_all'),
        (r'(?:сверни|свернуть)\s+все\s+(?:открытые\s+)?окна|покажи\s+рабочий\s+стол', 'minimize_all'),
        (r'(?:покажи|перечисли)\s+(?:все\s+)?(?:открытые\s+)?окна|какие\s+окна\s+открыты', 'list'),
        (r'(?:обнови|обновить)\s+(?:список|каталог)\s+(?:приложений|программ)', 'refresh_apps'),
        (r'(?:покажи|перечисли)\s+(?:установленные\s+)?(?:приложения|программы)|какие\s+(?:приложения|программы)\s+установлены', 'list_apps'),
    ):
        if re.fullmatch(pattern, value, re.I):
            return dict(operation=operation)
    match = re.fullmatch(r'(?:закрой|закрыть)\s+все\s+(?:открытые\s+)?окна\s+кроме\s+(.+)', value, re.I)
    if match:
        names = [_name(name) for name in re.split(r'\s*,\s*|\s+и\s+', match[1])]
        if all(names) and len(names) <= 8:
            return dict(operation='close_all', exclude=names)
        return None
    match = re.fullmatch(r'(?:покажи|перечисли)\s+кнопки\s+(?:в\s+)?(?:(?:приложении|окне)\s+)?(.+)', value, re.I)
    if match:
        return dict(operation='controls', query=_name(match[1]))
    match = re.fullmatch(r'(?:нажми|нажать)\s+(?:на\s+)?(?:кнопку\s+)?(.+?)\s+в\s+(?:(?:приложении|окне)\s+)?(.+)', value, re.I)
    if match:
        return dict(operation='invoke', control=_name(match[1]), query=_name(match[2]))
    match = re.fullmatch(r'(?:переключись|переключиться|перейди)\s+(?:на|в)\s+(?:окно\s+|приложение\s+)?(.+)', value, re.I)
    if match:
        return dict(operation='focus', query=_name(match[1]))
    for verbs, operation in ((r'сверни|свернуть', 'minimize'), (r'разверни|развернуть', 'maximize'),
                              (r'восстанови|восстановить', 'restore'), (r'закрой|закрыть', 'close')):
        match = re.fullmatch(r'(?:'+verbs+r')\s+(?:текущее\s+|активное\s+)?окно(?:\s+(.+))?', value, re.I)
        if match:
            return dict(operation=operation, query=_name(match[1] or ''))
        # Bare "close X" keeps its existing application/process semantics.
        if operation != 'close':
            match = re.fullmatch(r'(?:'+verbs+r')\s+(.+)', value, re.I)
            if match:
                return dict(operation=operation, query=_name(match[1]))
    return None
