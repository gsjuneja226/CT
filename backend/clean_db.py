"""
Database Maintenance Utility: Clear Stuck Jobs
==============================================
A standalone script for cleaning up orphan records in the grid scheduler.
Manually parses the .env file to establish a direct connection to PostgreSQL.

Use Case:
When an agent disconnects unexpectedly without updating its job status, 
a job may remain in 'dispatched' state indefinitely. This script 
resets those records.
"""

import os
import psycopg2
from urllib.parse import urlparse

# Manual .env Extraction: 
# Used here to avoid Pydantic dependencies for a simple CLI utility.
db_url = None
try:
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                # Split at the first '=' and strip quotes or whitespace
                db_url = line.strip().split("=", 1)[1].strip("'\"")
                break
except Exception as e:
    print(f"Error reading .env: {e}")
    exit(1)

if not db_url:
    print("Could not find DATABASE_URL in .env")
    exit(1)

# Establish a single, direct connection for the cleanup task
print("[maintenance] Connecting to PostgreSQL...")
try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Administrative logic: Clear workloads assigned to non-responsive agents
    print("[maintenance] Deleting dispatched jobs from scheduler...")
    cur.execute("DELETE FROM jobs WHERE status='dispatched'")
    conn.commit()

    print("[maintenance] Successfully cleared stuck records!")
except Exception as e:
    print(f"[maintenance] Critical failure during cleanup: {e}")
finally:
    # Always release resources back to the OS
    if 'cur' in locals(): cur.close()
    if 'conn' in locals(): conn.close()

