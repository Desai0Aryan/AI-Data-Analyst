import { Loader2, ShieldAlert, ShieldCheck, Swords } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, executeSql, probe } from "../lib/api";
import type { ApiErrorDetail, ProbeResult, SqlResult } from "../lib/types";
import { DataTable } from "./DataTable";
import { SqlCode } from "./SqlBlock";
import { Badge, Button, Panel, cx } from "./ui";

const LAYERS = [
  { id: "guard", title: "SQL guard", text: "Parses the query into a syntax tree and allows only SELECT on known tables." },
  { id: "transaction", title: "Read-only transaction", text: "Skips the guard on purpose: Postgres still refuses to write." },
  { id: "privileges", title: "Least-privilege role", text: "Forces a read-write transaction: the role has no write permission anyway." },
  { id: "timeout", title: "Statement timeout", text: "A runaway cross join is cancelled by the database after 100 ms here." },
] as const;

function ProbeCard({ layer, result, busy, onRun }: { layer: (typeof LAYERS)[number]; result?: ProbeResult; busy: boolean; onRun: () => void }) {
  return (
    <Panel className={cx("p-5 transition-colors", result?.blocked && "border-blocked/40")}>
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="font-semibold">{layer.title}</h3><p className="mt-0.5 text-sm text-muted">{layer.text}</p></div>
        <Button variant="danger" onClick={onRun} disabled={busy} className="shrink-0">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Swords size={15} />}Attack
        </Button>
      </div>
      {result && (
        <div className="mt-3 space-y-2" role="status">
          <SqlCode sql={result.statement} className="py-2 text-[12px]" />
          <div className={cx("flex items-start gap-2 rounded-lg p-3 text-sm", result.blocked ? "bg-blocked/10 text-blocked" : "bg-repaired/15 text-repaired")}>
            <ShieldAlert size={18} className="mt-0.5 shrink-0" />
            <div><p className="font-semibold">{result.blocked ? `Blocked by: ${result.blocked_by}` : "Not blocked"}</p><p className="break-words text-[13px] opacity-90">{result.error}</p></div>
            <span className="ml-auto shrink-0 font-mono text-xs tnum">{result.elapsed_ms} ms</span>
          </div>
        </div>
      )}
    </Panel>
  );
}

const PRESETS: { label: string; sql: string; hostile?: boolean }[] = [
  { label: "Revenue by country", sql: "SELECT c.country, ROUND(SUM(oi.quantity * oi.unit_price * (1 - COALESCE(oi.discount, 0))), 2) AS revenue\nFROM order_items oi\nJOIN orders o ON o.id = oi.order_id\nJOIN customers c ON c.id = o.customer_id\nWHERE o.status = 'completed'\nGROUP BY c.country\nORDER BY revenue DESC" },
  { label: "DROP TABLE", sql: "DROP TABLE orders", hostile: true },
  { label: "Hidden DELETE", sql: "WITH gone AS (DELETE FROM orders RETURNING *)\nSELECT * FROM gone", hostile: true },
  { label: "Stacked statements", sql: "SELECT 1; DELETE FROM customers", hostile: true },
  { label: "Read pg_shadow", sql: "SELECT usename, passwd FROM pg_shadow", hostile: true },
  { label: "pg_sleep", sql: "SELECT pg_sleep(60)", hostile: true },
];

export function SecurityLab({ initialSql }: { initialSql?: string }) {
  const [results, setResults] = useState<Record<string, ProbeResult>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [sql, setSql] = useState(initialSql ?? PRESETS[0].sql);
  const [out, setOut] = useState<{ ok: SqlResult } | { blocked: ApiErrorDetail } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (initialSql) { setSql(initialSql); setOut(null); } }, [initialSql]);

  const attack = async (id: (typeof LAYERS)[number]["id"]) => {
    setRunning(id);
    try { const r = await probe(id); setResults((cur) => ({ ...cur, [id]: r })); }
    catch (e) { setResults((cur) => ({ ...cur, [id]: { layer: id, statement: "", blocked: false, blocked_by: "Request failed", error: e instanceof Error ? e.message : "", elapsed_ms: 0 } })); }
    finally { setRunning(null); }
  };
  const attackAll = async () => { for (const l of LAYERS) { await attack(l.id); await new Promise((r) => setTimeout(r, 250)); } };

  const run = async () => {
    setBusy(true);
    try { setOut({ ok: await executeSql(sql) }); }
    catch (e) { setOut({ blocked: e instanceof ApiError ? e.detail : { stage: "client", code: "error", message: "Request failed." } }); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid items-start gap-6 xl:grid-cols-2">
      <div className="space-y-4">
        <div className="max-w-xl">
          <h2 className="text-2xl font-semibold">Try to break it</h2>
          <p className="mt-2 text-muted">Four independent defenses stand between the model and your data. Each attack below goes straight at one of them, with the others out of the way. Every statement is fixed on the server and cannot change a row.</p>
          <Button variant="danger" className="mt-3" onClick={attackAll} disabled={running !== null}><Swords size={15} />Attack all four</Button>
        </div>
        {LAYERS.map((l) => <ProbeCard key={l.id} layer={l} result={results[l.id]} busy={running === l.id} onRun={() => attack(l.id)} />)}
      </div>

      <div className="space-y-4">
        <div className="max-w-xl">
          <h2 className="text-2xl font-semibold">SQL lab</h2>
          <p className="mt-2 text-muted">Write your own SQL. It goes through the same guard as the model's queries.</p>
        </div>
        <Panel className="p-5">
          <div className="mb-3 flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button key={p.label} onClick={() => { setSql(p.sql); setOut(null); }}
                className={cx("cursor-pointer rounded-full border px-3 py-1 text-[13px] transition-colors", p.hostile ? "border-blocked/40 text-blocked hover:bg-blocked/10" : "border-line/80 text-muted hover:text-text")}>{p.label}</button>
            ))}
          </div>
          <label htmlFor="sql-lab" className="sr-only">SQL query</label>
          <textarea id="sql-lab" value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false} rows={8}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); run(); } }}
            className="scroll-thin w-full resize-y rounded-xl border border-line/60 bg-sunken p-4 font-mono text-[13px] leading-relaxed outline-none focus:border-signal" />
          <div className="mt-3 flex items-center gap-3">
            <Button variant="primary" onClick={run} disabled={busy || !sql.trim()}>{busy ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />}Run through the guard</Button>
            <span className="text-[13px] text-faint">Ctrl or ⌘ + Enter</span>
          </div>
        </Panel>

        {out && "blocked" in out && (
          <Panel className="border-blocked/50 p-5" role="alert">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 shrink-0 text-blocked" size={22} />
              <div>
                <p className="font-semibold text-blocked">Rejected{out.blocked.stage === "guard" ? " by the SQL guard" : ""}</p>
                <p className="mt-1 text-sm text-muted">{out.blocked.message}</p>
                <Badge tone="blocked" className="mt-2 font-mono">{out.blocked.stage}.{out.blocked.code}</Badge>
              </div>
            </div>
          </Panel>
        )}
        {out && "ok" in out && (
          <Panel className="space-y-3 p-5">
            <div className="flex flex-wrap gap-2">
              <Badge tone="verified">Allowed</Badge>
              <Badge className="tnum">{out.ok.row_count} rows, {out.ok.elapsed_ms} ms</Badge>
              {out.ok.limit_applied && <Badge tone="repaired">LIMIT {out.ok.effective_limit} added</Badge>}
            </div>
            <DataTable dense columns={out.ok.columns} rows={out.ok.rows.slice(0, 50)} />
          </Panel>
        )}
      </div>
    </div>
  );
}
