import { KeyRound, Link2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getSchema } from "../lib/api";
import { foreignKeys, placeTables, primaryKey } from "../lib/schemaLayout";
import type { SchemaInfo } from "../lib/types";
import { Badge, Empty, Panel, cx } from "./ui";

const W = 900, H = 290, NW = 176, NH = 58;

function Map({ schema, hover, setHover }: { schema: SchemaInfo; hover: string | null; setHover: (n: string | null) => void }) {
  const placed = useMemo(() => placeTables(schema.tables, W, H, NW, NH), [schema]);
  const pos = new window.Map(placed.map((p) => [p.name, p]));
  const edges = foreignKeys(schema.tables);
  return (
    <svg viewBox={`-10 -6 ${W + 20} ${H + 12}`} className="w-full" role="img" aria-label="How the tables relate to each other">
      {edges.map((e) => {
        const a = pos.get(e.from)!, b = pos.get(e.to)!;
        const x1 = a.x, y1 = a.y + NH / 2, x2 = b.x + NW, y2 = b.y + NH / 2;
        const mx = (x1 + x2) / 2;
        const lit = hover === e.from || hover === e.to;
        return (
          <g key={`${e.from}.${e.fromCol}`} opacity={hover && !lit ? 0.25 : 1}>
            <path d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`} fill="none" stroke={lit ? "#8fa2ff" : "#353c7d"} strokeWidth={lit ? 2.5 : 1.8} />
            <text x={x2 + 10} y={y2 - 7} textAnchor="start" fontSize="11" fill="#a3aadc" fontFamily="Spline Sans Mono Variable, monospace">{e.fromCol}</text>
          </g>
        );
      })}
      {schema.tables.map((t) => {
        const p = pos.get(t.name)!;
        const lit = hover === t.name;
        return (
          <g key={t.name} transform={`translate(${p.x} ${p.y})`} onMouseEnter={() => setHover(t.name)} onMouseLeave={() => setHover(null)} style={{ cursor: "default" }}>
            <rect width={NW} height={NH} rx="10" fill={lit ? "#242a5c" : "#1b1f48"} stroke={lit ? "#8fa2ff" : "#353c7d"} strokeWidth="1.5" />
            <text x="14" y="26" fontSize="15" fontWeight="600" fill="#eef0ff" fontFamily="Bricolage Grotesque Variable, sans-serif">{t.name}</text>
            <text x="14" y="44" fontSize="12" fill="#a3aadc" fontFamily="Bricolage Grotesque Variable, sans-serif">{t.columns.length} columns</text>
          </g>
        );
      })}
    </svg>
  );
}

export function SchemaExplorer() {
  const [schema, setSchema] = useState<SchemaInfo | null>(null);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  useEffect(() => { getSchema().then(setSchema).catch(() => setError(true)); }, []);

  if (error) return <Panel><Empty title="Couldn't load the schema">Check that the API is running.</Empty></Panel>;
  if (!schema) return <Panel><Empty title="Loading the schema…" /></Panel>;
  const fks = foreignKeys(schema.tables);

  return (
    <div className="space-y-6">
      <div className="max-w-2xl">
        <h2 className="text-2xl font-semibold">What the model can see</h2>
        <p className="mt-2 text-muted">This is read from Postgres at runtime, including column comments and the real values of low-cardinality text columns. It is exactly what goes into the model's prompt, which is why it knows that an order status is <span className="font-mono text-text">completed</span>, not "complete".</p>
      </div>
      <Panel className="p-4"><Map schema={schema} hover={hover} setHover={setHover} /></Panel>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {schema.tables.map((t) => {
          const pk = primaryKey(t);
          return (
            <Panel key={t.name} className={cx("p-5 transition-colors", hover === t.name && "border-signal/70")} onMouseEnter={() => setHover(t.name)} onMouseLeave={() => setHover(null)}>
              <h3 className="font-mono text-base font-semibold">{t.name}</h3>
              {t.comment && <p className="mt-1 text-[13px] text-muted">{t.comment}</p>}
              <ul className="mt-3 space-y-2">
                {t.columns.map((c) => {
                  const fk = fks.find((e) => e.from === t.name && e.fromCol === c.name);
                  return (
                    <li key={c.name} className="text-sm">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="font-mono">{c.name}</span>
                        <span className="font-mono text-[12px] text-faint">{c.type}</span>
                        {pk.includes(c.name) && <Badge tone="repaired"><KeyRound size={11} />key</Badge>}
                        {fk && <Badge tone="signal"><Link2 size={11} />{fk.to}</Badge>}
                        {c.nullable && <Badge>may be NULL</Badge>}
                      </div>
                      {c.comment && <p className="text-[12.5px] text-faint">{c.comment}</p>}
                      {c.sample_values.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{c.sample_values.map((v) => <span key={v} className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[11.5px] text-muted">{v}</span>)}</div>}
                    </li>
                  );
                })}
              </ul>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
