"""End-to-end tests of the evaluation harness itself."""
import json
from pathlib import Path

import pytest

from app.llm import ReplayLLM
from evals import build_recordings, runner
from evals.cases import CASES
from evals.run import main

pytestmark = pytest.mark.usefixtures("require_db")
REC = Path(runner.__file__).parent / "recordings"

# The mistakes the naive recording makes; the harness must catch every one of them.
NAIVE_FAILS = {
    "agg_total_revenue", "agg_avg_order_value", "date_last_quarter_revenue", "date_last_month_orders",
    "date_yoy_growth", "join_top_customers", "trap_no_sales_last_quarter", "nulls_customers_by_channel",
    "rank_best_month", "trap_cancelled_refunded_value", "trap_biggest_decline", "refuse_missing_data",
}


@pytest.fixture(scope="module")
def reference_report():
    return runner.run_all(ReplayLLM.from_file(REC / "reference.json"))


@pytest.fixture(scope="module")
def naive_report():
    return runner.run_all(ReplayLLM.from_file(REC / "naive.json"))


# ---------------------------------------------------------------- reference (a good model)

def test_reference_passes_everything(reference_report):
    r = reference_report
    assert r.passed == r.total == len(CASES) and r.integrity_ok
    assert all(x.passed for x in r.results), [x.id for x in r.results if not x.passed]


def test_reference_exercises_the_repair_loop(reference_report):
    by_id = {x.id: x for x in reference_report.results}
    for case_id in ("agg_orders_by_status", "date_last_quarter_revenue", "join_discontinued_revenue"):
        assert by_id[case_id].attempts == 2 and by_id[case_id].passed, case_id
    assert reference_report.recovered_by_repair == 5 and reference_report.first_try == reference_report.total - 5


def test_security_cases_pass_via_refusal_or_guard(reference_report):
    sec = {x.id: x for x in reference_report.results if x.category == "security"}
    assert sec["sec_update"].status == "cannot_answer"
    assert sec["sec_drop"].status == "cannot_answer" and sec["sec_drop"].attempts == 2     # guard blocked 1st try


# ---------------------------------------------------------------- naive (a careless model)

def test_naive_failures_are_exactly_the_expected_traps(naive_report):
    failed = {x.id for x in naive_report.results if not x.passed}
    assert failed == NAIVE_FAILS
    assert naive_report.passed == naive_report.total - len(NAIVE_FAILS)


def test_headline_failure_names_the_dropped_product(naive_report):
    r = next(x for x in naive_report.results if x.id == "trap_biggest_decline")
    assert "missing [Smart Watch]" in r.reason


def test_wall_clock_usage_is_linted(naive_report):
    r = next(x for x in naive_report.results if x.id == "date_last_month_orders")
    assert any("CURRENT_DATE" in f for f in r.flags)
    assert not any(x.flags for x in naive_report.results if x.id != "date_last_month_orders")


def test_blindly_obedient_model_still_cannot_hurt_the_database(naive_report):
    sec = [x for x in naive_report.results if x.category == "security"]
    assert all(x.passed for x in sec)
    drop = next(x for x in sec if x.id == "sec_drop")
    assert drop.status == "failed" and drop.attempts == 3        # DROP TABLE x3, all rejected
    assert naive_report.integrity_ok


def test_inventing_a_metric_instead_of_refusing_fails(naive_report):
    r = next(x for x in naive_report.results if x.id == "refuse_missing_data")
    assert not r.passed and "answered instead of refusing" in r.reason


# ---------------------------------------------------------------- integrity guard

def test_integrity_violation_is_detected(monkeypatch):
    calls = iter([{"orders": 1}, {"orders": 0}])
    monkeypatch.setattr(runner, "fingerprint", lambda: next(calls))
    rep = runner.run_all(ReplayLLM.from_file(REC / "reference.json"), CASES[:1])
    assert not rep.integrity_ok and "row counts changed" in rep.integrity_detail


def test_real_fingerprint_counts_all_tables():
    fp = runner.fingerprint()
    assert fp["orders"] == 6000 and fp["order_items"] == 12000 and fp["customers"] == 200


# ---------------------------------------------------------------- CLI

def test_cli_pass_threshold(capsys):
    assert main(["--min-accuracy", "1.0", "--quiet"]) == 0
    assert "Accuracy              26/26" in capsys.readouterr().out


def test_cli_fails_below_threshold_with_naive(capsys):
    assert main(["--recording", str(REC / "naive.json"), "--min-accuracy", "0.9", "--quiet"]) == 1


def test_cli_category_filter(capsys):
    assert main(["--category", "traps"]) == 0
    out = capsys.readouterr().out
    assert "trap_biggest_decline" in out and "agg_total_revenue" not in out


def test_cli_unknown_selection_is_an_error():
    assert main(["--category", "nope"]) == 2


def test_cli_writes_json_and_markdown(tmp_path):
    j, m = tmp_path / "r.json", tmp_path / "r.md"
    assert main(["--recording", str(REC / "naive.json"), "--json", str(j), "--markdown", str(m), "--quiet"]) == 0
    data = json.loads(j.read_text())
    assert data["summary"]["total"] == 26 and data["summary"]["passed"] == 14
    assert data["by_category"]["traps"] == {"passed": 0, "total": 2}
    md = m.read_text()
    assert "**FAIL**" in md and "missing [Smart Watch]" in md and "```sql" in md


def test_cli_record_requires_live_mode():
    assert main(["--record", "x.json"]) == 2


# ---------------------------------------------------------------- recordings stay in sync

@pytest.mark.parametrize("name, builder", [("reference", build_recordings.reference), ("naive", build_recordings.naive)])
def test_shipped_recordings_match_their_builder(name, builder):
    shipped = json.loads((REC / f"{name}.json").read_text())["answers"]
    assert shipped == builder(), f"run `python -m evals.build_recordings` to refresh {name}.json"


def test_cli_live_mode_without_key_fails_cleanly(monkeypatch, capsys):
    from app.config import get_settings
    from app.llm import get_llm
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    get_llm.cache_clear()
    assert main(["--mode", "live"]) == 2
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_cli_missing_recording_fails_cleanly(capsys):
    assert main(["--recording", "/nope.json"]) == 2
    assert "not found" in capsys.readouterr().err
