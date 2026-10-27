import { describe, expect, it } from "vitest";
import { delayFor, initialState, pipelineReducer, type PipelineState } from "../pipelineState";
import type { AskResult, PipelineEvent } from "../types";

const play = (events: PipelineEvent[], from: PipelineState = pipelineReducer(initialState, { type: "begin", question: "q" })) =>
  events.reduce((s, event) => pipelineReducer(s, { type: "event", event }), from);

const status = (s: PipelineState) => Object.fromEntries(Object.entries(s.stations).map(([k, v]) => [k, v.status]));

const base: AskResult = {
  status: "ok", question: "q", sql: "SELECT 1", pretty_sql: "SELECT 1", tables: ["orders"], columns: [], rows: [], row_count: 3,
  truncated: false, elapsed_ms: 4.2, effective_limit: 1000, limit_applied: true, warnings: [], attempts: [], message: null,
  model: "m", chart: null, verification: null, explanation: null, explanation_pending: false, cached: false,
};
const attempt = (n: number, outcome: any) => ({ number: n, sql: "x", outcome, detail: null, raw_sql: "x" });

const happy: PipelineEvent[] = [
  { type: "start", question: "q", max_attempts: 3 },
  { type: "attempt_start", n: 1 },
  { type: "sql", n: 1, sql: "select 1" },
  { type: "guard", n: 1, ok: true, sql: "SELECT 1", pretty_sql: "SELECT\n  1", tables: ["orders"], effective_limit: 1000, limit_applied: true },
  { type: "executed", n: 1, row_count: 3, elapsed_ms: 4.2 },
  { type: "checks", n: 1, issues: [] },
];

describe("pipelineReducer", () => {
  it("begins in a running state with the ask station active", () => {
    const s = pipelineReducer(initialState, { type: "begin", question: "hello" });
    expect(s.phase).toBe("running");
    expect(s.question).toBe("hello");
    expect(status(s).ask).toBe("active");
  });

  it("moves the packet station by station on the happy path", () => {
    const s = play(happy);
    expect(s.packetAt).toBe("verify");
    expect(status(s)).toEqual({ ask: "done", write: "done", guard: "done", run: "done", verify: "active" });
    expect(s.stations.run.caption).toBe("3 rows in 4.2 ms");
    expect(s.stations.guard.caption).toBe("1 table, LIMIT 1000");
    expect(s.draftSql).toBe("SELECT\n  1");               // switches to the guard's pretty SQL
  });

  it("draws a repair loop when the guard blocks the query, then retries", () => {
    const s = play([
      { type: "start", question: "q", max_attempts: 3 },
      { type: "attempt_start", n: 1 },
      { type: "sql", n: 1, sql: "DELETE FROM orders" },
      { type: "guard", n: 1, ok: false, code: "not_read_only", message: "Only SELECT queries are allowed" },
    ]);
    expect(status(s).guard).toBe("blocked");
    expect(s.stations.guard.caption).toBe("Blocked: not_read_only");
    expect(s.loops).toEqual([{ from: "guard", attempt: 1, reason: "Only SELECT queries are allowed" }]);

    const retry = play([{ type: "repair", n: 1, reason: "Only SELECT" }, { type: "attempt_start", n: 2 }], s);
    expect(retry.packetAt).toBe("write");
    expect(retry.attempt).toBe(2);
    expect(status(retry)).toMatchObject({ write: "active", guard: "idle", run: "idle", verify: "idle" });
    expect(retry.loops).toHaveLength(1);                   // earlier loop stays drawn
  });

  it("records database errors and suspicious results as loops from their stations", () => {
    const s = play([
      { type: "database_error", n: 1, code: "db_error", message: 'column "x" does not exist' },
      { type: "checks", n: 2, issues: [{ code: "empty_result", message: "The query returned zero rows.", repairable: true }] },
    ]);
    expect(s.loops.map((l) => l.from)).toEqual(["run", "verify"]);
    expect(status(s)).toMatchObject({ run: "blocked", verify: "blocked" });
  });

  it("ignores non-repairable check issues", () => {
    const s = play([...happy.slice(0, 5), { type: "checks", n: 1, issues: [{ code: "truncated", message: "cut off", repairable: false }] }]);
    expect(s.loops).toHaveLength(0);
    expect(status(s).verify).toBe("active");
  });

  it("marks the writer as repaired when a retried query succeeds", () => {
    const s = play([{ type: "result", data: { ...base, attempts: [attempt(1, "rejected_by_guard"), attempt(2, "ok")] } }], play(happy));
    expect(s.phase).toBe("done");
    expect(s.stations.write).toEqual({ status: "repaired", caption: "Recovered after 1 repair" });
  });

  it("uses the known-answer verdict for the verify station", () => {
    const v = { case_id: "x", category: "c", trap: "t", expect: "match" as const, matched: true, reason: "" };
    const ok = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")], verification: v } }], play(happy));
    expect(ok.stations.verify).toEqual({ status: "done", caption: "Matches the known answer" });
    const bad = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")], verification: { ...v, matched: false } } }], play(happy));
    expect(bad.stations.verify).toEqual({ status: "blocked", caption: "Differs from the known answer" });
    const none = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")] } }], play(happy));
    expect(none.stations.verify.caption).toBe("Checks passed, no stored answer");
  });

  it("handles a refusal", () => {
    const v = { case_id: "x", category: "security", trap: "t", expect: "refuse" as const, matched: true, reason: "" };
    const s = play([
      { type: "cannot_answer", n: 1, reason: "read-only" },
      { type: "result", data: { ...base, status: "cannot_answer", attempts: [attempt(1, "cannot_answer")], verification: v } },
    ]);
    expect(s.stations.write).toEqual({ status: "blocked", caption: "Correctly refused" });
    expect(s.phase).toBe("done");
  });

  it("keeps the guard stamped when it caught an attack that ended in a refusal", () => {
    const s = play([{ type: "result", data: { ...base, status: "cannot_answer", attempts: [attempt(1, "rejected_by_guard"), attempt(2, "cannot_answer")] } }]);
    expect(s.stations.guard).toEqual({ status: "blocked", caption: "Blocked an unsafe attempt" });
    const plain = play([{ type: "result", data: { ...base, status: "cannot_answer", attempts: [attempt(1, "cannot_answer")] } }]);
    expect(plain.stations.guard.status).toBe("idle");
  });

  it("reports giving up", () => {
    const s = play([
      { type: "guard", n: 3, ok: false, code: "unknown_table", message: "no" },
      { type: "result", data: { ...base, status: "failed", attempts: [attempt(1, "x"), attempt(2, "x"), attempt(3, "x")] } },
    ]);
    expect(s.stations.guard.caption).toBe("Gave up after 3 attempts");
  });

  it("surfaces stream errors", () => {
    const s = play([{ type: "error", stage: "llm", code: "not_configured", message: "no key" }]);
    expect(s.phase).toBe("error");
    expect(s.error).toEqual({ stage: "llm", code: "not_configured", message: "no key" });
  });

  it("waits for the summary after the result, then fills it in", () => {
    const exp = { text: "Sales fell.", source: "llm" as const, grounded: true, numbers_checked: 0, retried: false, ungrounded: [] };
    const waiting = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")], explanation_pending: true } }], play(happy));
    expect(waiting.phase).toBe("done");
    expect(waiting.explaining).toBe(true);
    expect(waiting.explanation).toBeNull();
    const done = play([{ type: "explanation", data: exp }], waiting);
    expect(done.explaining).toBe(false);
    expect(done.explanation).toEqual(exp);
    expect(done.result).toBe(waiting.result);                 // the answer itself is untouched
  });

  it("shows a summary delivered with the result (non-streaming or cached answers)", () => {
    const exp = { text: "Cached.", source: "template" as const, grounded: true, numbers_checked: 0, retried: false, ungrounded: [] };
    const s = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")], explanation: exp, cached: true } }]);
    expect(s.explaining).toBe(false);
    expect(s.explanation).toEqual(exp);
  });

  it("a failed summary (null) simply clears the pending state", () => {
    const waiting = play([{ type: "result", data: { ...base, attempts: [attempt(1, "ok")], explanation_pending: true } }]);
    expect(play([{ type: "explanation", data: null }], waiting)).toMatchObject({ explaining: false, explanation: null });
  });

  it("clears the previous summary when a new question begins", () => {
    const exp = { text: "x", source: "llm" as const, grounded: true, numbers_checked: 0, retried: false, ungrounded: [] };
    const s = pipelineReducer({ ...initialState, explanation: exp, explaining: true }, { type: "begin", question: "next" });
    expect(s.explanation).toBeNull();
    expect(s.explaining).toBe(false);
  });

  it("resets", () => { expect(pipelineReducer(play(happy), { type: "reset" })).toEqual(initialState); });
});

describe("delayFor", () => {
  it("lingers on SQL so it can be read, and never delays the final result", () => {
    expect(delayFor({ type: "sql", n: 1, sql: "x" })).toBeGreaterThan(delayFor({ type: "executed", n: 1, row_count: 1, elapsed_ms: 1 }));
    expect(delayFor({ type: "result", data: base })).toBe(0);
  });
  it("shortens everything for reduced motion", () => {
    const e: PipelineEvent = { type: "repair", n: 1, reason: "x" };
    expect(delayFor(e, true)).toBeLessThan(delayFor(e, false) / 2);
  });
});
