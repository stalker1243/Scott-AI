"""Run backend tests from an isolated source copy, without personal data.

    py -3.13 backend/run_tests.py
    py -3.13 backend/run_tests.py tests/test_chats.py -q

Default: unit/regression tests, excluding integration and slow tests.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile


def main():
    backend = Path(__file__).resolve().parent
    report_root = backend.parent / 'reports/isolated-tests'
    report_root.mkdir(parents=True, exist_ok=True)
    # Keep the disposable source tree inside the workspace. TemporaryDirectory
    # only cleans up the exact directory it created, after tests have ended.
    with tempfile.TemporaryDirectory(prefix='run-', dir=report_root) as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(report_root.resolve())
        isolated = root / 'backend'

        def ignore(path, names):
            skipped = {'__pycache__', '.pytest_cache', '*.pyc'}
            if Path(path).resolve() == backend:
                skipped |= {'data', 'models', 'logs', 'temp', '.venv', '*.wav', '*.mp3', '*.log', '*_memory.json'}
            return shutil.ignore_patterns(*skipped)(path, names)

        shutil.copytree(backend, isolated, ignore=ignore)
        # Distribution tests inspect the actual builders and public resources.
        # Copy only these known source files; release/cache/data stay excluded.
        for name in ('installer/build.py',
                     'installer/build_linux.py', 'installer/linux_python.py', 'installer/linux/install.py',
                     'installer/linux/install.sh', 'installer/linux/uninstall.sh',
                     'installer/linux/run.sh',
                     'installer/linux/python-environment.sh',
                     'VERSION.json', 'README.md', '.env.example', 'docs/installation.md', 'docs/models.md',
                     'assets/brand/scott-logo.png',
                     'assets/brand/scott-logo-light.png',
                     'experiments/voice_design/stream_voice.py',
                     'experiments/voice_design/create_scott_voice.py',
                     'experiments/voice_design/trial_utils.py',
                     'experiments/voice_design/generate_samples.py',
                     'experiments/voice_design/evaluate_samples.py'):
            source = backend.parent / name
            if source.is_file():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        (root / '.env').write_text('WARMUP_MODELS=0\nSCOTT_SEMANTIC_MEMORY=0\nWHISPER_MODEL=small\nWHISPER_ENGINE=auto\n', encoding='utf-8')
        env = dict(os.environ)
        for key in tuple(env):
            if key.upper().endswith(('_API_KEY', '_TOKEN')) or key.upper() in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
                env.pop(key, None)
        for key in ('OPENAI_API_KEY', 'GROQ_API_KEY', 'DEEPSEEK_API_KEY',
                    'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', 'AI_PROVIDER', 'AI_MODEL'):
            env[key] = ''
        env.update(WARMUP_MODELS='0', SCOTT_SEMANTIC_MEMORY='0', WHISPER_MODEL='small', WHISPER_ENGINE='auto',
                   SCOTT_VOICE_HOME='', SCOTT_VOICE_DEVICE='cuda',
                   PYTHONPATH=str(root)+os.pathsep+str(isolated), PYTHONDONTWRITEBYTECODE='1')
        args = sys.argv[1:] or ['tests', '-q', '-m', 'not integration and not slow']
        print('Tests use an isolated copy; personal data and API settings are excluded.', flush=True)
        protected = [str(backend/'data'), str(backend.parent/'data'),
                     str(backend.parent/'.env'), str(backend.parent/'audio_cache')]
        import json
        return subprocess.call([sys.executable, str(isolated/'testing_guard.py'),
                                json.dumps(protected), *args], cwd=isolated, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
