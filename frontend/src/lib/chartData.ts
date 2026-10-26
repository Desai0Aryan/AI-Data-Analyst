import type { ChartSpec, Column, Row } from "./types";

// Hex (not CSS vars): SVG presentation attributes and canvas exports are more predictable with literals.
export const SERIES = ["#8fa2ff", "#4de0a5", "#ffc857", "#ff8fc7", "#5fd0ff", "#c3a0ff"];
export const POSITIVE = "#4de0a5";
export const NEGATIVE = "#ff6b7a";
export const AXIS = "#a3aadc";
export const GRID = "rgba(143,162,255,0.14)";

export const signColor = (v: unknown) => (typeof v === "number" && v < 0 ? NEGATIVE : POSITIVE);

/** Turn the tabular result into the array-of-objects shape Recharts wants. */
export function buildChartData(columns: Column[], rows: Row[]): Record<string, string | number | boolean | null>[] {
  return rows.map((r) => Object.fromEntries(columns.map((c, i) => [c.name, r[i]])));
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2025-08-01" -> "Aug 2025" when every date is a first-of-month, else "Aug 5". Non-dates pass through. */
export function makeXFormatter(values: unknown[]): (v: unknown) => string {
  const iso = /^(\d{4})-(\d{2})-(\d{2})/;
  const dates = values.filter((v): v is string => typeof v === "string" && iso.test(v));
  const allDates = dates.length === values.length && values.length > 0;
  const monthly = allDates && dates.every((d) => d.slice(8, 10) === "01");
  return (v) => {
    const m = typeof v === "string" ? iso.exec(v) : null;
    if (!m || !allDates) return String(v ?? "");
    const mon = MONTHS[Number(m[2]) - 1];
    return monthly ? `${mon} ${m[1]}` : `${mon} ${Number(m[3])}`;
  };
}

/** Which chart types the switcher should offer (table/kpi/empty are handled outside the chart canvas). */
export function switchableTypes(spec: ChartSpec) {
  return [spec.type, ...spec.alternatives].filter((t, i, a) => a.indexOf(t) === i && ["bar", "line", "area", "pie", "scatter"].includes(t));
}
