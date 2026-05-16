import os
import queue
import pymysql
from pymysql.connections import Connection

# Configuration – can be overridden via env vars
_DB_HOST = os.getenv("DB_HOST", "database-1.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com")
_DB_PORT = int(os.getenv("DB_PORT", "3306"))
_DB_NAME = os.getenv("DB_NAME", "bug_daddy")
_DB_USER = os.getenv("DB_USER", "bug_daddy")
_DB_PASSWORD = os.getenv("DB_PASSWORD", "bug_daddy")

# Size of the pool – keep well below the RDS Proxy max_client_connections (e.g., 1500)
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))

# Initialise a thread‑safe queue that will hold live connections
_connection_pool: queue.Queue[Connection] = queue.Queue(maxsize=_POOL_SIZE)

def _create_connection() -> Connection:
    """Create a new pymysql connection using the same parameters as the original get_db()."""
    return pymysql.connect(
        host=_DB_HOST,
        port=_DB_PORT,
        user=_DB_USER,
        password=_DB_PASSWORD,
        database=_DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
    )

def init_pool() -> None:
    """Populate the pool at import time. If the pool is already filled, this is a no‑op."""
    while not _connection_pool.full():
        _connection_pool.put(_create_connection())

# Initialise once when the module is imported
init_pool()

def acquire() -> Connection:
    """Grab a connection from the pool, blocking if none are currently free."""
    conn = _connection_pool.get()
    # Ensure the connection is alive – pymysql will reconnect if needed
    if not conn.open:
        conn.ping(reconnect=True)
    return conn

def release(conn: Connection) -> None:
    """Return a connection to the pool for reuse."""
    if conn:
        _connection_pool.put(conn)
