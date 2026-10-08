"""
Real-Time Event Router (WebSockets)
===================================
Exposes the persistent connection endpoint for live job telemetry.
Enables the frontend to receive "push" updates for console logs and 
status transitions without polling the REST API.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    """
    Establishes a bi-directional pipe for a specific job lifecycle.
    
    Logic:
    - Registers the socket with the global WSManager.
    - Maintains a 'keep-alive' loop to detect transport-layer closures.
    - Unregisters the socket upon disconnection or fatal error.
    """
    await ws_manager.connect(job_id, websocket)
    try:
        # Keep the connection alive until the client disconnects
        while True:
            # Wait for messages (primarily used for server -> client broadcast)
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        # Ensure cleanup on any connection loss (standard or abnormal)
        ws_manager.disconnect(job_id, websocket)
