"""
Real-Time Communication Manager (WebSockets)
===========================================
Orchestrates active WebSocket connections for live job monitoring.
Groups connections by 'Job ID' to ensure logs and status updates are 
efficiently routed only to interested clients (researchers).

Features:
- Connection Grouping: Maintains a map of Job IDs to sets of active WebSockets.
- Graceful Errors: Automatically prunes "dead" or closed sockets during broadcast.
- Sync Bridge: Provides a thread-safe way to trigger broadcasts from sync services.
"""

import json
from typing import Dict, Set
from fastapi import WebSocket


class WSManager:
    """
    Stateful manager for tracking and notifying connected dashboard users.
    """
    def __init__(self):
        # Maps job_id -> set of WebSocket instances
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self, job_id: str, ws: WebSocket):
        """
        Accepts a new connection and registers it for a specific job lifecycle.
        """
        import asyncio
        if not self.loop:
            try:
                self.loop = asyncio.get_running_loop()
            except Exception:
                pass
        await ws.accept()
        if job_id not in self.connections:
            self.connections[job_id] = set()
        self.connections[job_id].add(ws)

    def disconnect(self, job_id: str, ws: WebSocket):
        """
        Removes a socket from the registry upon closure.
        """
        if job_id in self.connections:
            self.connections[job_id].discard(ws)
            if not self.connections[job_id]:
                del self.connections[job_id]

    async def broadcast(self, job_id: str, message: dict):
        """
        Sends a JSON message to all clients monitoring a specific job.
        Implements proactive cleanup of stale connections.
        """
        if job_id not in self.connections:
            return
            
        dead = set()
        for ws in self.connections[job_id].copy():
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                # Catch closed or failed sockets
                dead.add(ws)
        
        # Cleanup any connections that failed during broadcast
        for ws in dead:
            self.disconnect(job_id, ws)

    def broadcast_sync(self, job_id: str, message: dict):
        """
        Bridge method for synchronous services (e.g. background threads).
        Schedules the async broadcast on the main event loop.
        """
        import asyncio
        try:
            loop = self.loop
            if not loop or loop.is_closed():
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(job_id, message), loop)
        except Exception as e:
            print(f"[ws_manager] broadcast_sync warning: {e}")


# Singleton instance shared across the FastAPI application
ws_manager = WSManager()
