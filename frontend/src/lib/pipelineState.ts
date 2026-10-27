import type { AskResult, Explanation, PipelineEvent } from "./types";

export type StationId = "ask" | "write" | "guard" | "run" | "verify";
export const STATION_ORDER: StationId[] = ["ask", "write", "guard", "run", "verify"];
export type StationStatus = "idle" | "active" | "done" | "blocked" | "repaired";
export type Station = { status: StationStatus; caption: string };
export type Loop = { from: StationId; attempt: number; reason: string };

export type PipelineState = {
  phase: "idle" | "running" | "done" | "error";
  question: string;
  attempt: number;
  maxAttempts: number;
  stations: Record<StationId, Station>;
  packetAt: StationId;
  loops: Loop[];
  draftSql: string | null;
  result: AskResult | null;
  explanation: Explanation | null;
  explaining: boolean;           // the summary is still being written
  error: { stage: string; code: string; message: string } | null;
};

const idle = (): Record<StationId, Station> => ({
  ask: { status: "idle", caption: "Waiting for a question" },
  write: { status: "idle", caption: "Model writes the SQL" },
  guard: { status: "idle", caption: "Parsed and allow-listed" },
  run: { status: "idle", caption: "Read-only, with a timeout" },
  verify: { status: "idle", caption: "Compared with a known answer" },
});

export const initialState: PipelineState = {
  phase: "idle", question: "", attempt: 0, maxAttempts: 3, stations: idle(), packetAt: "ask",
  loops: [], draftSql: null, result: null, explanation: null, explaining: false, error: null,
};

export type Action = { type: "reset" } | { type: "begin"; question: string } | { type: "event"; event: PipelineEvent };

const set = (s: PipelineState, id: StationId, status: StationStatus, caption: string): PipelineState => ({
  ...s, stations: { ...s.stations, [id]: { status, caption } },
});
const short = (text: string, n = 64) => (text.length > n ? text.slice(0, n - 1) + "…" : text);

export function pipelineReducer(state: PipelineState, action: Action): PipelineState {
  if (action.type === "reset") return initialState;
  if (action.type === "begin") {
    return { ...initialState, phase: "running", question: action.question, stations: { ...idle(), ask: { status: "active", caption: "Sending the question" } } };
  }
  const e = action.event;
  let s = state;
  switch (e.type) {
    case "start":
      s = set({ ...s, maxAttempts: e.max_attempts, packetAt: "ask" }, "ask", "done", "Question received");
      return s;
    case "attempt_start":
      s = { ...s, attempt: e.n, packetAt: "write", stations: { ...s.stations, guard: idle().guard, run: idle().run, verify: idle().verify } };
      return set(s, "write", "active", e.n === 1 ? "Writing SQL" : `Attempt ${e.n} of ${s.maxAttempts}`);
    case "sql":
      s = set({ ...s, draftSql: e.sql, packetAt: "guard" }, "write", "done", `Attempt ${e.n}: SQL written`);
      return set(s, "guard", "active", "Checking the query");
    case "guard":
      if (e.ok) {
        s = set({ ...s, draftSql: e.pretty_sql, packetAt: "run" }, "guard", "done",
          `${e.tables.length} table${e.tables.length === 1 ? "" : "s"}, LIMIT ${e.effective_limit}`);
        return set(s, "run", "active", "Running read-only");
      }
      s = { ...s, loops: [...s.loops, { from: "guard", attempt: e.n, reason: e.message }] };
      return set(s, "guard", "blocked", `Blocked: ${e.code}`);
    case "database_error":
      s = { ...s, loops: [...s.loops, { from: "run", attempt: e.n, reason: e.message }] };
      return set(s, "run", "blocked", short(e.message, 48));
    case "executed":
      s = set({ ...s, packetAt: "verify" }, "run", "done", `${e.row_count} row${e.row_count === 1 ? "" : "s"} in ${e.elapsed_ms} ms`);
      return set(s, "verify", "active", "Checking the result");
    case "checks": {
      const bad = e.issues.filter((i) => i.repairable);
      if (!bad.length) return s;
      s = { ...s, loops: [...s.loops, { from: "verify", attempt: e.n, reason: bad[0].message }] };
      return set(s, "verify", "blocked", short(bad[0].message, 48));
    }
    case "repair":
      return set({ ...s, packetAt: "write" }, "write", "active", `Repairing: ${short(e.reason, 40)}`);
    case "no_sql":
      return set(s, "write", "blocked", "Reply had no SQL");
    case "cannot_answer":
      return set(s, "write", "blocked", `Declined: ${short(e.reason, 40)}`);
    case "explanation":
      return { ...s, explanation: e.data, explaining: false };
    case "error":
      return { ...s, phase: "error", explaining: false, error: { stage: e.stage, code: e.code, message: e.message } };
    case "result": {
      const r = e.data;
      s = { ...s, phase: "done", result: r, explanation: r.explanation ?? null, explaining: r.explanation_pending };
      if (r.status === "ok") {
        const repaired = r.attempts.length > 1;
        s = set(s, "write", repaired ? "repaired" : "done", repaired ? `Recovered after ${r.attempts.length - 1} repair${r.attempts.length > 2 ? "s" : ""}` : "SQL written");
        s = set(s, "guard", "done", `${r.tables.length} table${r.tables.length === 1 ? "" : "s"}, LIMIT ${r.effective_limit ?? "n/a"}`);
        s = set(s, "run", "done", `${r.row_count} row${r.row_count === 1 ? "" : "s"} in ${r.elapsed_ms} ms`);
        const v = r.verification;
        s = v
          ? set(s, "verify", v.matched ? "done" : "blocked", v.matched ? "Matches the known answer" : "Differs from the known answer")
          : set(s, "verify", "done", "Checks passed, no stored answer");
        return { ...s, packetAt: "verify" };
      }
      if (r.status === "cannot_answer") {
        const v = r.verification;
        s = set({ ...s, packetAt: "write" }, "write", "blocked", v?.matched ? "Correctly refused" : "Declined to answer");
        // If the guard rejected an attempt on the way to the refusal, keep it stamped: that is the defense that fired.
        return r.attempts.some((a) => a.outcome === "rejected_by_guard") ? set(s, "guard", "blocked", "Blocked an unsafe attempt") : s;
      }
      return set({ ...s, packetAt: s.packetAt }, s.stations.run.status === "blocked" ? "run" : "guard", "blocked", `Gave up after ${r.attempts.length} attempts`);
    }
  }
  return s;
}

/** How long to hold on each event so a person can follow along (ms). */
export function delayFor(e: PipelineEvent, reduceMotion = false): number {
  const base: Partial<Record<PipelineEvent["type"], number>> = {
    start: 350, attempt_start: 450, sql: 1100, guard: 850, database_error: 950, executed: 800,
    checks: 600, repair: 900, no_sql: 700, cannot_answer: 900, result: 0, explanation: 0, error: 0,
  };
  const ms = base[e.type] ?? 400;
  return reduceMotion ? Math.round(ms * 0.25) : ms;
}
