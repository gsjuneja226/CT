"""
GPU Detection Utility
====================
Detects the presence and specifications of NVIDIA GPUs on the host system.
Uses the nvidia-smi command-line tool.
"""

import subprocess


def detect_gpu() -> dict:
    """
    Attempts to detect a local GPU using the 'nvidia-smi' utility.
    
    Queries the GPU for its name and total VRAM. If the command fails or 
    nvidia-smi is not found, returns a dictionary indicating no GPU is 
    available.
    
    Returns:
        dict: {
            "available": bool,
            "model": str or None,
            "vram_mb": int or None
        }
    """
    try:
        # Querying NVIDIA SMI for GPU name and total memory in MB
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode().strip()
        
        parts = out.split(", ")
        if len(parts) >= 2:
            name = parts[0].strip()
            vram = int(parts[1].strip())
            return {"available": True, "model": name, "vram_mb": vram}
    except Exception:
        # Failure usually means nvidia-smi is not installed or no drivers present
        pass
        
    return {"available": False, "model": None, "vram_mb": None}
