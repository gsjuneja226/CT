# CampuShare Global Test Configuration
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import os

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://admin:secret@localhost:5432/campushare_test")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture(scope="session")
def db_conn():
    conn = psycopg2.connect(TEST_DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True

    schema_path = os.path.join(os.path.dirname(__file__), "backend", "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            with conn.cursor() as cur:
                cur.execute(f.read())

    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE results, heartbeats, jobs, nodes, users RESTART IDENTITY CASCADE")


@pytest.fixture
def r():
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    client.flushdb()


@pytest.fixture
def submitter_token(db_conn):
    from backend.services.auth_service import create_user_token
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, role) VALUES ('student@campus.edu','submitter')
            ON CONFLICT (email) DO UPDATE SET role='submitter' RETURNING id
        """)
        user_id = str(cur.fetchone()["id"])
    return create_user_token(user_id, "student@campus.edu", "submitter")


@pytest.fixture
def contributor_token(db_conn):
    from backend.services.auth_service import create_user_token
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, role) VALUES ('contrib@campus.edu','contributor')
            ON CONFLICT (email) DO UPDATE SET role='contributor' RETURNING id
        """)
        user_id = str(cur.fetchone()["id"])
    return create_user_token(user_id, "contrib@campus.edu", "contributor")


@pytest.fixture
def node_token(db_conn, contributor_token):
    from backend.services.auth_service import create_node_token
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (email, role) VALUES ('contrib@campus.edu','contributor')
            ON CONFLICT (email) DO NOTHING RETURNING id
        """)
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT id FROM users WHERE email='contrib@campus.edu'")
            row = cur.fetchone()
        user_id = str(row["id"])
        cur.execute("""
            INSERT INTO nodes (user_id, hostname, total_cpu, total_ram_mb, has_gpu)
            VALUES (%s,'testnode',4,8192,false) RETURNING id
        """, (user_id,))
        node_id = str(cur.fetchone()["id"])
    return create_node_token(node_id)
