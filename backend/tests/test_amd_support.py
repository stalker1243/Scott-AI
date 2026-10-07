"""ROCm routes to HIP PyTorch, never to a CUDA-only CTranslate2 wheel."""
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import device_settings as devices
import speech_to_text
import gpu_hardware
import bootstrap

pytestmark = pytest.mark.unit


@pytest.fixture
def hip(monkeypatch, tmp_path):
    torch = SimpleNamespace(__version__='2.13.0+rocm10.0.0', version=SimpleNamespace(hip='10.0', cuda=None),
        cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda _: 'AMD Radeon RX 7900 XTX',
            get_device_properties=lambda _: SimpleNamespace(total_memory=24 * 1024**3)),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)), device=lambda value: value)
    monkeypatch.setitem(sys.modules, 'torch', torch)
    monkeypatch.setattr(devices, 'CONFIG_PATH', tmp_path / 'devices.json')
    monkeypatch.setattr(devices, 'reset_loaded_models', lambda: None)
    for variable in devices.ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    return torch


@pytest.mark.parametrize('engine', ['whisper', 'silero'])
def test_hip_is_amd_and_uses_pytorch_cuda_spelling(hip, engine):
    assert devices.rocm_available() and not devices.cuda_available()
    assert devices.resolve_device(engine) == 'cuda'
    assert devices.set_choice(engine, 'rocm')['success']
    info = devices.describe()['engines'][engine]
    assert info['backend'] == 'rocm' and 'AMD' in info['device_label']
    assert {v['id']: v['available'] for v in info['options']}['rocm'] is True


@pytest.mark.parametrize('choice', ['rocm', 'cuda'])
def test_explicit_and_legacy_hip_env_choices_work(hip, monkeypatch, choice):
    monkeypatch.setenv('WHISPER_DEVICE', choice)
    assert devices.get_choice('whisper') == 'rocm'
    assert devices.resolve_device('whisper') == 'cuda'
    assert not devices.set_choice('whisper', 'cpu')['success']


def test_stale_rocm_choice_uses_cpu_and_cannot_be_newly_selected(hip, monkeypatch):
    assert devices.set_choice('whisper', 'rocm')['success']
    monkeypatch.setattr(hip.cuda, 'is_available', lambda: False)
    assert devices.resolve_device('whisper') == 'cpu'
    assert not devices.set_choice('silero', 'rocm')['success']


def test_rocm_does_not_override_explicit_cpu(hip):
    assert devices.set_choice('whisper', 'cpu')['success']
    assert devices.resolve_device('whisper') == 'cpu'


def test_gpu_settings_are_saved_atomically_without_losing_other_engine(hip):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: devices.set_choice(name, 'rocm'), ('whisper', 'silero')))
    assert all(r['success'] for r in results)
    assert json.loads(devices.CONFIG_PATH.read_text(encoding='utf-8')) == {'whisper': 'rocm', 'silero': 'rocm'}


@pytest.mark.parametrize('engine', ['auto', 'faster', 'openai'])
def test_hip_gpu_skips_prebuilt_faster_whisper(hip, monkeypatch, engine):
    monkeypatch.setattr(speech_to_text, 'ENGINE_CHOICE', engine)
    monkeypatch.setattr(speech_to_text, '_подсказка', lambda: 'Скотт.')
    monkeypatch.setattr(speech_to_text.Recognizer, '_try_fast', lambda self: pytest.fail('Must not start CUDA-only CTranslate2'))
    loads = []
    def load(name, device):
        loads.append(device)
        return SimpleNamespace(transcribe=lambda *a, **k: {'text': 'Скотт, открой блокнот'})
    monkeypatch.setitem(sys.modules, 'whisper', SimpleNamespace(load_model=load))
    recognizer = speech_to_text.Recognizer('fake', 'cuda')
    assert recognizer.transcribe('fake.wav') == 'Скотт, открой блокнот'
    assert recognizer.engine == 'openai-whisper' and loads == ['cuda']


@pytest.mark.parametrize('error', ['HIP out of memory', 'MIOpen failed', 'rocBLAS error', 'HSA invalid device function'])
def test_hip_runtime_failure_retries_once_on_cpu(hip, monkeypatch, error):
    monkeypatch.setattr(speech_to_text, 'ENGINE_CHOICE', 'openai')
    monkeypatch.setattr(speech_to_text, '_подсказка', lambda: 'Скотт.')
    loads = []
    def load(name, device):
        loads.append(device)
        def transcribe(*a, **k):
            if device == 'cuda':
                raise RuntimeError(error)
            return {'text': 'Скотт, сколько времени'}
        return SimpleNamespace(transcribe=transcribe)
    monkeypatch.setitem(sys.modules, 'whisper', SimpleNamespace(load_model=load))
    recognizer = speech_to_text.Recognizer('fake', 'cuda')
    assert recognizer.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert recognizer.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert loads == ['cuda', 'cpu']


@pytest.mark.parametrize('fail_at', ['transfer', 'synthesis'])
def test_silero_keeps_local_cpu_voice_after_hip_failure(hip, monkeypatch, tmp_path, fail_at):
    import silero_tts
    moves, saved = [], []
    class Model:
        current = 'cpu'
        def to(self, device):
            moves.append(device)
            if device == 'cuda' and fail_at == 'transfer':
                raise RuntimeError('HIP invalid device function')
            self.current = device
        def save_wav(self, **kwargs):
            saved.append(self.current)
            if self.current == 'cuda':
                raise RuntimeError('MIOpen failed')
            Path(kwargs['audio_path']).write_bytes(b'RIFF fake')
    monkeypatch.setattr(hip, 'hub', SimpleNamespace(load=lambda **k: (Model(), None)), raising=False)
    monkeypatch.setattr(silero_tts, '_model', None)
    monkeypatch.setattr(silero_tts, '_model_device', None)
    monkeypatch.setattr(silero_tts, '_resolve_device', lambda: 'cuda')
    for i in range(2):
        assert silero_tts.synthesize('Привет', str(tmp_path / f'{i}.wav'), 'aidar')
    assert moves == ['cuda', 'cpu'] and silero_tts._model_device == 'cpu'
    assert saved[-2:] == ['cpu', 'cpu']


def test_amd_diagnostics_never_labels_hip_as_nvidia(hip, monkeypatch):
    import diagnostics
    import health_checks
    monkeypatch.setattr(gpu_hardware, 'amd_adapters', lambda: [{'name': 'AMD Radeon', 'driver': 'test'}])
    report = diagnostics.collect_gpu_info()
    assert report['rocm_доступен'] and not report['cuda_доступна']
    assert report['ускоритель'] == 'AMD ROCm/HIP'
    assert 'AMD' in health_checks._видеокарта()['detail']
    assert 'openai-whisper' in health_checks._распознавание()['detail']


def test_cpu_build_on_amd_explains_correct_driver_and_runtime(hip, monkeypatch):
    import diagnostics
    monkeypatch.setattr(hip.version, 'hip', None)
    monkeypatch.setattr(hip.cuda, 'is_available', lambda: False)
    monkeypatch.setattr(gpu_hardware, 'amd_adapters', lambda: [{'name': 'AMD Radeon', 'driver': 'test'}])
    report = diagnostics.collect_gpu_info()
    assert 'AMD' in report['подсказка'] and 'cu126' not in report['подсказка']


def test_windows_adapter_probe_uses_pci_vendor_and_returns_driver(monkeypatch):
    gpu_hardware._probe_amd.cache_clear()
    monkeypatch.setattr(gpu_hardware.sys, 'platform', 'win32')
    calls = []
    monkeypatch.setattr(gpu_hardware.subprocess, 'run', lambda *a, **k: calls.append((a, k)) or
        SimpleNamespace(returncode=0, stdout='{"Name":"AMD Radeon RX 7900 XTX","DriverVersion":"32.0"}'))
    try:
        assert gpu_hardware.amd_adapters() == [{'name': 'AMD Radeon RX 7900 XTX', 'driver': '32.0'}]
        assert 'VEN_1002' in calls[0][0][0][-1]
        assert calls[0][1]['timeout'] == 8
    finally:
        gpu_hardware._probe_amd.cache_clear()


def test_linux_amd_probe_ignores_other_vendors(tmp_path):
    for name, vendor in [('card0', '0x1002'), ('card1', '0x10de')]:
        path = tmp_path / name / 'device'
        path.mkdir(parents=True)
        (path / 'vendor').write_text(vendor)
    assert [entry['name'] for entry in gpu_hardware._linux_amd(tmp_path)] == ['AMD GPU (card0)']


def test_bootstrap_chooses_amd_profile_instead_of_nvidia(monkeypatch):
    monkeypatch.delenv('SCOTT_TORCH_BACKEND', raising=False)
    monkeypatch.setattr(bootstrap, 'has_nvidia_gpu', lambda: False)
    monkeypatch.setattr(gpu_hardware, 'amd_adapters', lambda: [{'name': 'AMD Radeon', 'driver': 'test'}])
    args, reason = bootstrap.torch_requirement()
    assert bootstrap.ROCM_INDEX in args and 'AMD' in reason and bootstrap.CUDA_INDEX not in args


def test_bootstrap_does_not_replace_existing_rocm_build(monkeypatch):
    monkeypatch.delenv('SCOTT_TORCH_BACKEND', raising=False)
    monkeypatch.setattr(bootstrap, 'torch_requirement', lambda: (bootstrap.rocm_requirement(), 'AMD'))
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: None)
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='True'))
    commands = []
    monkeypatch.setattr(bootstrap, '_run_pip', lambda executable, args, *a, **k: commands.append(args) or (True, ''))
    assert bootstrap.install_dependencies('test-python').done
    assert len(commands) == 1 and commands[0][0] == '-r'


def test_explicit_cpu_install_overrides_amd_and_existing_rocm(monkeypatch):
    monkeypatch.setenv('SCOTT_TORCH_BACKEND', 'cpu')
    monkeypatch.setattr(bootstrap, 'has_nvidia_gpu', lambda: pytest.fail('CPU choice must skip GPU probe'))
    args, _ = bootstrap.torch_requirement()
    assert args == ['--index-url', bootstrap.CPU_INDEX, bootstrap.TORCH_CPU_PIN]
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: None)
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='True'))
    commands = []
    monkeypatch.setattr(bootstrap, '_run_pip', lambda executable, args, *a, **k: commands.append(args) or (True, ''))
    assert bootstrap.install_dependencies('test-python').done
    assert commands[0] == args and commands[1][0] == '-r'


def test_amd_install_failure_still_prepares_cpu_backend(monkeypatch):
    monkeypatch.setattr(bootstrap, 'torch_requirement', lambda: (bootstrap.rocm_requirement(), 'AMD'))
    monkeypatch.setattr(bootstrap, 'ensure_pip', lambda *a: None)
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=''))
    commands = []
    def pip(executable, args, *a, **k):
        commands.append(args)
        return len(commands) != 1, 'not compatible'
    monkeypatch.setattr(bootstrap, '_run_pip', pip)
    assert bootstrap.install_dependencies('test-python').done
    assert 'https://download.pytorch.org/whl/cpu' in commands[1]
    assert commands[2][0] == '-r'


@pytest.mark.parametrize('gfx', ['gfx9999', 'cuda', 'gfx1100;echo', '../gfx1100'])
def test_unknown_or_malformed_amd_architecture_is_rejected(gfx):
    with pytest.raises(ValueError):
        bootstrap.rocm_requirement(gfx)


def test_device_endpoint_returns_amd_options_without_hardware_access(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(devices, 'CONFIG_PATH', tmp_path / 'devices.json')
    monkeypatch.setattr(devices, 'rocm_available', lambda: True)
    monkeypatch.setattr(devices, 'cuda_available', lambda: False)
    monkeypatch.setattr(devices, 'rocm_build', lambda: True)
    monkeypatch.setattr(devices, 'reset_loaded_models', lambda: None)
    for variable in devices.ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            response = await client.post('/settings/device', json={'engine': 'whisper', 'choice': 'rocm'})
            assert response.status_code == 200 and response.json()['engines']['whisper']['backend'] == 'rocm'
            assert (await client.post('/settings/device', json={'engine': [], 'choice': 5})).status_code == 400
    asyncio.run(check())


def test_amd_setup_defaults_to_a_plan(monkeypatch, capsys):
    import setup_amd
    monkeypatch.setattr(sys, 'argv', ['setup_amd.py', '--gfx', 'gfx1100'])
    monkeypatch.setattr(setup_amd.subprocess, 'run', lambda *a, **k: pytest.fail('Plan must not install packages'))
    assert setup_amd.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert 'torch[device-gfx1100]==2.13.0+rocm10.0.0' in plan['commands'][0]
    assert plan['commands'][1][-1].endswith('requirements.txt')


def test_amd_setup_requires_a_virtualenv_for_install(monkeypatch):
    import setup_amd
    monkeypatch.setattr(sys, 'argv', ['setup_amd.py', '--install'])
    monkeypatch.setattr(sys, 'prefix', 'system-python')
    monkeypatch.setattr(sys, 'base_prefix', 'system-python')
    monkeypatch.setattr(setup_amd.subprocess, 'run', lambda *a, **k: pytest.fail('System Python must stay unchanged'))
    with pytest.raises(SystemExit) as error:
        setup_amd.main()
    assert error.value.code == 2
