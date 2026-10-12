"""
Job Sharding & Workload Partitioning Service
============================================
Divides a single large computational request into smaller, independent 
chunks that can be executed in parallel across the grid.

Supported Strategies:
- row_range: Splits a large dataset by numeric indices (e.g., lines in a CSV).
- param_grid: Dispatches identical code with different input parameter sets.
- file_list: Distributes a batch of files evenly across available nodes.
"""

import json
from typing import List, Dict


def compute_chunks(split_by: dict) -> List[Dict[str, str]]:
    """
    Generates a list of environment variable sets (one per chunk) 
    based on the chosen partitioning strategy.
    
    Args:
        split_by (dict): Configuration containing 'strategy', 'num_chunks', 
                         and strategy-specific data.
                         
    Returns:
        List[Dict]: A list of metadata dictionaries to be injected into 
                    the worker containers.
    """
    strategy = split_by.get("strategy")
    n = split_by.get("num_chunks", 1)

    # Strategy 1: Distributed or Data Parallelism (Numeric Ranges)
    if strategy in ("distributed", "concentrated", "row_range") or not strategy:
        total = split_by.get("total_rows")
        if total is None:
            total = 10000
        size = max(1, total // n)
        chunks = []
        for i in range(n):
            start = i * size
            end = (i + 1) * size if i < n - 1 else total
            chunks.append({
                "CHUNK_START": str(start),
                "CHUNK_END": str(end),
                "CHUNK_INDEX": str(i),
                "CHUNK_TOTAL": str(n)
            })
        return chunks

    # Strategy 2: Task Parallelism (Parameter Sweeps)
    if strategy == "param_grid":
        params = split_by.get("params") or []
        if not params:
            return [{"CHUNK_INDEX": str(i), "CHUNK_TOTAL": str(n)} for i in range(n)]
        return [
            {
                "PARAMS": json.dumps(p),
                "CHUNK_INDEX": str(i),
                "CHUNK_TOTAL": str(len(params))
            }
            for i, p in enumerate(params)
        ]

    # Strategy 3: Batch Parallelism (File Distribution)
    if strategy == "file_list":
        files = split_by.get("files") or []
        file_chunks = [files[i::n] for i in range(n)]
        return [
            {
                "CHUNK_FILES": json.dumps(c),
                "CHUNK_INDEX": str(i),
                "CHUNK_TOTAL": str(n)
            }
            for i, c in enumerate(file_chunks)
        ]

    raise ValueError(f"Unknown workload partitioning strategy: {strategy}")
