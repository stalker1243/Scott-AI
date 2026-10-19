"""Apply a checksum-verified Linux release using its per-user installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


def apply(archive, sha256, version, prefix):
    archive,prefix=Path(archive).resolve(),Path(prefix).absolute()
    if not re.fullmatch('[a-f0-9]{64}',sha256):raise ValueError('Некорректная контрольная сумма.')
    if any(part.is_symlink() for part in (prefix,*prefix.parents)):
        raise ValueError('Папка установки содержит ссылку.')
    if not (prefix/'.scott-linux-install.json').is_file():
        raise ValueError('Папка не является установленным ScottAI.')
    installation=json.loads((prefix/'.scott-linux-install.json').read_text(encoding='utf-8'))
    if not isinstance(installation,dict) or 'image_layout' in installation:
        raise ValueError('Для AppImage требуется заменить сам образ, а не его временную папку.')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=sha256:
            raise ValueError('Контрольная сумма обновления не совпала.')
    def stage(message):print(json.dumps(dict(message=message),ensure_ascii=False),flush=True)
    stage('Распаковываем обновление…')
    with tempfile.TemporaryDirectory(prefix='release-',dir=archive.parent) as temporary:
        with tarfile.open(archive) as bundle:
            members=bundle.getmembers()
            if not members or len(members)>50000:raise ValueError('Некорректный архив обновления.')
            roots=set();total=0
            for entry in members:
                name=PurePosixPath(entry.name)
                if name.is_absolute() or '..' in name.parts or not name.parts:
                    raise ValueError('Некорректный путь в архиве обновления.')
                roots.add(name.parts[0])
                if entry.mode&0o7000 or not (entry.isfile() or entry.isdir() or entry.issym() or entry.islnk()):
                    raise ValueError('Недопустимый тип файла в обновлении.')
                if name.parts[1:2]==('.env',) or name.parts[1:3]==('backend','data'):
                    raise ValueError('Обновление содержит пользовательские данные.')
                total+=entry.size
                if total>3*1024**3:raise ValueError('Распакованное обновление слишком велико.')
            if len(roots)!=1 or not re.fullmatch(r'ScottAI-[A-Za-z0-9.+-]+-Qt-linux-x86_64',next(iter(roots))):
                raise ValueError('Неизвестный формат Linux-пакета.')
            if shutil.disk_usage(temporary).free<total+16*1024**2 or shutil.disk_usage(prefix).free<total:
                raise ValueError('Недостаточно места для распаковки и установки обновления.')
            bundle.extractall(temporary,members=members,filter='data')
        source=Path(temporary)/next(iter(roots))
        metadata=json.loads((source/'VERSION.json').read_text(encoding='utf-8'))
        if metadata.get('version')!=version or not (source/'launcher/ScottAIQt').is_file():
            raise ValueError('Версия пакета не совпала с выбранным обновлением.')
        stage('Устанавливаем обновление…')
        subprocess.run(['/bin/bash',str(source/'install.sh'),'--prefix',str(prefix),'--no-shortcut'],check=True)
    stage('Обновление установлено')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','sha256','version','prefix'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:apply(args.archive,args.sha256,args.version,args.prefix)
    except (OSError,ValueError,tarfile.TarError,subprocess.CalledProcessError) as error:
        parser.exit(1,str(error)+'\n')
