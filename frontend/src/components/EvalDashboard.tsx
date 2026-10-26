import { motion, useReducedMotion } from "framer-motion";
import { Check, ChevronRight, FlaskConical, Loader2, X } from "lucide-react";
import { Fragment, useState } from "react";
import { ApiError, runEval } from "../lib/api";
import type { EvalCaseResult, EvalReport } from "../lib/types";
import { humanize } from "../lib/format";
import { SqlCode } from "./SqlBlock";
import { Button, Panel, cx } from "./ui";

function Gauge({ report, title, subtitle }: { report: EvalReport; title: string; subtitle: string }) {
  const reduce = useReducedMotion();
  const { passed, total, accuracy } = report.summary;
  const R = 54, C = 2 * Math.PI * R;
  const tone = accuracy >= 0.9 ? "#4de0a5" : accuracy >= 0.6 ? "#ffc857" : "#ff6b7a";
  return (
    <Panel className="flex items-center gap-6 p-6">
      <div className="relative h-[132px] w-[132px] shrink-0">
        <svg viewBox="0 0 132 132" className="-rotate-90" aria-hidden>
          <circle cx="66" cy="66" r={R} fill="none" stroke="#353c7d" strokeOpacity=".6" strokeWidth="11" />
          <motion.circle cx="66" cy="66" r={R} fill="none" stroke={tone} strokeWidth="11" strokeLinecap="round" strokeDasharray={C}
            initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: C * (1 - accuracy) }} transition={reduce ? { duration: 0 } : { duration: 1.2, ease: "easeOut" }} />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div><p className="text-[28px] font-semibold leading-none tnum">{passed}<span className="text-faint">/{total}</span></p><p className="mt-1 text-xs text-muted">{Math.round(accuracy * 100)}%</p></div>
        </div>
      </div>
      <div className="min-w-0">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mb-3 text-sm text-muted">{subtitle}</p>
        <dl className="grid grid-cols-[auto_auto] gap-x-5 gap-y-0.5 text-sm tnum">
          <dt className="text-muted">Right first try</dt><dd className="text-right font-mono">{report.summary.first_try_passes}</dd>
          <dt className="text-muted">Fixed by repair</dt><dd className="text-right font-mono">{report.summary.recovered_by_repair}</dd>
          <dt className="text-muted">Data changed</dt><dd className={cx("text-right font-mono", report.summary.database_integrity_ok ? "text-verified" : "text-blocked")}>{report.summary.database_integrity_ok ? "never" : "YES"}</dd>
        </dl>
      </div>
    </Panel>
  );
}

const Mark = ({ pass }: { pass: boolean }) => (
  <span className={cx("inline-grid h-6 w-6 place-items-center rounded-full", pass ? "bg-verified/15 text-verified" : "bg-blocked/15 text-blocked")} aria-label={pass ? "passed" : "failed"}>
    {pass ? <Check size={14} strokeWidth={3} /> : <X size={14} strokeWidth={3} />}
  </span>
);

function Detail({ good, bad }: { good: EvalCaseResult; bad: EvalCaseResult }) {
  return (
    <div className="space-y-3 bg-sunken/70 p-4">
      <div><p className="text-sm font-semibold">Why this question is tricky</p><p className="text-sm text-muted">{good.trap}</p></div>
      {!bad.passed && (
        <div><p className="text-sm font-semibold text-blocked">What the careless model got wrong</p><p className="text-sm text-muted">{bad.reason}</p></div>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        {good.golden_sql && <div><p className="mb-1 text-sm font-semibold">Known answer</p><SqlCode sql={good.golden_sql.trim().replace(/\s+/g, " ")} className="whitespace-pre-wrap text-[12px]" /></div>}
        {!bad.passed && bad.generated_sql && <div><p className="mb-1 text-sm font-semibold">Careless model's SQL</p><SqlCode sql={bad.generated_sql} className="whitespace-pre-wrap text-[12px]" /></div>}
      </div>
    </div>
  );
}

export function EvalDashboard() {
  const [reports, setReports] = useState<{ reference: EvalReport; naive: EvalReport } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [onlyDiff, setOnlyDiff] = useState(false);

  const run = async () => {
    setBusy(true); setError(null); setOpen(null);
    try {
      const [reference, naive] = await Promise.all([runEval("reference"), runEval("naive")]);
      setReports({ reference, naive });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail.message : "The evaluation could not run.");
    } finally { setBusy(false); }
  };

  const naiveById = new Map(reports?.naive.results.map((r) => [r.id, r]));
  const rows = reports?.reference.results.filter((r) => !onlyDiff || !naiveById.get(r.id)?.passed) ?? [];
  const categories = reports ? Object.keys(reports.reference.by_category) : [];

  return (
    <div className="space-y-6">
      <div className="max-w-2xl">
        <h2 className="text-2xl font-semibold">How do we know the answers are right?</h2>
        <p className="mt-2 text-muted">
          26 questions with known-correct SQL. Results are compared by value, not by SQL text. To prove the test can fail, the same suite
          grades two recorded models: a careful one and a careless one that falls into every trap. Nothing here calls a paid LLM.
        </p>
        <Button variant="primary" className="mt-4" onClick={run} disabled={busy}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />}{reports ? "Run it again" : "Run the evaluation"}
        </Button>
        {error && <p role="alert" className="mt-3 text-sm text-blocked">{error}</p>}
      </div>

      {reports && (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <Gauge report={reports.reference} title="Careful model" subtitle="Writes correct SQL; a few first tries are repaired." />
            <Gauge report={reports.naive} title="Careless model" subtitle="Plausible SQL that falls into the traps." />
          </div>

          <Panel className="p-5">
            <h3 className="mb-3 font-semibold">By category</h3>
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
              {categories.map((c) => {
                const a = reports.reference.by_category[c], b = reports.naive.by_category[c];
                return (
                  <div key={c}>
                    <div className="mb-1 flex justify-between text-sm"><span>{humanize(c)}</span><span className="font-mono text-muted tnum">{a.passed}/{a.total} · {b.passed}/{b.total}</span></div>
                    <div className="space-y-1">
                      <div className="h-1.5 overflow-hidden rounded-full bg-sunken"><motion.div className="h-full bg-verified" initial={{ width: 0 }} animate={{ width: `${(a.passed / a.total) * 100}%` }} /></div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-sunken"><motion.div className={cx("h-full", b.passed === b.total ? "bg-verified" : "bg-blocked")} initial={{ width: 0 }} animate={{ width: `${(b.passed / b.total) * 100}%` }} /></div>
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 text-[13px] text-faint">Top bar: careful model. Bottom bar: careless model.</p>
          </Panel>

          <Panel className="overflow-hidden">
            <div className="flex items-center justify-between p-5 pb-3">
              <h3 className="font-semibold">Every question</h3>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-muted"><input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} className="accent-[#8fa2ff]" />Only where the careless model fails</label>
            </div>
            <table className="w-full text-sm">
              <thead className="border-y border-line/50 bg-raised/50 text-left text-muted"><tr><th className="px-5 py-2 font-medium">Question</th><th className="px-3 py-2 text-center font-medium">Careful</th><th className="px-3 py-2 text-center font-medium">Careless</th></tr></thead>
              <tbody>
                {rows.map((g) => {
                  const b = naiveById.get(g.id)!;
                  const isOpen = open === g.id;
                  return (
                    <Fragment key={g.id}>
                      <tr onClick={() => setOpen(isOpen ? null : g.id)} className={cx("cursor-pointer border-b border-line/30 hover:bg-raised/50", !b.passed && "bg-blocked/[0.05]")}>
                        <td className="px-5 py-2.5">
                          <span className="flex items-center gap-2"><ChevronRight size={15} className={cx("shrink-0 text-faint transition-transform", isOpen && "rotate-90")} /><span>{g.question}</span></span>
                          <span className="ml-[23px] text-[12.5px] text-faint">{humanize(g.category)} · {g.id}</span>
                        </td>
                        <td className="px-3 text-center"><Mark pass={g.passed} /></td>
                        <td className="px-3 text-center"><Mark pass={b.passed} /></td>
                      </tr>
                      {isOpen && <tr><td colSpan={3} className="p-0"><Detail good={g} bad={b} /></td></tr>}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </div>
  );
}
