import type { Cell } from "./types";

const MONEY = /revenue|amount|price|cost|sales|value|spend|margin_amt|lost|change|delta|diff/i;
const PERCENT = /pct|percent|growth|rate|share/i;
const COUNT = /count|^n$|orders|customers|units|quantity|rows/i;

export type NumberKind = "money" | "percent" | "count" | "plain";

export function numberKind(column: string): NumberKind {
  if (PERCENT.test(column)) return "percent";
  if (COUNT.test(column) && !MONEY.test(column)) return "count";
  if (MONEY.test(column)) return "money";
  return "plain";
}

export function isNumericType(type: string): boolean {
  return ["int2", "int4", "int8", "numeric", "float4", "float8", "money"].includes(type);
}

export function formatNumber(value: number, column = ""): string {
  const kind = numberKind(column);
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (kind === "percent") return `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  if (kind === "money") {
    return `${sign}$${abs.toLocaleString("en-US", { minimumFractionDigits: Number.isInteger(abs) ? 0 : 2, maximumFractionDigits: 2 })}`;
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function formatCell(value: Cell, column = ""): string {
  if (value === null) return "NULL";
  if (typeof value === "number") return formatNumber(value, column);
  if (typeof value === "boolean") return value ? "true" : "false";
  return value;
}

export function compact(value: number, column = ""): string {
  const kind = numberKind(column);
  const body = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(Math.abs(value));
  const sign = value < 0 ? "-" : "";
  if (kind === "money") return `${sign}$${body}`;
  if (kind === "percent") return `${value}%`;
  return `${sign}${body}`;
}

/** "prev_quarter_revenue" -> "Prev quarter revenue" */
export function humanize(column: string): string {
  const s = column.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function plural(n: number, one: string, many = one + "s"): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}
