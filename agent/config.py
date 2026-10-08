"""
Agent Configuration Manager
===========================
Loads environment variables from .env and provides a utility to persist 
dynamically generated settings (like NODE_ID) back to the .env file.
"""

import os
from dotenv import load_dotenv

# Load local .env file relative to this script
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"[config] Loaded agent settings from {env_path}")
else:
    print(f"[config] WARNING: {env_path} not found. Using defaults.")

# Central scheduler URL (where the agent registers and sends heartbeats)
SCHEDULER_URL = os.getenv("SCHEDULER_URL", "http://localhost:8000").rstrip("/")

# Unique node identifier and authentication token (assigned by scheduler)
NODE_ID = os.getenv("NODE_ID", "")
NODE_TOKEN = os.getenv("NODE_TOKEN", "")

# Personal access token for the user running the agent (required for registration)
USER_TOKEN = os.getenv("USER_TOKEN", "")

# Redis connection string for job polling
# Using 127.0.0.1 instead of localhost for local dev to avoid Windows IPv6 issues
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Docker registry used for pulling job images
DOCKER_REGISTRY = os.getenv("DOCKER_REGISTRY", "localhost:5000")

# Path to the .env file for persistence
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def save_to_env(key: str, value: str):
    """
    Persists a key-value pair into the .env file.
    
    If the key already exists, its value is updated. If not, a new line 
    is appended to the file. Also updates the current process's environment.
    
    Args:
        key (str): The configuration key (e.g., 'NODE_ID').
        value (str): The value to persist.
    """
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    os.environ[key] = value
