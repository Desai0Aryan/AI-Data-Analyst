"""Connection pool and safe query execution.

Safety is layered: the SQL guard (sql_guard.py) is the first line, and this module
adds the second and third: a read-only transaction and a statement timeout. The
database role itself (analyst_ro) is the fourth: it only has SELECT.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from decimal import Decimal
from functools import lru_cache
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from .config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    settings = get_settings()
    pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": False},
    )
    try:
        pool.open(wait=True, timeout=5)
    except Exception:
        pool.close()          # don't leak the pool's background threads on a failed start
        raise
    return pool


def close_pool() -> None:
    if get_pool.cache_info().currsize:
        get_pool().close()
        get_pool.cache_clear()


@dataclass
class QueryResult:
    columns: list[dict[str, str]]   # [{"name": ..., "type": ...}]
    rows: list[list[Any]]           # JSON-safe values
    row_count: int
    truncated: bool                 # True if the row cap cut the result short
    elapsed_ms: float


def _json_safe(value: Any) -> Any:
    """Convert DB values into JSON-friendly ones. NULL stays None."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        # Integral decimals become ints, others floats (2dp money is exact enough for charts).
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    return str(value)


def execute_readonly(sql: str, *, effective_limit: int, limit_applied: bool) -> QueryResult:
    """Run already-validated SQL inside a read-only transaction with a timeout."""
    settings = get_settings()
    pool = get_pool()
    start = time.perf_counter()

    with pool.connection() as conn:
        conn.read_only = True  # BEGIN READ ONLY
        try:
            with conn.cursor() as cur:
                # set_config(..., is_local=true) == SET LOCAL, but parameterizable.
                cur.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (str(settings.statement_timeout_ms),),
                )
                cur.execute(sql)
                columns = [
                    {
                        "name": col.name,
                        "type": (conn.adapters.types.get(col.type_code).name
                                 if conn.adapters.types.get(col.type_code) else "unknown"),
                    }
                    for col in (cur.description or [])
                ]
                rows = [[_json_safe(v) for v in row] for row in cur.fetchall()]
        finally:
            conn.rollback()  # never commit anything, ever

    elapsed = (time.perf_counter() - start) * 1000
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=limit_applied and len(rows) >= effective_limit,
        elapsed_ms=round(elapsed, 2),
    )


def ping() -> bool:
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


DatabaseError = psycopg.Error
