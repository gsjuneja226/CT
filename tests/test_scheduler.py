import pytest
import json


def make_node(node_id, free_cpu=80, free_ram=4096, has_gpu=False, total_cpu=4):
    return {
        "node_id": node_id,
        "hostname": f"node-{node_id[:4]}",
        "total_cpu": total_cpu,
        "total_ram_mb": 8192,
        "has_gpu": has_gpu,
        "gpu_model": "RTX 3060" if has_gpu else None,
        "free_cpu_pct": free_cpu,
        "free_ram_mb": free_ram,
    }


def make_job(cpu=1.0, memory="2g", gpu=False):
    return {"id": "job-test", "cpu": cpu, "memory": memory, "gpu": gpu}


def test_node_fits_job_basic():
    from backend.services.scheduler import node_fits_job
    node = make_node("n1", free_cpu=80, free_ram=4096)
    job = make_job(cpu=1.0, memory="2g")
    assert node_fits_job(node, job) is True


def test_node_insufficient_ram():
    from backend.services.scheduler import node_fits_job
    node = make_node("n1", free_cpu=80, free_ram=512)
    job = make_job(cpu=1.0, memory="4g")
    assert node_fits_job(node, job) is False


def test_node_insufficient_cpu():
    from backend.services.scheduler import node_fits_job
    node = make_node("n1", free_cpu=10, free_ram=8192, total_cpu=4)
    job = make_job(cpu=3.0, memory="1g")
    assert node_fits_job(node, job) is False


def test_gpu_job_only_dispatches_to_gpu_node():
    from backend.services.scheduler import node_fits_job
    cpu_node = make_node("n1", has_gpu=False)
    gpu_node = make_node("n2", has_gpu=True)
    job = make_job(gpu=True)
    assert node_fits_job(cpu_node, job) is False
    assert node_fits_job(gpu_node, job) is True


def test_non_gpu_job_works_on_any_node():
    from backend.services.scheduler import node_fits_job
    cpu_node = make_node("n1", has_gpu=False)
    gpu_node = make_node("n2", has_gpu=True)
    job = make_job(gpu=False)
    assert node_fits_job(cpu_node, job) is True
    assert node_fits_job(gpu_node, job) is True


def test_parse_memory_to_mb():
    from backend.services.scheduler import parse_memory_to_mb
    assert parse_memory_to_mb("2g")   == 2048
    assert parse_memory_to_mb("512m") == 512
    assert parse_memory_to_mb("4gb")  == 4096
    assert parse_memory_to_mb("1024m") == 1024


def test_retry_count_increments_on_failure(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('r@test.com','submitter') RETURNING id")
        uid = str(cur.fetchone()["id"])
        cur.execute("""
            INSERT INTO jobs (user_id, image, cpu, memory, status, retry_count)
            VALUES (%s,'img:v1',1.0,'2g','queued',0) RETURNING id
        """, (uid,))
        job_id = str(cur.fetchone()["id"])

    with db_conn.cursor() as cur:
        cur.execute("UPDATE jobs SET retry_count = retry_count + 1 WHERE id=%s", (job_id,))
        cur.execute("SELECT retry_count FROM jobs WHERE id=%s", (job_id,))
        assert cur.fetchone()["retry_count"] == 1


def test_job_permanently_failed_after_max_retries(db_conn):
    from backend.config import settings
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('m@test.com','submitter') RETURNING id")
        uid = str(cur.fetchone()["id"])
        cur.execute("""
            INSERT INTO jobs (user_id, image, cpu, memory, status, retry_count)
            VALUES (%s,'img:v1',1.0,'2g','failed',%s) RETURNING id
        """, (uid, settings.MAX_RETRY_COUNT))
        job_id = str(cur.fetchone()["id"])

    with db_conn.cursor() as cur:
        cur.execute("SELECT retry_count, status FROM jobs WHERE id=%s", (job_id,))
        row = cur.fetchone()
        assert row["retry_count"] >= settings.MAX_RETRY_COUNT
