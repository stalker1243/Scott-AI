"""Verify the shipped fork, exact patch application and deterministic rebuilding."""
from pathlib import Path
import hashlib
import importlib.util
import json
import zipfile

import pytest
import scott_voice_sdk as sdk

pytestmark=pytest.mark.unit
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('voice_sdk_builder',ROOT/'tools/build_voice_sdk.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def test_developer_requirements_match_the_qualified_headless_sdk():
    lines=(ROOT/'voice/runtime/requirements.txt').read_text(encoding='utf-8').splitlines()
    assert {line for line in lines if line and not line.startswith('#')}==set(sdk.REQUIREMENTS)


def test_shipped_fork_matches_its_source_patch_and_preserves_license():
    wheel=ROOT/sdk.WHEEL
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==sdk.WHEEL_SHA256
    manifest=json.loads((ROOT/'tools/voice_compat/manifest.json').read_text())
    assert hashlib.sha256((ROOT/'tools/voice_compat/qwen-transformers5.patch').read_bytes()).hexdigest()==manifest['patch_sha256']
    with zipfile.ZipFile(wheel) as archive:
        assert any(name.endswith('/LICENSE') for name in archive.namelist())
        assert any(name.endswith('/SCOTT-NOTICE.txt') for name in archive.namelist())
        for name,info in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==info['after_sha256']
        metadata=archive.read('qwen_tts-'+sdk.QWEN+'.dist-info/METADATA').decode()
        assert 'Requires-Dist: transformers==5.20.1' in metadata
        assert 'Requires-Dist: gradio; extra == "web"' in metadata


def test_exact_patch_rejects_drift_and_missing_context():
    patch='--- a/module.py\n+++ b/module.py\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n'
    assert builder.apply_patch('alpha\nbeta\n',patch)=='alpha\ngamma\n'
    with pytest.raises(ValueError):builder.apply_patch('alpha\nchanged\n',patch)
    with pytest.raises(ValueError):builder.apply_patch('alpha\nbeta\n',patch.replace('@@ -1,2','@@ -1,3'))


def test_builder_is_reproducible_and_rejects_wrong_upstream(tmp_path):
    source=tmp_path/'upstream.whl';patches=tmp_path/'patches';patches.mkdir()
    original='alpha\nbeta\n';changed='alpha\ngamma\n'
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('module.py',original)
        archive.writestr('qwen_tts-0.1.1.dist-info/LICENSE','Apache fixture')
        archive.writestr('qwen_tts-0.1.1.dist-info/METADATA','Version: 0.1.1\nRequires-Dist: transformers==4.57.3\nRequires-Dist: accelerate==1.12.0\nRequires-Dist: gradio\n')
    patch='--- a/module.py\n+++ b/module.py\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n'
    (patches/'qwen-transformers5.patch').write_text(patch,encoding='utf-8',newline='\n')
    sha=lambda value:hashlib.sha256(value).hexdigest()
    manifest=dict(upstream_version='0.1.1',version_local='0.1.1+scott.fixture',transformers='5.20.1',accelerate='1.15.0',
        upstream_sha256=sha(source.read_bytes()),patch_sha256=sha(patch.encode()),
        files={'module.py':dict(before_sha256=sha(original.encode()),after_sha256=sha(changed.encode()))})
    (patches/'manifest.json').write_text(json.dumps(manifest))
    first=builder.build(source,tmp_path/'first',patches)
    second=builder.build(source,tmp_path/'second',patches)
    assert first['wheel_sha256']==second['wheel_sha256']
    source.write_bytes(b'wrong upstream')
    with pytest.raises(ValueError,match='Upstream wheel'):builder.build(source,tmp_path/'third',patches)
