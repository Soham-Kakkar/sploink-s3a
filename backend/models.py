from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ActionEnum(str, Enum):
    read_file = 'read_file'
    write_file = 'write_file'
    run_command = 'run_command'
    llm_call = 'llm_call'


class StatusEnum(str, Enum):
    success = 'success'
    failure = 'failure'


class EventMetadata(BaseModel):
    file: Optional[str] = None
    status: Optional[StatusEnum] = StatusEnum.success


class EventPayload(BaseModel):
    session_id: str
    timestamp: float
    step: int
    action: ActionEnum
    input: str
    output: str
    metadata: Optional[EventMetadata] = None


class SessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    updated_at: str
