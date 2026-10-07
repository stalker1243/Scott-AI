"""Optional voice installation with fixed commands and paths."""
import asyncio
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
try:
    from .voice_install_jobs import jobs, JobConflict
except ImportError:
    from voice_install_jobs import jobs, JobConflict

router = APIRouter(prefix='/voice/install', tags=['Scott Voice'])

class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['install', 'check']

class Cancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[0-9a-f]{32}$')

@router.get('')
def status():
    return jobs.snapshot()

@router.post('')
async def start(body: Start):
    try:
        return await asyncio.to_thread(jobs.start, body.action)
    except JobConflict as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except OSError:
        raise HTTPException(503, 'Не удалось запустить подготовку Scott Voice.') from None

@router.post('/cancel')
def cancel(body: Cancel):
    try:
        return jobs.cancel(body.id)
    except JobConflict as error:
        raise HTTPException(409, str(error)) from None
