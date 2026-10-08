"""
Grid Scheduler Service
======================
The brain of the CampuShare platform. Responsible for matching queued 
computational workloads with available, healthy compute nodes.

Features:
- Resource Validation: Ensures nodes have sufficient CPU/RAM/GPU for a job.
- Round-Robin Scoring: Heavily penalizes nodes that just received a job to 
  force distribution across multiple physical machines.
- Capacity Tracking: Dynamically deducts resources during a single tick to 
  handle multi-chunk parallel jobs correctly.
"""

from config import settings
from database import execute, fetchall, fetchone


def parse_memory_to_mb(memory_str: str) -> int:
    """
    Normalizes memory strings (e.g. '2g', '512m', '1gb') into integer Megabytes.
    """
    s = memory_str.lower().strip()
    if s.endswith("g"):
        return int(float(s[:-1]) * 1024)
    if s.endswith("m"):
        return int(s[:-1])
    if s.endswith("gb"):
        return int(float(s[:-2]) * 1024)
    if s.endswith("mb"):
        return int(s[:-2])
    return int(s)


def node_fits_job(node: dict, job: dict) -> bool:
    """
    Checks if a specific node has enough free capacity to execute the job.
    
    Calculation:
    - RAM: Absolute free MB >= required MB.
    - CPU: Relative free % >= required % (calculated against node's total cores).
    - GPU: Hardware availability must match the job requirement.
    """
    required_ram = parse_memory_to_mb(job.get("memory", "2g"))
    total_cpu = node.get("total_cpu", 1)
    
    # Calculate what percentage of this specific node's total CPU capacity is needed
    required_cpu_pct = (job.get("cpu", 1.0) / total_cpu) * 100

    return (
        node.get("free_cpu_pct", 0) >= required_cpu_pct
        and node.get("free_ram_mb", 0) >= required_ram
        and (not job.get("gpu", False) or node.get("has_gpu", False))
    )


def get_live_nodes():
    """
    Aggregates data from Redis (real-time telemetry) and Postgres (static metadata)
     to produce a snapshot of the grid's current state.
    """
    from services.queue import get_alive_node_ids, get_node_stats
    node_ids = get_alive_node_ids()
    nodes = []
    for nid in node_ids:
        stats = get_node_stats(nid)
        row = fetchone("SELECT * FROM nodes WHERE id=%s", (nid,))
        
        if row:
            cpu_used = float(stats.get("cpu_used_pct", 0))
            ram_used = int(stats.get("ram_used_mb", 0))

            nodes.append({
                "node_id": nid,
                "hostname": row["hostname"],
                "total_cpu": row["total_cpu"],
                "total_ram_mb": row["total_ram_mb"],
                "has_gpu": row["has_gpu"],
                "gpu_model": row["gpu_model"],
                "free_cpu_pct": max(0, 100 - cpu_used),
                "free_ram_mb": max(0, row["total_ram_mb"] - ram_used),
                "current_job_id": stats.get("job_id") or None,
            })
    return nodes


def dispatch_to_node(job: dict, node: dict):
    """
    Synchronizes the assignment by updating the database and pushing to 
    the node-specific Redis queue.
    """
    from services.queue import push_job_to_node
    push_job_to_node(node["node_id"], job)

    execute("""
        UPDATE jobs SET status='dispatched', node_id=%s, updated_at=NOW()
        WHERE id=%s
    """, (node["node_id"], job["id"]))


def on_new_node(node_id: str):
    """
    Event handler triggered when a node registers or sends its first heartbeat.
    Forces an immediate scheduler tick to minimize queue latency.
    """
    scheduler_tick()


def scheduler_tick():
    """
    Primary orchestration loop. 
    1. Expires stale queued jobs.
    2. Fetches live nodes.
    3. Pops jobs from the global queue and assigns them to the best-fit nodes.
    """
    from services.queue import pop_job, push_job_front

    # Step 1: Garbage collection for workloads that timed out waiting for a node.
    execute("""
        UPDATE jobs
        SET status='expired',
            queue_reason='No node available within timeout'
        WHERE status='queued'
        AND parent_id IS NULL
        AND created_at < NOW() - INTERVAL '1 second' * %s
    """, (settings.JOB_QUEUE_TIMEOUT_SECONDS,))

    nodes = get_live_nodes()

    # Early exit if no target hardware is reachable
    if not nodes:
        return

    # To ensure parallel chunks of the same job go to DIFFERENT machines,
    # we track recent assignments within this tick and apply a heavy score penalty.
    recent_dispatches = {}

    while True:
        job = pop_job()
        if not job:
            break

        # Filter nodes by hardware requirements
        eligible = [n for n in nodes if node_fits_job(n, job)]

        if not eligible:
            # Re-queue the job and update its reason if no node fits right now
            execute("""
                UPDATE jobs SET queue_reason='Waiting for suitable node'
                WHERE id=%s
            """, (job["id"],))
            push_job_front(job)
            break  # Stop processing to wait for new nodes or resources

        # Spread Strategy:
        # Choose the node with highest (FreeCPU + FreeRAM) - (AlreadyDispatchedPenalty).
        # The 1000 point penalty ensures a "stale" or "weaker" node is picked over 
        # a "strong" node that just received one chunk.
        def calc_score(n):
            base_score = n["free_cpu_pct"] + n["free_ram_mb"] / 1024
            penalty = recent_dispatches.get(n["node_id"], 0) * 1000
            return base_score - penalty

        best = max(eligible, key=calc_score)

        # Finalize assignment
        dispatch_to_node(job, best)
        recent_dispatches[best["node_id"]] = recent_dispatches.get(best["node_id"], 0) + 1

        # DYNAMIC DEDUCTION:
        # Update our in-memory node snapshot so the NEXT job in the queue 
        # sees the REDUCED resources on this node immediately, without 
        # waiting for a heartbeat update.
        required_ram = parse_memory_to_mb(job.get("memory", "2g"))
        total_cpu = best.get("total_cpu", 1)
        required_cpu_pct = (job.get("cpu", 1.0) / total_cpu) * 100

        best["free_cpu_pct"] -= required_cpu_pct
        best["free_ram_mb"] -= required_ram
        best["free_cpu_pct"] = max(best["free_cpu_pct"], 0)
        best["free_ram_mb"] = max(best["free_ram_mb"], 0)
