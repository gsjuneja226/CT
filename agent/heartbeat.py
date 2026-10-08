"""
Node Heartbeat Thread
=====================
This module provides a background thread that periodically reports the 
node's health and job status back to the scheduler while a job is running.
"""

import threading
import time
import requests
import psutil
from config import SCHEDULER_URL


class HeartbeatThread(threading.Thread):
    """
    A background thread that sends periodic 'running' status updates to 
    the scheduler. This prevents the scheduler from marking the node as 
    stale while it is busy executing a long-running job.
    """
    
    def __init__(self, job_id: str, node_id: str, node_token: str):
        """
        Initializes the heartbeat thread.
        
        Args:
            job_id (str): ID of the job currently executing.
            node_id (str): ID of the compute node.
            node_token (str): Authentication token for the node.
        """
        super().__init__(daemon=True)
        self.job_id = job_id
        self.node_id = node_id
        self.node_token = node_token
        self._stop_event = threading.Event()

    def run(self):
        """
        Main loop for the heartbeat thread. Sends resource usage and 
        status to the scheduler every 2 minutes.
        """
        while not self._stop_event.is_set():
            try:
                # Send node status and resource usage data
                requests.post(
                    f"{SCHEDULER_URL}/nodes/heartbeat",
                    json={
                        "node_id": self.node_id,
                        "job_id": self.job_id,
                        "cpu_used_pct": psutil.cpu_percent(interval=1),
                        "ram_used_mb": psutil.virtual_memory().used // 1024 // 1024,
                        "status": "running"
                    },
                    headers={"Authorization": f"Bearer {self.node_token}"},
                    timeout=5
                )
            except Exception as e:
                # Non-critical; we just log and try again in the next cycle
                print(f"[heartbeat] Failed to send: {e}")
            
            # Wait for 2 minutes or until stopped
            self._stop_event.wait(120)

    def stop(self):
        """
        Signals the thread to stop and exit its loop.
        """
        self._stop_event.set()
