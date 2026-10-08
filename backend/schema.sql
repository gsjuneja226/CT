-- CampuShare PostgreSQL Schema
-- ============================
-- Bootstraps the distributed computing platform's data layer.
-- Highlights:
-- - Uses UUIDs for globally unique resource identification.
-- - Enforces referential integrity with CASCADE deletes.
-- - Optimizes telemetry lookups with composite indices.

-- Enable cryptographic functions for UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Table: users
-- Tracks researchers (submitters) and hardware contributors.
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('submitter','contributor')),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Table: jobs
-- The core workload registry. Tracks requirements (CPU, RAM, GPU) and status.
-- Supports recursive sharding via the 'parent_id' field.
CREATE TABLE IF NOT EXISTS jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
    parent_id        UUID REFERENCES jobs(id) ON DELETE CASCADE,
    chunk_index      INT DEFAULT NULL,
    image            TEXT NOT NULL,
    cpu              FLOAT NOT NULL DEFAULT 1.0,
    memory           TEXT NOT NULL DEFAULT '2g',
    gpu              BOOLEAN DEFAULT FALSE,
    timeout_seconds  INT DEFAULT 3600,
    -- Status Lifecycle: queued -> dispatched -> running -> {done, failed, expired}
    status           TEXT DEFAULT 'queued'
                     CHECK (status IN ('queued','dispatched','running',
                       'done','failed','expired','partial')),
    queue_reason     TEXT DEFAULT NULL,
    node_id          UUID DEFAULT NULL,                        -- Assigned worker node
    retry_count      INT DEFAULT 0,
    result_path      TEXT DEFAULT NULL,                        -- Path to S3 results
    split_strategy   TEXT DEFAULT NULL,                        -- How the job was divided
    total_chunks     INT DEFAULT NULL,
    env_vars         JSONB DEFAULT '{}',                       -- Runtime environment
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

-- Table: nodes
-- Inventory of available student laptops and their hardware profiles.
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
-- Transactional log of real-time node telemetry (CPU/RAM usage).
CREATE TABLE IF NOT EXISTS heartbeats (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id       UUID REFERENCES nodes(id) ON DELETE CASCADE,
    job_id        UUID REFERENCES jobs(id) ON DELETE SET NULL, -- Currently active job
    cpu_used_pct  FLOAT,
    ram_used_mb   INT,
    status        TEXT,                                        -- 'idle' or 'running'
    recorded_at   TIMESTAMP DEFAULT NOW()
);

-- Table: results
-- Final mapping for completed job artifacts.
CREATE TABLE IF NOT EXISTS results (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID REFERENCES jobs(id) ON DELETE CASCADE UNIQUE,
    file_path   TEXT NOT NULL,                                 -- Result object key
    exit_code   INT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Indexing Strategy
-- -----------------
-- Optimize lookups for job hierarchies and ownership.
CREATE INDEX IF NOT EXISTS idx_jobs_parent   ON jobs(parent_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user     ON jobs(user_id);
-- Optimize the scheduler's frequent 'status=queued' queries.
CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
-- Optimize telemetry history aggregation.
CREATE INDEX IF NOT EXISTS idx_hb_node       ON heartbeats(node_id);
CREATE INDEX IF NOT EXISTS idx_hb_recorded   ON heartbeats(recorded_at DESC);
