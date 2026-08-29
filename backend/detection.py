import difflib
import aiosqlite
from . import config
from . import repository
from .utils import fetch_sessions_list
from .ws_manager import broadcast


async def _broadcast_sessions_list(db: aiosqlite.Connection):
    try:
        sessions_list = await fetch_sessions_list(db)
        await broadcast('all', {'sessions': sessions_list})
    except Exception:
        pass


def calculate_similarity(a, b) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def calculate_event_similarity(a, b) -> float:
    if a["action"] != b["action"]:
        return 0.0

    return calculate_similarity(
        (a["input"] or "").strip(),
        (b["input"] or "").strip()
    )


async def _flag(db: aiosqlite.Connection, session_id: str, status: str):
    """Set a session's status and broadcast the change (single + full list)."""
    await repository.set_session_status(db, session_id, status)
    try:
        await broadcast(session_id, {'session': {'session_id': session_id, 'status': status}})
    except Exception:
        pass
    await _broadcast_sessions_list(db)


async def detect_issues(db: aiosqlite.Connection, session_id: str):
    # 1. Loop Detection (Fuzzy) - Priority 1
    events = await repository.recent_events(
        db, session_id, config.LOOP_WINDOW_SIZE,
        columns="action, input, status, step",
    )
    if len(events) == config.LOOP_WINDOW_SIZE:
        half = config.LOOP_WINDOW_SIZE // 2
        window_a = events[:half]
        window_b = events[half:]

        similarities = [
            calculate_event_similarity(a, b)
            for a, b in zip(window_a, window_b)
        ]

        similarity = sum(similarities) / len(similarities)
        has_failure = any(e['status'] == 'failure' for e in events)
        # If similarity meets configured threshold and there is at least one failure, mark looping
        try:
            threshold = config.LOOP_SIMILARITY_THRESHOLD
        except Exception:
            threshold = 0.6
        if similarity >= threshold and has_failure:
            await _flag(db, session_id, 'looping')
            return

    # 2. Failure Detection - Priority 2
    failures = await repository.recent_events(
        db, session_id, config.MAX_CONSECUTIVE_FAILURES, columns="status",
    )
    if len(failures) == config.MAX_CONSECUTIVE_FAILURES and all(f['status'] == 'failure' for f in failures):
        await _flag(db, session_id, 'failing')
        return

    # 3. Stuck Detection
    stuck_events = await repository.recent_events(
        db, session_id, config.MAX_CONSECUTIVE_STUCK,
        columns="input, status, action, file_target",
    )
    if len(stuck_events) >= config.MAX_CONSECUTIVE_STUCK and all(s['status'] == 'success' for s in stuck_events):
        # Check for low diversity of inputs and no successful state transitions
        similarity = sum(
            calculate_similarity(stuck_events[0]['input'], e['input']) for e in stuck_events
        ) / len(stuck_events)

        # Check if state transitions exist (different actions or file_targets)
        actions = set(e['action'] for e in stuck_events if e['action'])
        file_targets = set(e['file_target'] for e in stuck_events if e['file_target'])
        no_state_transitions = len(actions) <= 1 and len(file_targets) <= 1

        if similarity >= config.STUCK_SIMILARITY_THRESHOLD and no_state_transitions:
            await _flag(db, session_id, 'stuck')
            return

    # 4. Drift Detection
    baseline = await repository.baseline_targets(db, session_id, config.DRIFT_BASELINE_EVENTS)
    recent = await repository.recent_targets(db, session_id, 5)

    if len(baseline) >= config.DRIFT_BASELINE_EVENTS and len(recent) >= 3:
        baseline_set = set((b['file_target'], b['action']) for b in baseline if b['file_target'])
        recent_set = set((r['file_target'], r['action']) for r in recent if r['file_target'])

        if baseline_set and recent_set and not (baseline_set & recent_set):
            await _flag(db, session_id, 'drifting')
            return

    # If no issues detected and not already marked, keep/set healthy
    # But only if it's not already something else (to avoid flickering)
    row = await repository.get_session_status(db, session_id)
    if not row:
        await repository.create_session(db, session_id)
