"""Shared "guard then execute" service used by /api/sql/execute and the AI pipeline.

Raising one typed exception (QueryFailure) lets callers decide what to do with a failure:
the REST endpoint turns it into an HTTP error, the repair loop turns it into LLM feedback.
"""
from __future__ import annotations

import psycopg
import psycopg.errors
import psycopg_pool.errors

from . import db
from .config import get_settings
from .schema import get_schema
from .sql_guard import GuardResult, SQLGuardError, validate_sql


class QueryFailure(Exception):
    def __init__(self, stage: str, code: str, message: str, http_status: int):
        super().__init__(message)
        self.stage = stage          # "guard" | "database"
        self.code = code
        self.message = message
        self.http_status = http_status


def _is_infrastructure_error(e: psycopg.Error) -> bool:
    """True for 'the database is unreachable/shutting down', as opposed to 'your SQL is wrong'.

    These must never be fed back to the LLM as a query problem; retrying a different query
    cannot fix a dead database.
    """
    state = e.sqlstate
    return (
        isinstance(e, (psycopg_pool.errors.PoolTimeout, psycopg_pool.errors.PoolClosed))
        or state is None                       # libpq-level failure (connection refused, ...)
        or state.startswith("08")              # connection exceptions
        or state in {"57P01", "57P02", "57P03"}  # admin/crash shutdown, cannot connect now
    )


def guard_sql(sql: str) -> GuardResult:
    try:
        return validate_sql(sql, get_schema().table_names, max_rows=get_settings().max_rows)
    except SQLGuardError as e:
        raise QueryFailure("guard", e.code, e.message, 422) from e


def execute_guarded(guarded: GuardResult) -> db.QueryResult:
    try:
        return db.execute_readonly(
            guarded.sql,
            effective_limit=guarded.effective_limit,
            limit_applied=guarded.limit_applied,
        )
    except psycopg.errors.QueryCanceled as e:
        raise QueryFailure(
            "database", "timeout",
            f"Query exceeded the {get_settings().statement_timeout_ms} ms time limit. "
            "Make it cheaper (avoid cross joins, aggregate earlier, filter sooner).",
            408,
        ) from e
    except psycopg.Error as e:
        if _is_infrastructure_error(e):
            raise    # surfaces as HTTP 503 via the API's exception handler
        # Postgres' own message ('column "x" does not exist', 'division by zero', ...) is
        # exactly the feedback an LLM needs to repair the query.
        raise QueryFailure("database", "db_error", str(e).splitlines()[0], 400) from e


def run_sql(sql: str) -> tuple[GuardResult, db.QueryResult]:
    guarded = guard_sql(sql)
    return guarded, execute_guarded(guarded)
