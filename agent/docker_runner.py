"""
Docker Runner Module
====================
Handles the lifecycle of a sandboxed computing job. 
Responsible for pulling images, creating volumes, running containers 
with resource limits, and streaming logs back to the scheduler.
"""

import docker
import requests
from config import SCHEDULER_URL
from heartbeat import HeartbeatThread

# Initialize Docker client from host environment
client = docker.from_env()


def run_job(job: dict, node_id: str, node_token: str):
    """
    Executes a computing job within a Docker container.
    
    This function manages the entire execution process:
    1. Pulls the required Docker image.
    2. Creates a dedicated data volume for results.
    3. Configures resource limits (CPU, RAM, GPU).
    4. Streams container logs to the scheduler in real-time.
    5. Monitors job health via a dedicated heartbeat thread.
    
    Args:
        job (dict): Detailed job specification from the scheduler.
        node_id (str): ID of the current compute node.
        node_token (str): Authentication token for this node.
        
    Returns:
        tuple: (exit_code, container_object, volume_name)
    """
    image = job["image"]
    job_id = job["id"]
    volume_name = f"job_{job_id}_output"
    container_name = f"campushare_{job_id}"

    print(f"[runner] Pulling image {image}...")
    run_kwargs = {}
    try:
        client.images.pull(image)
    except Exception as e:
        if "manifest" in str(e).lower() or "platform" in str(e).lower():
            print(f"[runner] Native platform pull failed, retrying with platform='linux/amd64'...")
            client.images.pull(image, platform="linux/amd64")
            run_kwargs["platform"] = "linux/amd64"
        else:
            print(f"[runner] Pull failed: {e}")
            raise

    client.volumes.create(name=volume_name)

    env = dict(job.get("env_vars") or {})
    env["CHUNK_INDEX"] = str(job.get("chunk_index") or 0)
    env["CHUNK_TOTAL"] = str(job.get("total_chunks") or 1)

    device_requests = []
    if job.get("gpu"):
        device_requests = [
            docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
        ]

    try:
        # Check if the internal network 'campus-net' exists; create if missing.
        # This provides basic isolation for the running containers.
        try:
            client.networks.get("campus-net")
        except docker.errors.NotFound:
            client.networks.create("campus-net", driver="bridge")

        # Start the container with specified resource constraints
        container = client.containers.run(
            image,
            name=container_name,
            detach=True,
            cpu_quota=int(job.get("cpu", 1.0) * 100000),
            cpu_period=100000,
            mem_limit=job.get("memory", "2g"),
            environment=env,
            volumes={volume_name: {"bind": "/job/output", "mode": "rw"}},
            device_requests=device_requests,
            network="campus-net",
            remove=False,
            **run_kwargs
        )
    except Exception as e:
        try:
            client.volumes.get(volume_name).remove()
        except Exception:
            pass
        raise

    hb = HeartbeatThread(job_id, node_id, node_token)
    hb.start()

    # Mark job as running
    try:
        requests.post(
            f"{SCHEDULER_URL}/jobs/{job_id}/running",
            headers={"Authorization": f"Bearer {node_token}"},
            timeout=5
        )
    except Exception:
        pass

    # Stream logs
    batch = []
    try:
        for log_bytes in container.logs(stream=True, follow=True):
            line = log_bytes.decode("utf-8", errors="replace").strip()
            if line:
                batch.append(line)
                if len(batch) >= 10:
                    _send_logs(job_id, node_token, batch)
                    batch.clear()
    except Exception as e:
        print(f"[runner] Log stream error: {e}")

    if batch:
        _send_logs(job_id, node_token, batch)

    result = container.wait()
    exit_code = result.get("StatusCode", 1)

    hb.stop()
    hb.join(timeout=10)

    return exit_code, container, volume_name


def _send_logs(job_id: str, node_token: str, lines: list):
    """
    Helper function to send a batch of log lines to the scheduler.
    
    Args:
        job_id (str): ID of the job generating logs.
        node_token (str): Authentication token for this node.
        lines (list): List of log strings to transmit.
    """
    try:
        requests.post(
            f"{SCHEDULER_URL}/jobs/{job_id}/logs",
            json={"lines": lines},
            headers={"Authorization": f"Bearer {node_token}"},
            timeout=5
        )
    except Exception:
        # Logging failures are non-critical to job execution
        pass
