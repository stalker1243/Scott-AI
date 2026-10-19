"""Audit the application's installed dependency tree without importing its code."""
from pathlib import Path
from importlib import metadata
from collections import deque
from datetime import datetime
import argparse
import json
import os
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def collect(requirements):
    queue = deque(); seen = {}; installed_versions = {}; visited = set(); missing = set(); mismatches = []
    def enqueue(requirement, parent):
        if requirement.marker and not requirement.marker.evaluate():
            return
        queue.append((requirement.name, frozenset(requirement.extras)))
        try:
            installed = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            return
        if not requirement.specifier.contains(installed):
            mismatches.append(dict(parent=parent, name=requirement.name, wanted=str(requirement.specifier), installed=installed))
    for line in requirements.read_text(encoding='utf-8-sig').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            enqueue(Requirement(line), 'requirements')
    while queue:
        name, extras = queue.popleft(); name = canonicalize_name(name)
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.add(name); continue
        seen[name] = Version(distribution.version).public
        installed_versions[name] = distribution.version
        for value in distribution.requires or ():
            requirement = Requirement(value)
            if requirement.marker and not any(requirement.marker.evaluate({'extra': extra}) for extra in extras or {''}):
                continue
            # The marker was already checked in the parent extras context.
            requirement.marker = None
            enqueue(requirement, name)
    return dict(packages=seen, installed_versions=installed_versions, missing=sorted(missing), mismatches=mismatches)


def verdict(scope, audit, returncode):
    affected = [dict(name=row['name'], version=row.get('version'),
                     advisories=[dict(id=item['id'], fixes=item.get('fix_versions', [])) for item in row.get('vulns', [])])
                for row in audit.get('dependencies', []) if row.get('vulns')]
    skipped = [row['name'] for row in audit.get('dependencies', []) if row.get('skip_reason')]
    dependencies = audit.get('dependencies', [])
    observed = {(canonicalize_name(row['name']), Version(row['version'])) for row in dependencies if row.get('version')}
    expected = {(canonicalize_name(name), Version(version)) for name, version in scope['packages'].items()}
    complete = bool(expected) and len(dependencies) == len(expected) and observed == expected
    passed = returncode == 0 and complete and not affected and not skipped and not scope['missing'] and not scope['mismatches']
    return dict(passed=passed, packages=len(scope['packages']), affected=affected, skipped=skipped,
                missing=scope['missing'], mismatches=scope['mismatches'], audit_complete=complete, auditor_exit_code=returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auditor-python', default=sys.executable, help='Python with pip-audit installed')
    parser.add_argument('--requirements', type=Path, default=ROOT/'backend/requirements.txt', help='Requirements for the selected backend or voice runtime')
    parser.add_argument('--output', type=Path, default=ROOT/'reports'/('security-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    args = parser.parse_args()
    requirements = args.requirements.resolve()
    if not requirements.is_file():
        parser.error('Requirements file does not exist')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    scope = collect(requirements)
    scope['requirements'] = str(requirements)
    (output/'scope.json').write_text(json.dumps(scope, indent=2), encoding='utf-8')
    exact = output/'requirements-exact.txt'
    exact.write_text(''.join(f'{name}=={version}\n' for name, version in sorted(scope['packages'].items())), encoding='utf-8')
    target = output/'audit.json'
    env = {name: value for name, value in os.environ.items() if not name.upper().endswith(('_API_KEY', '_TOKEN'))}
    try:
        with (output/'audit.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([args.auditor_python, '-m', 'pip_audit', '--disable-pip', '--no-deps', '-r', str(exact),
                                     '--cache-dir', str(output/'http-cache'), '--format', 'json', '--output', str(target)], stdout=log, stderr=subprocess.STDOUT,
                                    env=env, timeout=180)
        audit = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        report = verdict(scope, audit, result.returncode)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        report = dict(passed=False, packages=len(scope['packages']), error='Audit did not complete. See audit.log.')
    (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
