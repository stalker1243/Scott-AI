"""
Общий слой защиты для опасных эндпоинтов backend — вынесен из secure_exec.py,
чтобы не дублировать логику токена/IP-whitelist/rate-limit/аудита в каждом
новом защищённом маршруте (powershell, shutdown/restart, kill-process,
удаление файлов и т.п.).

Используется как обычные FastAPI-зависимости:

    @app.post("/kill-process", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
    async def kill_process(...): ...
"""

import json
import os
import time
import secrets
import threading
from pathlib import Path
from typing import Dict, List
try:
    from .support_logs import backend_log_directory, private_directory
except ImportError:
    from support_logs import backend_log_directory, private_directory

from fastapi import HTTPException, Request

EXECUTE_TOKEN = os.getenv("EXECUTE_TOKEN", "")
EXECUTE_WHITELIST = [ip.strip() for ip in os.getenv("EXECUTE_WHITELIST", "127.0.0.1,::1").split(",") if ip.strip()]
try:
    RATE_LIMIT_PER_MIN = max(1, min(1000, int(os.getenv("EXECUTE_RATE_LIMIT", "20"))))
except ValueError:
    RATE_LIMIT_PER_MIN = 20

LOG_DIR = Path(os.getenv("EXECUTE_LOG_DIR") or backend_log_directory())
private_directory(LOG_DIR)

_rate_store: Dict[str, List[float]] = {}
_rate_lock = threading.Lock()

# Опциональный Redis для распределённого rate-limit (несколько процессов/машин).
REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None
if REDIS_URL:
    try:
        import redis
        _redis = redis.from_url(REDIS_URL)
    except Exception:
        _redis = None


def audit_log(entry: dict, log_name: str = "security.log") -> None:
    """Записать событие безопасности в JSONL-лог. Никогда не бросает исключение —
    сбой логирования не должен ронять сам запрос."""
    try:
        path = LOG_DIR / log_name
        record = {"ts": time.time(), **entry}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def check_rate_limit(request: Request) -> None:
    """FastAPI-зависимость: ограничение частоты запросов на IP (EXECUTE_RATE_LIMIT/мин)."""
    client_ip = request.client.host if request.client else "unknown"

    if _redis:
        try:
            bucket = int(time.time() // 60)
            key = f"rl:{client_ip}:{bucket}"
            val = _redis.incr(key)
            if val == 1:
                _redis.expire(key, 61)
            if val > RATE_LIMIT_PER_MIN:
                raise HTTPException(status_code=429, detail="Too many requests")
            return
        except HTTPException:
            raise
        except Exception:
            pass  # Redis недоступен — считаем в памяти процесса ниже

    now = time.monotonic()
    with _rate_lock:
        if len(_rate_store) >= 4096:
            for address in list(_rate_store):
                if not _rate_store[address] or now - _rate_store[address][-1] >= 60:
                    del _rate_store[address]
            if client_ip not in _rate_store and len(_rate_store) >= 4096:
                raise HTTPException(status_code=429, detail="Too many requests")
        hits = [t for t in _rate_store.get(client_ip, []) if now - t < 60]
        if len(hits) >= RATE_LIMIT_PER_MIN:
            _rate_store[client_ip] = hits
            raise HTTPException(status_code=429, detail="Too many requests")
        hits.append(now)
        _rate_store[client_ip] = hits


def require_scott_token(request: Request) -> None:
    """
    FastAPI-зависимость: требует Bearer-токен (EXECUTE_TOKEN) + IP из
    EXECUTE_WHITELIST для доступа к опасным эндпоинтам.

    Fail-closed: если EXECUTE_TOKEN не задан в .env — доступ ВСЕГДА 403.
    Это намеренно: защита не должна быть "опциональной", которую можно
    случайно оставить выключенной, забыв прописать токен.
    """
    client = request.client.host if request.client else None
    path = request.url.path

    if not client or (EXECUTE_WHITELIST and client not in EXECUTE_WHITELIST):
        audit_log({"ip": client, "path": path, "result": "ip_rejected"}, "dangerous_actions.log")
        raise HTTPException(status_code=403, detail="IP not allowed")

    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        audit_log({"ip": client, "path": path, "result": "missing_token"}, "dangerous_actions.log")
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth.split(" ", 1)[1]
    if not EXECUTE_TOKEN or not secrets.compare_digest(token.encode('utf-8'), EXECUTE_TOKEN.encode('utf-8')):
        audit_log({"ip": client, "path": path, "result": "invalid_token"}, "dangerous_actions.log")
        raise HTTPException(status_code=403, detail="Invalid or missing token")
