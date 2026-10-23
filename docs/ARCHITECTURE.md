# Architecture

## Request flow (target design)

```
Question -> [schema-aware prompt] -> LLM -> SQL
         -> [SQL guard (SQLGlot)] -> reject / repair loop
         -> [read-only execution]  -> rows
         -> [validation] -> chart spec + written explanation
```

Part 1 (this commit) implements everything from "SQL guard" down to "rows" plus schema introspection.

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

## Dataset

Deterministic e-commerce data (no `random()`), so evaluation answers are stable.
Orders run 2024-01-01 to 2025-12-31. Q4 2025 is deliberately shaped so products 1-5
decline and 6-10 grow, giving questions like "biggest revenue decline last quarter" a real answer.
Built-in traps: NULL discounts, NULL signup channels, cancelled/refunded orders that must be
excluded from revenue.

`REFERENCE_DATE` (default 2026-01-15) is the app's notion of "today", so "last quarter" = Q4 2025.

## Roadmap

- [x] Part 1: Database, SQL guard, safe execution, schema introspection, API
- [ ] Part 2: LLM text-to-SQL, validation-and-repair loop, `/api/ask`
- [ ] Part 3: Evaluation suite (generated SQL vs known answers)
- [ ] Part 4: React frontend (question box, SQL inspector, charts)
- [ ] Part 5: Polish: written explanations, README demo, CI for evals
