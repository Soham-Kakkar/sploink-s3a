# Sploink S3a — Agent Observability

This repository implements a small agent observability system inspired by the S3 assessment task in `task.txt`.

Quick overview
- Backend: FastAPI + SQLite (aiosqlite) exposing an event ingestion API (`POST /events`), session list/detail endpoints, and WebSocket endpoints for real-time updates.
- Processing: Lightweight detection heuristics (loop, drift, failure) in `backend/detection.py` using fuzzy matching and simple ratios.
- Frontend: Next.js app (React) in `frontend/` with a dashboard and session detail pages. The UI subscribes to backend WebSocket streams for live updates.
- Simulator: `simulator/cli.py` posts synthetic events to the ingestion API for scenarios: `normal`, `loop`, `drift`, `failure`.

Requirements & setup

Prerequisites
- Python 3.10+ (for backend & simulator)
- Node.js + pnpm or npm (for frontend)

Backend (run locally)
```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend (run locally)
```bash
cd frontend
pnpm install   # or `npm install`
pnpm dev       # or `npm run dev`
# Set NEXT_PUBLIC_API_BASE_URL to http://localhost:8000 if needed
```

Simulator
```bash
python simulator/cli.py --scenario loop
python simulator/cli.py --scenario drift
python simulator/cli.py --scenario failure
```

API
- POST /events — ingest events (see `backend/models.py` for expected payload)
- GET /sessions — list sessions and aggregated metrics
- GET /sessions/{session_id} — session detail and events
- WS /ws/sessions — global sessions list stream
- WS /ws/sessions/{session_id} — per-session updates

Design decisions and deviations from `task.txt`

Data storage
- Implemented with SQLite (`aiosqlite`) for persistence and simplicity. This satisfies the requirement to handle out-of-order events, duplicates (via unique `hash_key` on events), and late arrivals. Using a persistent DB trades off deployment complexity for reliability vs an in-memory store.

Real-time vs batch
- The system is real-time-first: the ingestion endpoint enqueues detection as a background task and the backend broadcasts session updates over WebSocket. The frontend subscribes to these WS channels for live updates.

Detection logic (summary)
- Loop detection: collects a sliding window of recent events and computes fuzzy sequence similarity using `difflib.SequenceMatcher`. If two halves of the recent window are similar (similarity >= 0.6) and there is at least one failure in the window, the session is marked `looping`.
- Failure detection: marks a session `failing` when `MAX_CONSECUTIVE_FAILURES` (from `backend/config.py`) consecutive events are failures.
- Drift detection: compares a baseline set of `(file_target, action)` pairs vs recent pairs; if there's no overlap and baseline has enough examples, marks `drifting`.

Exact thresholds & heuristics
- The loop similarity threshold is currently 0.6 (tunable). The implementation uses practical heuristics (fuzzy matching / sample sizes) rather than plain string equality.

Trade-offs and limitations
- Simplicity: the detection heuristics are intentionally lightweight for the 3–4 hour scope. They are pragmatic but not exhaustive.
- In-memory WS manager: `backend/ws_manager.py` keeps WebSocket connections in memory (per-process). This is fine for local demos but not suitable for multi-process scaling.
- No message sequencing: WebSocket messages do not include per-message monotonic sequence numbers or timestamps. In rare cases messages may arrive out of order and a stale update could overwrite a newer state. The frontend attempts to merge session updates by `session_id` to mitigate this.
- Best-effort broadcasts: WS sends are best-effort and failures are ignored rather than retried.
- No auth: the prototype has no authentication or rate-limiting.

Files changed / deviations (important)
- Added: `backend/ws_manager.py` — in-memory connection manager and `broadcast()`.
- Modified: `backend/main.py` — broadcasts a session payload after ingest and exposes two WS endpoints: `/ws/sessions` (global) and `/ws/sessions/{session_id}` (per-session).
- Modified: `backend/detection.py` — detection now broadcasts session updates and the full sessions list after status changes.
- Modified: `frontend/src/app/page.tsx` — removed the 3s polling and added a WebSocket client to subscribe to global sessions and single-session updates; merged single-session messages into the sessions list.
- Modified: `frontend/src/app/sessions/[id]/page.tsx` — added a WebSocket connection for live session detail updates.
- `simulator/cli.py` still POSTs to `/events` (no websocket client); backend will broadcast received events.

How this maps to `task.txt` requirements
- Event ingestion: implemented at `POST /events` — handles duplicates by `hash_key` uniqueness, and out-of-order timestamps are accepted (detection logic uses ordering by timestamp when appropriate).
- Simulator CLI: implemented at `simulator/cli.py` with `normal`, `loop`, `drift`, `failure` scenarios.
- Processing & Detection: implemented basic loop/drift/failure heuristics in `backend/detection.py` (see file for details).
- Frontend: Next.js dashboard + session detail pages with live updates via WebSocket.

Known issues and recommended next improvements
- Add message sequence numbers/timestamps on WS messages and use them in the frontend to ignore stale updates.
- Make WS manager persistent/cluster-aware (Redis pub/sub or a dedicated message broker) for production scaling.
- Harden detection: add configuration toggles and a rules engine or ML model for robust heuristics.
- Add tests for edge cases (out-of-order, duplicates, bursts).

Quick test
1. Start backend and frontend as above.
2. Run the simulator: `python simulator/cli.py --scenario loop`.
3. Open http://localhost:3000, watch the dashboard populate and session pages update in real time.

Contact / Deliverables
- This README covers setup, architecture, detection choices, and deviations made while implementing the prototype.
- If you'd like, I can (pick one):
  - Update the simulator to send events via WebSocket instead of POST, or
  - Add per-message sequence numbers and implement ordering in the frontend, or
  - Produce a short demo script (recording instructions) for the 10-minute walkthrough requested in `task.txt`.
# Agent Observability System

A rapid-prototype monitoring system for autonomous AI agents, designed to detect behavioral anomalies like loops, intent drift, and persistent failures in messy real-world event streams.

The system is intentionally small but opinionated: it ingests raw event streams, stores them in SQLite, applies fuzzy heuristics, and exposes the result through a session dashboard and drill-down timeline.

## Architecture

- **Backend:** FastAPI (Python)
- **Database:** SQLite (Async via `aiosqlite`)
- **Frontend:** Next.js (App Router, Tailwind CSS)
- **Simulator:** Python CLI for scenario-based stress testing

### Key Design Decisions

1.  **Idempotency via Composite Hashing:** To handle duplicate events and out-of-order delivery, every event is assigned a `hash_key` generated from `sha256(session_id + step + timestamp)`. We use `INSERT OR IGNORE` in SQLite to ensure exactly-once processing without complex application logic.
2.  **Fuzzy Loop Detection:** Instead of exact string matches, we use `difflib.SequenceMatcher` to compare windows of activity. This detects loops even when the agent slightly varies its inputs (e.g., trying different variations of a failing command).
3.  **Intent Drift Detection:** We establish a baseline of "target files" and "actions" from the first 10 events. If the agent's most recent activity has zero intersection with this baseline for a sustained period, it is flagged as `drifting`.
4.  **Async Processing:** Ingestion is decoupled from detection. When an event is POSTed, it is saved immediately, and the detection engine runs in a FastAPI `BackgroundTasks` worker to maintain high ingestion throughput.

## What The UI Shows

- A live session list with counts, status, last action, and quick reading of whether the run is healthy, looping, drifting, or failing.
- A session detail page with the full event timeline, plain-language anomaly notes, and clear handling for missing metadata.
- A set of scenario hints so you can quickly see what each simulator mode is trying to demonstrate.

## Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Backend Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
export PYTHONPATH=$PYTHONPATH:.
export AGENT_OBS_DB_PATH=agent_obs.db
uvicorn backend.main:app --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run build
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` if the API is not running on `http://localhost:8000`.

### 3. Running Simulations
```bash
source venv/bin/activate
python simulator/cli.py --scenario loop
python simulator/cli.py --scenario drift
python simulator/cli.py --scenario normal
python simulator/cli.py --scenario failure
```

### Scenario Notes

- `normal`: a clean progression from inspection to code change to verification.
- `loop`: similar command variants keep failing, which should trip fuzzy loop detection.
- `drift`: the session starts in auth work, then gradually shifts into unrelated CSS work while a shadow session stays on task.
- `failure`: repeated retries fail in a tight streak, which should trip the failure detector.

The simulator also injects a small amount of duplicate and late-event chaos so the ingestion path is exercised a little more realistically.

## Example Flow

1. Start the backend and frontend.
2. Run `python simulator/cli.py --scenario drift`.
3. Open the dashboard and click the drifting session.
4. Read the timeline cards and the short heuristic summary to understand why the session was flagged.

## Detection Heuristics

- **Loop:** A fuzzy similarity score between the two halves of the recent event window must exceed the configured threshold and the window must include at least one failure.
- **Drift:** The recent activity must keep falling outside the baseline for 3 consecutive checks before the session is marked as drifting.
- **Failure:** 4 consecutive events with `status: "failure"`.

The thresholds live in `backend/config.py` so they can be tuned without touching the detection logic.

## Trade-offs & Limitations
- **In-Memory vs DB:** SQLite was chosen for its zero-config nature and ACID compliance, which simplified the idempotency logic. In a production system, a time-series DB like InfluxDB or a high-throughput store like Redis/ClickHouse would be preferred.
- **State Management:** Detection state is stored in the `sessions` table. The system does not auto-heal back to `healthy` without a stronger recovery policy, which was intentionally left out to keep the heuristics readable.
- **UI Scope:** The frontend is intentionally compact rather than app-like; the goal is to make the state legible and the examples obvious, not to build a full observability product.
