"""Check installed backend imports and ASGI routes in disposable CI data."""
import argparse
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefix', required=True, type=Path)
args = parser.parse_args()
prefix = args.prefix.resolve()
temporary = Path(os.environ['RUNNER_TEMP']).resolve()
assert prefix.is_relative_to(temporary) and (prefix/'.scott-linux-install.json').is_file()
assert os.environ.get('WARMUP_MODELS') == '0'
backend = prefix/'backend'
os.chdir(backend)
sys.path.insert(0, str(backend))
import main
from fastapi.testclient import TestClient

# Leave lifespan inactive: no model preparation, devices or background listener.
with_context = TestClient(main.app)
try:
    response = with_context.get('/health')
    assert response.status_code == 200 and response.json()['status'] == 'online'
    assert with_context.get('/chats').status_code == 200
    response = with_context.post('/chats', json={'title':'Linux package check'})
    assert response.status_code == 200
    ident = response.json()['chat']['id']
    response = with_context.patch('/chats/'+ident, json={'title':'Linux renamed check'})
    assert response.status_code == 200
    assert with_context.delete('/chats/'+ident).status_code == 200
finally:
    with_context.close()
print('Installed backend: imports, health and synthetic chat CRUD passed (no lifespan, models or devices).')
