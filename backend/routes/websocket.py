from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ws_manager import connect, disconnect

router = APIRouter()


@router.websocket('/ws/sessions/{session_id}')
async def session_ws(websocket: WebSocket, session_id: str):
    await connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect(session_id, websocket)


@router.websocket('/ws/sessions')
async def sessions_ws(websocket: WebSocket):
    await connect('all', websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect('all', websocket)
