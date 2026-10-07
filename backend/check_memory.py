"""Evaluate the configured real model with synthetic, isolated memory.

    py -3.13 backend/check_memory.py --live

Each probe starts in a new Python process. Only provider credentials are read
from the normal configuration; personal conversations, facts, projects and
personality are never loaded. No command executor or voice worker is imported.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
TOPIC_TURNS = 18
SEED = ('Меня зовут Алексей. Я живу в Казани. Я предпочитаю короткие ответы. '
        'Мой проект Орбита — лаунчер на C++ и Qt. '
        'Для базы проекта Орбита мы выбрали PostgreSQL на порту 5544. '
        'Следующий шаг проекта Орбита — добавить вкладку «Журнал». '
        'Ответь одним предложением.')
PROBES = {
    'profile': ('Как меня зовут, где я живу, какой длины ответы предпочитаю '
                'и на чём написан мой проект Орбита?',
                [r'алексе', r'казан', r'корот|кратк', r'[cс]\+\+', r'qt']),
    'archive': ('Какая база данных и какой порт выбраны у проекта Орбита?',
                [r'postgres', r'5544']),
    'continue': ('Продолжим проект Орбита. На чём остановились и какой следующий шаг?',
                 [r'журнал']),
    'corrected': ('Как меня зовут сейчас?', [r'михаил|mikhail']),
    'forgotten': ('Как меня зовут? Если имя не известно из памяти, прямо скажи об этом.',
                  [r'не (?:знаю|помню|известно|сохранено|указано)|'
                   r'не.*(?:имя|имени)|(?:имя|имени).*не|нет.*(?:имя|имени)']),
}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def evaluate_response(probe, answer):
    """Transparent checks for the synthetic facts, followed by manual review."""
    patterns = PROBES[probe][1]
    matched = [bool(re.search(pattern, answer, re.I)) for pattern in patterns]
    forbidden = bool(re.search(r'алексе', answer, re.I)) if probe in ('corrected', 'forgotten') else False
    return all(matched) and not forbidden, matched


def worker(args):
    # Redirect before imports: provider errors/logs must not expose credentials.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import intelligent_answerer as ia
        import memories
        import personality
        import projects
        from dotenv import load_dotenv
        state = args.state.resolve()
        state.mkdir(parents=True, exist_ok=True)
        ia.CONVERSATION_PATH = state / 'conversations.jsonl'
        ia.LEGACY_CHAT_PATH = state / 'unused-legacy.jsonl'
        memories.STORE_PATH = state / 'memories.json'
        personality.CONFIG_PATH = state / 'personality.json'
        projects.STORE_PATH = state / 'projects.json'
        load_dotenv(ROOT / '.env')
        ia.AI_CONFIG_PATH = ROOT / 'backend' / 'data' / 'ai_config.json'
        answerer = ia.IntelligentAnswerer()
        # Even an accidental save would now remain inside this test directory.
        ia.AI_CONFIG_PATH = state / 'unused-ai-config.json'
        if args.model:
            if answerer.api_provider != 'OpenRouter':
                raise RuntimeError('model_override_requires_openrouter')
            # The override is temporary and restricted to zero-priced models.
            catalog = ia.requests.get(f'{ia.OPENROUTER_BASE}/models', timeout=20).json().get('data', [])
            selected = next((row for row in catalog if row.get('id') == args.model), None)
            if (not selected or any(float(selected.get('pricing', {}).get(kind, 1)) != 0
                                    for kind in ('prompt', 'completion'))
                    or float(selected.get('pricing', {}).get('request', 0)) != 0):
                raise RuntimeError('model_override_requires_available_free_model')
            answerer.model = args.model

    secrets = list(answerer.custom_keys.values()) + list(answerer.env_keys.values())
    secrets += [value for key, value in os.environ.items() if 'API_KEY' in key]

    def redact(value):
        for secret in secrets:
            if isinstance(secret, str) and secret:
                value = value.replace(secret, '[скрыто]')
        return value

    rows = []

    def ask(label, text, probe=None):
        # Collect exactly the synthetic information available to this request.
        facts = memories.prompt_addition(text)
        recalled = answerer.memory.recall(text)
        recent = answerer.memory.get_context(max_chars=6000)
        start = time.perf_counter()
        diagnostics = io.StringIO()
        with contextlib.redirect_stdout(diagnostics), contextlib.redirect_stderr(diagnostics):
            answer, success = answerer.answer(text)
        passed, matches = evaluate_response(probe, answer) if probe else (success, [])
        row = {'id': label, 'query': text, 'answer': redact(answer), 'success': success,
               'passed': success and passed, 'matches': matches,
               'seconds': round(time.perf_counter() - start, 3),
               'facts': facts, 'recalled': recalled, 'recent_messages': len(recent),
               'pid': os.getpid()}
        if not success:
            row['diagnostics'] = redact(diagnostics.getvalue())
        rows.append(row)
        print(json.dumps({key: row[key] for key in ('id', 'success', 'passed', 'seconds')},
                         ensure_ascii=False), flush=True)
        if not success:
            raise RuntimeError('model_request_failed')

    result = {'operation': args.worker, 'provider': answerer.api_provider,
              'model': answerer.model, 'pid': os.getpid(), 'rows': rows}
    try:
        if not answerer.enabled:
            raise RuntimeError('configured_model_unavailable')
        if args.worker == 'seed':
            if args.seed_report:
                previous = json.loads(args.seed_report.read_text(encoding='utf-8'))
                saved = next(item for item in previous['results'] if item['operation'] == 'seed')
                if not previous.get('synthetic_only') or not saved['success'] or len(saved['rows']) < 13:
                    raise RuntimeError('invalid_synthetic_seed_report')
                for row in saved['rows']:
                    if not row['success']:
                        raise RuntimeError('incomplete_synthetic_seed_report')
                    answerer.memory.add_message('user', row['query'])
                    memories.observe(row['query'])
                    answerer.memory.add_message('assistant', row['answer'])
                    rows.append(row)
                result['reused_seed'] = str(args.seed_report)
            else:
                ask('seed', SEED)
            # Also exceed the four recalled turns: a topical continuation must
            # retrieve the right conversation, rather than every old turn.
            for n in range(len(rows) - 1, TOPIC_TURNS):
                ask(f'topic-{n + 1}', f'Посторонняя тема {n + 1}: сколько будет {n + 20} + 2? Ответь только числом.')
        elif args.worker == 'correct':
            ask('correction', 'Теперь меня зовут Михаил. Ответь одним предложением.')
        elif args.worker == 'forget':
            names = [row for row in memories.all_memories() if row.get('key') == 'profile:name']
            if len(names) != 1 or not memories.remove(names[0]['id']).get('success'):
                raise RuntimeError('synthetic_fact_delete_failed')
        else:
            ask(args.worker, PROBES[args.worker][0], args.worker)
        result['stats'] = answerer.memory.stats()
        result['fact_count'] = len(memories.all_memories())
        result['success'] = True
    except Exception as error:
        result['success'] = False
        # Do not serialize raw SDK exceptions (they may contain request details).
        result['error'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
    write_json(args.result, result)
    return 0 if result['success'] else 2


def main():
    parser = argparse.ArgumentParser(description='Проверка памяти на настоящей модели в отдельных файлах')
    parser.add_argument('--live', action='store_true', help='Отправить синтетические запросы настроенному провайдеру')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'memory-model-check')
    parser.add_argument('--model', help='Временная бесплатная модель OpenRouter, без сохранения настроек')
    parser.add_argument('--seed-report', type=Path, help='Повторить проверки с вымышленным диалогом из предыдущего отчёта')
    parser.add_argument('--worker', choices=['seed', 'correct', 'forget', *PROBES], help=argparse.SUPPRESS)
    parser.add_argument('--state', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.live:
        print('Для запросов к настоящей модели добавьте --live. Будет отправлена только вымышленная история.')
        return 0
    if args.worker:
        try:
            return worker(args)
        except Exception as error:
            write_json(args.result, {'operation': args.worker, 'success': False,
                                    'rows': [], 'error': type(error).__name__})
            return 2
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='run-', dir=args.output))
    results = []

    def start(operation, state):
        result_path = run / f'{operation}.json'
        command = [sys.executable, str(Path(__file__).resolve()), '--live',
                   '--worker', operation, '--state', str(state), '--result', str(result_path)]
        if args.model:
            command.extend(['--model', args.model])
        if args.seed_report and operation == 'seed':
            command.extend(['--seed-report', str(args.seed_report.resolve())])
        process = subprocess.run(command,
                                 cwd=ROOT / 'backend', timeout=900)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        results.append(result)
        if process.returncode or not result['success']:
            raise RuntimeError(f'{operation}: {result.get("error", "failed")}')

    try:
        with tempfile.TemporaryDirectory(prefix='synthetic-', dir=run) as temporary:
            base = Path(temporary)
            seed = base / 'seed'
            start('seed', seed)
            for probe in ('profile', 'archive', 'continue', 'corrected', 'forgotten'):
                state = base / probe
                shutil.copytree(seed, state)
                if probe == 'corrected':
                    start('correct', state)
                elif probe == 'forgotten':
                    start('forget', state)
                start(probe, state)
        probes = [row for result in results if result['operation'] in PROBES for row in result['rows']]
        report = {'results': results, 'passed': sum(row['passed'] for row in probes),
                  'total': len(probes), 'synthetic_only': True, 'real_model': True}
        write_json(run / 'report.json', report)
        print(json.dumps({'report': str(run / 'report.json'), 'passed': report['passed'],
                          'total': report['total']}, ensure_ascii=False), flush=True)
        return 0 if report['passed'] == report['total'] else 1
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        write_json(run / 'report.json', {'results': results, 'error': str(error), 'synthetic_only': True})
        print(json.dumps({'report': str(run / 'report.json'), 'error': str(error)}, ensure_ascii=False), flush=True)
        return 2


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
