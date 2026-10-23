# AI Data Analyst: Text-to-SQL that executes *safely* and verifies results

Ask a business question in plain English. The system writes SQL, checks it, runs it against
PostgreSQL in a locked-down read-only session, and (coming in later parts) draws a chart and explains the answer.

> **Status: Part 1 of 5 complete** (secure foundation). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
open http://localhost:8000/docs       # interactive API docs
```

Try it:

```bash
# Run a query safely
curl -s localhost:8000/api/sql/execute -H 'content-type: application/json' -d '{
  "sql": "SELECT status, COUNT(*) FROM orders GROUP BY status"
}'

# Watch the guard stop an attack
curl -s localhost:8000/api/sql/execute -H 'content-type: application/json' -d '{
  "sql": "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d"
}'
# -> 422 {"detail": {"code": "forbidden_statement", ...}}

# See what the LLM will be shown about your database
curl -s 'localhost:8000/api/schema?prompt=true' | python -m json.tool
```

## What exists so far

- **Schema-aware context**: introspects tables, keys, comments and real sample values.
- **SQLGlot guard**: single statement, SELECT-only, table allow-list, function deny-list, forced `LIMIT`.
- **Safe execution**: read-only transaction, statement timeout, JSON-safe results (NULLs, decimals, dates).
- **Four-layer defense** that holds even if one layer fails (tested).
- **72 tests** (59 unit for the guard, 13 integration against real Postgres).

## Tests

```bash
docker compose up -d db
make test
```

## Tech

Python 3.12, FastAPI, PostgreSQL 16, psycopg 3, SQLGlot, Docker. (React + LLM + evals in later parts.)
