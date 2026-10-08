"""
Redis Messaging & Telemetry Service
===================================
The high-speed communication backbone of the grid. 
Uses Redis for job queuing, real-time node heartbeats, and log streaming.

Data Structures:
- jobs:queue (List): Global FIFO queue for pending workloads.
- node:[id]:queue (List): Targeted queue for assigned jobs on a specific node.
- node:[id]:alive (String): TTL-backed indicator of node presence.
- node:[id]:stats (Hash): Real-time metrics (CPU/RAM/Job Status).
- job:[id]:logs (List): Capped buffer for live console output.
"""

import json
import redis as redis_lib
from config import settings

# Global Redis client singleton

_redis_client = None


def get_redis():
    """
    Lazy-loader for the shared Redis connection.
    Uses 'decode_responses=True' to handle strings instead of bytes.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def push_job(job_dict: dict):
    """
    Appends a new workload to the tail of the global processing queue.
    """
    r = get_redis()
    r.rpush("jobs:queue", json.dumps(job_dict))


def push_job_to_node(node_id: str, job_dict: dict):
    """
    Directly assigns a job to a specific worker node's private queue.
    Used by the scheduler after matching requirements.
    """
    r = get_redis()
    r.rpush(f"node:{node_id}:queue", json.dumps(job_dict))


def push_job_front(job_dict: dict):
    """
    Prioritizes a job by placing it at the head of the global queue.
    Useful for re-queuing failed assignments.
    """
    r = get_redis()
    r.lpush("jobs:queue", json.dumps(job_dict))


def pop_job():
    """
    Retrieves the next available workload from the global queue.
    """
    r = get_redis()
    raw = r.lpop("jobs:queue")
    return json.loads(raw) if raw else None


def set_node_alive(node_id: str, ttl: int = 15):
    """
    Updates the presence indicator for a node with a self-destructing key.
    If no update occurs within 'ttl' seconds, the node is considered offline.
    """
    r = get_redis()
    r.setex(f"node:{node_id}:alive", ttl, "1")


def set_node_stats(node_id: str, cpu_pct: float, ram_mb: int, job_id: str = None):
    """
    Updates the performance telemetry hash for a specific contributor.
    """
    r = get_redis()
    r.hset(f"node:{node_id}:stats", mapping={
        "cpu_used_pct": str(cpu_pct),
        "ram_used_mb": str(ram_mb),
        "job_id": job_id or ""
    })


def register_node_heartbeat(node_id: str, ttl: int, cpu_pct: float, ram_mb: int, job_id: str = None):
    """
    Atomic update of both presence and telemetry.
    Uses a Redis Pipeline to ensure consistency and minimize network round-trips.
    """
    r = get_redis()
    pipe = r.pipeline()
    pipe.setex(f"node:{node_id}:alive", ttl, "1")
    pipe.hset(f"node:{node_id}:stats", mapping={
        "cpu_used_pct": str(cpu_pct),
        "ram_used_mb": str(ram_mb),
        "job_id": job_id or ""
    })
    pipe.execute()


def get_alive_node_ids():
    """
    Scans the Redis keyspace for active 'alive' indicators.
    Returns a list of IDs for nodes that have checked-in recently.
    """
    r = get_redis()
    node_ids = []
    cursor = 0
    while True:
        # SCAN is used over KEYS to prevent blocking the Redis server in production

        cursor, keys = r.scan(cursor, match="node:*:alive", count=100)
        for k in keys:
            node_ids.append(k.split(":")[1])
        if cursor == 0:
            break
    return node_ids 


def get_node_stats(node_id: str) -> dict:
    """
    Retrieves the latest metric snapshot for a specific node.
    """
    r = get_redis()
    return r.hgetall(f"node:{node_id}:stats")


def push_log_line(job_id: str, line: str, max_lines: int = 1000):
    """
    Appends a new line of console output to the job's live log buffer.
    Automatically trims the buffer to 'max_lines' to prevent memory exhaustion.
    """
    r = get_redis()
    r.lpush(f"job:{job_id}:logs", line)
    r.ltrim(f"job:{job_id}:logs", 0, max_lines - 1)


def get_logs(job_id: str, count: int = 100):
    """
    Retrieves the most recent N lines of logs for a job.
    Reverses the list to restore original chronological order.
    """
    r = get_redis()
    lines = r.lrange(f"job:{job_id}:logs", 0, count - 1)
    return list(reversed(lines))
