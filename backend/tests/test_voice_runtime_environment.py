"""Voice children ignore foreign Python paths, homes and startup customizations."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import scott_voice_engine as engine
import scott_voice_process as process
from test_scott_voice_process import config

pytestmark=pytest.mark.unit


@pytest.fixture
def clean_worker(config):
    backend=repr(str(Path(process.__file__).resolve().parent))
    script='import sys\nsys.path.insert(0,'+backend+')\n'+'''
import argparse,importlib.util,json,os
from pathlib import Path
from scott_voice_process import PROTOCOL,VoiceProcessConfig,recipe_id,watch_owner
watch_owner()
p=argparse.ArgumentParser();p.add_argument('--configuration');a=p.parse_args()
c=VoiceProcessConfig.from_wire(json.loads(a.configuration))
info=dict(flags=[sys.flags.ignore_environment,sys.flags.no_user_site,sys.dont_write_bytecode,sys.flags.utf8_mode],
    foreign_module=importlib.util.find_spec('scott_foreign_module') is not None,
    startup=os.getenv('SCOTT_FOREIGN_STARTUP'),
    python_keys=sorted(k for k in os.environ if k.upper().startswith('PYTHON')),
    secrets=any((k.upper().endswith(('_API_KEY','_TOKEN')) or k.upper().startswith('AWS_'))
        and k.upper()!='HF_HUB_DISABLE_IMPLICIT_TOKEN' for k in os.environ))
(c.cache_dir/'startup.json').write_text(json.dumps(info),encoding='utf-8')
def emit(packet): print(json.dumps(packet),flush=True)
emit(dict(event='ready',protocol=PROTOCOL,recipe=recipe_id(c),features=['prepare_v1']))
for line in sys.stdin:
    packet=json.loads(line)
    emit(dict(event='prepared',id=packet['id'],recipe=recipe_id(c)))
'''
    config.worker.write_text(script,encoding='utf-8')
    return config


@pytest.mark.parametrize('setting',['PYTHONPATH','PYTHONHOME','PYTHONUSERBASE','PYTHONSAFEPATH',
                                  'PYTHONINSPECT','PYTHONWARNINGS','PYTHONPYCACHEPREFIX'])
def test_real_child_ignores_foreign_python_startup(clean_worker,tmp_path,monkeypatch,setting):
    foreign=tmp_path/'foreign'
    foreign.mkdir()
    (foreign/'scott_foreign_module.py').write_text('VALUE=1\n')
    (foreign/'sitecustomize.py').write_text("import os;os.environ['SCOTT_FOREIGN_STARTUP']='yes'\n")
    monkeypatch.setenv(setting,'1' if setting in ('PYTHONSAFEPATH','PYTHONINSPECT') else str(foreign))
    monkeypatch.setenv('scott_dummy_api_key','synthetic')
    monkeypatch.setenv('SCOTT_DUMMY_TOKEN','synthetic')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID','synthetic')
    snapshot=dict(os.environ)
    with process.ScottVoiceProcess(clean_worker,idle_timeout=0,startup_timeout=5) as client:
        client.prepare()
    info=json.loads((clean_worker.cache_dir/'startup.json').read_text())
    assert info['flags']==[1,1,True,1]
    assert not info['foreign_module'] and not info['startup'] and not info['secrets']
    assert info['python_keys']==['PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','PYTHONUTF8']
    assert dict(os.environ)==snapshot
    assert not client.status()['running']


def test_runtime_probe_uses_the_same_isolated_interpreter(monkeypatch,tmp_path):
    foreign=tmp_path/'foreign'
    foreign.mkdir()
    (foreign/'scott_foreign_module.py').write_text('VALUE=1\n')
    monkeypatch.setenv('PYTHONPATH',str(foreign))
    monkeypatch.setenv('PYTHONHOME',str(foreign))
    monkeypatch.setenv('scott_dummy_api_key','synthetic')
    real_popen=subprocess.Popen
    calls=[]
    def popen(command,**kw):
        calls.append((list(command),dict(kw)))
        assert 'import torch' in command[-1] and str(engine.SDK_VERSIONS) in command[-1]
        # Execute only the startup boundary in this unit test; actual CUDA and
        # pinned-package readiness are qualified with the real SDK separately.
        script="import importlib.util,json,sys; print(json.dumps(dict(ready=bool(sys.flags.ignore_environment and sys.flags.no_user_site and sys.flags.utf8_mode and sys.dont_write_bytecode and importlib.util.find_spec('scott_foreign_module') is None),compatible=True,cuda=True)))"
        return real_popen([*command[:-1],script],**kw)
    monkeypatch.setattr(engine.subprocess,'Popen',popen)
    engine._probe_runtime.cache_clear()
    try:
        assert engine._probe_runtime(sys.executable,'cuda','startup-boundary')==''
        command,kw=calls[0]
        assert command[1:-2]==['-E','-s','-B','-X','utf8']
        assert not any(k in kw['env'] for k in ('PYTHONPATH','PYTHONHOME','scott_dummy_api_key'))
        assert kw['env']['HF_HUB_OFFLINE']=='1' and kw['env']['TRANSFORMERS_OFFLINE']=='1'
    finally: engine._probe_runtime.cache_clear()
