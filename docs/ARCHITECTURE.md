# Architecture

## Request flow (target design)

```
Question -> [schema-aware prompt] -> LLM -> SQL
         -> [SQL guard (SQLGlot)] -> reject / repair loop
         -> [read-only execution]  -> rows
         -> [validation] -> chart spec + written explanation
```

Parts 1-2 implement everything up to and including the repair loop. Charts and explanations come later.

## Security model: four independent layers

| # | Layer | Where | Stops |
|---|-------|-------|-------|
| 1 | AST allow-list guard (the executed SQL is *regenerated from the AST*, never the model's text) | `app/sql_guard.py` | writes, DDL, stacked statements, data-modifying CTEs, `SELECT INTO`, dangerous functions, system catalogs, unbounded results, comment tricks |
| 2 | Read-only transaction (always rolled back) | `app/db.py` | accidental or injected writes that slip past the guard |
| 3 | Statement timeout | `app/db.py` + role setting | runaway queries (accidental cross joins) |
| 4 | Least-privilege role (`analyst_ro`: SELECT only, connection limit) | `db/init/03_readonly_role.sh` | everything, even if layers 1-3 had a bug |

Each layer is tested to hold **without** the one before it (`tests/test_api_integration.py`), and the Security lab
page attacks layers 1, 2, 4 and 3 individually via `POST /api/security/probe` (fixed server-side statements that
match no rows, run as the SELECT-only role).

## Why SQLGlot and not regex?

Keyword filters are easy to bypass (`WITH d AS (DELETE ... RETURNING *) SELECT ...`, comments,
casing, quoting). Parsing to an AST means we reason about what the query *is*, not how it is spelled.

## The repair loop (`app/pipeline.py`)

```
ask LLM -> extract SQL -> guard -> execute -> result checks
   ^                         |        |            |
   +---- error / suspicious -+--------+------------+     (up to MAX_ATTEMPTS)
```

| Signal | Example | Reaction |
|--------|---------|----------|
| Guard rejection | `DELETE ...`, unknown table | feed guard message back (it lists valid tables) |
| Postgres error | `column "revenue" does not exist` | feed Postgres' own message back |
| Timeout | accidental cross join | ask for a cheaper query |
| Empty result | `status = 'Completed'` (wrong case) | ask to re-check filters; accept if model re-submits the same SQL |
| All-NULL column | broken join | same |
| Truncated result | > MAX_ROWS | warning only, never repaired |
| Model declines | `CANNOT_ANSWER: ...` | status `cannot_answer`, nothing executed |

Design rules: the conversation history is preserved across repairs; once a runnable result exists a
later failed repair falls back to it (with warnings) rather than failing; every attempt is recorded and
returned so the UI can show the trace.

**Dates are computed in code** (`app/dates.py`): the prompt contains exact half-open windows for
"last quarter", "last month", etc. LLMs are unreliable at calendar arithmetic; code is not.

**No eval leakage:** the worked examples in the prompt deliberately differ from the evaluation questions.

**Prompt injection:** the question is untrusted input, but it can only influence *which SELECT* is
written. Destructive SQL is stopped by the four security layers (tested with a hostile "drop every table" prompt).

## Written explanations (`app/explain.py`)

Every answer gets a short summary. An LLM summary can state a figure that is not in the data, so each one is
**grounded**: every number it mentions must appear in the result or be simple arithmetic on it (a total, a
difference between rows, a percentage change, a share of total). A failing summary is returned to the model once with
the offending figures named; if it fails again, a deterministic rule-based summary replaces it. A summary problem can
never block or corrupt the answer.

Tolerances follow the precision the text uses ("$12.9K" matches 12,934 within 50; "$5,900" is a fair rounding of
5,942.70 but "$50,000" is not a rounding of 49,438.80). Years near the dataset's reference date are treated as labels.
Grounding is a *numeric* guarantee only; the prompt separately forbids speculating about causes.

In streaming mode the result is sent first and the summary arrives in a later `explanation` event.

## Cost and abuse protection (`app/cache.py`, `app/limits.py`)

- **Cache:** identical question + model + reference date reuses the answer (TTL, bounded size). Only `ok` and
  `cannot_answer` outcomes are cached; failures are retried. The free replay provider is never cached.
- **Rate limit:** per-client sliding window on model-backed endpoints (and lighter ones on DB-only endpoints).
  `X-Forwarded-For` is trusted only when `TRUST_PROXY=true`.
- **Daily budget:** a global cap on model-backed requests per UTC day, skipped for the free replay provider.
- All three are in memory and per process; a limit of 0 disables it.

## Dataset

Deterministic e-commerce data (no `random()`), so evaluation answers are stable.
Orders run 2024-01-01 to 2025-12-31. Q4 2025 is deliberately shaped so products 1-5
decline and 6-10 grow, giving questions like "biggest revenue decline last quarter" a real answer.
Built-in traps: a product (Smart Watch) with Q3 sales but *zero* Q4 sales, which naive queries drop; NULL discounts, NULL signup channels, cancelled/refunded orders that must be
excluded from revenue.

`REFERENCE_DATE` (default 2026-01-15) is the app's notion of "today", so "last quarter" = Q4 2025.

## Roadmap

- [x] Part 1: Database, SQL guard, safe execution, schema introspection, API
- [x] Part 2: LLM text-to-SQL, validation-and-repair loop, `/api/ask`
- [x] Part 3: Evaluation suite (generated SQL vs known answers), replay/record LLM, CI gate
- [x] Part 4: React frontend (live pipeline, SQL inspector, charts, eval + security pages), SSE streaming
- [x] Part 5: Grounded written explanations, response cache, rate limiting + daily budget, docs
