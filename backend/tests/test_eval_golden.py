"""Are the 'known answers' actually right?

Golden SQL checked only against itself would be circular. So the key answers are recomputed
*independently in Python* from the raw table rows (Decimal arithmetic, no SQL aggregation)
and compared with what the golden SQL returns. A snapshot test additionally pins every golden
result, so a change to the seed data or to a golden query cannot slip through unnoticed.
"""
import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import psycopg
import pytest

from app import services
from app.config import get_settings
from evals import snapshot
from evals.cases import BY_ID, CASES

pytestmark = pytest.mark.usefixtures("require_db")

CENT = Decimal("0.01")
Q3 = (date(2025, 7, 1), date(2025, 10, 1))
Q4 = (date(2025, 10, 1), date(2026, 1, 1))


def r2(x: Decimal) -> float:
    return float(x.quantize(CENT, rounding=ROUND_HALF_UP))


def golden(case_id):
    return services.run_sql(BY_ID[case_id].golden_sql)[1].rows


@pytest.fixture(scope="module")
def raw(require_db):
    with psycopg.connect(get_settings().database_url) as conn:
        lines = conn.execute(
            "SELECT oi.order_id, oi.product_id, oi.quantity, oi.unit_price, oi.discount, "
            "o.status, o.order_date, o.customer_id FROM order_items oi JOIN orders o ON o.id = oi.order_id"
        ).fetchall()
        customers = {r[0]: r[1:] for r in conn.execute("SELECT id, email, country, signup_channel FROM customers")}
        products = {r[0]: r[1:] for r in conn.execute("SELECT id, name, category_id, discontinued FROM products")}
        categories = dict(conn.execute("SELECT id, name FROM categories").fetchall())
        n_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    rows = [dict(order=o, product=p, qty=q, price=pr, disc=d, status=s, day=dt, cust=c,
                 rev=q * pr * (1 - (d or Decimal(0))), discount_amt=q * pr * (d or Decimal(0)))
            for o, p, q, pr, d, s, dt, c in lines]
    return dict(lines=rows, customers=customers, products=products, categories=categories, n_orders=n_orders)


def completed(raw, lo=None, hi=None):
    return [l for l in raw["lines"] if l["status"] == "completed" and (lo is None or lo <= l["day"] < hi)]


def total(ls, key="rev"):
    return sum((l[key] for l in ls), Decimal(0))


# ------------------------------------------------------------------ independent recomputation

def test_total_revenue(raw):
    assert golden("agg_total_revenue") == [[r2(total(completed(raw)))]]


def test_average_order_value_is_per_order_not_per_line(raw):
    per_order = defaultdict(Decimal)
    for l in completed(raw):
        per_order[l["order"]] += l["rev"]
    expected = r2(sum(per_order.values()) / len(per_order))
    assert golden("agg_avg_order_value") == [[expected]]
    # and the wrong (per-line) answer really is different, so this case can detect the mistake
    per_line = r2(total(completed(raw)) / len(completed(raw)))
    assert per_line != expected


def test_quarterly_and_period_revenue(raw):
    assert golden("date_last_quarter_revenue") == [[r2(total(completed(raw, *Q4)))]]
    assert golden("date_h2_2024_revenue") == [[r2(total(completed(raw, date(2024, 7, 1), date(2025, 1, 1))))]]
    quarters = [(date(2025, m, 1), date(2025, m + 3, 1) if m < 10 else date(2026, 1, 1)) for m in (1, 4, 7, 10)]
    got = golden("date_quarterly_2025")
    assert [(r[0], r[1]) for r in got] == [(q[0].isoformat(), r2(total(completed(raw, *q)))) for q in quarters]


def test_yoy_growth(raw):
    y24 = total(completed(raw, date(2024, 1, 1), date(2025, 1, 1)))
    y25 = total(completed(raw, date(2025, 1, 1), date(2026, 1, 1)))
    assert golden("date_yoy_growth") == [[r2(Decimal(100) * (y25 - y24) / y24)]]


def test_last_month_order_count(raw):
    # Orders are one-per-row in `orders`; recount from the line data's distinct order ids.
    ids = {l["order"] for l in completed(raw, date(2025, 12, 1), date(2026, 1, 1))}
    with psycopg.connect(get_settings().database_url) as conn:   # orders without items would be missed above
        n = conn.execute("SELECT COUNT(*) FROM orders WHERE status='completed' AND order_date >= '2025-12-01' "
                         "AND order_date < '2026-01-01'").fetchone()[0]
    assert golden("date_last_month_orders") == [[n]] and n >= len(ids) > 0


def test_discount_math(raw):
    assert golden("nulls_discount_lost") == [[r2(total(completed(raw), "discount_amt"))]]
    share = Decimal(100) * sum(l["disc"] is not None for l in raw["lines"]) / len(raw["lines"])
    assert golden("nulls_discount_share") == [[r2(share)]]


def test_cancelled_and_refunded_value(raw):
    bad = [l for l in raw["lines"] if l["status"] in ("cancelled", "refunded")]
    assert golden("trap_cancelled_refunded_value") == [[r2(total(bad))]]


def test_revenue_by_country_and_category(raw):
    by_country = defaultdict(Decimal)
    for l in completed(raw):
        by_country[raw["customers"][l["cust"]][1]] += l["rev"]
    assert dict(map(tuple, golden("join_revenue_by_country"))) == {k: r2(v) for k, v in by_country.items()}

    by_cat = defaultdict(Decimal)
    units = defaultdict(int)
    for l in completed(raw):
        cat = raw["categories"][raw["products"][l["product"]][1]]
        by_cat[cat] += l["rev"]
        units[cat] += l["qty"]
    top = max(by_cat, key=by_cat.get)
    assert golden("join_top_category") == [[top, r2(by_cat[top])]]
    assert dict(map(tuple, golden("agg_units_by_category"))) == dict(units)


def test_discontinued_revenue(raw):
    ls = [l for l in completed(raw) if raw["products"][l["product"]][2]]
    assert golden("join_discontinued_revenue") == [[r2(total(ls))]]


def test_top_customers_group_by_id_not_name(raw):
    by_cust = defaultdict(Decimal)
    for l in completed(raw):
        by_cust[l["cust"]] += l["rev"]
    ranked = sorted(by_cust.items(), key=lambda kv: -kv[1])[:5]
    assert {r[0] for r in golden("join_top_customers")} == {raw["customers"][c][0] for c, _ in ranked}
    assert sorted(r[1] for r in golden("join_top_customers")) == sorted(r2(v) for _, v in ranked)
    # The trap is real: customer names repeat, so grouping by name merges different people.
    names = [raw["customers"][c][0] for c in raw["customers"]]
    with psycopg.connect(get_settings().database_url) as conn:
        distinct_names = conn.execute("SELECT COUNT(DISTINCT name) FROM customers").fetchone()[0]
    assert distinct_names < len(names)


def test_top_products(raw):
    by_prod = defaultdict(Decimal)
    for l in completed(raw):
        by_prod[raw["products"][l["product"]][0]] += l["rev"]
    ranked = sorted(by_prod.items(), key=lambda kv: -kv[1])[:5]
    assert golden("rank_top_products") == [[n, r2(v)] for n, v in ranked]


def test_best_month(raw):
    by_month = defaultdict(Decimal)
    for l in completed(raw):
        by_month[l["day"].replace(day=1)] += l["rev"]
    best = max(by_month, key=by_month.get)
    assert golden("rank_best_month") == [[best.isoformat(), r2(by_month[best])]]


def test_channels_include_unknown(raw):
    counts = defaultdict(int)
    for _, _, channel in raw["customers"].values():
        counts[channel or "unknown"] += 1
    assert dict(map(tuple, golden("nulls_customers_by_channel"))) == dict(counts)
    assert "unknown" in counts


def test_orders_by_status(raw):
    with psycopg.connect(get_settings().database_url) as conn:
        expected = dict(conn.execute("SELECT status, COUNT(*) FROM orders GROUP BY status").fetchall())
    assert dict(map(tuple, golden("agg_orders_by_status"))) == expected
    assert sum(expected.values()) == raw["n_orders"]


# ------------------------------------------------------------------ the headline trap

def test_smart_watch_trap_is_real_and_golden_handles_it(raw):
    q3, q4 = defaultdict(Decimal), defaultdict(Decimal)
    for l in completed(raw):
        name = raw["products"][l["product"]][0]
        if Q3[0] <= l["day"] < Q3[1]:
            q3[name] += l["rev"]
        if Q4[0] <= l["day"] < Q4[1]:
            q4[name] += l["rev"]
    assert q3["Smart Watch"] > 0 and q4["Smart Watch"] == 0          # sold in Q3, nothing in Q4
    changes = {n: q4[n] - q3[n] for n in set(q3) | set(q4)}
    top5 = sorted(changes, key=changes.get)[:5]
    rows = golden("trap_biggest_decline")
    assert [r[0] for r in rows] == top5 and "Smart Watch" in top5
    assert [r[3] for r in rows] == [r2(changes[n]) for n in top5]
    no_q4 = [n for n in {raw["products"][p][0] for p in raw["products"]} if q4[n] == 0]
    assert [r[0] for r in golden("trap_no_sales_last_quarter")] == no_q4 == ["Smart Watch"]


# ------------------------------------------------------------------ snapshot + case hygiene

def test_golden_results_match_pinned_snapshot():
    pinned = json.loads(snapshot.PATH.read_text())
    now = snapshot.current()
    assert set(pinned) == set(now)
    for case_id in pinned:
        assert now[case_id] == pinned[case_id], f"{case_id} drifted; if intentional run `python -m evals.snapshot`"


def test_every_golden_query_passes_the_guard_and_returns_data():
    for c in CASES:
        if c.expect == "match":
            res = services.run_sql(c.golden_sql)[1]
            assert res.row_count > 0 and not res.truncated, c.id


def test_case_definitions_are_sane():
    assert len({c.id for c in CASES}) == len(CASES)
    for c in CASES:
        assert c.expect in {"match", "refuse"}
        assert (c.golden_sql is not None) == (c.expect == "match"), c.id
        assert c.trap, f"{c.id} should explain what it tests"
    assert {c.category for c in CASES} >= {"aggregation", "dates", "joins", "nulls", "ranking", "traps", "refusal", "security"}


def test_no_eval_question_leaks_into_the_prompt():
    from app.prompts import SYSTEM_TEMPLATE
    for c in CASES:
        assert c.question.lower() not in SYSTEM_TEMPLATE.lower(), f"{c.id} appears in the prompt (test-set leakage)"
