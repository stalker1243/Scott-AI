"""Reproduce the ScottAI Qwen compatibility wheel from its pinned upstream wheel.

The runtime installer uses the bundled wheel; this developer tool performs no
installation and needs no GPU, model weights, network or external patch utility.
"""
from pathlib import Path
import argparse
import base64
import csv
import hashlib
import io
import json
import re
import zipfile

HERE=Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply_patch(original, patch):
    """Apply exact unified hunks, rejecting context drift instead of guessing."""
    lines=original.splitlines(keepends=True)
    result=[];cursor=0;hunk=None;removed=added=0
    for line in patch.splitlines(keepends=True):
        if line.startswith(('--- ','+++ ')):
            continue
        if line.startswith('@@ '):
            if hunk and (removed,added)!=(hunk[1],hunk[3]):
                raise ValueError('Incomplete source hunk')
            match=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n',line)
            if not match:
                raise ValueError('Invalid source hunk')
            hunk=tuple(int(value) if value is not None else 1 for value in match.groups())
            start=hunk[0]-1 if hunk[0] else 0
            if not cursor<=start<=len(lines):
                raise ValueError('Unordered source patch')
            result.extend(lines[cursor:start]);cursor=start;removed=added=0
            continue
        if not hunk or line[:1] not in (' ','-','+'):
            raise ValueError('Unsupported source patch')
        if line[0] in (' ','-'):
            if cursor>=len(lines) or lines[cursor]!=line[1:]:
                raise ValueError('Source patch context mismatch')
            cursor+=1;removed+=1
        if line[0] in (' ','+'):
            result.append(line[1:]);added+=1
    if not hunk or (removed,added)!=(hunk[1],hunk[3]):
        raise ValueError('Incomplete source patch')
    return ''.join([*result,*lines[cursor:]])


def build(upstream, output, sources=HERE/'voice_compat'):
    manifest=json.loads((sources/'manifest.json').read_text(encoding='utf-8'))
    raw=Path(upstream).read_bytes()
    if sha(raw)!=manifest['upstream_sha256']:
        raise ValueError('Upstream wheel SHA256 mismatch')
    patch=(sources/'qwen-transformers5.patch').read_bytes()
    if sha(patch)!=manifest['patch_sha256']:
        raise ValueError('Source patch SHA256 mismatch')
    patches={}
    for block in patch.decode('utf-8').split('--- a/')[1:]:
        name=block.split('\n',1)[0]
        if name not in manifest['files'] or name in patches:
            raise ValueError('Unexpected patched file')
        patches[name]='--- a/'+block
    if set(patches)!=set(manifest['files']):
        raise ValueError('Incomplete source patch files')
    old_info='qwen_tts-'+manifest['upstream_version']+'.dist-info'
    new_info='qwen_tts-'+manifest['version_local']+'.dist-info'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files={name.replace(old_info,new_info):archive.read(name) for name in archive.namelist() if not name.endswith('/RECORD')}
    for name,patch in patches.items():
        before=files[name]
        if sha(before)!=manifest['files'][name]['before_sha256']:
            raise ValueError('Original source SHA256 mismatch')
        after=apply_patch(before.decode('utf-8'),patch).encode('utf-8')
        if sha(after)!=manifest['files'][name]['after_sha256']:
            raise ValueError('Patched source SHA256 mismatch')
        files[name]=after
    name=new_info+'/METADATA'
    value=files[name].decode('utf-8')
    changes=[('Version: '+manifest['upstream_version']+'\n','Version: '+manifest['version_local']+'\n'),
        ('Requires-Dist: transformers==4.57.3\n','Requires-Dist: transformers=='+manifest['transformers']+'\n'),
        ('Requires-Dist: accelerate==1.12.0\n','Requires-Dist: accelerate=='+manifest['accelerate']+'\n'),
        ('Requires-Dist: gradio\n','Provides-Extra: web\nRequires-Dist: gradio; extra == "web"\n')]
    for before,after in changes:
        if value.count(before)!=1:
            raise ValueError('Upstream metadata changed')
        value=value.replace(before,after,1)
    files[name]=value.encode('utf-8')
    notice=('ScottAI compatibility changes, 2026-10-19, Apache-2.0.\n'
        'Upstream: https://github.com/QwenLM/Qwen3-TTS\n'
        'Modified: three Python files for Transformers 5 API, generation masks,\n'
        'Mimi causal context and nonpersistent RoPE initialization.\n'
        'Transformers 4.57.3 default RoPE formula: Hugging Face, Apache-2.0.\n'
        'Source patch, provenance and reproducible builder ship with ScottAI.\n'
        'Gradio is optional (web extra); the headless worker does not use it.\n')
    files[new_info+'/SCOTT-NOTICE.txt']=notice.encode('utf-8')
    buffer=io.StringIO(newline='');writer=csv.writer(buffer,lineterminator='\n')
    for name,value in sorted(files.items()):
        writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(value).digest()).decode().rstrip('='),str(len(value))])
    writer.writerow([new_info+'/RECORD','','']);files[new_info+'/RECORD']=buffer.getvalue().encode('utf-8')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    wheel=output/('qwen_tts-'+manifest['version_local']+'-py3-none-any.whl')
    if wheel.exists():
        raise ValueError('Output wheel already exists')
    with zipfile.ZipFile(wheel,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,value in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            archive.writestr(info,value)
    provenance=dict(manifest,wheel=wheel.name,wheel_sha256=sha(wheel.read_bytes()),license_preserved=True)
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8',newline='\n')
    (output/'NOTICE.txt').write_text(notice,encoding='utf-8',newline='\n')
    return provenance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.upstream,args.output)))


if __name__=='__main__':main()
