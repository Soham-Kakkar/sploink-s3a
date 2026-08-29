import hashlib

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends

from .. import repository
from ..database import get_db
from ..detection import detect_issues
from ..models import EventPayload
from ..utils import epoch_to_iso_utc, fetch_sessions_list, summarize_events, to_iso_utc
from ..ws_manager import broadcast

router = APIRouter()


@router.post("/events")
async def ingest_event(
    payload: EventPayload,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
):
    # 1. Generate composite hash for idempotency
    hash_str = f"{payload.session_id}_{payload.step}_{payload.timestamp}"
    hash_key = hashlib.sha256(hash_str.encode()).hexdigest()

    # 2. Extract metadata and normalize enum values
    file_target = getattr(payload.metadata, "file", None) if payload.metadata else None
    status = getattr(getattr(payload.metadata, "status", None), "value", getattr(payload.metadata, "status", "success")) if payload.metadata else "success"
    action_value = getattr(payload.action, "value", payload.action)

    # 3. Insert session if not exists
    await repository.ensure_session(db, payload.session_id)

    # 4. Insert event (idempotent)
    try:
        await repository.insert_event(db, {
            "session_id": payload.session_id,
            "timestamp": payload.timestamp,
            "step": payload.step,
            "action": action_value,
            "input": payload.input,
            "output": payload.output,
            "status": status,
            "file_target": file_target,
            "hash_key": hash_key,
        })
    except aiosqlite.IntegrityError:
        return {"status": "ignored", "reason": "duplicate"}

    # 5. Trigger detection
    background_tasks.add_task(detect_issues, db, payload.session_id)

    # 6. Broadcast session and events
    await _broadcast_session_update(db, payload.session_id)

    return {"status": "success"}


async def _broadcast_session_update(db: aiosqlite.Connection, session_id: str):
    """Broadcast the updated single session and the full session list. Best-effort."""
    try:
        sess = await repository.get_session(db, session_id)
        events = await repository.events_for_session(db, session_id)
        events_list = [dict(e) for e in events]
        for e in events_list:
            e['timestamp'] = epoch_to_iso_utc(e.get('timestamp'))

        summary = summarize_events(events_list)

        sess_dict = dict(sess) if sess else {'session_id': session_id, 'status': 'healthy'}
        sess_dict['created_at'] = to_iso_utc(sess_dict.get('created_at'))
        sess_dict['updated_at'] = to_iso_utc(sess_dict.get('updated_at'))
        drift_streak = 1 if sess_dict.get('status') == 'drifting' else 0

        payload_msg = {
            'session': {**sess_dict, 'drift_streak': drift_streak},
            'summary': summary,
            'detected_issues': [],
            'events': events_list,
        }
        await broadcast(session_id, payload_msg)

        try:
            sessions_list = await fetch_sessions_list(db)
            await broadcast('all', {'sessions': sessions_list})
        except Exception:
            pass
    except Exception:
        pass
