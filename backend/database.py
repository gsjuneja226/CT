"""
Database Connectivity & Transaction Management
==============================================
Abstracts raw PostgreSQL interactions using a thread-safe connection pool.
Provides context managers and convenience wrappers for common CRUD operations.
"""

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import settings

# Global connection pool singleton

pool: ThreadedConnectionPool = None


def init_db():
    """
    Initializes the cross-thread connection pool using the project DSN.
    Configured with a minimum of 2 and a maximum of 20 concurrent connections.
    """
    global pool
    pool = ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=settings.DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def get_pool():
    """
    Lazy-loader for the connection pool.
    """
    global pool
    if pool is None:
        init_db()
    return pool


@contextmanager
def get_db():
    """
    Context manager for safe database transactions.
    Automatically commits on success or rolls back on exception.
    Always returns the connection to the pool upon completion.
    """
    conn = get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        get_pool().putconn(conn)


def execute(query: str, params=None):
    """
    Performs a non-returning DML operation (INSERT, UPDATE, DELETE).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def fetchone(query: str, params=None):
    """
    Retrieves a single record based on the provided query.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query: str, params=None):
    """
    Retrieves all records matching the query criteria.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetchone_returning(query: str, params=None):
    """
    Executes a query and returns the single resulting record.
    Useful for INSERT ... RETURNING id.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
