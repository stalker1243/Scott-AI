"""Small local text search shared by facts and conversation history."""
import re

WORDS = re.compile(r'[a-zа-яё0-9]+(?:[+#]+)?', re.I)
STOP = set('я ты он она мы вы они мне меня мой моя моё мои наш наша наши себя тебе тебя его ее это этот эта эти то и а но или в на за с из к о об у по для до не да нет как что кто где когда почему какой какая какие сколько ли бы был была было быть есть уже ещё еще теперь сейчас просто пожалуйста скажи расскажи помнишь вспомни'.split())
SUFFIX = re.compile(r'(?:иями|ами|ями|ого|ему|ому|иях|ах|ях|ов|ев|ий|ый|ой|ая|яя|ое|ее|ые|ие|ом|ем|ам|ям|ы|и|а|я|у|ю|е)$')


def normalize(word):
    word = word.casefold().replace('ё', 'е')
    if len(word) > 4 and re.fullmatch('[а-я]+', word):
        stem = SUFFIX.sub('', word)
        return stem if len(stem) >= 3 else word
    return word


def terms(text):
    return {normalize(word) for word in WORDS.findall(text or '') if word.casefold() not in STOP}


def excerpt(text, query='', limit=600):
    if len(text) <= limit:
        return text
    wanted = terms(query)
    start = 0
    for match in WORDS.finditer(text):
        if normalize(match.group()) in wanted:
            start = max(0, match.start() - limit // 3)
            break
    start = min(start, max(0, len(text) - limit))
    return ('… ' if start else '') + text[start:start + limit] + (' …' if start + limit < len(text) else '')
