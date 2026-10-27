# Security

This is a portfolio project that gives an LLM access to a database, so the threat model matters more than usual.

## Threat model

**Assets:** the data in PostgreSQL, the database's integrity, the LLM API key and its budget.

**Attackers considered**

| Attacker | Goal | Defense |
|---|---|---|
| A user typing a hostile *question* (prompt injection) | Make the model write destructive or exfiltrating SQL | The model's output is never trusted: it goes through the guard, a read-only transaction, a timeout and a SELECT-only role. Tested with hostile prompts. |
| A user typing hostile *SQL* in the SQL lab | Write, drop, read system catalogs, hang the database | Same four layers; stacked statements, data-modifying CTEs, `pg_sleep`, `pg_shadow`, `SELECT INTO`, `FOR UPDATE` are all rejected |
| Hostile *data* (a cell containing "ignore previous instructions") | Steer the summary writer | Cell values are fenced inside `<data>` and the prompt says they are data; the summary can only produce text, and every figure is checked against the result |
| A visitor running up the LLM bill | Cost / denial of service | Per-visitor rate limit, a global daily budget of model-backed requests, response caching, input length limits |
| A visitor dodging the rate limit | Same | `X-Forwarded-For` is trusted only when `TRUST_PROXY=true`, and the bundled nginx overwrites it with the real address |

**The four layers** (each is tested to hold without the others): AST allow-list guard, read-only transaction,
statement timeout, least-privilege role. The guard executes SQL **regenerated from its AST**, not the model's text.

## Known limits (not defended)

- No authentication, authorization or multi-tenancy. Anyone who can reach the app can ask questions of the demo dataset.
- Rate limits and the budget are per process and in memory. Run one instance or move them to Redis.
- If you expose the API port (8000) directly while `TRUST_PROXY=true`, clients can spoof their address.
  Publish only the nginx port (3000) in production.
- Summary grounding verifies figures, not the fairness of the prose.
- The LLM provider sees the question, the schema, sample values of low-cardinality columns, and result rows used for summaries.
  Do not point this at data you cannot send to your provider.
- Dependency versions are pinned; no automated vulnerability scanning is configured.

## If you adapt this to real data

Create a dedicated read-only role limited to the tables the model may see, review `_BLOCKED_FUNCTIONS` in
`backend/app/sql_guard.py`, set `DAILY_LLM_BUDGET`, and keep the API key in a secret manager, never in the repo.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository (Security tab), or email the maintainer.
Please include steps to reproduce. There is no bounty, but reports are appreciated and credited.
