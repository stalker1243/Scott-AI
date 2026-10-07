"""Extract explicit first-person facts locally, using only the user's words."""
import hashlib
import re

SECRET = re.compile(r'парол|секрет|api[ _-]*(?:key|token)|api[ _-]*ключ|токен|sk-[a-z0-9]|ghp_|eyJ[a-z0-9]', re.I)
PATTERNS = [
    (r'(?:меня зовут|мо[её] имя\s*[-—:]?)\s+(.+)', 'profile:name', 'fact'),
    (r'я живу\s+(.+)', 'profile:location', 'fact'),
    (r'(?:я работаю над|я разрабатываю|мой проект\s*[-—:]?)\s+(.+)', 'project', 'fact'),
    (r'я работаю\s+(.+)', 'profile:work', 'fact'),
    (r'(?:я предпочитаю|предпочитаю|мне нравится|не люблю|я не люблю)\s+(.+)', 'preference', 'preference'),
    (r'(?:я пишу на|я программирую на|я изучаю)\s+(.+)', 'skill', 'fact'),
    (r'(?:мой компьютер|у меня (?:установлен[ао]?|стоит))\s+(.+)', 'hardware', 'fact'),
]


def extract(text):
    # Code, quotes, questions and hypothetical examples are not declarations.
    text = re.sub(r'```[\s\S]*?(?:```|$)', '', text)
    text = re.sub(r'(?im)^(?:например|если|допустим|представь|переведи|напиши|цитата|в примере)\b[^\n]*', '', text)
    result = []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+|;\s*|,\s*(?=(?:я\s|мой\s|моя\s|меня\s|предпочитаю\s))', text, flags=re.I):
        sentence = re.sub(r'^(?:кстати|ещ[её]|теперь|вообще-то)[,\s]+', '', sentence.strip(), flags=re.I).strip(' .')
        if not sentence or len(sentence) > 200 or '?' in sentence or SECRET.search(sentence):
            continue
        for pattern, key, kind in PATTERNS:
            match = re.fullmatch(pattern, sentence, re.I)
            if not match:
                continue
            value = match.group(1).strip()
            if not value or re.search(r'\b(?:если|может|например|возможно|допустим|планирую|игнорируй|выполни|запусти|удали)\b', value, re.I):
                break
            if key == 'profile:name' and not re.fullmatch(r'[a-zа-яё0-9_-]+(?:[ -][a-zа-яё0-9_-]+){0,3}', value, re.I):
                break
            if key == 'project':
                name = re.sub(r'^проект(?:ом)?\s+', '', value, flags=re.I).split()[0].strip('«»"\'.,:').casefold()
                key += ':' + ('current' if name in ('на', 'написан', 'теперь', 'сделан') else name)
            elif key == 'preference' and re.search(r'ответ|объясн|кратк|коротк|подробн', value, re.I):
                key = 'preference:response_style'
            elif key in ('preference', 'skill', 'hardware'):
                key += ':' + hashlib.sha256(value.casefold().encode('utf-8')).hexdigest()[:12]
            result.append({'text': sentence, 'key': key, 'kind': kind, 'value': value})
            break
    return result[:5]
