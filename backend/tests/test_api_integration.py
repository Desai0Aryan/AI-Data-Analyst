"""Integration tests against a real, seeded PostgreSQL."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

pytestmark = pytest.mark.usefixtures("require_db")
client = TestClient(app)


def run(sql: str):
    return client.post("/api/sql/execute", json={"sql": sql})


def test_health():
    assert client.get("/api/health").json() == {"status": "ok", "database": True}


def test_schema_endpoint_describes_tables_and_samples():
    body = client.get("/api/schema?prompt=true").json()
    names = {t["name"] for t in body["tables"]}
    assert names == {"categories", "products", "customers", "orders", "order_items"}
    # Low-cardinality text columns expose their real values (key for text-to-SQL accuracy).
    assert "values: 'cancelled', 'completed', 'refunded'" in body["prompt"]
    assert "FOREIGN KEY" in body["prompt"]
    assert "may be NULL" in body["prompt"]


def test_simple_query_and_types():
    r = run("SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY status")
    assert r.status_code == 200
    body = r.json()
    assert [c["name"] for c in body["columns"]] == ["status", "n"]
    assert body["rows"] == [["cancelled", 300], ["completed", 5400], ["refunded", 300]]


def test_nulls_are_preserved():
    r = run("SELECT COUNT(*) FILTER (WHERE signup_channel IS NULL) AS unknown FROM customers")
    assert r.json()["rows"] == [[28]]


def test_decimals_and_dates_serialize():
    r = run("SELECT order_date, 1.5::numeric AS x FROM orders ORDER BY id LIMIT 1")
    row = r.json()["rows"][0]
    assert isinstance(row[0], str) and row[0].count("-") == 2
    assert row[1] == 1.5


def test_limit_is_enforced_and_truncation_flagged():
    r = run("SELECT * FROM order_items")  # 12,000 rows in table
    body = r.json()
    assert body["row_count"] == get_settings().max_rows
    assert body["truncated"] is True
    assert any("LIMIT" in w for w in body["warnings"])


def test_user_limit_is_not_flagged_truncated():
    body = run("SELECT * FROM orders LIMIT 3").json()
    assert body["row_count"] == 3 and body["truncated"] is False


def test_guard_rejection_returns_422_with_code():
    r = run("DROP TABLE orders")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "not_read_only"


def test_db_error_returns_message_for_repair_loop():
    r = run("SELECT nonexistent_column FROM orders")
    assert r.status_code == 400
    assert "nonexistent_column" in r.json()["detail"]["message"]


def test_statement_timeout(monkeypatch):
    # Force a tiny timeout and a genuinely slow query (cross join), no pg_sleep needed.
    monkeypatch.setattr(get_settings(), "statement_timeout_ms", 50)
    r = run("SELECT COUNT(*) FROM order_items a CROSS JOIN order_items b CROSS JOIN order_items c")
    assert r.status_code == 408
    assert r.json()["detail"]["code"] == "timeout"


# ---- defense in depth: bypass the guard on purpose and prove the DB still refuses ----

def test_layer_read_only_transaction_blocks_writes_without_guard():
    # Layer 3: the role defaults to read-only transactions.
    with psycopg.connect(get_settings().database_url) as conn:
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM orders")


def test_layer_privileges_block_writes_even_in_read_write_transaction():
    # Layer 4: even if someone forces a READ WRITE transaction, the role has no privileges.
    with psycopg.connect(get_settings().database_url) as conn:
        conn.read_only = False
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM orders")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE evil (id int)")


def test_validate_endpoint_shows_normalized_sql():
    r = client.post("/api/sql/validate", json={"sql": "select * from orders -- hi"})
    assert r.status_code == 200
    assert r.json()["sql"].endswith("LIMIT 1000") and "hi" not in r.json()["sql"]
