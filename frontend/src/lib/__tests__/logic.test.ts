import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildChartData, makeXFormatter, signColor, switchableTypes } from "../chartData";
import { toCSV } from "../csv";
import { compact, formatCell, formatNumber, humanize, numberKind, plural } from "../format";
import { clearHistory, loadHistory, pushHistory } from "../history";
import { Pacer } from "../pacer";
import { segmentFigures } from "../explain";
import { parseSSE } from "../sse";
import { foreignKeys, layers, placeTables, primaryKey } from "../schemaLayout";
import { tokenizeSql } from "../sqlHighlight";
import type { SchemaTable } from "../types";

describe("parseSSE", () => {
  it("parses complete events and keeps the unfinished tail", () => {
    const { events, rest } = parseSSE('data: {"a":1}\n\ndata: {"b":2}\n\ndata: {"c"');
    expect(events).toEqual([{ a: 1 }, { b: 2 }]);
    expect(rest).toBe('data: {"c"');
  });
  it("handles an event split across chunks", () => {
    let buf = "data: {\"type\":\"sta";
    expect(parseSSE(buf).events).toEqual([]);
    buf += 'rt"}\n\n';
    expect(parseSSE(buf).events).toEqual([{ type: "start" }]);
  });
  it("accepts CRLF line endings and ignores malformed or empty events", () => {
    const { events } = parseSSE('data: {"ok":true}\r\n\r\ndata: not-json\n\n: comment\n\n');
    expect(events).toEqual([{ ok: true }]);
  });
});

describe("Pacer", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("handles the first item immediately and spaces the rest by the previous item's delay", () => {
    const seen: string[] = [];
    const p = new Pacer<string>((s) => seen.push(s), () => 100);
    p.push("a"); p.push("b"); p.push("c");
    expect(seen).toEqual(["a"]);
    vi.advanceTimersByTime(100);
    expect(seen).toEqual(["a", "b"]);
    vi.advanceTimersByTime(100);
    expect(seen).toEqual(["a", "b", "c"]);
  });
  it("idle() resolves after the queue drains", async () => {
    const p = new Pacer<number>(() => {}, () => 50);
    p.push(1); p.push(2);
    let done = false;
    p.idle().then(() => (done = true));
    await vi.advanceTimersByTimeAsync(49);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(110);
    expect(done).toBe(true);
  });
  it("clear() drops pending items and releases waiters", async () => {
    const seen: number[] = [];
    const p = new Pacer<number>((n) => seen.push(n), () => 500);
    p.push(1); p.push(2);
    const idle = p.idle();
    p.clear();
    await idle;
    vi.advanceTimersByTime(2000);
    expect(seen).toEqual([1]);
  });
});

describe("format", () => {
  it("classifies columns", () => {
    expect(numberKind("total_revenue")).toBe("money");
    expect(numberKind("growth_pct")).toBe("percent");
    expect(numberKind("units")).toBe("count");
    expect(numberKind("quarter_idx")).toBe("plain");
  });
  it("formats money, percent, counts and NULL", () => {
    expect(formatNumber(2293646.94, "revenue")).toBe("$2,293,646.94");
    expect(formatNumber(-12934.38, "change")).toBe("-$12,934.38");
    expect(formatNumber(1551, "revenue")).toBe("$1,551");
    expect(formatNumber(12.5, "growth_pct")).toBe("12.5%");
    expect(formatNumber(5400, "orders")).toBe("5,400");
    expect(formatCell(null)).toBe("NULL");
    expect(formatCell(true)).toBe("true");
  });
  it("compacts axis values", () => {
    expect(compact(12934, "revenue")).toBe("$12.9K");
    expect(compact(-2500000, "revenue")).toBe("-$2.5M");
  });
  it("humanizes and pluralizes", () => {
    expect(humanize("prev_quarter_revenue")).toBe("Prev quarter revenue");
    expect(plural(1, "row")).toBe("1 row");
    expect(plural(1200, "row")).toBe("1,200 rows");
  });
});

describe("toCSV", () => {
  it("quotes commas, quotes and newlines; NULL becomes empty", () => {
    const csv = toCSV([{ name: "a", type: "text" }, { name: "b", type: "int4" }], [['x, "y"', null], ["line\nbreak", 3]]);
    expect(csv).toBe('a,b\n"x, ""y""",\n"line\nbreak",3\n');
  });
});

describe("tokenizeSql", () => {
  const kinds = (sql: string) => tokenizeSql(sql).filter((t) => t.kind !== "ws").map((t) => [t.kind, t.text]);
  it("recognizes keywords, functions, strings, numbers and comments", () => {
    expect(kinds("SELECT COALESCE(discount, 0) -- c\nFROM o WHERE s = 'it''s'")).toEqual([
      ["kw", "SELECT"], ["fn", "COALESCE"], ["op", "("], ["id", "discount"], ["op", ","], ["num", "0"], ["op", ")"],
      ["com", "-- c"], ["kw", "FROM"], ["id", "o"], ["kw", "WHERE"], ["id", "s"], ["op", "="], ["str", "'it''s'"],
    ]);
  });
  it("highlights destructive statements too", () => {
    expect(tokenizeSql("DROP TABLE orders").filter((t) => t.kind === "kw").map((t) => t.text)).toEqual(["DROP", "TABLE"]);
  });
  it("round-trips the exact text", () => {
    const sql = "SELECT a::int,\n  \"Odd Name\" FROM t /* x */ LIMIT 5";
    expect(tokenizeSql(sql).map((t) => t.text).join("")).toBe(sql);
  });
  it("does not treat keyword-like substrings in identifiers as keywords", () => {
    expect(tokenizeSql("selection")[0].kind).toBe("id");
  });
});

const T = (name: string, constraints: string[] = []): SchemaTable => ({ name, comment: null, columns: [], constraints });
const tables = [
  T("customers", ["PRIMARY KEY (id)"]), T("categories"),
  T("orders", ["FOREIGN KEY (customer_id) REFERENCES customers(id)"]),
  T("products", ["FOREIGN KEY (category_id) REFERENCES categories(id)"]),
  T("order_items", ["FOREIGN KEY (order_id) REFERENCES orders(id)", "FOREIGN KEY (product_id) REFERENCES products(id)"]),
];
describe("schemaLayout", () => {
  it("extracts foreign and primary keys", () => {
    expect(foreignKeys(tables)).toHaveLength(4);
    expect(foreignKeys(tables)[0]).toEqual({ from: "orders", fromCol: "customer_id", to: "customers", toCol: "id" });
    expect(primaryKey(tables[0])).toEqual(["id"]);
  });
  it("layers children to the right of their parents", () => {
    const l = layers(tables);
    expect([l.get("customers"), l.get("orders"), l.get("order_items")]).toEqual([0, 1, 2]);
    expect(l.get("products")).toBe(1);
  });
  it("orders layers so related tables line up and edges do not cross", () => {
    const placed = Object.fromEntries(placeTables(tables, 900, 300, 176, 58).map((p) => [p.name, p.y]));
    // customers is listed after categories alphabetically, but orders (child of customers) must sit below products (child of categories)
    expect(placed.categories < placed.customers).toBe(placed.products < placed.orders);
  });
  it("survives cycles and self references", () => {
    const cyc = [T("a", ["FOREIGN KEY (b_id) REFERENCES b(id)"]), T("b", ["FOREIGN KEY (a_id) REFERENCES a(id)"]), T("c", ["FOREIGN KEY (p) REFERENCES c(id)"])];
    expect(() => layers(cyc)).not.toThrow();
  });
  it("places every table inside the canvas without overlap in a layer", () => {
    const placed = placeTables(tables, 900, 330, 176, 58);
    expect(placed).toHaveLength(5);
    placed.forEach((p) => { expect(p.x).toBeGreaterThanOrEqual(0); expect(p.x + 176).toBeLessThanOrEqual(900); expect(p.y).toBeGreaterThanOrEqual(0); expect(p.y + 58).toBeLessThanOrEqual(330); });
    const l1 = placed.filter((p) => ["orders", "products"].includes(p.name)).map((p) => p.y).sort((a, b) => a - b);
    expect(l1[1] - l1[0]).toBeGreaterThan(58);
  });
});

describe("chartData", () => {
  it("builds row objects", () => {
    expect(buildChartData([{ name: "a", type: "text" }, { name: "n", type: "int4" }], [["x", 1]])).toEqual([{ a: "x", n: 1 }]);
  });
  it("colors by sign", () => { expect(signColor(-1)).toBe("#ff6b7a"); expect(signColor(0)).toBe("#4de0a5"); });
  it("formats monthly dates as 'Mon YYYY' and leaves labels alone", () => {
    expect(makeXFormatter(["2025-08-01", "2025-09-01"])("2025-08-01")).toBe("Aug 2025");
    expect(makeXFormatter(["2025-08-05", "2025-08-12"])("2025-08-05")).toBe("Aug 5");
    expect(makeXFormatter(["Smart Watch", "2025-01-01"])("Smart Watch")).toBe("Smart Watch");
  });
  it("offers only drawable chart types", () => {
    const spec = { type: "bar", alternatives: ["pie", "table"] } as any;
    expect(switchableTypes(spec)).toEqual(["bar", "pie"]);
  });
});

describe("history", () => {
  beforeEach(() => clearHistory());
  it("dedupes case-insensitively, keeps newest first and caps at 12", () => {
    let h = loadHistory();
    for (let i = 0; i < 15; i++) h = pushHistory(h, { question: `q${i}`, status: "ok", at: i });
    expect(h).toHaveLength(12);
    h = pushHistory(h, { question: "Q14", status: "failed", at: 99 });
    expect(h[0]).toMatchObject({ question: "Q14", status: "failed" });
    expect(h.filter((x) => x.question.toLowerCase() === "q14")).toHaveLength(1);
    expect(loadHistory()[0].question).toBe("Q14");
  });
  it("tolerates corrupt storage", () => {
    localStorage.setItem("verity.history.v1", "{not json");
    expect(loadHistory()).toEqual([]);
  });
});

describe("segmentFigures", () => {
  const figs = (t: string) => segmentFigures(t).filter((s) => s.figure).map((s) => s.text);
  it("finds money, percentages, compact and plain numbers", () => {
    expect(figs("Down $12,934.38 (89.3%), about -$12.9K, 3 products")).toEqual(["$12,934.38", "89.3%", "-$12.9K", "3"]);
  });
  it("leaves labels like Q4 alone", () => {
    expect(figs("In Q4 the B2B segment grew 5%")).toEqual(["5%"]);
  });
  it("round-trips the exact text", () => {
    const t = "Revenue was $1,200, then 300.";
    expect(segmentFigures(t).map((s) => s.text).join("")).toBe(t);
  });
  it("handles text with no figures", () => { expect(segmentFigures("Nothing here.")).toEqual([{ text: "Nothing here.", figure: false }]); });
});
