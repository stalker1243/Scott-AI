"""Update only identified Scott Voice runtime source files; preserve foreign edits."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(path):
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError('Неверный манифест файлов Scott Voice.')
    value=json.loads(path.read_text(encoding='utf-8'))
    files=value.get('files') if isinstance(value,dict) and value.get('version')==1 else None
    if not isinstance(files,dict) or any(not isinstance(name,str) or not isinstance(sha,str)
        or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) for name,sha in files.items()):
        raise ValueError('Неверный манифест файлов Scott Voice.')
    return files


def sync_assets(home, sources, legacy=None):
    """Stage updates after checking every target; roll back a failed commit."""
    home=Path(home).resolve()
    receipt=home/'scott-assets.json'
    previous=manifest(receipt) if receipt.exists() else (legacy or {})
    changed=[]
    hashes={name:digest(source) for name,source in sources.items()}
    for name,source in sources.items():
        target=home/name
        if not target.resolve().is_relative_to(home):
            raise ValueError('Путь установки выходит из выбранной папки: '+name)
        for item in (target,*target.parents):
            if item==home:
                break
            if item.is_symlink() or item.is_junction():
                raise ValueError('Папка установки содержит перенаправление: '+name)
        actual=digest(target) if target.is_file() else None
        if target.exists() and actual!=hashes[name]:
            if Path(name).suffix!='.py' or actual!=previous.get(name):
                raise ValueError('В папке другая версия файла; сохраните его перед обновлением: '+name)
        if actual!=hashes[name]:
            changed.append(name)
    if not changed and receipt.exists() and previous==hashes:
        return 0
    home.mkdir(parents=True,exist_ok=True)
    stage=home/('.asset-update-'+uuid.uuid4().hex)
    stage.mkdir()
    committed=[]
    old_receipt=receipt.read_bytes() if receipt.exists() else None
    try:
        for name in changed:
            new=stage/'new'/name
            new.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(sources[name],new)
            if digest(new)!=hashes[name]:
                raise ValueError('Изменился исходный файл Scott Voice: '+name)
            if (home/name).exists():
                backup=stage/'old'/name
                backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(home/name,backup)
        pending=stage/'receipt.json'
        pending.write_text(json.dumps(dict(version=1,files=hashes),indent=2),encoding='utf-8')
        for name in changed:
            target=home/name
            target.parent.mkdir(parents=True,exist_ok=True)
            os.replace(stage/'new'/name,target)
            committed.append(name)
        os.replace(pending,receipt)
    except BaseException:
        for name in reversed(committed):
            target=home/name
            if not target.is_file() or digest(target)!=hashes[name]:
                continue  # Preserve an edit made by somebody else during failure.
            backup=stage/'old'/name
            if backup.exists():
                os.replace(backup,target)
            else:
                target.unlink()
        if old_receipt is not None and not receipt.exists():
            receipt.write_bytes(old_receipt)
        raise
    finally:
        # Remove only the unique staging directory created above, under this home.
        if stage.resolve().is_relative_to(home) and not stage.is_symlink() and not stage.is_junction():
            shutil.rmtree(stage)
    return len(changed)
