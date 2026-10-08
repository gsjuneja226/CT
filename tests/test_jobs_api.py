import pytest
import json


def test_submit_job_writes_to_db(db_conn, r):
    from backend.services.queue import push_job, pop_job
    job = {"id": "test-job-1", "image": "img:v1", "cpu": 1.0, "memory": "2g", "gpu": False}
    push_job(job)
    popped = pop_job()
    assert popped is not None
    assert popped["id"] == "test-job-1"


def test_job_appears_in_redis_queue_after_push(r):
    from backend.services.queue import push_job
    job = {"id": "q-test", "image": "img:v1"}
    push_job(job)
    raw = r.lpop("jobs:queue")
    assert raw is not None
    data = json.loads(raw)
    assert data["id"] == "q-test"


def test_split_job_creates_correct_number_of_chunks():
    from backend.services.splitter import compute_chunks
    chunks = compute_chunks({
        "strategy": "row_range",
        "num_chunks": 4,
        "total_rows": 100000
    })
    assert len(chunks) == 4
    assert all("CHUNK_INDEX" in c for c in chunks)


def test_split_job_children_have_correct_chunk_indices():
    from backend.services.splitter import compute_chunks
    chunks = compute_chunks({
        "strategy": "row_range",
        "num_chunks": 3,
        "total_rows": 300
    })
    indices = [int(c["CHUNK_INDEX"]) for c in chunks]
    assert indices == [0, 1, 2]


def test_get_job_owner_check(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('owner@t.com','submitter') RETURNING id")
        owner_id = str(cur.fetchone()["id"])
        cur.execute("INSERT INTO users (email, role) VALUES ('other@t.com','submitter') RETURNING id")
        other_id = str(cur.fetchone()["id"])
        cur.execute("""
            INSERT INTO jobs (user_id, image, cpu, memory, status)
            VALUES (%s,'img:v1',1,'2g','queued') RETURNING id
        """, (owner_id,))
        job_id = str(cur.fetchone()["id"])

    with db_conn.cursor() as cur:
        cur.execute("SELECT user_id FROM jobs WHERE id=%s", (job_id,))
        row = cur.fetchone()
        assert str(row["user_id"]) == owner_id
        assert str(row["user_id"]) != other_id


def test_node_registration_creates_node(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, role) VALUES ('contrib2@t.com','contributor') RETURNING id")
        uid = str(cur.fetchone()["id"])
        cur.execute("""
            INSERT INTO nodes (user_id, hostname, total_cpu, total_ram_mb, has_gpu)
            VALUES (%s,'myhost',4,8192,false) RETURNING id
        """, (uid,))
        node_id = str(cur.fetchone()["id"])

    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM nodes WHERE id=%s", (node_id,))
        node = cur.fetchone()
        assert node["hostname"] == "myhost"
        assert node["total_cpu"] == 4


def test_heartbeat_sets_redis_key(r):
    from backend.services.queue import set_node_alive, set_node_stats
    set_node_alive("node-abc", ttl=15)
    set_node_stats("node-abc", 50.0, 2048)
    assert r.exists("node:node-abc:alive") == 1
    stats = r.hgetall("node:node-abc:stats")
    assert float(stats["cpu_used_pct"]) == 50.0
