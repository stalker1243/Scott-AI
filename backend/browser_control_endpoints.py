"""Typed local browser actions; URLs, selectors and executable code are not accepted."""
import asyncio
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
try:
    from .browser_control_jobs import jobs, JobConflict
except ImportError:
    from browser_control_jobs import jobs, JobConflict

router = APIRouter(prefix='/browser', tags=['Управление браузером'])


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['install', 'home', 'search', 'play', 'select', 'pause', 'resume', 'close']
    query: str = Field(default='', max_length=500)
    index: Optional[int] = Field(default=None, ge=0, le=4)
    results_id: Optional[str] = Field(default=None, pattern=r'^[0-9a-f]{32}$')


class Cancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[0-9a-f]{32}$')


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


@router.get('')
def status():
    return jobs.snapshot()


@router.post('')
async def start(body: Start):
    try:
        return await asyncio.to_thread(jobs.start, **body.model_dump())
    except JobConflict as error:
        raise HTTPException(409, str(error)) from None
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error) if isinstance(error, ValueError) else 'Не удалось запустить браузер.') from None


@router.post('/cancel')
async def cancel(body: Cancel):
    try:
        return await asyncio.to_thread(jobs.cancel, body.id)
    except JobConflict as error:
        raise HTTPException(409, str(error)) from None


@router.post('/settings')
async def settings(body: Settings):
    return await asyncio.to_thread(jobs.set_enabled, body.enabled)
