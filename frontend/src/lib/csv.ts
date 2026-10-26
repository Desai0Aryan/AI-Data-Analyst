import type { Cell, Column } from "./types";

const needsQuotes = /[",\n\r]/;
const esc = (v: Cell) => {
  if (v === null) return "";
  const s = String(v);
  return needsQuotes.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCSV(columns: Column[], rows: Cell[][]): string {
  return [columns.map((c) => esc(c.name)).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n") + "\n";
}

export function downloadCSV(filename: string, columns: Column[], rows: Cell[][]) {
  const url = URL.createObjectURL(new Blob([toCSV(columns, rows)], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
