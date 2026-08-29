"""Data-access layer. All SQL for the agent observability API lives here.

Functions return raw aiosqlite.Row / dict data. Timestamp formatting and
response shaping are the caller's concern (see utils.py).
"""
import aiosqlite


# --- Session-list aggregate --------------------------------------------------

SESSIONS_LIST_QUERY = """
SELECT
  s.session_id,
  s.status,
  s.created_at,
  s.updated_at,
  COUNT(e.id) AS total_events,
  SUM(CASE WHEN e.status = 'success' THEN 1 ELSE 0 END) AS success_events,
  SUM(CASE WHEN e.status = 'failure' THEN 1 ELSE 0 END) AS failure_events,
  (SELECT action FROM events WHERE session_id = s.session_id ORDER BY step DESC, timestamp DESC LIMIT 1) AS last_action,
  (SELECT timestamp FROM events WHERE session_id = s.session_id ORDER BY step DESC, timestamp DESC LIMIT 1) AS last_seen
FROM sessions s
LEFT JOIN events e ON s.session_id = e.session_id
GROUP BY s.session_id
ORDER BY s.updated_at DESC
"""


async def sessions_with_metrics(db: aiosqlite.Connection) -> list:
    """Return every session joined with aggregated event metrics (raw rows)."""
    async with db.execute(SESSIONS_LIST_QUERY) as cursor:
        return await cursor.fetchall()


# --- Session reads/writes ----------------------------------------------------

async def get_session(db: aiosqlite.Connection, session_id: str):
    async with db.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ) as cursor:
        return await cursor.fetchone()


async def get_session_status(db: aiosqlite.Connection, session_id: str):
    async with db.execute(
        "SELECT status FROM sessions WHERE session_id = ?", (session_id,)
    ) as cursor:
        return await cursor.fetchone()


async def ensure_session(db: aiosqlite.Connection, session_id: str):
    """Insert a healthy session if it does not already exist. Does not commit."""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (session_id, status) VALUES (?, 'healthy')",
        (session_id,),
    )


async def create_session(db: aiosqlite.Connection, session_id: str):
    """Insert a healthy session and commit."""
    await db.execute(
        "INSERT INTO sessions (session_id, status) VALUES (?, 'healthy')",
        (session_id,),
    )
    await db.commit()


async def set_session_status(db: aiosqlite.Connection, session_id: str, status: str):
    """Update a session's status and commit."""
    await db.execute(
        "UPDATE sessions SET status = ? WHERE session_id = ?", (status, session_id)
    )
    await db.commit()


# --- Event reads/writes ------------------------------------------------------

async def insert_event(db: aiosqlite.Connection, event: dict):
    """Insert an event and commit. Raises aiosqlite.IntegrityError on duplicate hash_key."""
    await db.execute(
        """
        INSERT INTO events (session_id, timestamp, step, action, input, output, status, file_target, hash_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["session_id"], event["timestamp"], event["step"], event["action"],
            event["input"], event["output"], event["status"], event["file_target"],
            event["hash_key"],
        ),
    )
    await db.commit()


async def events_for_session(db: aiosqlite.Connection, session_id: str) -> list:
    """All events for a session, oldest first by timestamp."""
    async with db.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC", (session_id,)
    ) as cursor:
        return await cursor.fetchall()


# --- Detection windows -------------------------------------------------------

async def recent_events(db: aiosqlite.Connection, session_id: str, limit: int, columns: str = "*") -> list:
    """Most-recent `limit` events (by step then timestamp, newest first)."""
    async with db.execute(
        f"SELECT {columns} FROM events WHERE session_id = ? ORDER BY step DESC, timestamp DESC LIMIT ?",
        (session_id, limit),
    ) as cursor:
        return await cursor.fetchall()


async def baseline_targets(db: aiosqlite.Connection, session_id: str, limit: int) -> list:
    """Distinct (file_target, action) pairs from the session's earliest events."""
    async with db.execute(
        "SELECT DISTINCT file_target, action FROM events WHERE session_id = ? ORDER BY step ASC, timestamp ASC LIMIT ?",
        (session_id, limit),
    ) as cursor:
        return await cursor.fetchall()


async def recent_targets(db: aiosqlite.Connection, session_id: str, limit: int) -> list:
    """Distinct (file_target, action) pairs from the session's most recent events."""
    async with db.execute(
        "SELECT DISTINCT file_target, action FROM events WHERE session_id = ? ORDER BY step DESC, timestamp DESC LIMIT ?",
        (session_id, limit),
    ) as cursor:
        return await cursor.fetchall()
