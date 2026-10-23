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
| 1 | AST allow-list guard | `app/sql_guard.py` | writes, DDL, multi-statement, data-modifying CTEs, `SELECT INTO`, dangerous functions, system catalogs, unbounded results |
| 2 | Regenerated SQL | `validate_sql` returns SQL rebuilt from the AST | comment/formatting tricks, parser-differential tricks |
| 3 | Read-only transaction + timeout | `app/db.py` | accidental writes, runaway queries |
| 4 | Least-privilege role | `db/init/03_readonly_role.sh` | everything, even if layers 1-3 had a bug (SELECT-only, 5s timeout, conn limit) |

Tests prove layers 3 and 4 hold *without* layer 1 (see `test_api_integration.py`).

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
- [ ] Part 3: Evaluation suite (generated SQL vs known answers)
- [ ] Part 4: React frontend (question box, SQL inspector, charts)
- [ ] Part 5: Polish: written explanations, README demo, CI for evals
