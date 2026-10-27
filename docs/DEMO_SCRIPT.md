# Five-minute demo script

Use demo mode (`LLM_PROVIDER=replay`) for a reliable, free walkthrough, or a real model if you have a key.
Open the app at http://localhost:3000.

## 1. The headline question (90 seconds)

Click **Biggest revenue decline last quarter**.

- Watch the **pipeline line**: the query travels, each station is stamped. "This isn't a canned animation; it's
  driven by server-sent events from the real pipeline."
- Point at the **chart**: red bars are decreases; the axis includes zero.
- Point at **Smart Watch** (second bar): "This product sold $10.5k in Q3 and *nothing* in Q4. A query that only
  looks at Q4 rows, or subtracts NULLs, silently drops it. This dataset is built with that trap on purpose."
- Open **Show the known answer** in the proof column: "The result is compared with a known-correct answer by
  value, ignoring aliases, order and rounding."

## 2. Show your work (60 seconds)

Click the **SQL** tab. "This is what actually ran. The tab beside it shows what the model wrote; the difference is
that the guard rebuilt the query from its syntax tree and added a LIMIT." Then **Safety checks passed**:
read-only transaction, time limit, SELECT-only role.

## 3. Break it (90 seconds)

Click the red **Drop the orders table** chip.

- The Guard station turns red and a loop arc sends the model back. "The model's first attempt was `DROP TABLE`.
  The guard rejected it, the error went back to the model as feedback, and the model refused."
- Open **Security lab**, click **Attack all four**. "Each attack skips the earlier layers on purpose. Postgres
  itself refuses the DELETE twice: once because the transaction is read-only, and again because the role has no
  write permission."
- Try **Hidden DELETE** or **Read pg_shadow** in the SQL lab.

## 4. How do we know it's right? (60 seconds)

Open **Evaluation**, click **Run the evaluation**.

- "26 questions with known answers. A careful model scores 26/26. A deliberately careless model scores 14/26,
  and the report names each mistake. If the harness couldn't fail a bad model, it would be worthless."
- Expand a failing row to show `missing [Smart Watch], unexpected [Dumbbell Set]`.
- Be upfront: "Replay mode validates the harness. `make eval-live` measures a real model."

## 5. The engineering story (30 seconds)

- Allow-list guard on an AST, not regexes. Four layers, each tested alone.
- Dates and "today" computed in code, not guessed by the model.
- Summaries are checked: every figure must trace to the result, or a rule-based summary replaces it.
- Cost protection: caching, rate limits, a daily budget.

## Questions to expect

- *"What happens with a question outside your evaluation set?"* The UI says there's no stored answer to compare
  with. It still runs the empty-result and NULL checks.
- *"Why not just use regex to block DROP?"* `WITH d AS (DELETE ... RETURNING *) SELECT * FROM d` is a SELECT
  by keyword. The AST sees the DELETE.
- *"What would you do next?"* Redis-backed limits, auth, per-tenant roles, and more evaluation cases per schema.
