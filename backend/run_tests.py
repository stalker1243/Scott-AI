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
        for name in ('installer/build.py', 'tools/audit_dependencies.py', 'tools/build_voice_sdk.py', 'tools/analyze_timings.py',
                     'tools/voice_compat/manifest.json', 'tools/voice_compat/qwen-transformers5.patch',
                     'assets/scott-voice/vendor/qwen_tts-0.1.1+scott.1-py3-none-any.whl',
                     'assets/scott-voice/vendor/provenance.json', 'assets/scott-voice/vendor/NOTICE.txt',
                     'installer/build_linux.py', 'installer/build_appimage.py',
                     'installer/linux/AppRun', 'installer/linux/com.scottai.launcher.desktop',
                     'installer/linux_python.py', 'installer/linux/install.py',
                     'installer/linux/install.sh', 'installer/linux/uninstall.sh',
                     'installer/linux/run.sh',
                     'installer/linux/python-environment.sh',
                     'VERSION.json', 'README.md', '.env.example', 'docs/guide.md', 'docs/installation.md', 'docs/models.md',
                     'docs/voice-check.md', 'docs/desktop-control.md', 'docs/interface.md', 'docs/security.md', 'docs/performance.md',
                     'docs/memory.md', 'docs/protocols.md', 'docs/recognition.md', 'docs/reliability.md', 'docs/release-notes-next.md',
                     'docs/release-notes-2.2.0.md',
                     'assets/brand/scott-logo.png',
                     'assets/scott-voice/reference/reference.json',
                     'assets/scott-voice/reference/scott-reference.wav',
                     'assets/brand/scott-logo-light.png',
                     'voice/runtime/stream_voice.py',
                     'voice/runtime/voice_worker.py',
                     'voice/runtime/requirements.txt',
                     'voice/runtime/create_scott_voice.py',
                     'voice/runtime/robotic_profiles.json',
                     'voice/runtime/trial_utils.py',
                     'voice/runtime/generate_samples.py',
                     'voice/runtime/evaluate_samples.py'):
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
        env.update(WARMUP_MODELS='0', SCOTT_SEMANTIC_MEMORY='0', SCOTT_DESKTOP_DISABLED='1', WHISPER_MODEL='small', WHISPER_ENGINE='auto', SCOTT_RUNTIME_PROFILE='full',
                   SCOTT_STORAGE_MODE='legacy',
                   SCOTT_VOICE_HOME='', SCOTT_VOICE_DEVICE='cuda', SCOTT_VOICE_CPU_THREADS='auto', SCOTT_LOG_DIR=str(root/'logs'),
                   PYTHONPATH=str(root)+os.pathsep+str(isolated), PYTHONDONTWRITEBYTECODE='1')
        # Readiness checks must not see or repair the caller's real model cache.
        cache = root/'cache'
        env.update(XDG_CACHE_HOME=str(cache), HF_HOME=str(cache/'huggingface'),
                   HF_HUB_CACHE=str(cache/'huggingface/hub'),
                   HUGGINGFACE_HUB_CACHE=str(cache/'huggingface/hub'),
                   TORCH_HOME=str(cache/'torch'), NUMBA_CACHE_DIR=str(cache/'numba'))
        env.pop('TRANSFORMERS_CACHE', None)
        args = sys.argv[1:] or ['tests', '-q', '-m', 'not integration and not slow']
        print('Tests use an isolated copy; personal data and API settings are excluded.', flush=True)
        protected = [str(backend/'data'), str(backend.parent/'data'),
                     str(backend.parent/'.env'), str(backend.parent/'audio_cache')]
        import json
        return subprocess.call([sys.executable, str(isolated/'testing_guard.py'),
                                json.dumps(protected), *args], cwd=isolated, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
