"""FastAPI application.

  GET  /api/health          liveness + DB check
  GET  /api/meta            runtime config for the UI (model, limits, example questions)
  GET  /api/schema          introspected schema (add ?prompt=true for the LLM view)
  POST /api/sql/validate    dry-run the SQL guard
  POST /api/sql/execute     guard + read-only execution (manual SQL), with a chart recommendation
  POST /api/ask             question -> SQL -> result (repair loop), chart + known-answer check
  POST /api/ask/stream      same, as server-sent events so the UI can show the pipeline live
  GET  /api/evals/cases     the evaluation questions
  POST /api/evals/run       run the suite against a *recorded* model (never calls a paid LLM)
  POST /api/security/probe  show each defense layer stopping an attack on its own

Part 5 adds written explanations.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import psycopg
import psycopg.errors
import psycopg_pool.errors
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db, known_answers, pipeline, services
from .charts import recommend_chart
from .config import get_settings
from .llm import LLMClient, LLMError, LLMNotConfigured, ReplayLLM, get_llm
from .schema import get_schema
from .sql_guard import SQLGuardError, validate_sql

log = logging.getLogger("analyst")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close_pool()


app = FastAPI(title="AI Data Analyst", version="0.4.0", lifespan=lifespan)
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
    raw_sql: str | None = None


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
    effective_limit: int | None = None
    limit_applied: bool = False
    pretty_sql: str | None = None
    warnings: list[str] = []
    attempts: list[AttemptOut] = []
    message: str | None = None
    model: str | None = None
    chart: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None


class EvalRunRequest(BaseModel):
    recording: Literal["reference", "naive"] = "reference"


class ProbeRequest(BaseModel):
    layer: Literal["guard", "transaction", "privileges", "timeout"]


def _build_ask_response(out: pipeline.Outcome, llm: LLMClient) -> AskResponse:
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
        effective_limit=out.effective_limit,
        limit_applied=out.limit_applied,
        pretty_sql=out.pretty_sql,
        warnings=out.warnings,
        attempts=[AttemptOut(**vars(a)) for a in out.attempts],
        message=out.message,
        model=getattr(llm, "model", None),
        chart=recommend_chart(res.columns, res.rows) if res else None,
        verification=known_answers.verify(out.question, out.status, res),
    )


def _http_error(f: services.QueryFailure) -> HTTPException:
    return HTTPException(status_code=f.http_status, detail={"stage": f.stage, "code": f.code, "message": f.message})


# ---------------------------------------------------------------- basics

@app.get("/api/health")
def health():
    ok = db.ping()
    return {"status": "ok" if ok else "degraded", "database": ok}


@app.get("/api/meta")
def meta():
    from evals.cases import CASES
    s = get_settings()
    return {
        "provider": s.llm_provider,
        "demo": s.llm_provider.lower() == "replay",
        "reference_date": s.reference_date,
        "max_rows": s.max_rows,
        "statement_timeout_ms": s.statement_timeout_ms,
        "max_attempts": s.max_attempts,
        "examples": [{"id": c.id, "question": c.question, "category": c.category, "expect": c.expect}
                     for c in CASES],
    }


@app.get("/api/schema")
def schema(prompt: bool = False):
    """Database schema as JSON. With ?prompt=true also returns the LLM-ready text."""
    s = get_schema()
    body = s.to_dict()
    if prompt:
        body["prompt"] = s.to_prompt()
    return body


# ---------------------------------------------------------------- raw SQL

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
        "effective_limit": r.effective_limit,
        "limit_applied": r.limit_applied,
        "pretty_sql": r.pretty_sql,
        "chart": recommend_chart(result.columns, result.rows),
    }


# ---------------------------------------------------------------- AI

@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, llm: LLMClient = Depends(get_llm)):
    """Natural language -> SQL -> guarded execution -> validated result.

    Always returns HTTP 200 for the pipeline's own outcomes (``status`` says ok / failed /
    cannot_answer) so a client can render the full attempt trace either way.
    """
    return _build_ask_response(pipeline.answer_question(req.question.strip(), llm), llm)


@app.post("/api/ask/stream")
def ask_stream(req: AskRequest, llm: LLMClient = Depends(get_llm)):
    """Server-sent events: one JSON event per pipeline step, then a final ``result`` event."""
    events: queue.Queue[dict | None] = queue.Queue()

    def worker():
        try:
            out = pipeline.answer_question(req.question.strip(), llm, on_event=events.put)
            events.put({"type": "result", "data": _build_ask_response(out, llm).model_dump()})
        except LLMNotConfigured as e:
            events.put({"type": "error", "stage": "llm", "code": "not_configured", "message": str(e)})
        except LLMError as e:
            events.put({"type": "error", "stage": "llm", "code": "llm_error", "message": str(e)})
        except (psycopg.OperationalError, psycopg_pool.errors.PoolTimeout, psycopg_pool.errors.PoolClosed):
            events.put({"type": "error", "stage": "database", "code": "unavailable",
                        "message": "The database is unreachable. Check that Postgres is running."})
        except Exception:                                   # never leak internals to the client
            log.exception("pipeline crashed")
            events.put({"type": "error", "stage": "server", "code": "internal", "message": "Unexpected server error."})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while (event := events.get()) is not None:
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},   # no proxy buffering
    )


# ---------------------------------------------------------------- evaluation

@app.get("/api/evals/cases")
def eval_cases():
    from evals.cases import CASES
    return [{"id": c.id, "category": c.category, "question": c.question, "expect": c.expect,
             "ordered": c.ordered, "trap": c.trap, "golden_sql": c.golden_sql} for c in CASES]


@app.post("/api/evals/run")
def eval_run(req: EvalRunRequest):
    """Run the suite offline against a recorded model. Only whitelisted recordings: this endpoint
    can never trigger paid LLM calls."""
    import evals
    from evals.runner import run_all
    path = Path(evals.__file__).parent / "recordings" / f"{req.recording}.json"
    started = time.perf_counter()
    report = run_all(ReplayLLM.from_file(path))
    body = report.to_dict()
    body["recording"] = req.recording
    body["wall_ms"] = round((time.perf_counter() - started) * 1000)
    return body


# ---------------------------------------------------------------- security lab

_PROBES = {
    "guard": "DROP TABLE orders",
    "transaction": "DELETE FROM orders WHERE id = -1",
    "privileges": "DELETE FROM orders WHERE id = -1",
    "timeout": "SELECT COUNT(*) FROM order_items a CROSS JOIN order_items b CROSS JOIN order_items c",
}


@app.post("/api/security/probe")
def security_probe(req: ProbeRequest):
    """Demonstrate each defense layer *on its own*, with fixed server-side statements.

    Layers 2-4 deliberately bypass the SQL guard to prove the database still refuses. The
    statements are constants (not user input), match no rows, and run as the SELECT-only role.
    """
    statement = _PROBES[req.layer]
    started = time.perf_counter()
    blocked_by, error = "", ""

    if req.layer == "guard":
        try:
            validate_sql(statement, get_schema().table_names)
        except SQLGuardError as e:
            blocked_by, error = "SQL guard (AST allow-list)", f"[{e.code}] {e.message}"
    else:
        try:
            with psycopg.connect(get_settings().database_url, connect_timeout=5) as conn:
                if req.layer == "privileges":
                    conn.read_only = False          # force a READ WRITE transaction
                if req.layer == "timeout":
                    conn.read_only = True
                    conn.execute("SELECT set_config('statement_timeout', '100', true)")
                try:
                    conn.execute(statement)
                finally:
                    conn.rollback()
        except psycopg.errors.ReadOnlySqlTransaction as e:
            blocked_by, error = "Read-only transaction", str(e).splitlines()[0]
        except psycopg.errors.InsufficientPrivilege as e:
            blocked_by, error = "Least-privilege database role", str(e).splitlines()[0]
        except psycopg.errors.QueryCanceled as e:
            blocked_by, error = "Statement timeout", str(e).splitlines()[0]

    return {
        "layer": req.layer,
        "statement": statement,
        "blocked": bool(blocked_by),
        "blocked_by": blocked_by or "NOT BLOCKED",
        "error": error,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
