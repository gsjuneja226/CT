"""
CampuShare: Redis Connectivity Diagnostic
========================================
A standalone script to verify the connection between a worker node 
and the Redis message broker. 

Features:
- .env Awareness: Loads configuration from the agent's environment file.
- SSL Verification: Automatically handles 'rediss://' schemes with 
  disabled certificate verification for cloud providers (e.g., Upstash).
- Health Check: Performs a raw PING command to verify full duplex communication.
"""

import os
import redis
import ssl
from dotenv import load_dotenv

# Load configuration from the agent's local environment
env_path = os.path.join("agent", ".env")
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"[diag] Loaded settings from {env_path}")
else:
    print(f"[diag] ERROR: {env_path} not found. Ensure you are running from the project root.")
    exit(1)

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    print("[diag] ERROR: REDIS_URL not found in environment or .env file.")
    exit(1)


# Security: Only print the endpoints of the URL to avoid leaking credentials in logs
print(f"[diag] Testing Redis connection to: {REDIS_URL[:20]}...{REDIS_URL[-20:]}")

try:
    kwargs = {"decode_responses": True}
    
    # Handle secure redis connections (TLS/SSL)
    if REDIS_URL.startswith("rediss://"):
        # Note: We disable certificate verification to support self-signed 
        # or simplified cloud provider certificates.
        kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
    
    r = redis.from_url(REDIS_URL, **kwargs)
    print("[diag] Pinging Redis...")
    
    response = r.ping()
    print(f"[diag] Success! Server responded with: {response}")
    
except Exception as e:
    print(f"[diag] Critical failure during Redis handshake: {e}")
