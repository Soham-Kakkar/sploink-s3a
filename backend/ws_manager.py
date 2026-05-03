from typing import Dict, Set
import json
import asyncio
from fastapi import WebSocket

# Simple in-memory manager: session_id -> set of WebSocket connections
_connections: Dict[str, Set[WebSocket]] = {}

async def connect(session_id: str, websocket: WebSocket):
    await websocket.accept()
    conns = _connections.setdefault(session_id, set())
    conns.add(websocket)

async def disconnect(session_id: str, websocket: WebSocket):
    conns = _connections.get(session_id)
    if conns and websocket in conns:
        conns.remove(websocket)
        if not conns:
            _connections.pop(session_id, None)

async def broadcast(session_id: str, message: dict):
    conns = list(_connections.get(session_id, set()))
    if not conns:
        return

    text = json.dumps(message)
    # send concurrently but tolerate failures
    async def _send(ws: WebSocket):
        try:
            await ws.send_text(text)
        except Exception:
            # ignore broken connections; they'll be cleaned on disconnect
            pass

    await asyncio.gather(*[_send(ws) for ws in conns])
