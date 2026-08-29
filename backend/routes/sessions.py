import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from .. import repository
from ..database import get_db
from ..utils import epoch_to_iso_utc, fetch_sessions_list, summarize_events, to_iso_utc

router = APIRouter()


@router.get("/sessions")
async def list_sessions(db: aiosqlite.Connection = Depends(get_db)):
    return await fetch_sessions_list(db)


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, db: aiosqlite.Connection = Depends(get_db)):
    session = await repository.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = await repository.events_for_session(db, session_id)
    events_list = [dict(e) for e in events]
    for e in events_list:
        e['timestamp'] = epoch_to_iso_utc(e.get('timestamp'))

    summary = summarize_events(events_list)

    sess = dict(session)
    sess['created_at'] = to_iso_utc(sess.get('created_at'))
    sess['updated_at'] = to_iso_utc(sess.get('updated_at'))
    drift_streak = 1 if sess.get('status') == 'drifting' else 0

    detected = _detected_issues(sess.get('status'), summary['failure_events'], summary['total_events'])

    return {
        'session': {**sess, 'drift_streak': drift_streak},
        'summary': summary,
        'detected_issues': detected,
        'events': events_list,
    }


def _detected_issues(status: str, failure_events: int, total_events: int) -> list:
    """Build plain-language notes describing why a session is flagged."""
    detected = []
    if status == 'looping':
        detected.append('Looping detected — the agent is repeating recent actions.')
    if status == 'failing':
        detected.append('Failing — recent events show consecutive failures.')
    if status == 'drifting':
        detected.append('Drift detected — recent actions deviate from the baseline.')
    if status == 'stuck':
        detected.append('Stuck — the agent is repeating the same action without progress.')

    if failure_events > 0 and total_events > 0:
        if failure_events / total_events > 0.5:
            detected.append(f'Failure rate is high ({failure_events}/{total_events}).')
    return detected
