"""Schema introspection.

Reads tables, columns, keys, comments and a few sample values from Postgres and renders
them as compact text for an LLM prompt (used from Part 2 on). Sample values for
low-cardinality text columns matter a lot for text-to-SQL accuracy: the model needs
to know that ``orders.status`` holds 'completed', not 'COMPLETE'.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache

from psycopg import sql as psql

from .db import get_pool

SAMPLE_LIMIT = 8  # show values only for text columns with <= this many distinct values

_COLUMNS_SQL = """
SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
       NOT a.attnotnull, col_description(c.oid, a.attnum), obj_description(c.oid, 'pg_class')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

_CONSTRAINTS_SQL = """
SELECT cl.relname, con.contype, pg_get_constraintdef(con.oid)
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
WHERE n.nspname = 'public' AND con.contype IN ('p', 'f')
ORDER BY cl.relname, con.contype DESC, con.conname
"""


@dataclass
class Column:
    name: str
    type: str
    nullable: bool
    comment: str | None = None
    sample_values: list[str] = field(default_factory=list)


@dataclass
class Table:
    name: str
    comment: str | None
    columns: list[Column]
    constraints: list[str] = field(default_factory=list)  # PRIMARY KEY / FOREIGN KEY defs


@dataclass
class Schema:
    tables: list[Table]

    @property
    def table_names(self) -> set[str]:
        return {t.name for t in self.tables}

    def to_dict(self) -> dict:
        return {"tables": [asdict(t) for t in self.tables]}

    def to_prompt(self) -> str:
        """Compact DDL-like description for an LLM."""
        out: list[str] = []
        for t in self.tables:
            out.append(f"TABLE {t.name}" + (f"  -- {t.comment}" if t.comment else ""))
            for c in t.columns:
                bits = [f"  {c.name} {c.type}" + ("" if c.nullable else " NOT NULL")]
                notes = []
                if c.nullable:
                    notes.append("may be NULL")
                if c.comment:
                    notes.append(c.comment)
                if c.sample_values:
                    notes.append("values: " + ", ".join(repr(v) for v in c.sample_values))
                if notes:
                    bits.append("-- " + "; ".join(notes))
                out.append(" ".join(bits))
            for con in t.constraints:
                out.append(f"  {con}")
            out.append("")
        return "\n".join(out).strip()


def _load_schema() -> Schema:
    tables: dict[str, Table] = {}
    with get_pool().connection() as conn:
        conn.read_only = True
        for name, col, dtype, nullable, ccomment, tcomment in conn.execute(_COLUMNS_SQL).fetchall():
            table = tables.setdefault(name, Table(name, tcomment, []))
            table.columns.append(Column(col, dtype, nullable, ccomment))

        for name, _kind, definition in conn.execute(_CONSTRAINTS_SQL).fetchall():
            tables[name].constraints.append(definition)

        # Sample values for low-cardinality text columns.
        for table in tables.values():
            for col in table.columns:
                if col.type != "text":
                    continue
                query = psql.SQL(
                    "SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL ORDER BY 1 LIMIT %s"
                ).format(c=psql.Identifier(col.name), t=psql.Identifier(table.name))
                values = [r[0] for r in conn.execute(query, (SAMPLE_LIMIT + 1,)).fetchall()]
                if len(values) <= SAMPLE_LIMIT:
                    col.sample_values = values
        conn.rollback()
    return Schema(tables=sorted(tables.values(), key=lambda t: t.name))


@lru_cache
def get_schema() -> Schema:
    """Cached; call ``get_schema.cache_clear()`` after DDL changes."""
    return _load_schema()
