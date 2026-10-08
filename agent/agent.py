"""
CampuShare Node Agent
=====================
This script runs on the worker node (student laptop). It registers the node 
with the central scheduler, listens for incoming computing jobs via Redis, 
executes them in sandboxed Docker containers, and ships results back.

Main components:
- Registration: Connects to the scheduler to identify this node.
- Heartbeat: Periodic status updates (CPU/RAM) sent to the scheduler.
- Job Loop: Wait for jobs in a Redis queue and execute them.
"""

import os
import json
import time
import socket
import psutil
import requests
import redis as redis_lib
from config import (
    SCHEDULER_URL, NODE_ID, NODE_TOKEN, USER_TOKEN,
    REDIS_URL, save_to_env
)
from docker_runner import run_job
from result_collector import ship_result
from gpu_detect import detect_gpu


def register() -> tuple:
    """
    Registers this compute node with the central scheduler.
    
    Detects hardware capabilities (CPU, RAM, GPU) and sends them to the
    scheduler's registration endpoint. Receives a unique NODE_ID and 
    NODE_TOKEN which are then persisted to the environment.
    
    Returns:
        tuple: (node_id, node_token)
    """
    gpu = detect_gpu()
    print(f"[agent] Registering node with scheduler at {SCHEDULER_URL}...")
    resp = requests.post(
        f"{SCHEDULER_URL}/nodes/register",
        json={
            "hostname": socket.gethostname(),
            "total_cpu": psutil.cpu_count(logical=False) or 1,
            "total_ram_mb": psutil.virtual_memory().total // 1024 // 1024,
            "has_gpu": gpu["available"],
            "gpu_model": gpu.get("model"),
            "gpu_vram_mb": gpu.get("vram_mb")
        },
        headers={"Authorization": f"Bearer {USER_TOKEN}"},
        timeout=60
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Registration failed: {resp.status_code} {resp.text}")

    data = resp.json()
    node_id = data["node_id"]
    node_token = data["node_token"]
    
    # Persist registration info to .env for future restarts
    save_to_env("NODE_ID", node_id)
    save_to_env("NODE_TOKEN", node_token)
    
    print(f"[agent] Registered. Node ID: {node_id}")
    return node_id, node_token


def main():
    """
    Main entry point for the agent daemon.
    
    Initializes the agent, handles registration if needed, starts the
    heartbeat thread, and enters the main job-polling loop.
    """
    node_id = NODE_ID
    node_token = NODE_TOKEN

    if not node_id or not node_token:
        if not USER_TOKEN:
            print("[agent] ERROR: USER_TOKEN not set. Cannot register.")
            print("[agent] Set USER_TOKEN in .env and restart.")
            return
        node_id, node_token = register()

    print(f"[agent] Running. Node: {node_id}")
    print(f"[agent] Scheduler: {SCHEDULER_URL}")
    print(f"[agent] Waiting for jobs on node:{node_id}:queue ...")

    import ssl as _ssl
    redis_kwargs = {"decode_responses": True}
    if REDIS_URL.startswith("rediss://"):
        redis_kwargs["ssl_cert_reqs"] = _ssl.CERT_NONE
    r = redis_lib.from_url(REDIS_URL, **redis_kwargs)

    # Start idle heartbeat loop in background
    import threading
    def idle_heartbeat():
        while True:
            try:
                requests.post(
                    f"{SCHEDULER_URL}/nodes/heartbeat",
                    json={
                        "node_id": node_id,
                        "job_id": None,
                        "cpu_used_pct": psutil.cpu_percent(interval=1),
                        "ram_used_mb": psutil.virtual_memory().used // 1024 // 1024,
                        "status": "idle"
                    },
                    headers={"Authorization": f"Bearer {node_token}"},
                    timeout=5
                )
            except Exception:
                pass
            time.sleep(30)  # every 30 seconds

    hb_thread = threading.Thread(target=idle_heartbeat, daemon=True)
    hb_thread.start()

    while True:
        try:
            # Blocking pop from the Redis queue specific to this node
            result = r.blpop(f"node:{node_id}:queue", timeout=300)
            if not result:
                continue

            _, raw = result
            job = json.loads(raw)
            job_id = job["id"]
            chunk = job.get("chunk_index", 0)
            print(f"\n[agent] Job received: {job_id} (chunk {chunk})")

            try:
                # Execute the job using the Docker runner
                exit_code, container, volume_name = run_job(job, node_id, node_token)
                print(f"[agent] Job {job_id} finished with exit code {exit_code}")
                
                # Upload logs and results to the scheduler
                ship_result(job, exit_code, container, volume_name, node_token)
            except Exception as e:
                print(f"[agent] Job {job_id} error: {e}")
                # Notify scheduler of job failure
                try:
                    requests.post(
                        f"{SCHEDULER_URL}/jobs/{job_id}/failed",
                        json={"error_logs": str(e), "chunk_index": chunk},
                        headers={"Authorization": f"Bearer {node_token}"},
                        timeout=5
                    )
                except Exception:
                    pass

        except KeyboardInterrupt:
            print("\n[agent] Shutting down.")
            break
        except redis_lib.exceptions.ConnectionError as e:
            masked_url = REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL
            print(f"[agent] Redis connection lost to {masked_url}: {e}")
            print("[agent] Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[agent] Unexpected error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
