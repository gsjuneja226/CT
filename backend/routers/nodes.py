"""
Node Management & Telemetry Router
==================================
Handles the lifecycle and monitoring of distributed compute nodes.

Responsibilities:
- Registration: Onboarding new hardware into the grid and issuing long-lived tokens.
- Inventory: Reporting active, healthy hardware to the dashboard.
- Heartbeats: Receiving real-time performance telemetry and broadcasting it to users.
"""

from fastapi import APIRouter, Depends, HTTPException
from schemas.node import NodeRegister, NodeResponse, HeartbeatPayload
from middleware.auth_guard import get_current_user, get_node_from_token
from middleware.role_check import require_role
from services.auth_service import create_node_token
from services.queue import (
    set_node_alive, set_node_stats, register_node_heartbeat,
    get_alive_node_ids, get_node_stats
)
from services.scheduler import on_new_node
from services.ws_manager import ws_manager
from database import execute, fetchone, fetchone_returning
from config import settings

router = APIRouter()


@router.post("/register", response_model=NodeResponse)
def register_node(
    body: NodeRegister,
    user: dict = Depends(require_role("contributor"))
):
    """
    Registers a new physical machine in the grid.
    
    Logic:
    - Stores hardware specs (CPU/RAM/GPU) in Postgres.
    - Generates a high-persistence Node Token for the agent.
    - Triggers an immediate scheduler tick to utilize the new capacity.
    """
    node = fetchone_returning("""
        INSERT INTO nodes (user_id, hostname, total_cpu, total_ram_mb,
                           has_gpu, gpu_model, gpu_vram_mb)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
    """, (
        user["id"], body.hostname, body.total_cpu, body.total_ram_mb,
        body.has_gpu, body.gpu_model, body.gpu_vram_mb
    ))
    if not node:
        raise HTTPException(status_code=500, detail="Failed to register node in database")

    node_id = str(node["id"])
    
    # Node tokens are designed for long-term headless use (1 year expiry)
    node_token = create_node_token(node_id)

    try:
        # Initialize telemetry state in Redis
        register_node_heartbeat(node_id, settings.HEARTBEAT_TTL_SECONDS, 0.0, 0)
        # Alert the scheduler to process waiting queue with new resources
        on_new_node(node_id)
    except Exception as e:
        # Redis may be misconfigured — log it but don't fail the registration
        print(f"[register_node] Redis warning (non-fatal): {e}")

    return NodeResponse(node_id=node_id, node_token=node_token)


@router.get("/available")
def get_available_nodes(user: dict = Depends(get_current_user)):
    """
    Returns a unified snapshot of active hardware.
    Merges static DB profiles with real-time Redis telemetry.
    """
    node_ids = get_alive_node_ids()
    result = []
    for nid in node_ids:
        stats = get_node_stats(nid)
        row = fetchone("SELECT * FROM nodes WHERE id=%s", (nid,))
        if row:
            cpu_used = float(stats.get("cpu_used_pct", 0))
            ram_used = int(stats.get("ram_used_mb", 0))
            
            # Construct a rich node profile for the UI
            result.append({
                "node_id": nid,
                "hostname": row["hostname"],
                "total_cpu": row["total_cpu"],
                "total_ram_mb": row["total_ram_mb"],
                "has_gpu": row["has_gpu"],
                "gpu_model": row["gpu_model"],
                # Calculate absolute free capacity (MB and %)
                "free_cpu_pct": round(max(0, 100 - cpu_used), 1),
                "free_ram_mb": max(0, row["total_ram_mb"] - ram_used),
                "current_job_id": stats.get("job_id") or None,
            })
    return result


@router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatPayload,
    node: dict = Depends(get_node_from_token)
):
    """
    Telemetery ingestion point for compute agents.
    
    Logic:
    1. Updates the node's 'Alive' TTL and stats in Redis.
    2. Logs the metric point in Postgres (history table).
    3. Broadcasts the raw metrics to any dashboard users watching the active Job.
    """
    # 1. High-speed lookup data (Redis)
    register_node_heartbeat(str(node["id"]), settings.HEARTBEAT_TTL_SECONDS, 
                            body.cpu_used_pct, body.ram_used_mb, body.job_id)

    # 2. Historical telemetry (Postgres)
    execute("""
        INSERT INTO heartbeats (node_id, job_id, cpu_used_pct, ram_used_mb, status)
        VALUES (%s,%s,%s,%s,%s)
    """, (str(node["id"]), body.job_id, body.cpu_used_pct,
          body.ram_used_mb, body.status))

    # 3. Real-time UI synchronization
    if body.job_id:
        from database import fetchone as db_fetchone
        job_row = db_fetchone("SELECT created_at FROM jobs WHERE id=%s", (body.job_id,))
        elapsed = 0
        
        # Calculate uptime for the active task
        if job_row:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            created = job_row["created_at"]
            if created.tzinfo is None:
                from datetime import timezone as tz
                created = created.replace(tzinfo=tz.utc)
            elapsed = int((now - created).total_seconds())

        # Notify the UI layer immediately
        await ws_manager.broadcast(body.job_id, {
            "type": "heartbeat",
            "cpu_used_pct": body.cpu_used_pct,
            "ram_used_mb": body.ram_used_mb,
            "elapsed_seconds": elapsed,
            "node_hostname": node["hostname"],
            "status": body.status
        })

    return {"ok": True}

