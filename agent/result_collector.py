"""
Result Collector Module
=======================
Handles the extraction of output files from completed Docker containers, 
packages them into a ZIP archive, and uploads the results to the central scheduler.
"""

import os
import zipfile
import tempfile
import shutil
import requests
import docker
from config import SCHEDULER_URL

# Docker client for container and volume management
client = docker.from_env()


def ship_result(job: dict, exit_code: int, container, volume_name: str, node_token: str):
    """
    Collects, archives, and transmits the results of a finished job.
    
    This function performs the following steps:
    1. Extracts the contents of /job/output from the container as a tarball.
    2. Unpacks the tarball into a temporary directory.
    3. Recursively zips the extracted files.
    4. Sends either a 'complete' (success) or 'failed' (non-zero exit) 
       notification to the scheduler, including the result ZIP if successful.
    5. Cleans up the container, volume, and temporary files.
    
    Args:
        job (dict): Original job specification.
        exit_code (int): Exit code returned by the Docker container.
        container: The Docker container object.
        volume_name (str): The name of the volume used by the container.
        node_token (str): Authentication token for the node.
    """
    job_id = job["id"]
    chunk_index = job.get("chunk_index", 0) or 0
    zip_path = os.path.join(tempfile.gettempdir(), f"result_{job_id}_{chunk_index}.zip")
    tmp_dir = tempfile.mkdtemp()

    try:
        # Get files directly from container before removing it.
        # Docker's get_archive returns a stream of bytes representing a tar file.
        try:
            bits, stat = container.get_archive("/job/output")
            tar_path = os.path.join(tempfile.gettempdir(), f"output_{job_id}.tar")
            with open(tar_path, "wb") as f:
                for chunk in bits:
                    f.write(chunk)

            import tarfile
            with tarfile.open(tar_path) as tar:
                tar.extractall(tmp_dir)

            os.remove(tar_path)

            # Determine the actual root of the extracted output
            output_subdir = os.path.join(tmp_dir, "output")
            if os.path.exists(output_subdir):
                source_dir = output_subdir
            else:
                source_dir = tmp_dir

        except Exception as e:
            print(f"[collector] Could not extract output: {e}")
            source_dir = tmp_dir

        # ZIP the collected output files
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(source_dir):
                for f in files:
                    filepath = os.path.join(root, f)
                    arcname = os.path.relpath(filepath, source_dir)
                    z.write(filepath, arcname)

        print(f"[collector] Zipped output: {zip_path} ({os.path.getsize(zip_path)} bytes)")

        # Transmit the results to the scheduler
        if exit_code == 0:
            # Job succeeded; upload ZIP
            with open(zip_path, "rb") as zf:
                resp = requests.post(
                    f"{SCHEDULER_URL}/jobs/{job_id}/complete",
                    files={"output": ("result.zip", zf, "application/zip")},
                    data={
                        "exit_code": str(exit_code),
                        "chunk_index": str(chunk_index)
                    },
                    headers={"Authorization": f"Bearer {node_token}"},
                    timeout=60
                )
                print(f"[collector] Complete response: {resp.status_code} {resp.text[:200]}")
        else:
            # Job failed; report error logs without result file
            resp = requests.post(
                f"{SCHEDULER_URL}/jobs/{job_id}/failed",
                json={
                    "error_logs": f"Container exited with code {exit_code}",
                    "chunk_index": chunk_index
                },
                headers={"Authorization": f"Bearer {node_token}"},
                timeout=10
            )
            print(f"[collector] Failed response: {resp.status_code}")

    except Exception as e:
        print(f"[collector] Error shipping result: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup container resources
        try:
            container.remove(force=True)
            print(f"[collector] Container removed")
        except Exception as e:
            print(f"[collector] Could not remove container: {e}")

        # Cleanup dedicated Docker volume
        try:
            client.volumes.get(volume_name).remove()
            print(f"[collector] Volume removed")
        except Exception as e:
            print(f"[collector] Could not remove volume: {e}")

        # Cleanup local temporary files and directories
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            os.remove(zip_path)