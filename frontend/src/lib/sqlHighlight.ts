export type TokenKind = "kw" | "fn" | "str" | "num" | "com" | "op" | "id" | "ws";
export type Token = { kind: TokenKind; text: string };

const KEYWORDS = new Set(
  `select from where group by order having limit offset join left right inner outer full cross on using as and or not in is null like ilike
   between case when then else end distinct union all intersect except with exists asc desc filter over partition true false interval
   cast date current_date extract nulls first last any some
   drop table delete update insert into set alter create truncate values returning grant revoke copy database schema index view`.split(/\s+/),
);

const RULES: [TokenKind, RegExp][] = [
  ["com", /^(--[^\n]*|\/\*[\s\S]*?\*\/)/],
  ["str", /^'(?:[^']|'')*'/],
  ["num", /^\d+(?:\.\d+)?/],
  ["id", /^"[^"]*"/],
  ["id", /^[A-Za-z_][A-Za-z0-9_$.]*/],
  ["ws", /^\s+/],
  ["op", /^(::|<>|<=|>=|!=|\|\||[-+*/%=<>(),;])/],
];

export function tokenizeSql(sql: string): Token[] {
  const out: Token[] = [];
  let rest = sql;
  while (rest.length) {
    let matched = false;
    for (const [kind, re] of RULES) {
      const m = re.exec(rest);
      if (!m) continue;
      let k: TokenKind = kind;
      if (kind === "id" && !m[0].startsWith('"')) {
        const lower = m[0].toLowerCase();
        if (KEYWORDS.has(lower)) k = "kw";
        else if (/^\s*\(/.test(rest.slice(m[0].length))) k = "fn";
      }
      out.push({ kind: k, text: m[0] });
      rest = rest.slice(m[0].length);
      matched = true;
      break;
    }
    if (!matched) {
      out.push({ kind: "id", text: rest[0] });
      rest = rest.slice(1);
    }
  }
  return out;
}
