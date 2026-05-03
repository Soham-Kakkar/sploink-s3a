import difflib
import aiosqlite
from . import config

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
            
            print(f"DEBUG: Session {session_id} - Similarity: {similarity:.2f}, Has Failure: {has_failure}")
            
            if similarity >= 0.6 and has_failure: # Hardcoded 0.6 for now to test
                await db.execute("UPDATE sessions SET status = 'looping' WHERE session_id = ?", (session_id,))
                await db.commit()
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
