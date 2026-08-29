# Agent OHMS: Agent Observability and Health Monitoring System

A monitoring system for autonomous AI agents. It ingests raw agent event streams, stores them durably, and applies fuzzy heuristics to detect behavioral anomalies: repetition loops, intent drift, persistent failures, and stuck progress. Results surface through a live session dashboard and a per-session timeline.

The system is deliberately small and explainable. Every detection is a readable heuristic rather than an opaque model, so a flagged session can always be traced back to the events and thresholds that produced the flag.

## Architecture

- Backend: FastAPI (Python), async ingestion and detection
- Database: SQLite via `aiosqlite`
- Real-time transport: WebSocket broadcasts for live dashboard and session updates
- Frontend: Next.js (App Router) with Tailwind CSS
- Simulator: Python CLI that replays scenario-based event streams against the ingestion API

### Design decisions

1. Idempotent ingestion via composite hashing. Each event gets a `hash_key` of `sha256(session_id + step + timestamp)` with a unique constraint in SQLite. Duplicate sends are ignored automatically, so retries, out-of-order delivery, and late arrivals are all safe. Deduping by step *and* timestamp (rather than step alone) preserves legitimate retries of the same step with corrected data.

2. Fuzzy loop detection. Comparing windows of activity with `difflib.SequenceMatcher` catches loops even when the agent varies its inputs slightly between attempts, which exact string matching would miss.

3. Ingestion decoupled from detection. `POST /events` persists the event and returns immediately; detection runs in a FastAPI `BackgroundTasks` worker. Ingestion throughput stays high and independent of detection cost.

4. Real-time first. After each ingest the backend broadcasts the updated session and the full session list over WebSocket. The frontend subscribes rather than polls, and merges per-session updates into the list by `session_id`.

5. Persistent store over in-memory. SQLite gives ACID guarantees and zero-config durability, which keeps the idempotency logic simple. A production deployment would move to a time-series or high-throughput store (for example ClickHouse or Redis).

## API

- `POST /events` — ingest a single event; duplicates are ignored by `hash_key`
- `GET /sessions` — list sessions with aggregated metrics
- `GET /sessions/{session_id}` — session detail, summary, detected issues, and full event timeline
- `WS /ws/sessions` — global session-list stream
- `WS /ws/sessions/{session_id}` — per-session update stream

Event payload shape is defined in `backend/models.py`.

## Detection heuristics

Detection runs on every ingest in priority order and stops at the first match.

- Loop: within a recent window of events, the mean fuzzy similarity between the two halves must exceed the threshold and the window must contain at least one failure.
- Failure: a streak of consecutive events all reporting `status: "failure"`.
- Stuck: a streak of consecutive successes with near-identical inputs and no state transition (same action, same file target), indicating repetition without progress.
- Drift: the recent activity has zero overlap with the baseline set of `(file_target, action)` pairs established from the session's earliest events.

Statuses a session can hold: `healthy`, `looping`, `failing`, `stuck`, `drifting`.

### Thresholds

All thresholds live in `backend/config.py` and can be tuned without touching detection logic:

- `LOOP_WINDOW_SIZE = 10` — recent window compared for loop similarity
- `LOOP_SIMILARITY_THRESHOLD = 0.85` — high likeness required between window halves to avoid coincidental-repeat false positives
- `DRIFT_BASELINE_EVENTS = 10` — baseline size before drift can be evaluated
- `MAX_CONSECUTIVE_FAILURES = 4` — failure streak length before flagging
- `MAX_CONSECUTIVE_STUCK = 6` — success streak length before evaluating stuck
- `STUCK_SIMILARITY_THRESHOLD = 0.9` — input similarity required to call a run stuck

## What the UI shows

- A live session list with event counts, current status, and last action.
- A session detail page with the full event timeline, plain-language anomaly notes, and graceful handling of missing metadata.
- Scenario hints describing what each simulator mode demonstrates.

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
pnpm install   # or npm install
pnpm dev       # or npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` if the API is not on `http://localhost:8000`.

### Simulator
```bash
source venv/bin/activate
python simulator/cli.py --scenario normal
python simulator/cli.py --scenario loop
python simulator/cli.py --scenario drift
python simulator/cli.py --scenario failure
```

Scenarios:

- `normal` — a clean progression from inspection to code change to verification.
- `loop` — similar command variants keep failing, tripping fuzzy loop detection.
- `drift` — a session that starts on auth work and gradually shifts into unrelated CSS work while a control session stays on task.
- `failure` — repeated retries fail in a tight streak, tripping the failure detector.

The simulator also injects a small amount of duplicate and late-arriving events so the ingestion path is exercised realistically.

## Example flow

1. Start the backend and frontend.
2. Run `python simulator/cli.py --scenario drift`.
3. Open `http://localhost:3000` and click the drifting session.
4. Read the timeline and the heuristic summary to see why it was flagged.

## Possible next steps

- Sequence numbers on WebSocket messages, with stale-update rejection in the frontend.
- Cluster-aware broadcast (Redis pub/sub or a broker).
- Recovery policy so sessions can return to `healthy`.
- Test coverage for out-of-order events, duplicates, and burst traffic.
