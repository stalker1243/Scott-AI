"""Background preparation of an installed optional voice model."""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
try:
    from .voice_prepare import preparation, PrepareConflict
except ImportError:
    from voice_prepare import preparation, PrepareConflict

router = APIRouter(prefix='/voice/prepare', tags=['Scott Voice'])

class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Cancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[0-9a-f]{32}$')

@router.get('')
def status():
    return preparation.snapshot()

@router.post('')
async def start(body: Start):
    try:
        return await asyncio.to_thread(preparation.start)
    except PrepareConflict as error:
        raise HTTPException(409,str(error)) from None
    except ValueError as error:
        raise HTTPException(400,str(error)) from None

@router.post('/cancel')
async def cancel(body: Cancel):
    try:
        return await asyncio.to_thread(preparation.cancel,body.id)
    except PrepareConflict as error:
        raise HTTPException(409,str(error)) from None
