"""
Node & Telemetry Domain Schemas
===============================
Defines the Pydantic models for agent-orchestration. These schemas 
standardize the hardware reports and real-time metric streams sent 
by compute nodes to the central scheduler.
"""

from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class NodeRegister(BaseModel):
    """
    Hardware specification report sent by a node during the 'register' phase.
    """
    hostname: str
    total_cpu: int
    total_ram_mb: int
    has_gpu: bool = False
    gpu_model: Optional[str] = None
    gpu_vram_mb: Optional[int] = None


class NodeResponse(BaseModel):
    """
    Secure credentials returned to a successfully registered node.
    """
    node_id: str
    node_token: str


class HeartbeatPayload(BaseModel):
    """
    Telemetery packet sent periodically (heartbeat) by an active agent.
    """
    node_id: str
    # Present if the machine is currently executing a workload
    job_id: Optional[str] = None
    cpu_used_pct: float
    ram_used_mb: int
    status: str = "idle"  # 'idle' or 'running'
