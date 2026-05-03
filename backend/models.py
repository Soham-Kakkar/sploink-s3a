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
    input: Optional[str] = None
    output: Optional[str] = None
    metadata: Optional[EventMetadata] = None

class SessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    updated_at: str
    drift_streak: int = 0
    total_events: int = 0
    success_events: int = 0
    failure_events: int = 0
    last_action: Optional[str] = None
    last_seen: Optional[float] = None
