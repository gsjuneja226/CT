"""
Distributed Job Orchestration Router
=====================================
The primary engine for workload lifecycle management. Handles user-facing 
job submissions, status tracking, and result delivery, as well as 
agent-facing status reporting and artifact ingestion.

Key Workflows:
1. Submission: Accepts a job, optionally shards it into chunks, and queues them.
2. Execution: Agents pick up 'queued' jobs, moving them to 'running'.
3. Monitoring: Real-time telemetry and log streaming via WebSockets.
4. Aggregation: Child results are merged into a final parent artifact upon completion.
5. Reliability: Automatic retries for failed chunks up to a configured limit.
"""

import os
import json
import zipfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional, List
from schemas.job import JobCreate, JobResponse, JobDetail, ChunkStatus
from middleware.auth_guard import get_current_user, get_node_from_token
from middleware.role_check import require_role
from services.queue import push_job, get_logs, push_log_line
from services.splitter import compute_chunks
from services.aggregator import aggregate
from services.ws_manager import ws_manager
from database import execute, fetchone, fetchall, fetchone_returning
from config import settings

router = APIRouter()


def _job_to_dict(row) -> dict:
    """
    Normalizes a Postgres RealDictRow into a JSON-serializable dictionary.
    Handles UUID-to-String and ISO-Timestamp conversions.
    """
    d = dict(row)
    d["id"] = str(d["id"])
    d["user_id"] = str(d["user_id"]) if d.get("user_id") else None
    d["parent_id"] = str(d["parent_id"]) if d.get("parent_id") else None
    d["node_id"] = str(d["node_id"]) if d.get("node_id") else None
    
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    if d.get("updated_at"):
        d["updated_at"] = d["updated_at"].isoformat()
    return d


@router.get("/admin/cleanup")
def admin_cleanup():
    """
    Emergency utility to clear jobs stuck in the 'dispatched' state.
    Used when multiple agents disconnect without fulfilling their assignments.
    """
    execute("DELETE FROM jobs WHERE status='dispatched'")
    return {"message": "All dispatched jobs deleted!"}


@router.post("", response_model=JobResponse)
def submit_job(
    body: JobCreate,
    user: dict = Depends(require_role("submitter"))
):
    """
    Receives a new computational workload.
    
    Logic:
    - If 'split_by' is provided: Creates a parent record and multiple 
      child 'chunk' jobs (sharding).
    - If 'split_by' is null: Creates a single standalone job.
    - All executable tasks are pushed to the Redis global queue.
    """
    os.makedirs(settings.RESULTS_DIR, exist_ok=True)

    if body.split_by:
        # 1. Parent Record: Serves as a container and aggregation point.
        parent = fetchone_returning("""
            INSERT INTO jobs (user_id, image, cpu, memory, gpu, timeout_seconds,
                               status, split_strategy, total_chunks)
            VALUES (%s,%s,%s,%s,%s,%s,'running',%s,%s)
            RETURNING *
        """, (
            user["id"], body.image, body.cpu, body.memory, body.gpu,
            body.timeout_seconds, body.split_by.strategy,
            body.split_by.num_chunks
        ))
        parent_id = str(parent["id"])

        # 2. Sharding: Compute the environment variable sets for each chunk.
        chunks = compute_chunks(body.split_by.model_dump())
        
        for i, chunk_env in enumerate(chunks):
            # Create child job record tied to the parent ID
            child = fetchone_returning("""
                INSERT INTO jobs (user_id, parent_id, chunk_index, image, cpu,
                                  memory, gpu, timeout_seconds, status, env_vars,
                                  split_strategy, total_chunks)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s)
                RETURNING *
            """, (
                user["id"], parent_id, i, body.image, body.cpu, body.memory,
                body.gpu, body.timeout_seconds, json.dumps(chunk_env),
                body.split_by.strategy, body.split_by.num_chunks
            ))
            
            # Dispatch: Make the work available to nodes
            child_dict = _job_to_dict(child)
            child_dict["env_vars"] = chunk_env
            push_job(child_dict)

        return JobResponse(
            job_id=parent_id,
            status="running",
            is_split=True,
            total_chunks=body.split_by.num_chunks
        )

    else:
        # Standalone Workload: Single execution unit
        job = fetchone_returning("""
            INSERT INTO jobs (user_id, image, cpu, memory, gpu, timeout_seconds, status)
            VALUES (%s,%s,%s,%s,%s,%s,'queued')
            RETURNING *
        """, (user["id"], body.image, body.cpu, body.memory, body.gpu, body.timeout_seconds))
        
        job_dict = _job_to_dict(job)
        push_job(job_dict)

        return JobResponse(job_id=job_dict["id"], status="queued", is_split=False)


@router.get("")
def list_jobs(user: dict = Depends(get_current_user)):
    """
    Retrieves the execution history for the active researcher.
    Hides child chunks to present a clean, parent-level view.
    Includes a summary of chunks if the job was split.
    """
    jobs = fetchall("""
        SELECT * FROM jobs
        WHERE user_id=%s AND parent_id IS NULL
        ORDER BY created_at DESC
    """, (user["id"],))
    
    result = []
    for j in (jobs or []):
        d = _job_to_dict(j)
        # Fetch chunk summaries for real-time progress bars in the UI
        if d.get("total_chunks"):
            chunks = fetchall("""
                SELECT chunk_index, status, node_id FROM jobs
                WHERE parent_id=%s ORDER BY chunk_index
            """, (d["id"],))
            d["chunks"] = [
                {"chunk_index": c["chunk_index"], "status": c["status"],
                 "node_id": str(c["node_id"]) if c["node_id"] else None}
                for c in (chunks or [])
            ]
        result.append(d)
    return result


@router.get("/{job_id}")
def get_job(job_id: str, user: dict = Depends(get_current_user)):
    """
    Fetches detailed metadata and chunk status for a specific workload.
    """
    job = fetchone("SELECT * FROM jobs WHERE id=%s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Ownership Security Guard
    if str(job["user_id"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Access denied")
        
    d = _job_to_dict(job)
    
    # Enrich with chunk details if applicable
    if d.get("total_chunks"):
        chunks = fetchall("""
            SELECT chunk_index, status, node_id FROM jobs
            WHERE parent_id=%s ORDER BY chunk_index
        """, (d["id"],))
        d["chunks"] = [
            {"chunk_index": c["chunk_index"], "status": c["status"],
             "node_id": str(c["node_id"]) if c["node_id"] else None}
            for c in (chunks or [])
        ]
    return d


@router.get("/{job_id}/results")
def download_results(job_id: str, user: dict = Depends(get_current_user)):
    """
    Serves the final computational artifact (ZIP).
    Ensures job is complete and user has access.
    """
    job = fetchone("SELECT * FROM jobs WHERE id=%s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if str(job["user_id"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if job["status"] != "done":
        raise HTTPException(status_code=404, detail="Results not ready yet")
        
    result = fetchone("SELECT * FROM results WHERE job_id=%s", (job_id,))
    if not result or not os.path.exists(result["file_path"]):
        raise HTTPException(status_code=404, detail="Result file not found on disk")
        
    return FileResponse(
        result["file_path"],
        media_type="application/zip",
        filename=f"results_{job_id[:8]}.zip"
    )


@router.get("/{job_id}/logs")
def get_job_logs(job_id: str, user: dict = Depends(get_current_user)):
    """
    Polls the latest console output lines from the Redis buffer.
    """
    lines = get_logs(job_id)
    return {"lines": lines}


# --- Agent-Facing Endpoints ---
# These endpoints are used by compute nodes to report operational progress.

@router.post("/{job_id}/running")
def mark_running(job_id: str, node: dict = Depends(get_node_from_token)):
    """
    Agent check-in: Informs the system that Docker container execution has started.
    """
    execute("""
        UPDATE jobs SET status='running', updated_at=NOW() WHERE id=%s
    """, (job_id,))
    # Sync UI immediately
    ws_manager.broadcast_sync(job_id, {"type": "status_change", "status": "running"})
    return {"ok": True}


@router.post("/{job_id}/logs")
async def append_logs(
    job_id: str,
    body: dict,
    node: dict = Depends(get_node_from_token)
):
    """
    Agent stream: Accepts a batch of console log lines from the container.
    Logic: Pushes to Redis for polling and broadcasts to WebSockets for live UI view.
    """
    lines = body.get("lines", [])
    for line in lines:
        push_log_line(job_id, line)
        # Real-time relay
        await ws_manager.broadcast(job_id, {"type": "log_line", "line": line})
    return {"ok": True}


@router.post("/{job_id}/complete")
async def complete_job(
    job_id: str,
    exit_code: int = Form(...),
    chunk_index: int = Form(0),
    output: UploadFile = File(...),
    node: dict = Depends(get_node_from_token)
):
    """
    Agent handover: Uploads the finished ZIP artifact from the compute node.
    
    Lifecycle Trigger:
    If the job was part of a SHARDED parent, this checks if all siblings are done.
    If yes, it triggers the 'aggregator' service to merge them into one file.
    """
    # 1. Persist the shard artifact
    os.makedirs(f"{settings.RESULTS_DIR}/{job_id}", exist_ok=True)
    zip_path = f"{settings.RESULTS_DIR}/{job_id}/chunk_{chunk_index}.zip"
    content = await output.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    # 2. Update DB status
    execute("""
        UPDATE jobs SET status='done', result_path=%s, updated_at=NOW()
        WHERE id=%s
    """, (zip_path, job_id))

    execute("""
        INSERT INTO results (job_id, file_path, exit_code)
        VALUES (%s,%s,%s)
        ON CONFLICT (job_id) DO UPDATE SET file_path=EXCLUDED.file_path, exit_code=EXCLUDED.exit_code
    """, (job_id, zip_path, exit_code))

    # 3. Aggregation Logic: Check if we can finalize the parent job
    job = fetchone("SELECT * FROM jobs WHERE id=%s", (job_id,))
    if job and job["parent_id"]:
        parent_id = str(job["parent_id"])
        siblings = fetchall("SELECT status FROM jobs WHERE parent_id=%s", (parent_id,))
        
        # Are all parallel chunks in a terminal state?
        all_done = all(s["status"] in ("done", "failed") for s in (siblings or []))
        
        if all_done:
            # Sync UI state for the master progress bar
            await ws_manager.broadcast(parent_id, {
                "type": "chunk_done",
                "chunk_index": chunk_index,
                "chunks_complete": sum(1 for s in siblings if s["status"] == "done"),
                "total": len(siblings)
            })
            # Trigger heavy merge operation
            aggregate(parent_id)
    else:
        # Standalone job: Direct completion broadcast
        await ws_manager.broadcast(job_id, {
            "type": "job_complete",
            "download_url": f"/jobs/{job_id}/results"
        })

    return {"ok": True}


@router.post("/{job_id}/failed")
async def fail_job(
    job_id: str,
    body: dict,
    node: dict = Depends(get_node_from_token)
):
    """
    Error Recovery Handler.
    Implement automatic retries for intermittent failures (network, transient errors).
    Calls the retry logic: if the retry count is below the threshold, 
    the job is re-queued; otherwise, it is marked as 'failed' permanently.
    """
    from services.queue import push_job as push_to_queue
    error_logs = body.get("error_logs", "")
    
    job = fetchone("SELECT * FROM jobs WHERE id=%s", (job_id,))
    if not job:
        return {"ok": False}

    retry_count = job["retry_count"] + 1

    if retry_count < settings.MAX_RETRY_COUNT:
        # LOGIC: Re-queue the job with incremented retry counter
        execute("""
            UPDATE jobs SET retry_count=%s, status='queued',
            queue_reason='Retrying after failure', updated_at=NOW()
            WHERE id=%s
        """, (retry_count, job_id))
        
        job_dict = _job_to_dict(job)
        job_dict["retry_count"] = retry_count
        push_to_queue(job_dict)
    else:
        # LOGIC: Permanent failure after N attempts
        execute("""
            UPDATE jobs SET status='failed', retry_count=%s, updated_at=NOW()
            WHERE id=%s
        """, (retry_count, job_id))
        
        await ws_manager.broadcast(job_id, {
            "type": "job_failed",
            "error": error_logs[:500]
        })
        
        # Check if this failure affects the parent aggregation
        if job["parent_id"]:
            parent_id = str(job["parent_id"])
            siblings = fetchall("SELECT status FROM jobs WHERE parent_id=%s", (parent_id,))
            if siblings and all(s["status"] in ("done", "failed") for s in siblings):
                all_failed = all(s["status"] == "failed" for s in siblings)
                if all_failed:
                    execute("UPDATE jobs SET status='failed', updated_at=NOW() WHERE id=%s", (parent_id,))
                else:
                    # Still aggregate the successful chunks!
                    aggregate(parent_id)

    return {"ok": True}


@router.delete("/{job_id}")
def delete_job(job_id: str, user: dict = Depends(get_current_user)):
    """
    Administrative deletion. Cleans up DB records and disk artifacts.
    Prevents deletion of active (running) jobs to ensure grid stability.
    Permanently deletes a job from the system, including any 
    linked results, heartbeats, and child chunks.
    """
    job = fetchone("SELECT * FROM jobs WHERE id=%s", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if str(job["user_id"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if job["status"] in ("running", "dispatched"):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete an active job. Wait for completion or failure first."
        )

    # 1. Artifact deletion
    if job.get("result_path") and os.path.exists(job["result_path"]):
        try:
            os.remove(job["result_path"])
        except Exception:
            pass
            
    # 2. Database cascade
    execute("DELETE FROM results     WHERE job_id=%s", (job_id,))
    execute("DELETE FROM heartbeats  WHERE job_id=%s", (job_id,))
    execute("DELETE FROM jobs        WHERE id=%s",     (job_id,))
    return {"ok": True}