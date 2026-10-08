"""
CampuShare: API Connectivity Diagnostic
=======================================
A standalone script to verify the reachability of the central scheduler 
API from a worker node or development machine. 

Usage:
  This script performs a raw POST to the node registration endpoint.
  It is used primarily to debug 404 (Not Found) errors or network isolation issues.
"""

import requests

# Target endpoint for connectivity verification
url = "http://localhost:8000/nodes/register"
print(f"[diag] Testing POST to {url}...")

try:
    # Note: This request is deliberately malformed (missing body/auth).
    # We are looking for a 401/422/400 response, NOT a 404 or Timeout.
    resp = requests.post(url, timeout=10)
    print(f"[diag] Status: {resp.status_code}")
    print(f"[diag] Body: {resp.text[:200]}")
except Exception as e:
    print(f"[diag] Connection Error: {e}")
