from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class EventMetadata(BaseModel):
    file: Optional[str] = None
    status: Optional[str] = "success"

class EventPayload(BaseModel):
    session_id: str
    timestamp: float
    step: int
    action: str
    input: str
    output: str
    metadata: Optional[EventMetadata] = None

class SessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    updated_at: str
