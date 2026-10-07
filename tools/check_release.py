"""Check a Windows distribution against source files, without importing the backend."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(folder):
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT) or folder==ROOT:
        raise ValueError('Choose a distribution inside the project')
    version = json.loads((ROOT/'VERSION.json').read_text(encoding='utf-8'))
    assert json.loads((folder/'VERSION.json').read_text(encoding='utf-8'))==version
    modules = list((ROOT/'backend').glob('*.py'))
    assert all(sha(folder/'backend'/source.name)==sha(source) for source in modules)
    assert sha(folder/'backend/requirements.txt')==sha(ROOT/'backend/requirements.txt')
    assert not (folder/'backend/data').exists() and not (folder/'data').exists()
    assert not (folder/'.env').exists() and not (folder/'backend/tests').exists()
    assert not (folder/'voice-runtime').exists()
    assert sha(folder/'launcher/ScottAIQt.exe')==sha(ROOT/'ScottAI_qt/build/ScottAIQt.exe')
    assert all((folder/'launcher'/name).is_file() for name in
               ('Qt6Core.dll','Qt6Quick.dll','Qt6Network.dll','platforms/qwindows.dll'))
    spec = importlib.util.spec_from_file_location('voice_install_builder',ROOT/'backend/scott_voice_install.py')
    setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
    sources = setup.asset_sources(ROOT)
    bundled = setup.asset_sources(folder)
    assert all(sha(sources[name])==sha(bundled[name]) for name in sources)
    assert sha(bundled['reports/voice-design/reference/scott-reference.wav'])==setup.REFERENCE_SHA
    assert all((folder/name).is_file() for name in ('runtime/python.exe','runtime/get-pip.py',
                                                  'LICENSE','RELEASE-NOTES.md','.env.example'))
    runtime = subprocess.run([str(folder/'runtime/python.exe'),'-c',
        'import json,sys; print(json.dumps({"version":sys.version_info[:3],"prefix":sys.prefix,"paths":sys.path}))'],
        capture_output=True,text=True,check=True)
    interpreter = json.loads(runtime.stdout)
    assert interpreter['version']==[3,13,7]
    assert Path(interpreter['prefix']).resolve()==folder/'runtime'
    assert all(Path(path).resolve().is_relative_to(folder) for path in interpreter['paths'])
    return dict(version=version['version'],backend_modules=len(modules),backend_sources_equal=True,
        optional_voice_assets=len(sources),reference_sha256=setup.REFERENCE_SHA,
        personal_data_included=False,python_version='3.13.7',python_isolated=True,
        qt_dlls_included=True,launcher_sha256=sha(folder/'launcher/ScottAIQt.exe'),
        distribution_bytes=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file()))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',required=True,type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    result = verify(args.dist)
    if args.report:
        target = args.report.resolve()
        assert target.is_relative_to(ROOT/'reports')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
