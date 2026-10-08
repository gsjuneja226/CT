"""
Job Domain Schemas
==================
Defines the Pydantic models for validating job-related requests and serializing 
responses. These schemas ensure type safety between the API and the React frontend.
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class SplitBy(BaseModel):
    """
    Configuration for parallel workload sharding.
    """
    strategy: str  # row_range | file_list | param_grid
    num_chunks: int
    # Strategy-specific data
    total_rows: Optional[int] = None
    files: Optional[List[str]] = None
    params: Optional[List[Dict[str, Any]]] = None


class JobCreate(BaseModel):
    """
    Schema for new job submissions from the 'Submit Job' form.
    """
    image: str
    cpu: float = 1.0
    memory: str = "2g"
    gpu: bool = False
    timeout_seconds: int = 3600
    split_by: Optional[SplitBy] = None


class JobResponse(BaseModel):
    """
    Compact response confirming job acceptance.
    """
    job_id: str
    status: str
    is_split: bool = False
    total_chunks: Optional[int] = None


class ChunkStatus(BaseModel):
    """
    Status summary for an individual shard of a parent job.
    """
    chunk_index: int
    status: str
    node_id: Optional[str] = None


class JobDetail(BaseModel):
    """
    Deep-view schema for the specific job details page.
    Includes full metadata, history, and child chunks.
    """
    id: str
    user_id: str
    image: str
    cpu: float
    memory: str
    gpu: bool
    status: str
    queue_reason: Optional[str] = None
    node_id: Optional[str] = None
    retry_count: int
    split_strategy: Optional[str] = None
    total_chunks: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    chunks: Optional[List[ChunkStatus]] = None
