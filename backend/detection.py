import difflib
import aiosqlite
from . import config
from .ws_manager import broadcast


async def _broadcast_sessions_list(db: aiosqlite.Connection):
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

def calculate_similarity(s1: str, s2: str) -> float:
    return difflib.SequenceMatcher(None, s1, s2).ratio()

async def detect_issues(db: aiosqlite.Connection, session_id: str):
    # 1. Loop Detection (Fuzzy) - Priority 1
    async with db.execute(
        "SELECT action, input, status FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, config.LOOP_WINDOW_SIZE)
    ) as cursor:
        events = await cursor.fetchall()
        if len(events) == config.LOOP_WINDOW_SIZE:
            half = config.LOOP_WINDOW_SIZE // 2
            window_a = events[:half]
            window_b = events[half:]
            
            str_a = " ".join([f"{e['action']}:{e['input']}" for e in window_a])
            str_b = " ".join([f"{e['action']}:{e['input']}" for e in window_b])
            
            similarity = calculate_similarity(str_a, str_b)
            has_failure = any(e['status'] == 'failure' for e in events)
            # Debug info (uses configured threshold)
            # If similarity meets configured threshold and there is at least one failure, mark looping
            try:
                threshold = config.LOOP_SIMILARITY_THRESHOLD
            except Exception:
                threshold = 0.6

            if similarity >= threshold and has_failure:
                await db.execute("UPDATE sessions SET status = 'looping' WHERE session_id = ?", (session_id,))
                await db.commit()
                try:
                    await broadcast(session_id, {'session': {'session_id': session_id, 'status': 'looping'}})
                except Exception:
                    pass
                await _broadcast_sessions_list(db)
                return

    # 2. Failure Detection - Priority 2
    async with db.execute(
        "SELECT status FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, config.MAX_CONSECUTIVE_FAILURES)
    ) as cursor:
        failures = await cursor.fetchall()
        if len(failures) == config.MAX_CONSECUTIVE_FAILURES and all(f['status'] == 'failure' for f in failures):
            await db.execute("UPDATE sessions SET status = 'failing' WHERE session_id = ?", (session_id,))
            await db.commit()
            try:
                await broadcast(session_id, {'session': {'session_id': session_id, 'status': 'failing'}})
            except Exception:
                pass
            await _broadcast_sessions_list(db)
            return

    # 3. Drift Detection
    async with db.execute(
        "SELECT DISTINCT file_target, action FROM events WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
        (session_id, config.DRIFT_BASELINE_EVENTS)
    ) as cursor:
        baseline = await cursor.fetchall()
        
    async with db.execute(
        "SELECT DISTINCT file_target, action FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT 5",
        (session_id,)
    ) as cursor:
        recent = await cursor.fetchall()

    if len(baseline) >= config.DRIFT_BASELINE_EVENTS and len(recent) >= 3:
        baseline_set = set((b['file_target'], b['action']) for b in baseline if b['file_target'])
        recent_set = set((r['file_target'], r['action']) for r in recent if r['file_target'])
        
        if baseline_set and recent_set and not (baseline_set & recent_set):
            # Check if this persists for a few steps (simplified here)
            await db.execute("UPDATE sessions SET status = 'drifting' WHERE session_id = ?", (session_id,))
            await db.commit()
            try:
                await broadcast(session_id, {'session': {'session_id': session_id, 'status': 'drifting'}})
            except Exception:
                pass
            await _broadcast_sessions_list(db)
            return

    # If no issues detected and not already marked, keep/set healthy
    # But only if it's not already something else (to avoid flickering)
    async with db.execute("SELECT status FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
        row = await cursor.fetchone()
        if row and row['status'] == 'healthy':
            pass # Stay healthy
        elif not row:
            await db.execute("INSERT INTO sessions (session_id, status) VALUES (?, 'healthy')", (session_id,))
            await db.commit()
