from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite
import hashlib
from typing import List

from .database import init_db, get_db
from .models import EventPayload, SessionResponse
from .detection import detect_issues

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
    status = payload.metadata.status if payload.metadata and payload.metadata.status else "success"
    file_target = payload.metadata.file if payload.metadata else None
    input_text = payload.input or ""
    output_text = payload.output or ""
    
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
            input_text, output_text, status, file_target, hash_key
        ))
        await db.commit()
    except aiosqlite.IntegrityError:
        # Duplicate event, ignore
        return {"status": "ignored", "reason": "duplicate"}

    # 5. Trigger Detection (Async)
    background_tasks.add_task(detect_issues, payload.session_id)
    
    return {"status": "success"}

@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        """
        SELECT
            s.session_id,
            s.status,
            s.created_at,
            s.updated_at,
            s.drift_streak,
            COUNT(e.id) AS total_events,
            COALESCE(SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END), 0) AS success_events,
            COALESCE(SUM(CASE WHEN e.status = 'failure' THEN 1 ELSE 0 END), 0) AS failure_events,
            (
                SELECT e2.action
                FROM events e2
                WHERE e2.session_id = s.session_id
                ORDER BY e2.timestamp DESC, e2.id DESC
                LIMIT 1
            ) AS last_action,
            MAX(e.timestamp) AS last_seen
        FROM sessions s
        LEFT JOIN events e ON e.session_id = s.session_id
        GROUP BY s.session_id
        ORDER BY s.updated_at DESC
        """
    ) as cursor:
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

    total_events = len(events)
    success_events = sum(1 for event in events if event["status"] == "success")
    failure_events = sum(1 for event in events if event["status"] == "failure")
    action_distribution = {}
    for event in events:
        action = event["action"] or "unknown"
        action_distribution[action] = action_distribution.get(action, 0) + 1

    first_seen = events[0]["timestamp"] if events else None
    last_seen = events[-1]["timestamp"] if events else None
    duration = None if first_seen is None or last_seen is None else max(0.0, last_seen - first_seen)

    detected_issues = []
    if session["status"] == "looping":
        detected_issues.append("Repeated command patterns with recent failures suggest the agent is looping.")
    elif session["status"] == "drifting":
        detected_issues.append("The current work has stopped overlapping with the session baseline, which looks like intent drift.")
    elif session["status"] == "failing":
        detected_issues.append("The latest events are failing back-to-back, which points to a stuck retry path.")
    else:
        detected_issues.append("No anomaly has crossed the heuristic thresholds yet.")

    return {
        "session": dict(session),
        "summary": {
            "total_events": total_events,
            "success_events": success_events,
            "failure_events": failure_events,
            "action_distribution": action_distribution,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "duration": duration,
        },
        "detected_issues": detected_issues,
        "events": [dict(e) for e in events]
    }
