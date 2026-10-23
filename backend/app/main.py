"""FastAPI application.

  GET  /api/health         liveness + DB check
  GET  /api/schema         introspected schema (add ?prompt=true for the LLM view)
  POST /api/sql/validate   dry-run the SQL guard
  POST /api/sql/execute    guard + read-only execution (manual SQL)
  POST /api/ask            natural language question -> SQL -> result (with repair loop)

Part 4 adds chart specs; Part 5 adds written explanations.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import psycopg
import psycopg_pool.errors
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db, pipeline, services
from .config import get_settings
from .llm import LLMClient, LLMError, LLMNotConfigured, get_llm
from .schema import get_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close_pool()


app = FastAPI(title="AI Data Analyst", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(LLMNotConfigured)
async def _llm_not_configured(_, e: LLMNotConfigured):
    return JSONResponse(status_code=503, content={"detail": {"stage": "llm", "code": "not_configured", "message": str(e)}})


@app.exception_handler(LLMError)
async def _llm_error(_, e: LLMError):
    return JSONResponse(status_code=502, content={"detail": {"stage": "llm", "code": "llm_error", "message": str(e)}})


@app.exception_handler(psycopg_pool.errors.PoolTimeout)
@app.exception_handler(psycopg_pool.errors.PoolClosed)
@app.exception_handler(psycopg.OperationalError)
async def _db_unavailable(_, e: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": {"stage": "database", "code": "unavailable",
                            "message": "The database is unreachable. Check that Postgres is running."}},
    )


# ---------------------------------------------------------------- models

class SQLRequest(BaseModel):
    sql: str = Field(..., max_length=10_000, examples=["SELECT status, COUNT(*) FROM orders GROUP BY status"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000,
                          examples=["Which products had the biggest revenue decline last quarter?"])


class AttemptOut(BaseModel):
    number: int
    sql: str | None
    outcome: str
    detail: str | None = None


class AskResponse(BaseModel):
    status: str                      # ok | failed | cannot_answer
    question: str
    sql: str | None = None
    tables: list[str] = []
    columns: list[dict[str, str]] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: float | None = None
    warnings: list[str] = []
    attempts: list[AttemptOut] = []
    message: str | None = None
    model: str | None = None


# ---------------------------------------------------------------- endpoints

@app.get("/api/health")
def health():
    ok = db.ping()
    return {"status": "ok" if ok else "degraded", "database": ok}


@app.get("/api/schema")
def schema(prompt: bool = False):
    """Database schema as JSON. With ?prompt=true also returns the LLM-ready text."""
    s = get_schema()
    body = s.to_dict()
    if prompt:
        body["prompt"] = s.to_prompt()
    return body


def _http_error(f: services.QueryFailure) -> HTTPException:
    return HTTPException(status_code=f.http_status, detail={"stage": f.stage, "code": f.code, "message": f.message})


@app.post("/api/sql/validate")
def validate(req: SQLRequest):
    """Dry-run the guard: shows the normalized SQL that *would* be executed."""
    try:
        r = services.guard_sql(req.sql)
    except services.QueryFailure as f:
        raise _http_error(f)
    return {"sql": r.sql, "tables": r.tables, "effective_limit": r.effective_limit, "warnings": r.warnings}


@app.post("/api/sql/execute")
def execute(req: SQLRequest):
    """Validate, then execute read-only with a timeout and row cap."""
    try:
        r, result = services.run_sql(req.sql)
    except services.QueryFailure as f:
        raise _http_error(f)
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


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, llm: LLMClient = Depends(get_llm)):
    """Natural language -> SQL -> guarded execution -> validated result.

    Always returns HTTP 200 for the pipeline's own outcomes (``status`` says ok / failed /
    cannot_answer) so a client can render the full attempt trace either way.
    """
    out = pipeline.answer_question(req.question.strip(), llm)
    res = out.result
    return AskResponse(
        status=out.status,
        question=out.question,
        sql=out.sql,
        tables=out.tables,
        columns=res.columns if res else [],
        rows=res.rows if res else [],
        row_count=res.row_count if res else 0,
        truncated=res.truncated if res else False,
        elapsed_ms=res.elapsed_ms if res else None,
        warnings=out.warnings,
        attempts=[AttemptOut(**vars(a)) for a in out.attempts],
        message=out.message,
        model=getattr(llm, "model", None),
    )
