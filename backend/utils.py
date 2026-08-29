"""Shared helpers for shaping API responses and WebSocket payloads."""
from datetime import datetime, timezone

import aiosqlite

from . import repository


def to_iso_utc(sqlite_ts: str) -> str:
    """Convert a SQLite CURRENT_TIMESTAMP string to a UTC ISO-8601 string."""
    if sqlite_ts is None:
        return None
    dt = datetime.strptime(sqlite_ts, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')


def epoch_to_iso_utc(ts: float) -> str:
    """Convert an epoch timestamp to a UTC ISO-8601 string."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


async def fetch_sessions_list(db: aiosqlite.Connection) -> list:
    """Fetch the aggregated session list and normalize each row for output."""
    rows = await repository.sessions_with_metrics(db)
    result = []
    for r in rows:
        row = dict(r)
        row['created_at'] = to_iso_utc(row.get('created_at'))
        row['updated_at'] = to_iso_utc(row.get('updated_at'))
        row['last_seen'] = epoch_to_iso_utc(row.get('last_seen'))
        row['total_events'] = int(row.get('total_events') or 0)
        row['success_events'] = int(row.get('success_events') or 0)
        row['failure_events'] = int(row.get('failure_events') or 0)
        result.append(row)
    return result


def summarize_events(events_list: list) -> dict:
    """Build the summary block (counts, action distribution, span) for a session's events."""
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
        if ts:
            if first_seen is None or ts < first_seen:
                first_seen = ts
            if last_seen is None or ts > last_seen:
                last_seen = ts

    duration = None
    if first_seen and last_seen:
        dt_first = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
        dt_last = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
        duration = (dt_last - dt_first).total_seconds()

    return {
        'total_events': total_events,
        'success_events': success_events,
        'failure_events': failure_events,
        'action_distribution': action_distribution,
        'first_seen': first_seen,
        'last_seen': last_seen,
        'duration': duration,
    }
