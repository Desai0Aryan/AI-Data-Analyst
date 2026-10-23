from datetime import date

from app.dates import date_windows, describe_windows


def w(today, name):
    return date_windows(today)[name]


def test_last_quarter_from_mid_january():
    assert w(date(2026, 1, 15), "last quarter") == (date(2025, 10, 1), date(2026, 1, 1))


def test_quarter_before_last():
    assert w(date(2026, 1, 15), "the quarter before last quarter") == (date(2025, 7, 1), date(2025, 10, 1))


def test_quarter_boundaries():
    assert w(date(2026, 3, 31), "last quarter") == (date(2025, 10, 1), date(2026, 1, 1))
    assert w(date(2026, 4, 1), "last quarter") == (date(2026, 1, 1), date(2026, 4, 1))
    assert w(date(2026, 12, 31), "last quarter") == (date(2026, 7, 1), date(2026, 10, 1))


def test_last_month_across_year_boundary():
    assert w(date(2026, 1, 15), "last month") == (date(2025, 12, 1), date(2026, 1, 1))


def test_last_year_and_ytd():
    assert w(date(2026, 1, 15), "last year") == (date(2025, 1, 1), date(2026, 1, 1))
    assert w(date(2026, 1, 15), "this year (to date)") == (date(2026, 1, 1), date(2026, 1, 16))


def test_rolling_windows_include_today():
    start, end = w(date(2024, 3, 1), "last 30 days")
    assert end == date(2024, 3, 2) and start == date(2024, 1, 31)   # leap-year safe


def test_description_is_prompt_ready():
    text = describe_windows(date(2026, 1, 15))
    assert ">= '2025-10-01' AND < '2026-01-01'" in text
