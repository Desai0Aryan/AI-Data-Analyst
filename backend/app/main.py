"""FastAPI application: schema, SQL validation and safe execution endpoints.

Part 2 adds POST /api/ask (natural language -> SQL -> result -> explanation).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import psycopg.errors
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db
from .config import get_settings
from .schema import get_schema
from .sql_guard import SQLGuardError, validate_sql


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close_pool()


app = FastAPI(title="AI Data Analyst", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SQLRequest(BaseModel):
    sql: str = Field(..., max_length=10_000, examples=["SELECT status, COUNT(*) FROM orders GROUP BY status"])


def _guard(sql: str):
    settings = get_settings()
    try:
        return validate_sql(sql, get_schema().table_names, max_rows=settings.max_rows)
    except SQLGuardError as e:
        raise HTTPException(status_code=422, detail={"stage": "guard", "code": e.code, "message": e.message})


@app.get("/api/health")
def health():
    return {"status": "ok" if db.ping() else "degraded", "database": db.ping()}


@app.get("/api/schema")
def schema(prompt: bool = False):
    """Database schema as JSON. With ?prompt=true also returns the LLM-ready text."""
    s = get_schema()
    body = s.to_dict()
    if prompt:
        body["prompt"] = s.to_prompt()
    return body


@app.post("/api/sql/validate")
def validate(req: SQLRequest):
    """Dry-run the guard: shows the normalized SQL that *would* be executed."""
    r = _guard(req.sql)
    return {"sql": r.sql, "tables": r.tables, "effective_limit": r.effective_limit, "warnings": r.warnings}


@app.post("/api/sql/execute")
def execute(req: SQLRequest):
    """Validate, then execute read-only with a timeout and row cap."""
    r = _guard(req.sql)
    try:
        result = db.execute_readonly(r.sql, effective_limit=r.effective_limit, limit_applied=r.limit_applied)
    except psycopg.errors.QueryCanceled:
        raise HTTPException(
            status_code=408,
            detail={"stage": "database", "code": "timeout",
                    "message": f"Query exceeded the {get_settings().statement_timeout_ms} ms time limit."},
        )
    except psycopg.Error as e:
        # Postgres error text (e.g. 'column "x" does not exist') is exactly what the repair loop needs.
        raise HTTPException(
            status_code=400,
            detail={"stage": "database", "code": "db_error", "message": str(e).splitlines()[0]},
        )
    return {
        "sql": r.sql,
        "tables": r.tables,
        "warnings": r.warnings,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "elapsed_ms": result.elapsed_ms,
    }
