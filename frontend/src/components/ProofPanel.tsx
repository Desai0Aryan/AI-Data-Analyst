import { BadgeCheck, Check, ChevronDown, CircleSlash, Info, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import type { Attempt, AskResult, Column, Meta, Verification } from "../lib/types";
import { DataTable } from "./DataTable";
import { SqlCode } from "./SqlBlock";
import { Badge, Panel, cx } from "./ui";

const asColumns = (names: string[], rows: unknown[][]): Column[] =>
  names.map((name, i) => ({ name, type: typeof rows[0]?.[i] === "number" ? "numeric" : "text" }));

export function VerificationCard({ v }: { v: Verification | null }) {
  const [open, setOpen] = useState(false);
  if (!v) {
    return (
      <Panel className="p-5">
        <div className="flex items-start gap-3">
          <Info size={20} className="mt-0.5 shrink-0 text-faint" />
          <div>
            <p className="font-semibold">No stored answer to compare with</p>
            <p className="mt-1 text-sm text-muted">
              Verity compares results with a known answer when the question belongs to its evaluation set. The result still passed
              the empty-result and NULL checks. Try one of the example questions to see a full comparison.
            </p>
          </div>
        </div>
      </Panel>
    );
  }
  const ok = v.matched;
  const refusal = v.expect === "refuse";
  const title = refusal ? (ok ? "Correctly refused" : "Answered when it should have refused")
    : ok ? "Matches the known answer" : "Differs from the known answer";
  const hasGolden = !refusal && v.golden_rows && v.golden_columns;
  return (
    <Panel className={cx("overflow-hidden", ok ? "border-verified/50" : "border-blocked/60")}>
      <div className={cx("flex items-start gap-3 p-5", ok ? "bg-verified/[0.07]" : "bg-blocked/[0.08]")}>
        <div className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-full", ok ? "bg-verified text-page" : "bg-blocked text-page")}>
          {ok ? <BadgeCheck size={22} /> : <CircleSlash size={22} />}
        </div>
        <div>
          <p className={cx("text-[17px] font-semibold", ok ? "text-verified" : "text-blocked")}>{title}</p>
          <p className="mt-0.5 text-sm text-muted">{refusal ? (ok ? "Nothing was run against your data." : v.reason) : ok ? "Every value matched, ignoring column names, order and cents-level rounding." : v.reason}</p>
        </div>
      </div>
      <div className="space-y-3 p-5 pt-4">
        <div>
          <p className="text-sm font-semibold">Why this question is tricky</p>
          <p className="mt-0.5 text-sm text-muted">{v.trap}</p>
        </div>
        {hasGolden && (
          <div>
            <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="inline-flex cursor-pointer items-center gap-1.5 text-sm font-medium text-signal">
              <ChevronDown size={16} className={cx("transition-transform", open && "rotate-180")} />{open ? "Hide" : "Show"} the known answer
            </button>
            {open && (
              <div className="mt-3 space-y-3">
                <DataTable dense columns={asColumns(v.golden_columns!, v.golden_rows!)} rows={v.golden_rows!} />
                {v.golden_sql && <SqlCode sql={v.golden_sql.trim().replace(/\s+/g, " ")} className="whitespace-pre-wrap text-[12px]" />}
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

export function GuardChecklist({ r, meta }: { r: AskResult; meta: Meta | null }) {
  const items = [
    ["One statement, SELECT only", "Parsed into a syntax tree; anything that writes is rejected."],
    [`Tables allow-listed: ${r.tables.join(", ")}`, "System catalogs and unknown tables are refused."],
    [r.limit_applied ? `Row limit ${r.effective_limit?.toLocaleString("en-US")} added automatically` : `Row limit ${r.effective_limit} (the query's own)`, "Results can never be unbounded."],
    ["Ran in a read-only transaction", "Rolled back afterwards; nothing is ever committed."],
    [`Time limit ${meta ? `${meta.statement_timeout_ms.toLocaleString("en-US")} ms` : "enforced"}`, "Runaway queries are cancelled by Postgres."],
    ["Database role can only SELECT", "The last line of defense, independent of the app."],
  ];
  return (
    <Panel className="p-5">
      <div className="mb-3 flex items-center gap-2"><ShieldCheck size={18} className="text-verified" /><h3 className="font-semibold">Safety checks passed</h3></div>
      <ul className="space-y-2.5">
        {items.map(([t, d]) => (
          <li key={t} className="flex gap-2.5">
            <Check size={16} strokeWidth={3} className="mt-1 shrink-0 text-verified" />
            <div><p className="text-sm font-medium leading-snug">{t}</p><p className="text-[12.5px] text-faint">{d}</p></div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

const OUTCOME: Record<Attempt["outcome"], { tone: "verified" | "blocked" | "repaired" | "muted"; label: string }> = {
  ok: { tone: "verified", label: "Worked" },
  rejected_by_guard: { tone: "blocked", label: "Guard blocked it" },
  database_error: { tone: "blocked", label: "Database error" },
  timeout: { tone: "blocked", label: "Timed out" },
  suspicious_result: { tone: "repaired", label: "Suspicious result" },
  no_sql: { tone: "blocked", label: "No SQL in reply" },
  cannot_answer: { tone: "muted", label: "Declined" },
};

export function AttemptTrace({ attempts }: { attempts: Attempt[] }) {
  const retries = attempts.length - 1;
  return (
    <Panel className="p-5">
      <h3 className="font-semibold">{attempts.length === 1 ? "Worked on the first attempt" : `${attempts.length} attempts, ${retries} ${retries === 1 ? "repair" : "repairs"}`}</h3>
      {attempts.length > 1 && <p className="mt-0.5 text-sm text-muted">Each failure went back to the model as feedback.</p>}
      <ol className="mt-4 space-y-4">
        {attempts.map((a, i) => {
          const o = OUTCOME[a.outcome];
          return (
            <li key={a.number} className="relative flex gap-3">
              {i < attempts.length - 1 && <span className="absolute left-[13px] top-8 h-[calc(100%-4px)] w-px bg-line" aria-hidden />}
              <span className={cx("z-10 grid h-[27px] w-[27px] shrink-0 place-items-center rounded-full border text-[12px] font-semibold tnum",
                o.tone === "verified" ? "border-verified/60 text-verified" : o.tone === "blocked" ? "border-blocked/60 text-blocked" : o.tone === "repaired" ? "border-repaired/60 text-repaired" : "border-line text-muted", "bg-surface")}>
                {a.outcome === "ok" ? <Check size={14} strokeWidth={3} /> : a.outcome === "cannot_answer" ? <X size={14} /> : a.number}
              </span>
              <div className="min-w-0 flex-1">
                <Badge tone={o.tone}>{o.label}</Badge>
                {a.detail && <p className="mt-1.5 break-words text-sm text-muted">{a.detail}</p>}
                {a.outcome !== "ok" && (a.raw_sql ?? a.sql) && (
                  <details className="mt-1.5 text-sm">
                    <summary className="cursor-pointer text-faint hover:text-muted">The model's SQL</summary>
                    <SqlCode sql={(a.raw_sql ?? a.sql)!} className="mt-1.5 text-[12px]" />
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

export function ProofPanel({ r, meta }: { r: AskResult; meta: Meta | null }) {
  return (
    <div className="space-y-4">
      <VerificationCard v={r.verification} />
      {r.status === "ok" && <GuardChecklist r={r} meta={meta} />}
      <AttemptTrace attempts={r.attempts} />
    </div>
  );
}
