"""Check real local embeddings with synthetic Russian conversations only."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import intelligent_answerer as ia
import memories
import semantic_memory as semantic
from memory_retrieval import terms

DOCUMENTS = [
    ('Дизайн лаунчера: Glass, закруглённые панели и мягкие тени.', 'Для внешнего вида выбран Glass.'),
    ('Синтез речи выполняется локальным движком Silero, голос Айдар.', 'Для озвучивания используется Silero.'),
    ('Переписка сохраняется на диске в базе SQLite.', 'Постоянная история находится в SQLite.'),
    ('Распознавание речи работает через Whisper, без облака.', 'Whisper превращает речь в текст.'),
    ('Разнообразие ответов модели ограничено температурой 0,4.', 'Температура установлена в 0,4.'),
    ('Утренний протокол запускается каждый день в девять часов.', 'Расписание: 09:00 каждый день.'),
    ('Для проекта Атлас выбрали C++ и Qt.', 'Атлас использует C++ и Qt.'),
    ('Музыка проигрывается на громкости 35 процентов.', 'Уровень музыки: 35 процентов.'),
    ('В продуктовом списке есть помидоры и хлеб.', 'Нужно купить помидоры и хлеб.'),
    ('На завтрак готовим овсяную кашу с яблоком.', 'Утром едим овсянку с яблоком.'),
]
CASES = [
    ('Что мы выбрали для оформления окна?', 0, 'Glass'),
    ('Как оформить интерфейс программы?', 0, 'Glass'),
    ('Что решили насчёт внешнего вида приложения?', 0, 'Glass'),
    ('Каким способом озвучиваем ответы помощника?', 1, 'Silero'),
    ('Какой движок превращает текст в звук?', 1, 'Silero'),
    ('Где хранится история диалога?', 2, 'SQLite'),
    ('Куда записываются наши беседы?', 2, 'SQLite'),
    ('Чем переводим сказанное человеком в текст?', 3, 'Whisper'),
    ('Как обрабатывается запись с микрофона?', 3, 'Whisper'),
    ('Какая настройка управляет случайностью генерации?', 4, '0,4'),
    ('Во сколько срабатывает автоматизация утром?', 5, '09:00'),
    ('Какие технологии используются в Атласе?', 6, 'C++'),
    ('Насколько громко играет плеер?', 7, '35'),
]
NEGATIVE_CASES = ['Сколько спутников у Юпитера?', 'Почему произошла Французская революция?',
                  'Как устроен фотосинтез?', 'Какая высота у Эвереста?']


def wait_index(archive, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = archive.semantic_status()
        if state['indexed_turns'] == state['total_turns']:
            return state
        if state['state'] == 'unavailable':
            raise RuntimeError('semantic_index_unavailable')
        time.sleep(0.05)
    raise RuntimeError('semantic_index_timeout')


def main():
    parser = argparse.ArgumentParser(description='Проверка локального поиска памяти по смыслу на вымышленных данных')
    parser.add_argument('--download', action='store_true', help='Загрузить открытую модель, если её нет в кэше')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent / 'reports' / 'semantic-memory-check')
    args = parser.parse_args()
    os.environ['SCOTT_SEMANTIC_MEMORY'] = '1'
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    if semantic.load(download=args.download) is None:
        print(json.dumps({'error': 'model_unavailable', 'hint': 'Use --download to prepare the public model.'}))
        return 2
    load_seconds = time.perf_counter() - start
    rows = []
    with tempfile.TemporaryDirectory(prefix='synthetic-semantic-', dir=args.output) as temporary:
        state = Path(temporary)
        memories.STORE_PATH = state / 'memories.json'
        path = state / 'conversations.jsonl'
        memory = ia.ConversationMemory(max_history=4, context_file=path)
        for user, assistant in DOCUMENTS:
            memory.record_external_turn(user, assistant)
        for n in range(10):
            memory.record_external_turn(f'Посторонняя тема {n}: сколько будет {n} + 2?', str(n + 2))
        indexed = wait_index(memory.archive)
        for query, target, expected in CASES:
            os.environ['SCOTT_SEMANTIC_MEMORY'] = '0'
            lexical = memory.recall(query)
            os.environ['SCOTT_SEMANTIC_MEMORY'] = '1'
            start = time.perf_counter()
            candidates = semantic.candidates(memory.archive, query)
            recalled = memory.recall(query)
            rows.append({'query': query, 'expected': expected,
                         'no_shared_words': not (terms(query) & terms(DOCUMENTS[target][0] + ' ' + DOCUMENTS[target][1])),
                         'lexical_found': any(expected in row['content'] for row in lexical),
                         'semantic_found': any(expected in row['content'] for row in recalled),
                         'top_semantic_id': next(iter(candidates), None),
                         'expected_id': target + 1, 'scores': candidates,
                         'seconds': round(time.perf_counter() - start, 4)})
        negatives = [{'query': query, 'matches': semantic.candidates(memory.archive, query)}
                     for query in NEGATIVE_CASES]
        # New object loads the same persisted vectors; indexing is not repeated.
        restarted = ia.ConversationMemory(max_history=4, context_file=path)
        restart_ok = any('Glass' in row['content'] for row in restarted.recall(CASES[0][0]))
        memories.add('Для дизайна лаунчера выбраны Glass и мягкие тени.')
        for n in range(50):
            memories.add(f'Покупка номер {n}: помидоры и хлеб.')
        previous_limit = memories.MAX_IN_PROMPT
        memories.MAX_IN_PROMPT = 2
        facts_ok = 'Glass' in memories.prompt_addition(CASES[0][0])
        memories.MAX_IN_PROMPT = previous_limit
        memory.clear()
        with memory.archive.connection() as db:
            clear_ok = db.execute('SELECT COUNT(*) FROM semantic_chunks').fetchone()[0] == 0
        report = {'model': semantic.status(), 'load_seconds': round(load_seconds, 3),
                  'index': indexed, 'cases': rows, 'passed': sum(row['semantic_found'] for row in rows),
                  'total': len(rows), 'top1': sum(row['top_semantic_id'] == row['expected_id'] for row in rows),
                  'lexical_passed': sum(row['lexical_found'] for row in rows),
                  'negative_cases': negatives, 'negative_false_matches': sum(bool(row['matches']) for row in negatives),
                  'restart_ok': restart_ok, 'facts_ok': facts_ok, 'clear_ok': clear_ok,
                  'synthetic_only': True, 'chat_api_requests': 0}
    output = args.output / 'report.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('passed', 'total', 'top1', 'lexical_passed', 'restart_ok', 'facts_ok', 'clear_ok')}, ensure_ascii=False))
    print(str(output))
    return 0 if report['passed'] == report['total'] and restart_ok and facts_ok and clear_ok else 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
