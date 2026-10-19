"""A release gate must not silently ignore incomplete or unfixable findings."""
from pathlib import Path
import importlib.util
import pytest

pytestmark = pytest.mark.unit


def load():
    path = Path(__file__).resolve().parents[2]/'tools/audit_dependencies.py'
    spec = importlib.util.spec_from_file_location('audit_dependency_fixture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('mode', ['finding', 'missing', 'mismatch', 'skipped', 'incomplete', 'wrong-version', 'tool-failed'])
def test_incomplete_or_unsafe_audit_fails(mode):
    module = load()
    scope = dict(packages={'fixture': '1'}, missing=[], mismatches=[])
    audit = dict(dependencies=[dict(name='fixture', version='1', vulns=[])])
    code = 0
    if mode == 'finding': audit['dependencies'][0]['vulns'] = [dict(id='FIXTURE-1', fix_versions=[])]
    if mode == 'missing': scope['missing'] = ['other']
    if mode == 'mismatch': scope['mismatches'] = [dict(name='fixture', installed='1', wanted='==2')]
    if mode == 'skipped': audit['dependencies'][0]['skip_reason'] = 'unavailable'
    if mode == 'incomplete': audit['dependencies'] = []
    if mode == 'wrong-version': audit['dependencies'][0]['version'] = '2'
    if mode == 'tool-failed': code = 2
    assert not module.verdict(scope, audit, code)['passed']


def test_complete_clean_audit_passes():
    module = load()
    assert module.verdict(dict(packages={'fixture': '1'}, missing=[], mismatches=[]),
                          dict(dependencies=[dict(name='fixture', version='1', vulns=[])]), 0)['passed']


def test_empty_scope_does_not_approve_a_release():
    module=load()
    assert not module.verdict(dict(packages={},missing=[],mismatches=[]),dict(dependencies=[]),0)['passed']


@pytest.mark.parametrize('transformers', ['5.20.1','4.57.3'])
def test_local_build_versions_remain_visible_and_dependencies_are_checked(tmp_path, monkeypatch, transformers):
    from types import SimpleNamespace
    module=load()
    requirements=tmp_path/'voice-requirements.txt'
    requirements.write_text('qwen-tts==0.1.1+scott.compat3\ntorch>=2.13.0\n')
    rows={'qwen-tts':SimpleNamespace(version='0.1.1+scott.compat3',requires=['transformers==5.20.1']),
          'transformers':SimpleNamespace(version=transformers,requires=[]),
          'torch':SimpleNamespace(version='2.14.1+cu126',requires=[])}
    monkeypatch.setattr(module.metadata,'distribution',lambda name:rows[name])
    monkeypatch.setattr(module.metadata,'version',lambda name:rows[name].version)
    scope=module.collect(requirements)
    assert scope['packages']=={'qwen-tts':'0.1.1','transformers':transformers,'torch':'2.14.1'}
    assert scope['installed_versions']['qwen-tts']=='0.1.1+scott.compat3'
    assert scope['installed_versions']['torch']=='2.14.1+cu126'
    assert bool(scope['mismatches'])==(transformers!='5.20.1')
