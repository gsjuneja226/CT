"""
CampuShare API Root
===================
The primary entry point for the Python/FastAPI backend.

Responsibilities:
- Application Lifecycle: Handles startup hooks for database initialization.
- Background Orchestration: Spawns a dedicated thread for the job scheduler.
- Routing Architecture: Aggregates modular routers for Auth, Jobs, Nodes, and WebSockets.
- Security: Configures CORS for cross-origin frontend communication.
"""

import os
import threading
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import init_db
from routers import auth, jobs, nodes, ws

# Ensure the ephemeral artifact storage directory exists on the host
os.makedirs(settings.RESULTS_DIR, exist_ok=True)

app = FastAPI(
    title="CampuShare API",
    description="Campus distributed computing platform",
    version="1.0.0"
)

# Global CORS Configuration: 
# Bridges the security gap between the API and the React frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    """
    Bootstrap logic executed before the server begins accepting traffic.
    Initializes the database connection pool and starts the background 
    scheduler thread to poll for jobs to dispatch.
    """
    import asyncio
    try:
        ws_manager.set_loop(asyncio.get_running_loop())
    except Exception:
        pass

    # 1. Synchronization: Ensure the SQLite/Postgres schema is current.
    init_db()
    
    # 2. Scheduling: Dispatches queued jobs to available worker nodes.
    # Note: Using a native Python thread for lightweight round-robin distribution.
    def run_scheduler():
        from services.scheduler import scheduler_tick
        while True:
            try:
                # Poll for queued workloads and matching agents via Redis
                scheduler_tick()
            except Exception as e:
                print(f"[scheduler] error: {e}")
            
            # Tick Interval: 10s to balance distribution latency and CPU usage.
            time.sleep(10)

    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    print("[scheduler] background thread started")


@app.get("/health")
def health():
    """
    Infrastructure Health Check.
    Used by load balancers and deployment probes to verify service availability.
    """
    return {"status": "ok", "service": "campushare"}


# --- Router Inclusions ---
# Modular namespaces for clean dependency separation.
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
app.include_router(ws.router, tags=["websocket"])
