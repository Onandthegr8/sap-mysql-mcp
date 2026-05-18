"""
Database layer: MySQL connection pool + async query/write helpers.

The pool is lazily created on first use (double-checked lock) so the module
can be imported safely before the event loop starts.

Auto-instrumentation: every execute_write() call is automatically logged to
activity_log (table, SQL statement, duration). Writes to activity_log itself
are skipped to avoid infinite recursion.
"""

import asyncio
import logging
import re
import time
import uuid
from typing import Any

import mysql.connector
from mysql.connector import pooling
from mysql.connector import Error as MySQLError

logger = logging.getLogger(__name__)

_pool: pooling.MySQLConnectionPool | None = None
_init_lock = asyncio.Lock()   # Python 3.10+ locks are loop-independent

# One token per server run — all auto-logged writes share this session ID.
SERVER_SESSION_TOKEN = uuid.uuid4().hex[:16]


# ── Pool lifecycle ──────────────────────────────────────────────────────────

def _create_pool_sync() -> pooling.MySQLConnectionPool:
    from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_POOL_SIZE
    return pooling.MySQLConnectionPool(
        pool_name="sap_erp_pool",
        pool_size=DB_POOL_SIZE,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        autocommit=True,
        connection_timeout=30,
        use_unicode=True,
        charset="utf8mb4",
    )


async def initialize_pool() -> None:
    """Create the connection pool (idempotent — safe to call multiple times)."""
    global _pool
    if _pool is not None:
        return
    async with _init_lock:
        if _pool is not None:          # Re-check after acquiring lock
            return
        from config import DB_HOST, DB_NAME, DB_POOL_SIZE
        logger.info(f"Creating DB pool ({DB_POOL_SIZE} connections) -> {DB_HOST}/{DB_NAME}")
        try:
            _pool = await asyncio.to_thread(_create_pool_sync)
            logger.info("Database pool ready.")
        except MySQLError as exc:
            logger.error(f"Failed to create DB pool: {exc}")
            raise


async def close_pool() -> None:
    """Release the pool reference (connections are returned to pool on GC)."""
    global _pool
    _pool = None
    logger.info("Database pool released.")


# ── Auto-instrumentation helpers ────────────────────────────────────────────

_TABLE_RE = re.compile(
    r'(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+`?(\w+)`?',
    re.IGNORECASE,
)
_UPDATE_FIELD_RE = re.compile(r'SET\s+`?(\w+)`?\s*=',        re.IGNORECASE)
_UPDATE_WHERE_RE = re.compile(r'\bWHERE\b(.+)$', re.IGNORECASE | re.DOTALL)
_INSERT_COLS_RE  = re.compile(r'INSERT\s+INTO\s+\w+\s*\(([^)]+)\)', re.IGNORECASE)


def _extract_table(sql: str) -> str:
    m = _TABLE_RE.search(sql)
    return m.group(1).lower() if m else "unknown"


def _fetch_before_value_sync(table: str, field: str, sql: str, params: tuple):
    """SELECT the current value of `field` from `table` using the WHERE clause."""
    where_m = _UPDATE_WHERE_RE.search(sql)
    if not where_m or _pool is None:
        return None
    where_clause = where_m.group(1).strip()
    # params before WHERE are the SET values; params after are the WHERE values
    set_count = sql[:sql.upper().find('WHERE')].count('%s')
    where_params = params[set_count:]
    try:
        conn = _pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT `{field}` FROM `{table}` WHERE {where_clause}",
                where_params,
            )
            row = cursor.fetchone()
            cursor.close()
            return str(row[field]) if row and field in row else None
        finally:
            conn.close()
    except Exception:
        return None


def _parse_change_info(sql: str, params: tuple):
    """
    Return (field_changed, value_before, value_after) by analysing the SQL.
    value_before is fetched from DB for UPDATE statements (pre-change snapshot).
    """
    sql_stripped = sql.strip()
    upper = sql_stripped.upper()
    table = _extract_table(sql_stripped)

    if upper.startswith("UPDATE"):
        fm = _UPDATE_FIELD_RE.search(sql_stripped)
        field = fm.group(1) if fm else "unknown"
        value_after  = str(params[0]) if params else None
        value_before = _fetch_before_value_sync(table, field, sql_stripped, params)
        return field, value_before, value_after

    elif upper.startswith("INSERT"):
        cm = _INSERT_COLS_RE.search(sql_stripped)
        if cm:
            cols = [c.strip().strip('`') for c in cm.group(1).split(',')]
            field = ", ".join(cols[:3])          # first 3 column names
        else:
            field = "new_record"
        value_after = str(params[:3]) if params else None
        return field, None, value_after

    elif upper.startswith("DELETE"):
        return "deleted_record", str(params) if params else None, None

    return None, None, None


def _auto_log_sync(sql: str, params: tuple, duration_ms: float) -> None:
    """Insert one audit row into activity_log. Never raises on failure."""
    table = _extract_table(sql)
    if table in ("activity_log", "unknown"):
        return
    if _pool is None:
        return
    field_changed, value_before, value_after = _parse_change_info(sql, params)
    try:
        conn = _pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO activity_log
                   (token_id, login_time, logout_time, user_id,
                    affected_table, command_statement, duration,
                    field_changed, value_before, value_after)
                   VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s)""",
                (
                    SERVER_SESSION_TOKEN,
                    "claude",
                    table,
                    sql.strip()[:500],
                    round(duration_ms, 3),
                    field_changed,
                    value_before,
                    value_after,
                ),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Auto-log write failed (non-fatal): {exc}")


# ── Internal sync helpers (run in thread pool) ──────────────────────────────

def _query_sync(sql: str, params: tuple) -> list[dict[str, Any]]:
    if _pool is None:
        raise RuntimeError("DB pool not initialised. Call initialize_pool() first.")
    conn = _pool.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        results = cursor.fetchall()
        cursor.close()
        return results
    except MySQLError as exc:
        logger.error(f"Query error | SQL: {sql} | Params: {params} | {exc}")
        raise
    finally:
        conn.close()


def _write_sync(sql: str, params: tuple) -> int:
    if _pool is None:
        raise RuntimeError("DB pool not initialised. Call initialize_pool() first.")
    conn = _pool.get_connection()
    try:
        t0 = time.perf_counter()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        affected = cursor.rowcount
        duration_ms = (time.perf_counter() - t0) * 1000
        cursor.close()
        _auto_log_sync(sql, params, duration_ms)   # auto-instrument every write
        return affected
    except MySQLError as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error(f"Write error | SQL: {sql} | Params: {params} | {exc}")
        raise
    finally:
        conn.close()


# ── Public async API ────────────────────────────────────────────────────────

async def execute_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return results as a list of dicts. Auto-inits pool."""
    global _pool
    if _pool is None:
        await initialize_pool()
    return await asyncio.to_thread(_query_sync, sql, params)


async def execute_write(sql: str, params: tuple = ()) -> int:
    """Run INSERT/UPDATE/DELETE and return affected-row count. Auto-inits pool."""
    global _pool
    if _pool is None:
        await initialize_pool()
    return await asyncio.to_thread(_write_sync, sql, params)
