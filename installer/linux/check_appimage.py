"""Exercise real AppImages with private synthetic stores, without API calls.

Default uses the official extract-and-run runtime path (no FUSE). --fuse is an
explicit additional check and fails if /dev/fuse is unavailable. Run under Xvfb
or a desktop session, preferably with the Qt SDK hidden.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def check(image, second, work, fuse=False):
    images = [Path(image).resolve(strict=True), Path(second).resolve(strict=True)]
    if fuse and not Path('/dev/fuse').exists():
        raise ValueError('FUSE check requires /dev/fuse; no fallback was tested as FUSE.')
    work = Path(work).absolute()
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    home = work/'home'
    home.mkdir(mode=0o700)
    env = {key: value for key, value in os.environ.items()
           if not key.upper().endswith(('_API_KEY', '_TOKEN')) and
           key not in ('SCOTT_STORAGE_MODE', 'SCOTT_VOICE_HOME', 'PYTHONHOME', 'PYTHONPATH',
                       'QT_PLUGIN_PATH', 'QML_IMPORT_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH',
                       'APPIMAGE', 'APPDIR', 'APPIMAGE_EXTRACT_AND_RUN')}
    env.update(HOME=str(home), XDG_DATA_HOME=str(home/'data'), XDG_CONFIG_HOME=str(home/'config'),
               XDG_CACHE_HOME=str(home/'cache'), XDG_STATE_HOME=str(home/'state'),
               PYTHONDONTWRITEBYTECODE='1', PIP_NO_INDEX='1', QT_QUICK_BACKEND='software',
               QSG_RHI_BACKEND='software')
    checks = []

    def run(name, command, cwd=work, timeout=90):
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        (work/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(name+' failed; see '+str(work/(name+'.log')))
        checks.append(name)
        return result.stdout.strip()

    payloads = []
    hashes = []
    for index, source in enumerate(images):
        with source.open('rb') as stream:
            hashes.append(hashlib.file_digest(stream, 'sha256').hexdigest())
        directory = work/('extract-'+str(index))
        directory.mkdir()
        run('extract-'+str(index), [str(source), '--appimage-extract'], cwd=directory)
        payload = directory/'squashfs-root'
        assert json.loads((payload/'.scott-linux-install.json').read_text()) == {'image_layout': 1}
        assert not (payload/'runtime').exists() and not (payload/'backend/data').exists()
        for file in payload.rglob('*'):
            if not file.is_symlink():
                file.chmod(0o555 if file.is_dir() or file.stat().st_mode & 0o111 else 0o444)
        payload.chmod(0o555)
        payloads.append(payload)
    assert hashes[0] != hashes[1], 'Use two separately built images to test replacement'

    def select(index):
        root = payloads[index]
        return Path(run('select-'+str(index), [str(root/'python-runtime/bin/python3.13'), '-I',
                        str(root/'backend/linux_runtime.py'), '--root', str(root)]))

    python = select(0)
    slot = python.parents[2]
    assert python.is_relative_to(home/'data/scottai/runtimes')
    cfg = slot/'runtime/pyvenv.cfg'
    stamp = cfg.stat().st_mtime_ns
    site = slot/'runtime/lib/python3.13/site-packages'
    sentinel = site/'scott_image_fixture.py'
    sentinel.write_text("VALUE='persistent dependency'\n")
    synthetic = {home/'config/ScottAI/.env': b'SCOTT_APPIMAGE_FIXTURE=1\n',
                 home/'config/ScottAI/ai_config.json': b'{"provider":"fixture"}',
                 home/'data/scottai/attachments/fixture.txt': b'synthetic attachment',
                 home/'data/scottai/qt/profile/avatar.json': b'{"cleared":true}',
                 home/'config/ScottAI/QtPrototype.conf': b'[General]\nstyle=Glass\n'}
    for path, content in synthetic.items():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(content)
    # Use the actual stdlib store, not a simulated JSON history.
    store_code = ("import sys;sys.path.insert(0,sys.argv[1]);from chat_store import ChatStore;"
                  "from storage_paths import backend_path;s=ChatStore(backend_path('chats'));"
                  "chat=s.create();s.rename(chat['id'],'AppImage fixture');"
                  "s.commit_turn(chat['id'],'Synthetic question','Synthetic question','Synthetic answer',"
                  "'fixture',[('user','fixture.txt','text/plain',b'synthetic attachment')]);print(chat['id'])")
    ident = run('create-history', [str(python), '-I', '-c', store_code, str(payloads[0]/'backend')])

    def launch(name, source, flag):
        command = [str(source), *([] if fuse else ['--appimage-extract-and-run']), flag]
        run(name, command)

    launch('first-image-chat', images[0], '--smoke-chat')
    launch('first-image-setup', images[0], '--smoke-setup')
    # Remove the first extracted root from its original path and replace the
    # executable image itself at the same pathname. Runtime/data stay outside.
    # Move its writable extraction parent. Moving a 0555 directory between
    # parents requires changing its '..' entry, even when both parents are ours.
    payloads[0].parent.rename(work/'retained-first-extraction')
    replacement = work/'Scott AI обновление.AppImage'
    shutil.copy2(images[0], replacement)
    run('before-replacement', [str(replacement), '--appimage-version'])
    pending = work/'new-image.AppImage'
    shutil.copy2(images[1], pending)
    os.replace(pending, replacement)
    assert select(1) == python
    launch('second-image-chat', replacement, '--smoke-chat')
    launch('second-image-profile', replacement, '--smoke-profile')
    run('dependencies-preserved', [str(python), '-I', '-c',
        "import scott_image_fixture,ssl,sqlite3;assert scott_image_fixture.VALUE=='persistent dependency'"])
    run('pip-preserved', [str(slot/'runtime/bin/pip'), '--version'])
    run('history-preserved', [str(python), '-I', '-c',
        "import sys;sys.path.insert(0,sys.argv[1]);from chat_store import ChatStore;"
        "from storage_paths import backend_path;s=ChatStore(backend_path('chats'));"
        "chat=s.get(sys.argv[2]);assert chat['title']=='AppImage fixture';"
        "assert [m['text'] for m in chat['messages']]==['Synthetic question','Synthetic answer'];"
        "asset=chat['messages'][0]['attachments'][0]['url'].rsplit('/',1)[-1];"
        "assert (s.assets/asset).read_bytes()==b'synthetic attachment'", str(payloads[1]/'backend'), ident])
    assert cfg.stat().st_mtime_ns == stamp, 'Ready environment was recreated'
    assert all(path.read_bytes() == content for path, content in synthetic.items())
    result = dict(checks=checks, image_sha256=hashes, runtime=str(slot),
                  runtime_reused=True, synthetic_data_preserved=True,
                  fuse_tested=fuse, extract_and_run_tested=not fuse, physical_desktop=False,
                  dependencies='stdlib plus synthetic module; full backend/models not installed')
    (work/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--second-image', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--fuse', action='store_true')
    args = parser.parse_args()
    check(args.image, args.second_image, args.work, args.fuse)
