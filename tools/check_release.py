"""Check a Windows distribution against source files, without starting the backend."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pe_version(path):
    """Read the fixed PE resource, rather than trusting the adjacent JSON."""
    import ctypes
    api = ctypes.windll.version
    size = api.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        raise ValueError('Missing Windows executable version: ' + path.name)
    data = ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path), 0, size, data):
        raise ValueError('Unreadable Windows executable version: ' + path.name)
    pointer, length = ctypes.c_void_p(), ctypes.c_uint()
    if not api.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        raise ValueError('Invalid Windows executable version: ' + path.name)
    fixed = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
    return [fixed[2] >> 16, fixed[2] & 65535, fixed[3] >> 16, fixed[3] & 65535]


def verify(folder, build_directory=None):
    folder = folder.resolve()
    build = (build_directory or ROOT/'ScottAI_qt/build').resolve()
    assert build.is_relative_to(ROOT) and build != ROOT
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
    for source in (ROOT/'installer/licenses').rglob('*'):
        if source.is_file():
            assert sha(folder/'licenses'/source.relative_to(ROOT/'installer/licenses'))==sha(source)
    for name in ('guide.md', 'installation.md', 'interface.md', 'security.md', 'performance.md', 'models.md', 'commands.md', 'desktop-control.md', 'browser-control.md', 'chat.md', 'companions.md', 'logs.md', 'voice-check.md', 'voice.md', 'linux.md', 'memory.md', 'protocols.md', 'recognition.md', 'reliability.md', 'release-notes-next.md'):
        assert sha(folder/'docs'/name)==sha(ROOT/'docs'/name)
    notes = ROOT/'docs'/f"release-notes-{version['version']}.md"
    assert sha(folder/'RELEASE-NOTES.md') == sha(notes)
    assert sha(folder/'docs'/notes.name) == sha(notes)
    assert sha(folder/'launcher/ScottAIQt.exe')==sha(build/'ScottAIQt.exe')
    assert sha(folder/'launcher/ScottAIUpdater.exe')==sha(build/'ScottAIUpdater.exe')
    expected_version = [int(value) for value in version['version'].split('.')] + [int(version['build_number'])]
    versions = {name: pe_version(folder/'launcher'/name) for name in ('ScottAIQt.exe', 'ScottAIUpdater.exe')}
    assert all(parts == expected_version for parts in versions.values()), versions
    helper = folder/'backend/native/ScottSystem.exe'
    assert sha(helper)==sha(build/'ScottSystem.exe')
    native = subprocess.run([str(helper), 'probe'], capture_output=True, text=True, check=True,
                            timeout=4, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert json.loads(native.stdout)=={'protocol': 1, 'success': True}
    assert all((folder/'launcher'/name).is_file() for name in
               ('Qt6Core.dll','Qt6Quick.dll','Qt6Network.dll','platforms/qwindows.dll'))
    spec = importlib.util.spec_from_file_location('voice_install_builder',ROOT/'backend/scott_voice_install.py')
    setup = importlib.util.module_from_spec(spec)
    # This CLI must also work outside the repository's backend directory.
    # Only the installer helper is loaded; its sibling modules belong here.
    previous_path = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT/'backend'))
        spec.loader.exec_module(setup)
    finally:
        sys.path[:] = previous_path
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
        qt_dlls_included=True,license_contents_equal=True,public_command_docs_equal=True,
        native_helper_bytes=helper.stat().st_size,native_probe_passed=True,
        launcher_sha256=sha(folder/'launcher/ScottAIQt.exe'),
        updater_sha256=sha(folder/'launcher/ScottAIUpdater.exe'),pe_versions=versions,
        distribution_bytes=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file()))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',required=True,type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--build-directory',type=Path,default=ROOT/'ScottAI_qt/build')
    args = parser.parse_args()
    result = verify(args.dist,args.build_directory)
    if args.report:
        target = args.report.resolve()
        assert target.is_relative_to(ROOT/'reports')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
