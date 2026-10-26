import pytest

from app.charts import recommend_chart as rc


def cols(*pairs):
    return [{"name": n, "type": t} for n, t in pairs]


def test_empty():
    assert rc(cols(("a", "int4")), [])["type"] == "empty"


def test_single_value_is_kpi():
    spec = rc(cols(("total_revenue", "numeric")), [[2293646.94]])
    assert spec["type"] == "kpi" and spec["measures"] == ["total_revenue"]


def test_one_row_with_label_and_measures_is_kpi():
    spec = rc(cols(("category", "text"), ("revenue", "numeric")), [["Home", 5.0]])
    assert spec["type"] == "kpi" and spec["x"] == "category"


def test_time_series_is_line():
    spec = rc(cols(("month", "date"), ("revenue", "numeric")), [["2025-01-01", 1], ["2025-02-01", 2], ["2025-03-01", 3]])
    assert spec["type"] == "line" and spec["x"] == "month" and "area" in spec["alternatives"]


def test_two_dates_prefer_bars():
    assert rc(cols(("d", "date"), ("n", "int8")), [["2025-01-01", 1], ["2025-02-01", 2]])["type"] == "bar"


def test_category_measure_is_bar_with_pie_alternative_for_few_positive_rows():
    spec = rc(cols(("country", "text"), ("revenue", "numeric")), [["US", 5], ["CA", 3], ["DE", 2]])
    assert spec["type"] == "bar" and spec["alternatives"][0] == "pie" and not spec["horizontal"]


def test_many_or_long_labels_go_horizontal():
    rows = [[f"Long product name {i}", i] for i in range(10)]
    assert rc(cols(("product", "text"), ("n", "int8")), rows)["horizontal"] is True


def test_too_many_categories_become_a_table():
    rows = [[f"c{i}", i] for i in range(60)]
    assert rc(cols(("c", "text"), ("n", "int8")), rows)["type"] == "table"


def test_no_numeric_column_is_a_table():
    assert rc(cols(("name", "text"), ("email", "text")), [["a", "b"], ["c", "d"]])["type"] == "table"


def test_id_columns_are_labels_not_measures():
    spec = rc(cols(("customer_id", "int4"), ("revenue", "numeric")), [[1, 10.0], [2, 20.0]])
    assert spec["x"] == "customer_id" and spec["measures"] == ["revenue"]


def test_headline_shape_charts_only_the_change_column_diverging():
    c = cols(("product", "text"), ("prev_quarter_revenue", "numeric"), ("last_quarter_revenue", "numeric"), ("change", "numeric"))
    rows = [["Wireless Earbuds", 14486.19, 1551.81, -12934.38], ["Smart Watch", 10532.7, 0, -10532.7],
            ["Robot Vacuum", 49438.8, 43496.1, -5942.7]]
    spec = rc(c, rows)
    assert spec["type"] == "bar" and spec["x"] == "product" and spec["measures"] == ["change"]
    assert spec["diverging"] is True and spec["horizontal"] is True
    assert spec["available_measures"] == ["prev_quarter_revenue", "last_quarter_revenue", "change"]


def test_columns_on_different_scales_are_not_mixed():
    spec = rc(cols(("p", "text"), ("revenue", "numeric"), ("margin_pct", "numeric")), [["a", 1_000_000, 12.5], ["b", 900_000, 9.1]])
    assert spec["measures"] == ["revenue"] and "margin_pct" in spec["available_measures"]


def test_comparable_scales_are_drawn_together():
    spec = rc(cols(("p", "text"), ("q3", "numeric"), ("q4", "numeric")), [["a", 100, 120], ["b", 90, 80]])
    assert spec["measures"] == ["q3", "q4"]


def test_only_numeric_columns_scatter_needs_enough_rows():
    c = cols(("a", "int4"), ("b", "float8"))
    assert rc(c, [[i, i * 2.0] for i in range(6)])["type"] == "scatter"
    assert rc(c, [[1, 2.0], [2, 3.0]])["type"] == "table"


def test_nulls_do_not_crash():
    spec = rc(cols(("p", "text"), ("v", "numeric")), [["a", None], ["b", 3.0]])
    assert spec["type"] == "bar"


def test_every_spec_has_a_reason():
    assert rc(cols(("p", "text"), ("v", "numeric")), [["a", 1], ["b", 2]])["reason"]
