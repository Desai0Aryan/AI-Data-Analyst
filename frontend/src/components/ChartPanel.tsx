import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { AXIS, GRID, NEGATIVE, POSITIVE, SERIES, buildChartData, makeXFormatter, signColor, switchableTypes } from "../lib/chartData";
import { compact, formatNumber, humanize } from "../lib/format";
import type { ChartSpec, ChartType, Column, Row } from "../lib/types";
import { Button, cx } from "./ui";

const tick = { fill: AXIS, fontSize: 12, fontFamily: "Spline Sans Mono Variable, ui-monospace, monospace" };

function CountUp({ value, column }: { value: number; column: string }) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce) { setV(value); return; }
    const controls = animate(0, value, { duration: 0.9, ease: "easeOut", onUpdate: setV });
    return () => controls.stop();
  }, [value, reduce]);
  return <span className="tnum">{formatNumber(Number.isInteger(value) ? Math.round(v) : v, column)}</span>;
}

function Kpis({ columns, rows, spec }: { columns: Column[]; rows: Row[]; spec: ChartSpec }) {
  const row = rows[0];
  const label = spec.x ? String(row[columns.findIndex((c) => c.name === spec.x)] ?? "") : "";
  return (
    <div>
      {label && <p className="mb-3 text-sm text-muted">{label}</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {spec.measures.map((m) => {
          const v = row[columns.findIndex((c) => c.name === m)];
          return (
            <div key={m} className="rounded-xl bg-sunken p-5">
              <p className="text-sm text-muted">{humanize(m)}</p>
              <p className={cx("mt-1 text-[40px] font-semibold leading-tight", typeof v === "number" && v < 0 && "text-blocked")}>
                {typeof v === "number" ? <CountUp value={v} column={m} /> : <span>{String(v ?? "NULL")}</span>}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Value label that sits beyond the bar's end, on the correct side for negative values. */
const barLabel = (measure: string, horizontal: boolean) => (props: any) => {
  const { x, y, width, height, value } = props;
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  const neg = Number(value) < 0;
  const common = { fill: "#eef0ff", fontSize: 12, fontFamily: tick.fontFamily } as const;
  if (horizontal) {
    const left = Math.min(x, x + width), right = Math.max(x, x + width);
    return <text x={neg ? left - 6 : right + 6} y={y + height / 2} dy="0.35em" textAnchor={neg ? "end" : "start"} {...common}>{compact(Number(value), measure)}</text>;
  }
  const top = Math.min(y, y + height), bottom = Math.max(y, y + height);
  return <text x={x + width / 2} y={neg ? bottom + 15 : top - 6} textAnchor="middle" {...common}>{compact(Number(value), measure)}</text>;
};

// Include zero and leave headroom so negative bars and their labels are never clipped.
const padded: [(min: number) => number, (max: number) => number] = [(min) => Math.min(0, min * 1.22), (max) => Math.max(0, max * 1.22)];

function ChartTooltip({ active, payload, label, fx }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-page px-3 py-2 text-sm shadow-lg">
      <p className="mb-1 font-semibold">{fx(label ?? payload[0]?.payload?.[payload[0]?.name] ?? payload[0].name)}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey ?? p.name} className="flex items-center gap-2 tnum">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color ?? p.payload?.fill ?? SERIES[0] }} />
          <span className="text-muted">{humanize(String(p.dataKey ?? p.name))}</span>
          <span className="ml-auto pl-3 font-mono">{typeof p.value === "number" ? formatNumber(p.value, String(p.dataKey ?? p.name)) : String(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export function ChartPanel({ columns, rows, spec, onShowTable }: { columns: Column[]; rows: Row[]; spec: ChartSpec; onShowTable: () => void }) {
  const options = useMemo(() => switchableTypes(spec), [spec]);
  const [type, setType] = useState<ChartType>(spec.type);
  const [measures, setMeasures] = useState<string[]>(spec.measures);
  useEffect(() => { setType(spec.type); setMeasures(spec.measures); }, [spec]);

  const data = useMemo(() => buildChartData(columns, rows), [columns, rows]);
  const xKey = spec.x ?? columns[0]?.name;
  const fx = useMemo(() => makeXFormatter(data.map((d) => d[xKey])), [data, xKey]);
  const m0 = measures[0];

  if (spec.type === "empty" || spec.type === "table") {
    return (
      <div className="flex flex-col items-start gap-3 py-6">
        <p className="text-sm text-muted">{spec.reason}</p>
        {spec.type === "table" && <Button onClick={onShowTable}>Open the table</Button>}
      </div>
    );
  }
  if (spec.type === "kpi") return <Kpis columns={columns} rows={rows} spec={spec} />;

  // Zero-inclusive padded domain only when negatives exist; positive-only charts keep Recharts' round ticks.
  const hasNegative = spec.diverging || rows.some((r) => measures.some((m) => { const v = r[columns.findIndex((c) => c.name === m)]; return typeof v === "number" && v < 0; }));
  const domain: any = hasNegative ? padded : [0, "auto"];

  const toggle = (m: string) => setMeasures((cur) => (cur.includes(m) ? (cur.length > 1 ? cur.filter((x) => x !== m) : cur) : [...cur, m]));
  const horizontal = type === "bar" && spec.horizontal;
  const labelled = rows.length <= 12 && measures.length === 1;
  const margin = { top: 16, right: horizontal ? 56 : 16, bottom: 4, left: 4 };

  const axes = (
    <>
      <CartesianGrid stroke={GRID} strokeDasharray="3 5" vertical={horizontal} horizontal={!horizontal} />
      {horizontal ? (
        <>
          <XAxis type="number" domain={domain} tick={tick} tickFormatter={(v) => compact(v, m0)} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey={xKey} tick={tick} width={150} axisLine={false} tickLine={false} tickFormatter={(v) => fx(v)} />
        </>
      ) : (
        <>
          <XAxis dataKey={xKey} tick={tick} tickFormatter={(v) => fx(v)} axisLine={{ stroke: GRID }} tickLine={false} interval="preserveStartEnd" padding={type === "bar" ? undefined : { left: 24, right: 24 }} />
          <YAxis domain={domain} tick={tick} tickFormatter={(v) => compact(v, m0)} axisLine={false} tickLine={false} width={64} />
        </>
      )}
      <Tooltip content={<ChartTooltip fx={fx} />} cursor={{ fill: "rgba(143,162,255,0.08)" }} />
      {measures.length > 1 && <Legend formatter={(v) => <span className="text-sm text-muted">{humanize(String(v))}</span>} />}
    </>
  );

  let chart: React.ReactElement;
  if (type === "line") {
    chart = (
      <LineChart data={data} margin={margin}>
        {axes}
        {measures.map((m, i) => <Line key={m} type="monotone" dataKey={m} stroke={SERIES[i % 6]} strokeWidth={2.5} dot={rows.length <= 24} activeDot={{ r: 5 }} isAnimationActive />)}
      </LineChart>
    );
  } else if (type === "area") {
    chart = (
      <AreaChart data={data} margin={margin}>
        <defs>{measures.map((m, i) => (
          <linearGradient key={m} id={`fill-${i}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES[i % 6]} stopOpacity={0.45} /><stop offset="100%" stopColor={SERIES[i % 6]} stopOpacity={0.02} />
          </linearGradient>))}
        </defs>
        {axes}
        {measures.map((m, i) => <Area key={m} type="monotone" dataKey={m} stroke={SERIES[i % 6]} strokeWidth={2.5} fill={`url(#fill-${i})`} />)}
      </AreaChart>
    );
  } else if (type === "pie") {
    chart = (
      <PieChart>
        <Tooltip content={<ChartTooltip fx={fx} />} />
        <Pie data={data} dataKey={m0} nameKey={xKey} innerRadius={78} outerRadius={128} paddingAngle={2} stroke="#1b1f48">
          {data.map((_, i) => <Cell key={i} fill={SERIES[i % 6]} />)}
        </Pie>
        <Legend formatter={(v) => <span className="text-sm text-muted">{fx(v)}</span>} />
      </PieChart>
    );
  } else if (type === "scatter") {
    chart = (
      <ScatterChart margin={margin}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 5" />
        <XAxis type="number" dataKey={xKey} name={humanize(xKey)} tick={tick} tickFormatter={(v) => compact(v, xKey)} axisLine={false} tickLine={false} />
        <YAxis type="number" dataKey={m0} name={humanize(m0)} tick={tick} tickFormatter={(v) => compact(v, m0)} axisLine={false} tickLine={false} width={64} />
        <Tooltip content={<ChartTooltip fx={fx} />} />
        <Scatter data={data} fill={SERIES[0]} />
      </ScatterChart>
    );
  } else {
    const diverge = spec.diverging && measures.length === 1;
    chart = (
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={margin} barCategoryGap="22%">
        {axes}
        {measures.map((m, i) => (
          <Bar key={m} dataKey={m} fill={diverge ? POSITIVE : SERIES[i % 6]} radius={horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0]} isAnimationActive>
            {diverge && data.map((d, k) => <Cell key={k} fill={signColor(d[m])} />)}
            {labelled && <LabelList dataKey={m} content={barLabel(m, horizontal)} />}
          </Bar>
        ))}
      </BarChart>
    );
  }

  const height = horizontal ? Math.max(300, rows.length * 46 + 40) : 360;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        {options.length > 1 && (
          <div className="flex gap-1.5" role="group" aria-label="Chart type">
            {options.map((t) => (
              <button key={t} onClick={() => setType(t)} aria-pressed={type === t}
                className={cx("cursor-pointer rounded-full border px-3 py-1 text-[13px] font-medium capitalize transition-colors",
                  type === t ? "border-signal/60 bg-signal/15 text-signal" : "border-line/70 text-muted hover:text-text")}>{t}</button>
            ))}
          </div>
        )}
        {spec.available_measures.length > 1 && type !== "pie" && type !== "scatter" && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Measures to plot">
            {spec.available_measures.map((m) => (
              <button key={m} onClick={() => toggle(m)} aria-pressed={measures.includes(m)}
                className={cx("cursor-pointer rounded-full border px-3 py-1 text-[13px] transition-colors",
                  measures.includes(m) ? "border-verified/50 bg-verified/10 text-verified" : "border-line/70 text-faint hover:text-muted")}>{humanize(m)}</button>
            ))}
          </div>
        )}
      </div>
      <div style={{ height }} role="img" aria-label={`${type} chart of ${measures.map(humanize).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>
      </div>
      <p className="mt-2 text-[13px] text-faint">{spec.reason}{spec.diverging && measures.length === 1 && <span> Red bars are decreases.</span>}</p>
      <span className="sr-only">{NEGATIVE}</span>
    </div>
  );
}
