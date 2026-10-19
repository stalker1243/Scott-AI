import errno
import json
import subprocess
from types import SimpleNamespace

import pytest
from voice_install_errors import child_failure, failure_code, InstallationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('error, code', [
    (OSError(errno.ENOSPC, 'full'), 'disk_full'),
    (PermissionError(errno.EACCES, 'denied'), 'permission_denied'),
    (TimeoutError('timed out'), 'download_timeout'),
    (ConnectionResetError('connection aborted'), 'network_unavailable'),
    (RuntimeError('ChunkedEncodingError: IncompleteRead(12 bytes read, 4 more expected)'), 'network_unavailable'),
    (RuntimeError('CERTIFICATE_VERIFY_FAILED'), 'download_certificate'),
    (ValueError('bad checksum'), ''),
    (subprocess.CalledProcessError(1, ['pip'], stderr='ReadTimeoutError: timed out'), 'download_timeout'),
    (RuntimeError('unsupported CUDA device'), ''),
])
def test_specific_failures_are_distinguished(error, code):
    assert failure_code(error) == code


@pytest.mark.parametrize('status, code', [(403, 'download_access'), (429, 'download_server'), (503, 'download_server')])
def test_http_status_is_classified(status, code):
    error = RuntimeError('HTTP request failed')
    error.response = SimpleNamespace(status_code=status)
    assert failure_code(error) == code


def test_model_child_preserves_reason_through_process_exit():
    output = json.dumps(dict(type='error', code='download_access', message='untrusted text'))
    error = child_failure(subprocess.CalledProcessError(1, ['worker'], output=output))
    assert isinstance(error, InstallationError) and error.code == 'download_access'
    assert 'untrusted text' not in str(error)


def test_process_deadline_is_not_misreported_as_network_timeout():
    error = subprocess.TimeoutExpired(['python', 'runtime-check'], 60)
    assert child_failure(error) is error
