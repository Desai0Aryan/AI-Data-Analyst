# Evaluation suite

How do you know a text-to-SQL system is *right*, not just plausible? This suite answers that with
26 questions, each paired with known-correct ("golden") SQL, scored by comparing **result values**, never SQL text.

```bash
make eval         # offline: replays a recorded good model       -> 26/26
make eval-naive   # offline: replays a careless model            -> 14/26 (12 traps caught)
make eval-live    # your real LLM, saves a replayable recording  -> your number
```

## What it measures

| Category | Cases | What goes wrong without care |
|----------|-------|------------------------------|
| aggregation | 4 | averaging per line item instead of per order; forgetting the `completed` filter |
| dates | 5 | "last quarter" computed from the wall clock; boundary dates; growth-formula direction |
| joins | 5 | multi-table joins; grouping by a non-unique name; anti-joins (rows with *no* match) |
| nulls | 3 | `1 - NULL`, dropped NULL groups, `COUNT(col)` vs `COUNT(*)` |
| ranking | 2 | top-N with deterministic ties; ranking by the wrong measure |
| traps | 2 | the headline question (below) and an inverted-filter question |
| refusal | 2 | unanswerable questions: the model must decline, not invent a metric |
| security | 3 | prompt injection (`drop the table`), write requests, reading `pg_shadow` |

### The headline trap

> *"Which products had the biggest revenue decline last quarter?"*

**Smart Watch** sold $10.5k in Q3 and **nothing** in Q4. It is the second-largest decline, but any query that
inner-joins Q3 and Q4 subtotals, or subtracts NULLs, silently omits it. The naive recording does exactly that and
the harness reports:

```
trap_biggest_decline: column 'product' differs from result column 'product':
                      missing [Smart Watch], unexpected [Dumbbell Set]
```

## How answers are compared (`evals/compare.py`)

Strict on values, lenient on presentation. A correct query never fails because of:

- column aliases or column order, or extra helpful columns
- row order (unless the question implies one, e.g. "top 5")
- float noise (within one cent) or `5` vs `5.0`
- date spelling (`2025-08`, `2025-08-01`, `2025-08-01T00:00:00`)

A wrong query fails with an explanation of *what* differs (missing / unexpected values, wrong row count,
right rows in the wrong order). `NULL` is never equal to `0`.

Refusal cases pass if the pipeline returns `cannot_answer` **or** the guard rejects every attempt.

## Can the golden answers be trusted?

Golden SQL checked against itself would prove nothing, so `tests/test_eval_golden.py`:

1. **Recomputes the answers to all 21 answerable cases independently in Python** from raw table rows using
   `Decimal` arithmetic (no SQL aggregation; the order counts use a plain `COUNT`) and requires them to equal the
   golden SQL's output. The other 5 cases are refusals, which have no answer to check.
2. **Pins every golden result** in `evals/golden_snapshot.json`; changing the seed data or a golden query
   without regenerating the snapshot fails the build.
3. Proves each trap is **real** (for example, that customer names repeat, and that the per-line average differs
   from the per-order average).
4. Checks that **no eval question appears in the prompt**, so there is no test-set leakage.

## Metrics reported

Accuracy overall and per category, **correct on the first try** vs **recovered by the repair loop**, average
attempts per question, lint warnings (for example generated SQL that uses `CURRENT_DATE` on a historical dataset), and a
**database integrity check**: row counts of every table before and after the run must be identical.

## What replay mode does and does not prove

Replaying the *reference* recording validates the **harness and pipeline** (parsing, guard, repair loop, comparison,
reporting). It does **not** measure any model, because the recording was authored from the golden SQL.
The *naive* recording is the other half of the proof: a harness that cannot fail a bad model is worthless, and this one
fails 12 of 26 for specific, named reasons.

Only `--mode live` measures a model:

```bash
cd backend
python -m evals.run --mode live --record evals/recordings/mine.json --markdown report.md
python -m evals.run --recording evals/recordings/mine.json     # replay it later, for free
```

Other flags: `--category dates`, `--case trap_biggest_decline`, `--min-accuracy 0.9` (non-zero exit for CI),
`--json out.json`.

## Adding a case

1. Add a `Case(...)` to `evals/cases.py` with golden SQL and a `trap` description.
2. Add an independent Python check to `tests/test_eval_golden.py` if the answer is non-trivial.
3. `python -m evals.snapshot` and `python -m evals.build_recordings`.

Sample output: [reference](sample-reports/reference-replay.md), [naive](sample-reports/naive-replay.md).
