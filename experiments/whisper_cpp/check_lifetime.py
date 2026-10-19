"""Kill only disposable test owners and verify their workers release the model."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]


class OwnedProcess:
    def __init__(self, pid, created, exe, parent):
        self.process = psutil.Process(pid)
        if abs(self.process.create_time()-created) > .001:
            raise RuntimeError('unexpected_process_identity')
        if Path(self.process.exe()).resolve() != Path(exe).resolve() or self.process.ppid() != parent:
            raise RuntimeError('unexpected_process_path_or_parent')
        self.created = created
        self.exe = exe

    def alive(self):
        try:
            return self.process.is_running() and self.process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def stop(self):
        if self.alive():
            # Check current identity, parent and path before stopping a known fixture.
            current = psutil.Process(self.process.pid)
            if abs(current.create_time()-self.created) > .001 or Path(current.exe()).resolve() != Path(self.exe).resolve():
                raise RuntimeError('changed_process_identity')
            current.ppid()  # Reparenting after the disposable owner dies is expected.
            current.kill()
            deadline = time.monotonic()+5
            while self.alive() and time.monotonic() < deadline:
                time.sleep(.01)
            if self.alive(): raise RuntimeError('fixture_cleanup_timeout')
        if os.name != 'nt':
            try:
                os.waitpid(self.process.pid, os.WNOHANG)
            except ChildProcessError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'model', 'corpus', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'vulkan'), default='cpu')
    parser.add_argument('--observe', action='store_true')
    parser.add_argument('--explicit-owner', action='store_true')
    args = parser.parse_args()
    for name in ('worker', 'model', 'corpus', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    if not args.output.is_relative_to(ROOT/'reports') or args.output.exists():
        parser.error('Choose a new report directory')
    if not args.model.is_relative_to(ROOT/'reports'):
        parser.error('Use experimental weights inside reports')
    args.output.mkdir(parents=True)
    fixtures = args.output/'fixtures'
    fixtures.mkdir()
    shutil.copy2(args.corpus/'prompt.txt', fixtures/'prompt.txt')
    pcm = (args.corpus/'000.f32').read_bytes()
    length = 16000*30*4
    (fixtures/'000.f32').write_bytes((pcm*((length+len(pcm)-1)//len(pcm)))[:length])
    rows = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    scenarios = [('active', True, False, False), ('idle_inherited_pipe', False, True, False)]
    if args.explicit_owner:
        scenarios.append(('during_startup', False, False, True))
    for name, active, inherited, startup in scenarios:
        state = args.output/f'{name}.json'
        command = [sys.executable, str(Path(__file__).with_name('owner_fixture.py')),
            '--worker', str(args.worker), '--model', str(args.model), '--corpus', str(fixtures),
            '--state', str(state), '--device', args.device]
        if active: command.append('--active')
        if inherited: command.append('--inherit-pipe')
        if args.explicit_owner: command.append('--explicit-owner')
        worker = holder = None
        with (args.output/f'{name}.owner.log').open('w', encoding='utf-8') as log:
            owner = subprocess.Popen(command, stdout=log, stderr=log, creationflags=flags)
            try:
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    value = json.loads(state.read_text()) if state.exists() else {}
                    if value.get('phase') == ('starting' if startup else 'active' if active else 'idle'):
                        break
                    if owner.poll() is not None: raise RuntimeError('owner_fixture_exited')
                    time.sleep(.01)
                else: raise RuntimeError('owner_fixture_not_ready')
                assert value['owner_pid'] == owner.pid
                worker = OwnedProcess(value['worker_pid'], value['worker_created'], value['worker_exe'], owner.pid)
                if inherited:
                    holder = OwnedProcess(value['holder_pid'], value['holder_created'], value['holder_exe'], owner.pid)
                if active: time.sleep(.25)
                started = time.monotonic()
                owner.kill(); owner.wait(timeout=5)
                while worker.alive() and time.monotonic()-started < 2:
                    time.sleep(.01)
                stopped = not worker.alive()
                rows.append(dict(name=name, worker_stopped=stopped, seconds=time.monotonic()-started,
                    holder_still_alive=holder.alive() if holder else None))
            finally:
                if owner.poll() is None:
                    owner.kill(); owner.wait(timeout=5)
                if worker: worker.stop()
                if holder: holder.stop()
    report = dict(checks=rows, observation_only=args.observe, microphone_used=False,
        playback_used=False, commands_executed=False)
    (args.output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    if not args.observe:
        assert all(r['worker_stopped'] for r in rows)


if __name__ == '__main__':
    main()
