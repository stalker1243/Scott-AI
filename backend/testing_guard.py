"""Reject accidental access to working ScottAI data from the isolated test process."""
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit


def install(protected):
    protected = tuple(Path(path).resolve() for path in protected)

    def blocked(value):
        if isinstance(value, int) or value is None:
            return False
        try:
            path = os.fsdecode(value)
            if path.startswith('file:'):
                path = unquote(urlsplit(path).path)
                if len(path) > 3 and path[0] == '/' and path[2] == ':':
                    path = path[1:]
            resolved = Path(path).resolve()
            return any(resolved == root or resolved.is_relative_to(root) for root in protected)
        except (TypeError, ValueError, OSError):
            return False

    def audit(event, args):
        # All reads as well as writes are refused. Tests do not need real keys,
        # conversations, settings, recordings or attachments.
        if event in ('open', 'sqlite3.connect', 'os.remove', 'os.rmdir', 'os.mkdir', 'os.listdir', 'os.scandir'):
            paths = args[:1]
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            paths = args[:2]
        else:
            return
        if any(blocked(path) for path in paths):
            raise PermissionError('Tests cannot access working ScottAI data; use an isolated store')

    sys.addaudithook(audit)


def main():
    import json
    install(json.loads(sys.argv[1]))
    import pytest
    return pytest.main(sys.argv[2:])


if __name__ == '__main__':
    raise SystemExit(main())
