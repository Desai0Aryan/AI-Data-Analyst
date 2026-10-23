"""Unit tests for the SQL guard. No database required."""
import pytest

from app.sql_guard import SQLGuardError, validate_sql

TABLES = {"orders", "order_items", "products", "customers", "categories"}


def ok(sql: str, **kw):
    return validate_sql(sql, TABLES, **kw)


def code_of(sql: str) -> str:
    with pytest.raises(SQLGuardError) as exc:
        ok(sql)
    return exc.value.code


# ---------- things that must be allowed ----------

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "SELECT * FROM orders",
    "SELECT p.name, SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN products p ON p.id = oi.product_id GROUP BY p.name",
    "WITH q AS (SELECT * FROM orders) SELECT * FROM q",
    "SELECT * FROM public.orders",
    "SELECT id FROM orders UNION SELECT id FROM customers",
    "SELECT generate_series(1, 10)",
    "SELECT DATE_TRUNC('quarter', order_date) AS q, COUNT(*) FROM orders GROUP BY 1",
    "SELECT COALESCE(discount, 0) FROM order_items",
    "SELECT * FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '90 days'",
    "SELECT * FROM (SELECT * FROM orders) AS sub",
    "SELECT * FROM orders; ",                       # trailing semicolon is fine
    "SELECT 'DROP TABLE orders' AS harmless",       # keywords inside string literals
    "SELECT * FROM orders -- DROP TABLE orders",    # keywords inside comments
])
def test_allows_safe_queries(sql):
    assert ok(sql).sql


# ---------- things that must be blocked ----------

@pytest.mark.parametrize("sql, expected", [
    ("DROP TABLE orders", "not_read_only"),
    ("DELETE FROM orders", "not_read_only"),
    ("UPDATE orders SET status = 'x'", "not_read_only"),
    ("INSERT INTO orders VALUES (1)", "not_read_only"),
    ("TRUNCATE orders", "not_read_only"),
    ("ALTER TABLE orders ADD COLUMN x int", "not_read_only"),
    ("CREATE TABLE x (id int)", "not_read_only"),
    ("GRANT ALL ON orders TO public", "not_read_only"),
    ("COPY orders TO '/tmp/x'", "not_read_only"),
    ("SET statement_timeout = 0", "not_read_only"),
    ("SELECT 1; DROP TABLE orders", "multiple_statements"),
    ("SELECT 1; SELECT 2", "multiple_statements"),
    ("", "empty"),
    ("   ", "empty"),
    ("SELEC * FROM", "syntax"),
])
def test_blocks_non_read_only(sql, expected):
    assert code_of(sql) == expected


def test_blocks_data_modifying_cte():
    assert code_of("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d") == "forbidden_statement"


def test_blocks_select_into():
    assert code_of("SELECT * INTO backup FROM orders") == "forbidden_statement"


def test_blocks_locking_reads():
    assert code_of("SELECT * FROM orders FOR UPDATE") == "forbidden_statement"


@pytest.mark.parametrize("sql", [
    "SELECT pg_sleep(100)",
    "SELECT PG_SLEEP(100)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_ls_dir('/')",
    "SELECT set_config('statement_timeout', '0', false)",
    "SELECT current_setting('is_superuser')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)",
    "SELECT version()",
    "SELECT pg_terminate_backend(1)",
])
def test_blocks_dangerous_functions(sql):
    assert code_of(sql) in {"forbidden_function", "unknown_table"}


@pytest.mark.parametrize("sql", [
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM secret_table",
    "SELECT * FROM other_schema.orders",
    "SELECT * FROM somedb.public.orders",
    "SELECT * FROM orders o JOIN pg_user u ON true",
    "SELECT * FROM orders WHERE id IN (SELECT usesysid FROM pg_user)",
])
def test_blocks_unknown_tables(sql):
    assert code_of(sql) == "unknown_table"


def test_unknown_table_message_lists_available_tables():
    with pytest.raises(SQLGuardError) as exc:
        ok("SELECT * FROM prodcuts")
    assert "products" in exc.value.message  # repair-loop friendly


def test_cte_name_shadowing_does_not_bypass_allowlist():
    # A CTE named like a real table is fine, but a CTE can't smuggle in pg_user.
    assert code_of("WITH x AS (SELECT * FROM pg_user) SELECT * FROM x") == "unknown_table"


# ---------- LIMIT enforcement ----------

def test_adds_limit_when_missing():
    r = ok("SELECT * FROM orders", max_rows=50)
    assert r.effective_limit == 50 and r.limit_applied
    assert "LIMIT 50" in r.sql


def test_keeps_smaller_limit():
    r = ok("SELECT * FROM orders LIMIT 5", max_rows=50)
    assert r.effective_limit == 5 and not r.limit_applied


def test_lowers_larger_limit():
    r = ok("SELECT * FROM orders LIMIT 999999", max_rows=50)
    assert r.effective_limit == 50 and r.limit_applied
    assert "LIMIT 50" in r.sql and "999999" not in r.sql


def test_limit_on_union():
    r = ok("SELECT id FROM orders UNION ALL SELECT id FROM customers", max_rows=10)
    assert r.effective_limit == 10 and "LIMIT 10" in r.sql


def test_limit_preserves_order_by():
    r = ok("SELECT id FROM orders ORDER BY order_date DESC", max_rows=10)
    assert r.sql.index("ORDER BY") < r.sql.index("LIMIT")


# ---------- normalization ----------

def test_comments_are_stripped_from_executed_sql():
    r = ok("SELECT 1 /* sneaky */ -- more")
    assert "sneaky" not in r.sql and "--" not in r.sql


def test_reports_referenced_tables():
    r = ok("SELECT * FROM orders o JOIN products p ON true")
    assert r.tables == ["orders", "products"]
