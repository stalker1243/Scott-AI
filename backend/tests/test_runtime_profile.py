"""A compact install must be explicit and must not fall into a heavy/cloud repair."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import bootstrap
import model_setup
import recognition_models
import runtime_profile
import speech_to_text

pytestmark = pytest.mark.unit


@pytest.fixture
def compact(monkeypatch):
    monkeypatch.setenv('SCOTT_RUNTIME_PROFILE', 'compact')
    monkeypatch.setenv('WHISPER_ENGINE', 'faster')
    monkeypatch.setenv('WHISPER_DEVICE', 'cpu')


@pytest.mark.parametrize('choice', ['', 'full', 'FULL'])
def test_full_profile_is_the_default(monkeypatch, choice):
    if choice:
        monkeypatch.setenv('SCOTT_RUNTIME_PROFILE', choice)
    else:
        monkeypatch.delenv('SCOTT_RUNTIME_PROFILE', raising=False)
    assert runtime_profile.compact_mode() is False


@pytest.mark.parametrize('engine,device', [('auto','cpu'), ('openai','cpu'), ('faster',''),
                                        ('faster','auto'), ('faster','cuda'), ('faster','rocm')])
def test_compact_requires_explicit_faster_cpu(compact, monkeypatch, engine, device):
    monkeypatch.setenv('WHISPER_ENGINE', engine)
    monkeypatch.setenv('WHISPER_DEVICE', device)
    with pytest.raises(runtime_profile.ProfileError, match='WHISPER_ENGINE=faster'):
        runtime_profile.compact_mode()


def test_unknown_profile_fails_before_install(monkeypatch):
    monkeypatch.setenv('SCOTT_RUNTIME_PROFILE', 'comapct')
    monkeypatch.setattr(bootstrap, 'torch_requirement', lambda: pytest.fail('No hardware/pip on invalid config'))
    result = bootstrap.install_dependencies()
    assert not result.done and 'SCOTT_RUNTIME_PROFILE' in result.error


def test_compact_requirements_preserve_other_pins_and_markers():
    from packaging.requirements import Requirement
    source = Path(runtime_profile.__file__).with_name('requirements.txt')
    lines = [line.strip() for line in source.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    expected = [line for line in lines if Requirement(line).name not in ('torch', 'openai-whisper')]
    assert runtime_profile.compact_requirements() == expected + ['ctranslate2==4.8.2']


def test_compact_rejects_new_requirement_directives(tmp_path):
    source = tmp_path/'requirements.txt'
    source.write_text('torch>=2.13.0\nopenai-whisper==20250625\nfaster-whisper==1.1.0\n-r hidden.txt\n')
    with pytest.raises(runtime_profile.ProfileError):
        runtime_profile.compact_requirements(source)


@pytest.mark.parametrize('works', [True, False])
def test_compact_does_not_select_openai_when_native_provider_fails(compact, monkeypatch, works):
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=object) if works else None)
    if works:
        assert recognition_models.selected_engine() == 'faster'
    else:
        with pytest.raises(runtime_profile.ProfileError, match='подготов'):
            recognition_models.selected_engine()
        assert model_setup.models_ready() is False


def test_compact_runtime_never_loads_openai_after_fast_failure(compact, monkeypatch):
    recognizer = speech_to_text.Recognizer('small', 'cpu')
    monkeypatch.setattr(recognizer, '_try_fast', lambda: False)
    monkeypatch.setattr(recognizer, '_load_openai', lambda: pytest.fail('No OpenAI fallback in compact profile'))
    with pytest.raises(runtime_profile.RecognitionUnavailable, match='чат доступен'):
        recognizer.load()


def test_compact_runtime_rejects_gpu_device(compact, monkeypatch):
    recognizer = speech_to_text.Recognizer('small', 'cuda')
    monkeypatch.setattr(recognizer, '_try_fast', lambda: pytest.fail('No GPU model in compact CPU mode'))
    with pytest.raises(runtime_profile.RecognitionUnavailable):
        recognizer.load()


def test_compact_native_failure_has_clear_error_and_preserves_cause(compact, monkeypatch):
    recognizer = speech_to_text.Recognizer('small', 'cpu')
    error = OSError('synthetic native library failure')
    def broken():
        raise error
    monkeypatch.setattr(recognizer, '_try_fast', broken)
    with pytest.raises(runtime_profile.RecognitionUnavailable) as caught:
        recognizer.load()
    assert caught.value.__cause__ is error


def test_compact_missing_verified_model_never_downloads_at_inference(compact, monkeypatch):
    monkeypatch.setattr(recognition_models, 'prepared_faster_path', lambda _: None)
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(
        WhisperModel=lambda *a, **k: pytest.fail('No implicit provider download')))
    recognizer = speech_to_text.Recognizer('small', 'cpu')
    with pytest.raises(runtime_profile.RecognitionUnavailable):
        recognizer.load()


@pytest.mark.parametrize('pip_success', [True, False])
def test_compact_setup_never_probes_or_installs_torch(compact, monkeypatch, tmp_path, pip_success):
    monkeypatch.setattr(bootstrap, '__file__', str(tmp_path/'backend/bootstrap.py'))
    monkeypatch.setattr(bootstrap, 'torch_requirement', lambda: pytest.fail('No GPU/Torch selection'))
    monkeypatch.setattr(bootstrap, '_install_torch', lambda *a: pytest.fail('No Torch installer'))
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k: pytest.fail('No Torch probe'))
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: None)
    import installation_space
    monkeypatch.setattr(installation_space, 'require_space', lambda *a, **k: {})
    calls = []
    def pip(exe, args, *a, **k):
        calls.append(args)
        return (True if len(calls) == 1 else pip_success), 'test failure'
    monkeypatch.setattr(bootstrap, '_run_pip', pip)
    executable = tmp_path/('runtime/python.exe' if sys.platform == 'win32' else 'runtime/bin/python')
    result = bootstrap.install_dependencies(str(executable))
    assert result.done == pip_success
    assert len(calls) == 2
    assert calls[0] == ['setuptools==83.0.0']
    assert calls[1][0] == '--no-build-isolation'
    assert 'ctranslate2==4.8.2' in calls[1]
    assert not any(line.startswith(('torch', 'openai-whisper')) for args in calls for line in args)
    if not pip_success:
        assert 'test failure' in result.error


def test_build_backend_failure_stops_before_other_dependencies(compact, monkeypatch, tmp_path):
    import installation_space
    monkeypatch.setattr(bootstrap, '__file__', str(tmp_path/'backend/bootstrap.py'))
    monkeypatch.setattr(installation_space, 'require_space', lambda *a, **k: {})
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: None)
    calls = []
    monkeypatch.setattr(bootstrap, '_run_pip', lambda exe,args,*a,**k: calls.append(args) or (False,'backend failed'))
    executable = tmp_path/('runtime/python.exe' if sys.platform == 'win32' else 'runtime/bin/python')
    result = bootstrap.install_dependencies(str(executable))
    assert not result.done and 'backend failed' in result.error
    assert calls == [['setuptools==83.0.0']]


def test_compact_install_rejects_global_python_before_pip(compact, monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, '__file__', str(tmp_path/'backend/bootstrap.py'))
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: pytest.fail('Do not modify global interpreter'))
    result = bootstrap.install_dependencies(str(tmp_path/'global/python.exe'))
    assert not result.done and 'изолирован' in result.error


def test_compact_low_space_fails_before_pip(compact, monkeypatch, tmp_path):
    import installation_space
    monkeypatch.setattr(bootstrap, '__file__', str(tmp_path/'backend/bootstrap.py'))
    monkeypatch.setattr(installation_space, 'free_bytes', lambda path: 0)
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: pytest.fail('Space before pip'))
    executable = tmp_path/('runtime/python.exe' if sys.platform == 'win32' else 'runtime/bin/python')
    result = bootstrap.install_dependencies(str(executable))
    assert not result.done and 'Недостаточно места' in result.error


def test_bad_compact_configuration_is_explained_before_cli_check(compact, monkeypatch, capsys):
    import json
    monkeypatch.setenv('WHISPER_ENGINE', 'openai')
    monkeypatch.setattr(model_setup, 'load_environment', lambda: None)
    monkeypatch.setattr(bootstrap, 'gpu_name', lambda: pytest.fail('Invalid config before GPU probe'))
    assert bootstrap.main(['--check', '--json']) == 1
    event = json.loads(capsys.readouterr().out)
    assert event['code'] == 'runtime_profile_invalid' and 'WHISPER_ENGINE=faster' in event['message']


def test_compact_dependency_check_imports_native_provider_without_torch(compact, monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda args,**kwargs:
                        calls.append(args) or SimpleNamespace(returncode=0,stdout='ok'))
    assert bootstrap.dependencies_ready('owned-python')
    code = calls[0][2]
    assert 'from faster_whisper import WhisperModel' in code
    assert 'import torch' not in code and 'import whisper' not in code
    assert 'ctranslate2==4.8.2' in code and 'r.specifier.contains' in code


def test_compact_uploaded_audio_failure_never_uses_cloud(compact, main_module, monkeypatch):
    monkeypatch.setattr(main_module, '_get_whisper_model', lambda: (_ for _ in ()).throw(RuntimeError('model unavailable')))
    monkeypatch.setitem(sys.modules, 'speech_recognition', SimpleNamespace(
        Recognizer=lambda: pytest.fail('No automatic Google upload on local failure')))
    with pytest.raises(runtime_profile.RecognitionUnavailable):
        main_module._transcribe_audio_file('synthetic.wav')


def test_compact_transcription_unavailable_is_actionable_503(compact, monkeypatch):
    import audio_uploads
    def unavailable(path):
        raise runtime_profile.RecognitionUnavailable(runtime_profile.REPAIR_MESSAGE)
    status, payload = audio_uploads.transcribe_upload(b'synthetic invalid audio', 'sample.wav', unavailable)
    assert status == 503 and payload['error'] == 'recognition_unavailable'
    assert 'подготов' in payload['message'] and 'чат доступен' in payload['message']


@pytest.mark.parametrize('available', [True, False])
def test_compact_health_names_real_provider_and_missing_dependency(compact, monkeypatch, available):
    import health_checks
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=object) if available else None)
    check = health_checks._распознавание()
    assert check['state'] == (health_checks.WARN if available else health_checks.FAIL)
    assert 'faster-whisper' in check['detail'] if available else 'подготов' in check['detail']
    assert 'openai-whisper' not in check['detail']
    assert 'Компактный режим' in health_checks._видеокарта()['detail']


def test_isolated_runner_preserves_the_callers_model_caches(monkeypatch, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('cache_runner_probe',
        Path(__file__).resolve().parents[1]/'run_tests.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    backend = tmp_path/'project/backend'
    backend.mkdir(parents=True)
    (backend/'testing_guard.py').write_text('# synthetic child; subprocess is mocked\n')
    monkeypatch.setattr(runner, '__file__', str(backend/'run_tests.py'))
    variables = ('HF_HOME', 'HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE', 'XDG_CACHE_HOME', 'TORCH_HOME')
    original = []
    for key in variables:
        folder = tmp_path/'caller-cache'/key
        folder.mkdir(parents=True)
        marker = folder/'receipt.json'
        marker.write_text('preserve caller cache')
        original.append(marker)
        monkeypatch.setenv(key, str(folder))
    def child(args, *, cwd, env):
        # Simulate a dependency/model check updating its own receipt.
        for key in variables:
            folder = Path(env[key])
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'receipt.json').write_text('child cache update')
        return 0
    monkeypatch.setattr(runner.subprocess, 'call', child)
    monkeypatch.setattr(sys, 'argv', ['run_tests.py', 'synthetic-probe'])
    assert runner.main() == 0
    assert all(path.read_text() == 'preserve caller cache' for path in original)
