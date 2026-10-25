# AI Data Analyst: Text-to-SQL that executes *safely* and verifies results

Ask a business question in plain English. The system writes SQL, checks it, runs it against
PostgreSQL in a locked-down read-only session, and (coming in later parts) draws a chart and explains the answer.

> **Status: Part 3 of 5 complete** (secure foundation + LLM text-to-SQL with a repair loop + evaluation suite). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```bash
cp .env.example .env        # then set LLM_API_KEY (or LLM_PROVIDER=replay for a keyless demo)
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

# Ask a business question in plain English (needs LLM_API_KEY)
curl -s localhost:8000/api/ask -H 'content-type: application/json' -d '{
  "question": "Which products had the biggest revenue decline last quarter?"
}' | python -m json.tool

# See what the LLM will be shown about your database
curl -s 'localhost:8000/api/schema?prompt=true' | python -m json.tool
```

## What exists so far

- **Schema-aware context**: introspects tables, keys, comments and real sample values.
- **SQLGlot guard**: single statement, SELECT-only, table allow-list, function deny-list, forced `LIMIT`.
- **Safe execution**: read-only transaction, statement timeout, JSON-safe results (NULLs, decimals, dates).
- **Four-layer defense** that holds even if one layer fails (tested).
- **Text-to-SQL (`POST /api/ask`)**: schema-aware prompt (comments, keys, real sample values), with
  "last quarter" and friends computed *in code* and handed to the model as facts.
- **Validation-and-repair loop**: guard rejections, Postgres errors, timeouts, empty results and
  all-NULL columns are fed back to the LLM (up to `MAX_ATTEMPTS`). Once a runnable result exists,
  later failures never throw it away. The response includes the full attempt trace.
- **Provider-agnostic LLM layer**: Anthropic, OpenAI, or any OpenAI-compatible server (Ollama, vLLM),
  over plain HTTP with retries. No vendor SDK lock-in.
- **Evaluation suite** ([docs/EVALUATION.md](docs/EVALUATION.md)): 26 questions with known-correct SQL, scored by
  comparing *results* (alias/order/float tolerant). Golden answers are re-derived independently in Python.
  A careless "naive" model scores **14/26** and the report says exactly why (e.g. `missing [Smart Watch]`).
- **Keyless demo mode** (`LLM_PROVIDER=replay`): answers the recorded questions with no API key.
- **200 tests**, including the repair loop (scripted fake LLM against real Postgres), a
  prompt-injection test proving destructive SQL never runs, and a database-integrity check around every eval run.

## Evaluate a model

```bash
make eval         # offline replay of the reference recording -> 26/26
make eval-naive   # a careless model -> 14/26, with the reasons
make eval-live    # your real LLM (needs LLM_API_KEY)
```

## Tests

```bash
docker compose up -d db
make test
```

## Tech

Python 3.12, FastAPI, PostgreSQL 16, psycopg 3, SQLGlot, httpx, Docker. (React + evals in later parts.)
