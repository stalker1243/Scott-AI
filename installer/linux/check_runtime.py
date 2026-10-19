"""Offline package checks for persistent Linux Python and read-only mount paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def check(package, work, wayland=False):
    package=package.resolve()
    if (package/'.env').exists() or (package/'backend/data').exists():
        raise ValueError('Expected a clean distribution without personal data')
    work=work.resolve()
    work.mkdir(mode=0o700,parents=True,exist_ok=False)
    home=work/'home';home.mkdir(mode=0o700)
    env={key:value for key,value in os.environ.items()
         if not key.upper().endswith(('_API_KEY','_TOKEN'))
         and key not in ('SCOTT_STORAGE_MODE','SCOTT_VOICE_HOME','PYTHONPATH','PYTHONHOME')}
    env.update(HOME=str(home),XDG_DATA_HOME=str(home/'data'),XDG_CONFIG_HOME=str(home/'config'),
               XDG_STATE_HOME=str(home/'state'),XDG_CACHE_HOME=str(home/'cache'),
               PYTHONDONTWRITEBYTECODE='1',PIP_NO_INDEX='1')
    for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM','QML_IMPORT_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):
        env.pop(key,None)
    checks=[]
    def run(name,command,timeout=90):
        result=subprocess.run(command,env=env,cwd=work,capture_output=True,text=True,
                              encoding='utf-8',errors='replace',timeout=timeout)
        (work/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:
            raise RuntimeError(name+' failed; see '+str(work/(name+'.log')))
        checks.append(dict(name=name,exit_code=result.returncode))
        return result.stdout.strip()
    prefix=work/'Installed Scott AI'
    def install(name):
        run(name,['bash',str(package/'install.sh'),'--prefix',str(prefix),'--no-shortcut'])
    install('fresh-install')
    metadata=json.loads((prefix/'.scott-linux-install.json').read_text())
    slot=Path(metadata['runtime_home'])
    python=slot/'runtime/bin/python'
    assert prefix.joinpath('runtime').is_symlink() and not slot.is_relative_to(prefix)
    info=json.loads(run('persistent-python',[str(python),'-I','-c',
        'import sys,json,sqlite3,ssl;print(json.dumps(dict(base=sys.base_prefix,prefix=sys.prefix)))']))
    assert info==dict(base=str(slot/'python-runtime'),prefix=str(slot/'runtime'))
    site=slot/'runtime/lib/python3.13/site-packages'
    sentinel=site/'scott_runtime_fixture.py';sentinel.write_text("VALUE='persistent fixture'\n")
    before=hashlib.sha256(sentinel.read_bytes()).hexdigest()
    cfg=slot/'runtime/pyvenv.cfg';stamp=cfg.stat().st_mtime_ns
    def intact():
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
        assert cfg.stat().st_mtime_ns==stamp,'Ready venv was recreated'
    install('update-offline');intact()
    run('uninstall',['bash',str(prefix/'uninstall.sh')]);intact()
    assert not (prefix/'runtime').is_symlink() and not (prefix/'launcher/ScottAIQt').exists()
    install('reinstall-offline');intact()
    env['XDG_DATA_HOME']=str(home/'changed data')
    install('xdg-change-update');intact()
    assert json.loads((prefix/'.scott-linux-install.json').read_text())['runtime_home']==str(slot)
    env['XDG_DATA_HOME']=str(home/'data')
    # Model changing AppImage mounts without requiring FUSE. Both images are
    # read-only, have no runtime pointer, and use the same persistent venv.
    def image(path):
        shutil.copytree(package,path,symlinks=True)
        (path/'.scott-linux-install.json').write_text('{"image_layout":1}')
        for file in path.rglob('*'):
            if not file.is_symlink():
                file.chmod(0o555 if file.is_dir() or file.stat().st_mode&0o111 else 0o444)
        path.chmod(0o555)
        return path
    first=image(work/'image mount A')
    def select(name,mount):
        value=run(name,[str(mount/'python-runtime/bin/python3.13'),'-I',
                  str(mount/'backend/linux_runtime.py'),'--root',str(mount)])
        assert value==str(python)
    select('first-readonly-mount',first)
    first.rename(work/'retained previous mount')
    second=image(work/'image mount B')
    select('second-readonly-mount',second)
    run('dependencies-after-mount-change',[str(python),'-I','-c',
        "import scott_runtime_fixture;assert scott_runtime_fixture.VALUE=='persistent fixture'"])
    run('pip-after-mount-change',[str(slot/'runtime/bin/pip'),'--version'])
    intact()
    if wayland:
        run('readonly-wayland',[sys.executable,str(Path(__file__).with_name('check_wayland.py')),
            '--prefix',str(second),'--output',str(work/'wayland')],timeout=180)
    value=dict(checks=checks,python_base=info['base'],runtime=info['prefix'],
               base_regular_file_bytes=sum(file.stat().st_size for file in (slot/'python-runtime').rglob('*')
                                           if file.is_file() and not file.is_symlink()),
               read_only_mounts=True,offline=True,venv_preserved=True,
               physical_desktop=False,appimage_fuse_tested=False)
    (work/'results.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps(value))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--wayland',action='store_true')
    args=parser.parse_args()
    check(args.package,args.work,args.wayland)
