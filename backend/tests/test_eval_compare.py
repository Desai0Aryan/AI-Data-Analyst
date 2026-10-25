"""Unit tests for the result comparator: strict on values, lenient on presentation."""
from evals.compare import compare_results as cmp

COLS = ["product", "revenue"]
EXP = [["A", 10.0], ["B", 20.5], ["C", 30.0]]


def ok(actual, cols=COLS, exp=EXP, **kw):
    return cmp(cols, exp, actual, **kw)


# ---------- should pass: presentation differences ----------
def test_identical():
    assert ok(EXP).match

def test_row_order_ignored_by_default():
    assert ok([["C", 30.0], ["A", 10.0], ["B", 20.5]]).match

def test_column_order_and_aliases_ignored():
    assert ok([[10.0, "A"], [20.5, "B"], [30.0, "C"]]).match

def test_extra_columns_allowed():
    assert ok([["A", 1, 10.0], ["B", 2, 20.5], ["C", 3, 30.0]]).match

def test_int_vs_float():
    assert cmp(["n"], [[5]], [[5.0]]).match

def test_float_noise_within_a_cent():
    assert ok([["A", 10.004], ["B", 20.499], ["C", 30.0]]).match

def test_date_spellings_equivalent():
    assert cmp(["m"], [["2025-08-01"]], [["2025-08"]]).match
    assert cmp(["m"], [["2025-08-01"]], [["2025-08-01T00:00:00"]]).match

def test_both_empty_matches():
    assert cmp(["x"], [], []).match

def test_null_equals_null():
    assert cmp(["a", "b"], [["x", None]], [["x", None]]).match


# ---------- should fail: real differences ----------
def test_wrong_value_fails():
    r = ok([["A", 10.0], ["B", 99.0], ["C", 30.0]])
    assert not r.match and "missing [20.5]" in r.reason and "unexpected [99]" in r.reason

def test_numeric_difference_beyond_tolerance_fails():
    assert not cmp(["n"], [[100.0]], [[100.05]]).match

def test_row_count_mismatch():
    r = ok(EXP[:2])
    assert not r.match and "expected 3, got 2" in r.reason

def test_missing_row_replaced_by_other():
    assert not ok([["A", 10.0], ["B", 20.5], ["Z", 1.0]]).match

def test_missing_column_is_reported_by_name():
    r = ok([["A"], ["B"], ["C"]])
    assert not r.match and "'revenue'" in r.reason


def test_diagnostic_names_the_missing_and_unexpected_values():
    """The headline trap: the result lacks 'Smart Watch' and has 'Dumbbell Set' instead."""
    exp = [["Earbuds"], ["Smart Watch"], ["Vacuum"]]
    act = [["Earbuds"], ["Vacuum"], ["Dumbbell Set"]]
    r = cmp(["product"], exp, act, actual_cols=["name"])
    assert not r.match
    assert "missing [Smart Watch]" in r.reason and "unexpected [Dumbbell Set]" in r.reason
    assert "result column 'name'" in r.reason


def test_scalar_mismatch_shows_both_numbers():
    r = cmp(["total"], [[2293646.94]], [[2698876.5]], actual_cols=["revenue"])
    assert "missing [2293646.94]" in r.reason and "unexpected [2698876.5]" in r.reason

def test_null_vs_zero_is_a_difference():
    assert not cmp(["x"], [[0.0]], [[None]]).match

def test_columns_present_but_misaligned_rows_fail():
    # same per-column values, but paired with the wrong products
    r = ok([["A", 20.5], ["B", 30.0], ["C", 10.0]])
    assert not r.match

def test_string_values_are_exact():
    assert not cmp(["p"], [["Smart Watch"]], [["Smart Watches"]]).match


# ---------- ordering ----------
def test_ordered_pass():
    assert ok(EXP, ordered=True).match

def test_ordered_wrong_order_is_named():
    r = ok([["B", 20.5], ["A", 10.0], ["C", 30.0]], ordered=True)
    assert not r.match and "wrong order" in r.reason

def test_ordered_with_different_columns_order():
    assert ok([[10.0, "A"], [20.5, "B"], [30.0, "C"]], ordered=True).match
