import { ChartColumn, CircleAlert, Code, Table2 } from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";
import type { AskResult, Meta } from "../lib/types";
import { DataTable } from "./DataTable";
import { ProofPanel } from "./ProofPanel";
import { SqlPanel, lastWritten } from "./SqlPanel";
import { Badge, Panel, Tabs } from "./ui";

// Recharts is the heaviest dependency; load it only when a chart is actually shown.
const ChartPanel = lazy(() => import("./ChartPanel").then((m) => ({ default: m.ChartPanel })));

type Tab = "chart" | "table" | "sql";

export function Results({ r, meta, onOpenInLab }: { r: AskResult; meta: Meta | null; onOpenInLab: (sql: string) => void }) {
  const [tab, setTab] = useState<Tab>("chart");
  useEffect(() => { setTab(r.chart?.type === "table" ? "table" : "chart"); }, [r]);
  const ok = r.status === "ok" && r.chart;

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
      <Panel className="p-5 sm:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold leading-snug">{r.question}</h2>
            {ok && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge className="tnum">{r.row_count.toLocaleString("en-US")} {r.row_count === 1 ? "row" : "rows"}</Badge>
                <Badge className="tnum">{r.elapsed_ms} ms</Badge>
                {r.model && <Badge className="font-mono">{r.model}</Badge>}
                {r.warnings.filter((w) => !w.startsWith("LIMIT")).map((w) => <Badge key={w} tone="repaired">{w}</Badge>)}
              </div>
            )}
          </div>
          {ok && (
            <Tabs<Tab> label="Result view" value={tab} onChange={setTab} items={[
              { id: "chart", label: "Chart", icon: <ChartColumn size={15} /> },
              { id: "table", label: "Table", icon: <Table2 size={15} /> },
              { id: "sql", label: "SQL", icon: <Code size={15} /> },
            ]} />
          )}
        </div>

        {ok ? (
          <>
            {tab === "chart" && (
              <Suspense fallback={<div className="grid h-[300px] place-items-center text-sm text-faint" role="status">Drawing the chart…</div>}>
                <ChartPanel columns={r.columns} rows={r.rows} spec={r.chart!} onShowTable={() => setTab("table")} />
              </Suspense>
            )}
            {tab === "table" && <DataTable columns={r.columns} rows={r.rows} filename="verity-result.csv" />}
            {tab === "sql" && r.sql && (
              <SqlPanel executed={r.pretty_sql ?? r.sql} written={lastWritten(r.attempts)} tables={r.tables}
                limitApplied={r.limit_applied} limit={r.effective_limit} onOpenInLab={onOpenInLab} />
            )}
          </>
        ) : (
          <div className="flex gap-3 rounded-xl bg-sunken p-5">
            <CircleAlert className="mt-0.5 shrink-0 text-repaired" size={22} />
            <div>
              <p className="font-semibold">{r.status === "cannot_answer" ? "Verity declined to answer" : "No working query after " + r.attempts.length + " attempts"}</p>
              <p className="mt-1 text-sm text-muted">{r.message ?? "The request could not be answered from this database."}</p>
            </div>
          </div>
        )}
      </Panel>
      <ProofPanel r={r} meta={meta} />
    </div>
  );
}
