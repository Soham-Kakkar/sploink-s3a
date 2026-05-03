from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite
import hashlib
from typing import List

from .database import init_db, get_db
from .models import EventPayload, SessionResponse

app = FastAPI(title="Agent Observability API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_db()

@app.post("/events")
async def ingest_event(payload: EventPayload, background_tasks: BackgroundTasks, db: aiosqlite.Connection = Depends(get_db)):
    # 1. Generate Composite Hash for Idempotency
    hash_str = f"{payload.session_id}_{payload.step}_{payload.timestamp}"
    hash_key = hashlib.sha256(hash_str.encode()).hexdigest()
    
    # 2. Extract metadata
    status = payload.metadata.status if payload.metadata else "success"
    file_target = payload.metadata.file if payload.metadata else None
    
    # 3. Insert Session if not exists (to ensure foreign key works and session shows up)
    await db.execute(
        "INSERT OR IGNORE INTO sessions (session_id, status) VALUES (?, 'healthy')",
        (payload.session_id,)
    )
    
    # 4. Insert Event (Idempotent)
    try:
        await db.execute("""
            INSERT INTO events (session_id, timestamp, step, action, input, output, status, file_target, hash_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.session_id, payload.timestamp, payload.step, payload.action,
            payload.input, payload.output, status, file_target, hash_key
        ))
        await db.commit()
    except aiosqlite.IntegrityError:
        # Duplicate event, ignore
        return {"status": "ignored", "reason": "duplicate"}

    return {"status": "success"}

@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM sessions ORDER BY updated_at DESC") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        session = await cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    
    async with db.execute("SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)) as cursor:
        events = await cursor.fetchall()
        
    return {
        "session": dict(session),
        "events": [dict(e) for e in events]
    }
