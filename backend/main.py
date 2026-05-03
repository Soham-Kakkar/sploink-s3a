from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite
import hashlib
from typing import List

from .database import init_db, get_db
from .models import EventPayload
from .detection import detect_issues
from .ws_manager import broadcast, connect, disconnect
from fastapi import WebSocket, WebSocketDisconnect
import json

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

    # 5. Trigger Detection (Async)
    background_tasks.add_task(detect_issues, db, payload.session_id)

    # Broadcast updated session detail to any connected WebSocket clients
    try:
        async with db.execute("SELECT * FROM sessions WHERE session_id = ?", (payload.session_id,)) as cursor:
            sess = await cursor.fetchone()
        async with db.execute("SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC", (payload.session_id,)) as cursor:
            events = await cursor.fetchall()
        events_list = [dict(e) for e in events]
        total_events = len(events_list)
        success_events = sum(1 for e in events_list if (e.get('status') or 'success') == 'success')
        failure_events = sum(1 for e in events_list if (e.get('status') or 'success') == 'failure')
        action_distribution = {}
        first_seen = None
        last_seen = None
        for e in events_list:
            action = e.get('action') or 'unknown'
            action_distribution[action] = action_distribution.get(action, 0) + 1
            ts = e.get('timestamp')
            if ts is not None:
                if first_seen is None or ts < first_seen:
                    first_seen = ts
                if last_seen is None or ts > last_seen:
                    last_seen = ts

        duration = None
        if first_seen is not None and last_seen is not None:
            try:
                duration = float(last_seen) - float(first_seen)
            except Exception:
                duration = None

        sess_dict = dict(sess) if sess else {'session_id': payload.session_id, 'status': 'healthy'}
        drift_streak = 1 if sess_dict.get('status') == 'drifting' else 0

        payload_msg = {
            'session': {**sess_dict, 'drift_streak': drift_streak},
            'summary': {
                'total_events': total_events,
                'success_events': success_events,
                'failure_events': failure_events,
                'action_distribution': action_distribution,
                'first_seen': first_seen,
                'last_seen': last_seen,
                'duration': duration,
            },
            'detected_issues': [],
            'events': events_list,
        }

        await broadcast(payload.session_id, payload_msg)
        # also broadcast an updated sessions list to global listeners
        try:
            query = """
            SELECT
              s.session_id,
              s.status,
              s.created_at,
              s.updated_at,
              COUNT(e.id) AS total_events,
              SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) AS success_events,
              SUM(CASE WHEN e.status = 'failure' THEN 1 ELSE 0 END) AS failure_events,
              (SELECT action FROM events WHERE session_id = s.session_id ORDER BY timestamp DESC LIMIT 1) AS last_action,
              (SELECT timestamp FROM events WHERE session_id = s.session_id ORDER BY timestamp DESC LIMIT 1) AS last_seen
            FROM sessions s
            LEFT JOIN events e ON s.session_id = e.session_id
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            """
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                sessions_list = []
                for r in rows:
                    row = dict(r)
                    row['total_events'] = int(row.get('total_events') or 0)
                    row['success_events'] = int(row.get('success_events') or 0)
                    row['failure_events'] = int(row.get('failure_events') or 0)
                    sessions_list.append(row)
            await broadcast('all', {'sessions': sessions_list})
        except Exception:
            pass
    except Exception:
        pass

    return {"status": "success"}

@app.get("/sessions")
async def list_sessions(db: aiosqlite.Connection = Depends(get_db)):
    # Aggregate per-session metrics so the frontend can display counts and last seen/action
    query = """
    SELECT
      s.session_id,
      s.status,
      s.created_at,
      s.updated_at,
      COUNT(e.id) AS total_events,
      SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) AS success_events,
      SUM(CASE WHEN e.status = 'failure' THEN 1 ELSE 0 END) AS failure_events,
      (SELECT action FROM events WHERE session_id = s.session_id ORDER BY timestamp DESC LIMIT 1) AS last_action,
      (SELECT timestamp FROM events WHERE session_id = s.session_id ORDER BY timestamp DESC LIMIT 1) AS last_seen
    FROM sessions s
    LEFT JOIN events e ON s.session_id = e.session_id
    GROUP BY s.session_id
    ORDER BY s.updated_at DESC
    """
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            row = dict(r)
            # sqlite returns None for aggregates when no rows exist; normalize to integers
            row['total_events'] = int(row.get('total_events') or 0)
            row['success_events'] = int(row.get('success_events') or 0)
            row['failure_events'] = int(row.get('failure_events') or 0)
            result.append(row)
        return result

@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        session = await cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    
    async with db.execute("SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)) as cursor:
        events = await cursor.fetchall()
    # Build summary statistics expected by the frontend
    events_list = [dict(e) for e in events]
    total_events = len(events_list)
    success_events = sum(1 for e in events_list if (e.get('status') or 'success') == 'success')
    failure_events = sum(1 for e in events_list if (e.get('status') or 'success') == 'failure')
    action_distribution = {}
    first_seen = None
    last_seen = None
    for e in events_list:
        action = e.get('action') or 'unknown'
        action_distribution[action] = action_distribution.get(action, 0) + 1
        ts = e.get('timestamp')
        if ts is not None:
            if first_seen is None or ts < first_seen:
                first_seen = ts
            if last_seen is None or ts > last_seen:
                last_seen = ts

    duration = None
    if first_seen is not None and last_seen is not None:
        try:
            duration = float(last_seen) - float(first_seen)
        except Exception:
            duration = None

    # Detected issues: surface simple human-friendly messages
    detected = []
    sess = dict(session)
    status = sess.get('status')
    if status == 'looping':
        detected.append('Looping detected — the agent is repeating recent actions.')
    if status == 'failing':
        detected.append('Failing — recent events show consecutive failures.')
    if status == 'drifting':
        detected.append('Drift detected — recent actions deviate from the baseline.')

    # Additional heuristic: note long sessions or many failures
    if failure_events > 0 and total_events > 0:
        fail_ratio = failure_events / total_events
        if fail_ratio > 0.5:
            detected.append(f'Failure rate is high ({failure_events}/{total_events}).')

    # drift_streak is not tracked separately; provide a basic value for frontend
    drift_streak = 1 if status == 'drifting' else 0

    summary = {
        'total_events': total_events,
        'success_events': success_events,
        'failure_events': failure_events,
        'action_distribution': action_distribution,
        'first_seen': first_seen,
        'last_seen': last_seen,
        'duration': duration,
    }

    return {
        'session': {**sess, 'drift_streak': drift_streak},
        'summary': summary,
        'detected_issues': detected,
        'events': events_list,
    }


@app.websocket('/ws/sessions/{session_id}')
async def session_ws(websocket: WebSocket, session_id: str):
    await connect(session_id, websocket)
    try:
        while True:
            # keep the connection open; clients may send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect(session_id, websocket)


@app.websocket('/ws/sessions')
async def sessions_ws(websocket: WebSocket):
    await connect('all', websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect('all', websocket)
