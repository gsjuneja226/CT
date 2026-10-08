"""
Database Connectivity Diagnostic Tool
====================================
A standalone script to verify PostgreSQL connectivity and inspect registered 
hardware without booting the full FastAPI application.

Logic:
1. Manually parses '.env' for DATABASE_URL (bypassing Pydantic for isolation).
2. Establishes a direct psycopg2 connection.
3. Prints a summary of the most recently updated compute nodes.
"""

import os
import psycopg2
from urllib.parse import urlparse

# Step 1: Bootstrap environment manually
db_url = None
if os.path.exists(".env"):
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    # Extract the URI string from the key=value pair
                    db_url = line.strip().split("=", 1)[1].strip("'\"")
                    break
    except Exception as e:
        print(f"[Error] Failed to read .env: {e}")
        exit(1)
else:
    print("[Error] .env file not found in current directory.")
    exit(1)

if not db_url:
    print("[Error] DATABASE_URL not found in .env")
    exit(1)

# Step 2: Establish raw connection
try:
    print("--- LIVE GRID STATUS: REGISTERED NODES ---")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Step 3: Inspect node inventory
    cur.execute("""
        SELECT id, hostname, has_gpu, total_ram_mb 
        FROM nodes 
        ORDER BY registered_at DESC 
        LIMIT 5
    """)
    
    rows = cur.fetchall()
    if not rows:
        print("No nodes found in registry.")
    else:
        for row in rows:
            # Display formatted summary of the 5 most recently active nodes
            print(f"ID: {str(row[0])[:8]}... | Host: {row[1]:<15} | GPU: {str(row[2]):<5} | RAM: {row[3]}MB")
            
    cur.close()
    conn.close()
    print("--- DIAGNOSTIC COMPLETE ---")

except Exception as e:
    print(f"[Error] Database connection failed: {e}")
