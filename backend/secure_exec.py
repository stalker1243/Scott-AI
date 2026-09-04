from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
import subprocess
from typing import List
import time

from security import require_scott_token, check_rate_limit, audit_log

router = APIRouter()


class ExecRequest(BaseModel):
    cmd: List[str]


# Белый список допустимых команд (первый элемент)
ALLOWED_CMDS = {
    "whoami",
    "ipconfig",
    "ping",
    "tasklist",
    "systeminfo",
    "dir",
    "echo",
}


@router.post("/execute", dependencies=[Depends(require_scott_token), Depends(check_rate_limit)])
async def execute(req: ExecRequest, request: Request):
    """Execute a whitelisted OS command. Uses Authorization: Bearer <token>."""
    client_ip = request.client.host if request.client else "unknown"

    if not req.cmd or not isinstance(req.cmd, list):
        raise HTTPException(status_code=400, detail="Invalid cmd format")

    cmd0 = req.cmd[0]
    if cmd0.lower() not in ALLOWED_CMDS:
        raise HTTPException(status_code=403, detail=f"Command '{cmd0}' not allowed")

    # audit entry base
    entry = {
        "ip": client_ip,
        "cmd": req.cmd,
        "user_agent": request.headers.get("User-Agent"),
    }

    start = time.time()
    try:
        proc = subprocess.run(req.cmd, capture_output=True, text=True, timeout=30)
        duration = time.time() - start
        result = {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[:1000],
            "stderr": proc.stderr[:1000],
            "duration": duration,
        }
        entry.update({"result": result})
        audit_log(entry, "secure_exec.log")
        return result
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        entry.update({"result": {"success": False, "error": "timeout", "duration": duration}})
        audit_log(entry, "secure_exec.log")
        raise HTTPException(status_code=504, detail="Command timed out")
    except Exception as e:
        duration = time.time() - start
        entry.update({"result": {"success": False, "error": str(e), "duration": duration}})
        audit_log(entry, "secure_exec.log")
        raise HTTPException(status_code=500, detail=str(e))
