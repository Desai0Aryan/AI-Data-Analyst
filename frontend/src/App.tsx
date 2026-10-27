import { AnimatePresence, motion } from "framer-motion";
import { Database, FlaskConical, Layers, MessageSquareText, ShieldAlert } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { AskBar } from "./components/AskBar";
import { PipelineLine } from "./components/PipelineLine";
import { Results } from "./components/Results";
import { Badge, Panel, cx } from "./components/ui";
import { getMeta } from "./lib/api";
import { clearHistory, loadHistory, pushHistory, type HistoryItem } from "./lib/history";
import { useAsk } from "./lib/useAsk";
import type { Meta } from "./lib/types";

const EvalDashboard = lazy(() => import("./components/EvalDashboard").then((m) => ({ default: m.EvalDashboard })));
const SecurityLab = lazy(() => import("./components/SecurityLab").then((m) => ({ default: m.SecurityLab })));
const SchemaExplorer = lazy(() => import("./components/SchemaExplorer").then((m) => ({ default: m.SchemaExplorer })));

type View = "analyst" | "eval" | "lab" | "schema";
const NAV: { id: View; label: string; icon: React.ReactNode }[] = [
  { id: "analyst", label: "Analyst", icon: <MessageSquareText size={16} /> },
  { id: "eval", label: "Evaluation", icon: <FlaskConical size={16} /> },
  { id: "lab", label: "Security lab", icon: <ShieldAlert size={16} /> },
  { id: "schema", label: "Schema", icon: <Layers size={16} /> },
];

const longDate = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="#242a5c" />
      <path d="M8 17.5l5.2 5L24 10" fill="none" stroke="#4de0a5" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const HINTS: Record<string, string> = {
  not_configured: "Set LLM_API_KEY in your .env file, or set LLM_PROVIDER=replay to use the recorded demo.",
  unreachable: "Start the backend (docker compose up -d, or uvicorn app.main:app) and try again.",
  unavailable: "Postgres isn't reachable. Check the db container.",
  rate_limited: "This demo limits how fast questions can be asked. Wait a few seconds and try again.",
  budget_exhausted: "The daily question budget for this demo is used up. Run it locally, or use the keyless demo mode.",
};

export default function App() {
  const [view, setView] = useState<View>("analyst");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [labSql, setLabSql] = useState<string | undefined>();
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory());
  const [focusSignal, setFocusSignal] = useState(0);
  const { state, run, reset } = useAsk();
  const logged = useRef<unknown>(null);

  useEffect(() => { getMeta().then(setMeta).catch(() => setMeta(null)); }, []);

  useEffect(() => {
    const r = state.result;
    if (state.phase === "done" && r && logged.current !== r) {
      logged.current = r;
      setHistory((h) => pushHistory(h, { question: r.question, status: r.status, at: Date.now(), rows: r.row_count }));
    }
  }, [state.phase, state.result]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
      if (e.key === "/" && !typing) { e.preventDefault(); setView("analyst"); setFocusSignal((n) => n + 1); }
      if (e.key === "Escape" && state.phase === "running") reset();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, reset]);

  const openInLab = useCallback((sql: string) => { setLabSql(sql); setView("lab"); }, []);
  const busy = state.phase === "running";

  return (
    <div className="mx-auto flex min-h-full max-w-[1280px] flex-col px-4 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-5">
        <div className="flex items-center gap-2.5"><Logo /><span className="text-[22px] font-semibold tracking-tight">Verity</span></div>
        <nav aria-label="Sections" className="order-3 flex w-full justify-between gap-1 overflow-x-auto sm:order-none sm:w-auto sm:justify-start">
          {NAV.map((n) => (
            <button key={n.id} onClick={() => setView(n.id)} aria-current={view === n.id ? "page" : undefined} aria-label={n.label}
              className={cx("inline-flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-[10px] px-3.5 py-2 text-[15px] font-medium transition-colors",
                view === n.id ? "bg-raised text-text" : "text-muted hover:text-text")}>{n.icon}<span className={cx(view !== n.id && "max-[480px]:hidden")}>{n.label}</span></button>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          {meta?.demo ? <Badge tone="repaired" title="Answers come from recorded replies, not a live model">Demo mode: recorded answers</Badge>
            : meta ? <Badge tone="verified" className="font-mono">{meta.provider}</Badge>
            : <Badge tone="blocked">API offline</Badge>}
        </div>
      </header>

      <main className="flex-1 pb-16">
        {view === "analyst" && (
          <div className="space-y-6">
            <AnimatePresence initial={false}>
              {state.phase === "idle" && (
                <motion.div key="hero" className="max-w-3xl overflow-hidden pt-2" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.35 }}>
                  <h1 className="text-[clamp(30px,4.6vw,46px)] font-semibold leading-[1.08] tracking-tight">Ask in plain English. Get an answer you can check.</h1>
                  <p className="mt-3 max-w-2xl text-[17px] text-muted">
                    Verity writes the SQL, runs it in a read-only sandbox, and shows its work.
                    {meta && <> In this dataset, today is <span className="text-text">{longDate(meta.reference_date)}</span>, so "last quarter" means Q4 2025.</>}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            <AskBar examples={meta?.examples ?? []} busy={busy} onAsk={run} onStop={reset} history={history}
              onClearHistory={() => { clearHistory(); setHistory([]); }} focusSignal={focusSignal} />

            <Panel className="px-3 pb-4 pt-6 sm:px-6"><PipelineLine state={state} /></Panel>

            {state.phase === "error" && state.error && (
              <Panel className="border-blocked/50 p-5" role="alert">
                <p className="font-semibold text-blocked">{state.error.message}</p>
                <p className="mt-1 text-sm text-muted">{HINTS[state.error.code] ?? "Try again in a moment."}</p>
              </Panel>
            )}

            {state.result && <Results r={state.result} meta={meta} explanation={state.explanation} explaining={state.explaining} onOpenInLab={openInLab} />}

            {state.phase === "idle" && (
              <p className="flex items-center gap-2 text-sm text-faint"><Database size={15} />Pick an example or type your own. The red one is a prompt-injection attempt: watch the guard refuse it.</p>
            )}
          </div>
        )}
        <Suspense fallback={<p className="py-10 text-center text-faint" role="status">Loading…</p>}>
          {view === "eval" && <EvalDashboard />}
          {view === "lab" && <SecurityLab initialSql={labSql} />}
          {view === "schema" && <SchemaExplorer />}
        </Suspense>
      </main>

      <footer className="border-t border-line/40 py-5 text-[13px] text-faint">
        Read-only Postgres · SQL parsed with SQLGlot · results compared with known answers
        {meta && <> · up to {meta.max_rows.toLocaleString("en-US")} rows, {meta.statement_timeout_ms.toLocaleString("en-US")} ms</>}
      </footer>
    </div>
  );
}
