# Frontend (Verity)

React 19 + TypeScript + Vite, Tailwind v4, Recharts, Framer Motion. 77 tests (Vitest + Testing Library).

![The answer, with proof](screenshots/03-answer-and-proof.png)

## The idea: make trust visible

Most text-to-SQL demos show a chat bubble and a chart. The interesting part of this system is *why you can
believe the answer*, so the whole UI is organised around that:

- **The pipeline line** (hero element): Ask, Write SQL, Guard, Run, Verify. The query travels along it, each
  station is stamped as it completes, and a rejected query visibly loops back to "Write SQL" (the repair loop,
  drawn literally). It is driven by **real server events**, not a canned animation.
- **Proof column**: a verdict against the known answer, the safety checks that were actually enforced, and the
  full attempt trace including the model's rejected SQL.
- **Evaluation page**: runs the 26-question suite against a careful and a careless recorded model, side by side.
- **Security lab**: attacks each of the four defense layers on its own, plus a SQL console behind the same guard.
- **Schema page**: what the model sees, with a relationship map (tables laid out by foreign-key depth and ordered
  to avoid crossing lines).

Colors carry fixed meaning everywhere: **mint** = verified, **coral** = blocked, **amber** = repaired,
**periwinkle** = running. Type: Bricolage Grotesque for text, Spline Sans Mono for SQL and numbers (both bundled
via Fontsource, so there are no runtime font requests).

## How the live pipeline works

```
POST /api/ask/stream  --SSE-->  parseSSE()  -->  Pacer  -->  pipelineReducer  -->  PipelineLine
```

1. The backend runs the same pipeline as `/api/ask` and emits one event per step (`attempt_start`, `sql`, `guard`,
   `database_error`, `executed`, `checks`, `repair`, `cannot_answer`, `result`).
2. `parseSSE` reassembles events across arbitrary network chunk boundaries.
3. `Pacer` plays them at human speed. A replay backend answers in milliseconds, so without pacing nobody could
   watch the stages. Delays shrink under `prefers-reduced-motion`.
4. `pipelineReducer` is a pure state machine (13 tests): it decides each station's status, caption and where the
   query packet is. The component only renders state.

nginx disables response buffering for `/api/`, and the API also sends `X-Accel-Buffering: no`, so each step reaches the
browser as it happens. This was tested against a real nginx 1.24 with an upstream emitting events one second apart
(they arrive at +0s, +1s, +2s). Buffering behaviour varies by proxy and version, so both protections are kept; compression
is also kept off for `text/event-stream`.

## Summaries

The answer panel opens with a written summary. In streaming mode it shows a skeleton ("Writing a summary, then
checking every figure against the result...") while the result is already usable, then fills in. Figures are
highlighted, and a footer says either *"Written by the model. N figures checked against the result"* or
*"Rule-based summary (no model involved)"*, so the UI never overstates what was verified.

## Charts come from the data

The backend picks a chart from the *shape* of the result (`app/charts.py`, 16 tests): one row becomes headline
numbers, a date column becomes a trend line, a category becomes bars (horizontal when labels are long),
negatives switch on sign coloring, and columns on very different scales are not drawn on one axis. The user can
override the type and measures. For the headline question only the `change` column is plotted, in red, which makes
the Smart Watch decline obvious.

## Accessibility and robustness

- Keyboard: `/` focuses the question box, `Esc` stops a run, `Ctrl/Cmd+Enter` runs SQL in the lab.
- The pipeline is a `role="group"` with `aria-live="polite"`; sort state uses `aria-sort`; icon-only nav on tiny
  screens keeps `aria-label`s; focus rings are always visible.
- `prefers-reduced-motion` disables pulses and shakes and shortens pacing.
- Honest empty states: when a question is not in the evaluation set the UI says "no stored answer" instead of
  implying it was verified. Errors map to specific hints (no API key, API offline, database down).
- Heavy code is lazy-loaded: first load is ~126 kB gzipped; Recharts (~127 kB) loads only when a chart is drawn.

## How it was checked

Beyond the unit and component tests, the app was driven end to end in headless Chromium (Postgres + API in demo
mode + Vite): the idle, mid-run, answer, prompt-injection, evaluation, security-lab, schema and mobile (390px)
views were all inspected, with zero console or page errors. That pass found and fixed real bugs that tests missed
(clipped negative axis, colliding schema labels, a clipped packet label on mobile, a double focus border).
The screenshots in `docs/screenshots` are from that run.

## Develop

```bash
make dev-api    # terminal 1: API in keyless demo mode (docker compose up -d db first)
make dev-ui     # terminal 2: http://localhost:5173
make test-ui    # typecheck + tests + build
```
