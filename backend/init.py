"""
Database Schema Initialization
==============================
Bootstraps the PostgreSQL environment by creating necessary tables, 
extensions, and indices. This script is designed to be idempotent 
(using IF NOT EXISTS) for safe re-execution.

Tables:
- users: Identity management for researchers and contributors.
- jobs: Workload tracking (including sharding/parent-child relationships).
- nodes: Hardware inventory and capability registration.
- heartbeats: Real-time telemetry and health monitoring.
- results: Persistent storage mapping for completed workloads.
"""

import psycopg2
import os

# Extraction of connection string from the environment.
# Target: Production PostgreSQL (Neon/Render/RDS) or local dev.
db_url = os.getenv("DATABASE_URL")

schema = """
-- Enable cryptographic primitives for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Table: users
-- Core identity partition for the platform.
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('submitter','contributor')),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Table: jobs
-- Tracks computational requests, their resource requirements, and status lifecycle.
CREATE TABLE IF NOT EXISTS jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
    
    -- Self-referential link for sharding (parent_id points to the master job)
    parent_id        UUID REFERENCES jobs(id) ON DELETE CASCADE,
    chunk_index      INT DEFAULT NULL,
    
    -- Execution parameters
    image            TEXT NOT NULL,
    cpu              FLOAT NOT NULL DEFAULT 1.0,
    memory           TEXT NOT NULL DEFAULT '2g',
    gpu              BOOLEAN DEFAULT FALSE,
    timeout_seconds  INT DEFAULT 3600,
    
    -- State machine: queued -> dispatched -> running -> done|failed|expired
    status           TEXT DEFAULT 'queued'
                     CHECK (status IN ('queued','dispatched','running',
                       'done','failed','expired','partial')),
    queue_reason     TEXT DEFAULT NULL,
    
    -- Node assignment (if status is active)
    node_id          UUID DEFAULT NULL,
    retry_count      INT DEFAULT 0,
    
    -- Artifact storage
    result_path      TEXT DEFAULT NULL,
    
    -- Parallelization metadata
    split_strategy   TEXT DEFAULT NULL,
    total_chunks     INT DEFAULT NULL,
    
    -- Custom workloads
    env_vars         JSONB DEFAULT '{}',
    
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

-- Table: nodes
-- Inventory of active hardware contributors.
CREATE TABLE IF NOT EXISTS nodes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
    hostname      TEXT NOT NULL,
    total_cpu     INT NOT NULL,
    total_ram_mb  INT NOT NULL,
    has_gpu       BOOLEAN DEFAULT FALSE,
    gpu_model     TEXT DEFAULT NULL,
    gpu_vram_mb   INT DEFAULT NULL,
    registered_at TIMESTAMP DEFAULT NOW()
);

-- Table: heartbeats
-- Time-series telemetry for system observability and alive-check.
CREATE TABLE IF NOT EXISTS heartbeats (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id       UUID REFERENCES nodes(id) ON DELETE CASCADE,
    job_id        UUID REFERENCES jobs(id) ON DELETE SET NULL,
    cpu_used_pct  FLOAT,
    ram_used_mb   INT,
    status        TEXT,
    recorded_at   TIMESTAMP DEFAULT NOW()
);

-- Table: results
-- Immutable record of specific job completions.
CREATE TABLE IF NOT EXISTS results (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID REFERENCES jobs(id) ON DELETE CASCADE UNIQUE,
    file_path   TEXT NOT NULL,
    exit_code   INT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Indices for performance optimization on common foreign key and status filters.
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user   ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

print(f"[init] Connecting to database at {db_url[:15]}...")
try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    print("[init] Connected! Executing schema definition...")
    cur.execute(schema)
    conn.commit()
    cur.close()
    conn.close()
    print("[init] SUCCESS — Grid schema is synchronized.")
except Exception as e:
    print(f"[init] FAILED: {e}")
