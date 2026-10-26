import { ArrowDown, ArrowUp, Check, Copy, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { downloadCSV, toCSV } from "../lib/csv";
import { formatCell, humanize, isNumericType, plural } from "../lib/format";
import type { Cell, Column, Row } from "../lib/types";
import { Button, cx } from "./ui";

const PAGE = 100;

function compare(a: Cell, b: Cell): number {
  if (a === b) return 0;
  if (a === null) return 1;              // NULLs always last
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function DataTable({ columns, rows, filename = "result.csv", dense = false, highlight }: {
  columns: Column[]; rows: Row[]; filename?: string; dense?: boolean; highlight?: (row: Row, i: number) => boolean;
}) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [all, setAll] = useState(false);
  const [copied, setCopied] = useState(false);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      const x = a[sort.col], y = b[sort.col];
      if (x === null || y === null) return compare(x, y);       // keep NULLs last in both directions
      return compare(x, y) * sort.dir;
    });
  }, [rows, sort]);
  const shown = all ? sorted : sorted.slice(0, PAGE);

  const clickHeader = (i: number) =>
    setSort((s) => (!s || s.col !== i ? { col: i, dir: 1 } : s.dir === 1 ? { col: i, dir: -1 } : null));

  const copy = async () => {
    try { await navigator.clipboard.writeText(toCSV(columns, rows)); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch { /* clipboard blocked */ }
  };

  return (
    <div>
      {!dense && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-sm text-muted tnum">{plural(rows.length, "row")}{rows.length > PAGE && !all && `, showing ${PAGE}`}</p>
          <div className="flex gap-2">
            <Button onClick={copy} aria-label="Copy as CSV">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copied" : "Copy"}</Button>
            <Button onClick={() => downloadCSV(filename, columns, rows)}><Download size={15} />CSV</Button>
          </div>
        </div>
      )}
      <div className="scroll-thin max-h-[440px] overflow-auto rounded-xl border border-line/60">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-raised">
            <tr>
              {columns.map((c, i) => {
                const num = isNumericType(c.type);
                const active = sort?.col === i;
                return (
                  <th key={c.name} aria-sort={active ? (sort!.dir === 1 ? "ascending" : "descending") : "none"} className={cx("whitespace-nowrap px-3.5 py-2.5 font-semibold", num ? "text-right" : "text-left")}>
                    <button onClick={() => clickHeader(i)} className={cx("inline-flex cursor-pointer items-center gap-1.5", active ? "text-signal" : "text-text")}>
                      {humanize(c.name)}
                      {active ? (sort!.dir === 1 ? <ArrowUp size={13} /> : <ArrowDown size={13} />) : <span className="w-[13px]" />}
                    </button>
                    <span className="block text-[11px] font-normal text-faint">{c.type}</span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, ri) => (
              <tr key={ri} className={cx("border-t border-line/40 hover:bg-raised/60", highlight?.(r, ri) && "bg-blocked/10")}>
                {r.map((v, ci) => {
                  const num = isNumericType(columns[ci].type);
                  return (
                    <td key={ci} className={cx("px-3.5 tnum", dense ? "py-1.5" : "py-2", num ? "text-right font-mono" : "text-left", sort?.col === ci && "bg-signal/5")}>
                      {v === null ? <span className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[11px] italic text-faint">NULL</span> : formatCell(v, columns[ci].name)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > PAGE && (
        <button onClick={() => setAll((a) => !a)} className="mt-3 cursor-pointer text-sm text-signal hover:underline">
          {all ? `Show the first ${PAGE}` : `Show all ${rows.length.toLocaleString("en-US")} rows`}
        </button>
      )}
    </div>
  );
}
