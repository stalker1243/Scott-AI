"""Actionable provisioning failures; no optional voice libraries are imported."""
import errno
import json
import subprocess


MESSAGES = {
    'network_unavailable': 'Сервис загрузки Scott Voice не отвечает. Возможен сбой сервиса, DNS или прокси. Скачанные части сохранены; повторите установку позже.',
    'download_timeout': 'Сервис загрузки слишком долго не передаёт данные. Скачанные части сохранены; повторите установку.',
    'download_server': 'Сервис загрузки временно перегружен или ограничил запросы. Повторите установку позже; скачанные части сохранены.',
    'download_access': 'Сервис отклонил загрузку файлов Scott Voice. Проверьте доступ к Hugging Face и PyTorch, настройки прокси и соберите логи.',
    'download_certificate': 'Не удалось проверить сертификат сервиса загрузки. Проверьте дату компьютера и сертификаты прокси или антивируса; соберите логи.',
    'disk_full': 'Недостаточно места для Scott Voice. Освободите место на диске установки и в папке временных файлов, затем продолжите.',
    'permission_denied': 'Нет доступа к файлам установки Scott Voice. Проверьте права на папку и журнал защитного ПО.',
}


class InstallationError(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def failure_code(error):
    """Classify concrete evidence, rather than calling every failure an internet issue."""
    if isinstance(error, OSError):
        if error.errno == errno.ENOSPC or getattr(error, 'winerror', None) == 112:
            return 'disk_full'
        if error.errno in (errno.EACCES, errno.EPERM):
            return 'permission_denied'
    status = getattr(getattr(error, 'response', None), 'status_code', None)
    if status in (401, 403, 404):
        return 'download_access'
    if status == 429 or isinstance(status, int) and 500 <= status < 600:
        return 'download_server'
    detail = (type(error).__name__ + ' ' + str(error) + ' ' + str(getattr(error, 'stderr', '') or '')).lower()
    if any(s in detail for s in ('sslerror', 'certificate_verify_failed', 'certificate verify failed')):
        return 'download_certificate'
    if any(s in detail for s in ('no space left on device', 'not enough space on the disk', 'disk full')):
        return 'disk_full'
    if any(s in detail for s in ('readtimeout', 'connecttimeout', 'timed out', 'timeouterror')):
        return 'download_timeout'
    if any(s in detail for s in ('connectionerror', 'connecterror', 'readerror', 'remoteprotocolerror', 'chunkedencodingerror', 'incompleteread', 'connectionreseterror', 'connection aborted', 'connection refused', 'nameresolutionerror', 'temporary failure in name resolution', 'getaddrinfo failed', 'proxyerror')):
        return 'network_unavailable'
    return ''


def child_failure(error):
    """Keep a download child's structured failure when wrapping its nonzero exit."""
    if isinstance(error, subprocess.TimeoutExpired):
        return error  # A whole process deadline does not prove a network failure.
    if isinstance(error, subprocess.CalledProcessError):
        for line in reversed(str(error.output or '').splitlines()):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get('type') == 'error' and event.get('code') in MESSAGES:
                return InstallationError(MESSAGES[event['code']], event['code'])
    code = failure_code(error)
    return InstallationError(MESSAGES[code], code) if code else error
