import difflib

import aiosqlite

from . import config
from .database import DB_PATH


def calculate_similarity(s1: str, s2: str) -> float:
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def _normalize_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _build_signature(event) -> str:
    action = event["action"] or "unknown"
    file_target = event["file_target"] or ""
    input_text = _normalize_text(event["input"])
    output_text = _normalize_text(event["output"])
    return f"{action}|{file_target}|{input_text}|{output_text}"


async def _set_session_state(db: aiosqlite.Connection, session_id: str, *, status: str | None = None, drift_streak: int | None = None) -> None:
    assignments = ["updated_at = CURRENT_TIMESTAMP"]
    params: list[object] = []

    if status is not None:
        assignments.append("status = ?")
        params.append(status)

    if drift_streak is not None:
        assignments.append("drift_streak = ?")
        params.append(drift_streak)

    params.append(session_id)
    await db.execute(f"UPDATE sessions SET {', '.join(assignments)} WHERE session_id = ?", params)


async def detect_issues(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        async with db.execute(
            "SELECT status, drift_streak FROM sessions WHERE session_id = ?",
            (session_id,)
        ) as cursor:
            session = await cursor.fetchone()

        if not session:
            await db.execute(
                "INSERT INTO sessions (session_id, status, drift_streak) VALUES (?, 'healthy', 0)",
                (session_id,)
            )
            await db.commit()
            async with db.execute(
                "SELECT status, drift_streak FROM sessions WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                session = await cursor.fetchone()

        async with db.execute(
            "SELECT action, input, output, status, file_target FROM events WHERE session_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
            (session_id, config.LOOP_WINDOW_SIZE)
        ) as cursor:
            events = await cursor.fetchall()

        if len(events) == config.LOOP_WINDOW_SIZE:
            half = config.LOOP_WINDOW_SIZE // 2
            window_a = events[:half]
            window_b = events[half:]

            signature_a = " ".join(_build_signature(event) for event in window_a)
            signature_b = " ".join(_build_signature(event) for event in window_b)
            similarity = calculate_similarity(signature_a, signature_b)
            has_failure = any(event["status"] == "failure" for event in events)

            if similarity >= config.LOOP_SIMILARITY_THRESHOLD and has_failure:
                await _set_session_state(db, session_id, status="looping", drift_streak=0)
                await db.commit()
                return

        async with db.execute(
            "SELECT status FROM events WHERE session_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
            (session_id, config.MAX_CONSECUTIVE_FAILURES)
        ) as cursor:
            recent_statuses = await cursor.fetchall()

        if len(recent_statuses) == config.MAX_CONSECUTIVE_FAILURES and all(event["status"] == "failure" for event in recent_statuses):
            await _set_session_state(db, session_id, status="failing", drift_streak=0)
            await db.commit()
            return

        async with db.execute(
            "SELECT action, input, output, file_target FROM events WHERE session_id = ? ORDER BY timestamp ASC, id ASC LIMIT ?",
            (session_id, config.DRIFT_BASELINE_EVENTS)
        ) as cursor:
            baseline = await cursor.fetchall()

        async with db.execute(
            "SELECT action, input, output, file_target FROM events WHERE session_id = ? ORDER BY timestamp DESC, id DESC LIMIT 5",
            (session_id,)
        ) as cursor:
            recent = await cursor.fetchall()

        if len(baseline) >= config.DRIFT_BASELINE_EVENTS and len(recent) >= 3:
            baseline_set = set(_build_signature(event) for event in baseline)
            recent_set = set(_build_signature(event) for event in recent)

            if baseline_set and recent_set and not (baseline_set & recent_set):
                drift_streak = int(session["drift_streak"] or 0) + 1
            else:
                drift_streak = 0

            await _set_session_state(db, session_id, drift_streak=drift_streak)

            if drift_streak >= 3:
                await _set_session_state(db, session_id, status="drifting", drift_streak=drift_streak)
                await db.commit()
                return

        await db.commit()
