"""Disposable test owner/pipe holder; only saved experimental PCM is sent."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold-pipe', action='store_true')
    for name in ('worker', 'model', 'corpus', 'state'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--active', action='store_true')
    parser.add_argument('--device', choices=('cpu', 'vulkan'), default='cpu')
    parser.add_argument('--inherit-pipe', action='store_true')
    parser.add_argument('--explicit-owner', action='store_true')
    args = parser.parse_args()
    if args.hold_pipe:
        time.sleep(40)
        return
    command = [str(args.worker), str(args.model), str(args.corpus), 'gpu' if args.device == 'vulkan' else 'cpu', '8',
        str(args.corpus/'prompt.txt'), '0']
    if args.explicit_owner:
        command.append(json.dumps(dict(owner_pid=os.getpid())))
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    holder = None
    ready = None
    def save(phase):
        value = dict(phase=phase, owner_pid=os.getpid(), worker_pid=process.pid,
            worker_created=child.create_time(), worker_exe=child.exe(),
            owner_monitor=ready.get('owner_monitor') if ready else None)
        if holder:
            identity = psutil.Process(holder.pid)
            value.update(holder_pid=holder.pid, holder_created=identity.create_time(), holder_exe=identity.exe())
        temporary = args.state.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(args.state)
    with args.state.with_suffix('.worker.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, encoding='utf-8', creationflags=flags)
        child = psutil.Process(process.pid)
        try:
            save('starting')
            ready = json.loads(process.stdout.readline())
            if ready.get('event') != 'ready':
                raise RuntimeError('worker_not_ready')
            if args.inherit_pipe:
                # A duplicate write handle remains open even when this owner dies.
                holder = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--hold-pipe'],
                    stdin=process.stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            if args.active:
                process.stdin.write(json.dumps(dict(id=1, pcm='000.f32', timeout_ms=120000))+'\n')
                process.stdin.flush()
            save('active' if args.active else 'idle')
            while True:
                time.sleep(.1)
        finally:
            if holder and holder.poll() is None:
                holder.kill(); holder.wait(timeout=10)
            if process.poll() is None:
                process.kill(); process.wait(timeout=10)


if __name__ == '__main__':
    main()
