import type { SchemaTable } from "./types";

export type Edge = { from: string; fromCol: string; to: string; toCol: string };

/** Parses "FOREIGN KEY (a) REFERENCES t(b)" constraint strings. */
export function foreignKeys(tables: SchemaTable[]): Edge[] {
  const re = /FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)/i;
  return tables.flatMap((t) =>
    t.constraints.flatMap((c) => {
      const m = re.exec(c);
      return m ? [{ from: t.name, fromCol: m[1], to: m[2], toCol: m[3] }] : [];
    }),
  );
}

export function primaryKey(table: SchemaTable): string[] {
  const c = table.constraints.find((x) => /^PRIMARY KEY/i.test(x));
  const m = c && /\(([^)]+)\)/.exec(c);
  return m ? m[1].split(",").map((s) => s.trim()) : [];
}

/** Layer 0 = tables nothing points away from (customers, categories); children sit one layer right of their parents. */
export function layers(tables: SchemaTable[]): Map<string, number> {
  const edges = foreignKeys(tables);
  const memo = new Map<string, number>();
  const visit = (name: string, seen: Set<string>): number => {
    if (memo.has(name)) return memo.get(name)!;
    if (seen.has(name)) return 0; // cycle guard
    seen.add(name);
    const parents = edges.filter((e) => e.from === name && e.to !== name).map((e) => e.to);
    const layer = parents.length ? 1 + Math.max(...parents.map((p) => visit(p, seen))) : 0;
    memo.set(name, layer);
    return layer;
  };
  tables.forEach((t) => visit(t.name, new Set()));
  return memo;
}

export type Placed = { name: string; x: number; y: number };

/** Order tables inside each layer by the average position of their parents (barycenter heuristic),
 *  which untangles most crossing lines for small schemas. */
export function orderLayers(tables: SchemaTable[]): Map<number, string[]> {
  const ls = layers(tables);
  const edges = foreignKeys(tables);
  const byLayer = new Map<number, string[]>();
  [...tables].sort((a, b) => a.name.localeCompare(b.name)).forEach((t) => {
    const l = ls.get(t.name)!;
    byLayer.set(l, [...(byLayer.get(l) ?? []), t.name]);
  });
  const maxLayer = Math.max(0, ...byLayer.keys());
  const index = new Map<string, number>();
  byLayer.get(0)?.forEach((n, i) => index.set(n, i));
  for (let l = 1; l <= maxLayer; l++) {
    const names = byLayer.get(l) ?? [];
    const score = (n: string) => {
      const parents = edges.filter((e) => e.from === n && index.has(e.to)).map((e) => index.get(e.to)!);
      return parents.length ? parents.reduce((a, b) => a + b, 0) / parents.length : Infinity;
    };
    names.sort((a, b) => score(a) - score(b) || a.localeCompare(b));
    names.forEach((n, i) => index.set(n, i));
  }
  return byLayer;
}

export function placeTables(tables: SchemaTable[], width: number, height: number, nodeW: number, nodeH: number): Placed[] {
  const byLayer = orderLayers(tables);
  const maxLayer = Math.max(0, ...byLayer.keys());
  const placed: Placed[] = [];
  byLayer.forEach((names, layer) => {
    names.forEach((name, i) => {
      const x = maxLayer === 0 ? (width - nodeW) / 2 : (layer * (width - nodeW)) / maxLayer;
      const y = ((i + 1) * height) / (names.length + 1) - nodeH / 2;
      placed.push({ name, x, y });
    });
  });
  return placed;
}
