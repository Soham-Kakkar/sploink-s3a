import aiosqlite
import os

DB_PATH = "agent_obs.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Sessions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'healthy',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp REAL,
                step INTEGER,
                action TEXT,
                input TEXT,
                output TEXT,
                status TEXT,
                file_target TEXT,
                hash_key TEXT UNIQUE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        
        # Trigger to update updated_at in sessions
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS update_session_timestamp 
            AFTER INSERT ON events
            BEGIN
                UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = NEW.session_id;
            END
        """)
        
        await db.commit()

async def get_db():
    # Ensure DB and tables exist before returning a connection.
    # Calling init_db() is idempotent because it uses CREATE TABLE IF NOT EXISTS.
    await init_db()
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
