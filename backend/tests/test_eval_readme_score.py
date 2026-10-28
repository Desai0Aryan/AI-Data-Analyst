import json

import pytest

from evals.readme_score import END, START, ScoreError, main, summarize, update_readme

README = f"intro\n\n**Live model result:** {START}not run yet.{END}\n\noutro\n"


def report(model="claude-test", failed=()):
    results = [{"id": f"case_{i}", "passed": f"case_{i}" not in failed} for i in range(26)]
    p = sum(r["passed"] for r in results)
    return {"model": model, "results": results,
            "summary": {"total": 26, "passed": p, "accuracy": p / 26, "first_try_passes": p - 2, "recovered_by_repair": 2, "avg_attempts": 1.2308}}


def test_writes_the_score_between_the_markers_and_leaves_the_rest_alone(tmp_path):
    f = tmp_path / "README.md"
    f.write_text(README)
    update_readme(f, report(failed={"case_3"}), "2026-02-01")
    text = f.read_text()
    assert text.startswith("intro\n\n**Live model result:** ") and text.endswith("\n\noutro\n")
    assert "**25/26 (96%)** with `claude-test` on 2026-02-01" in text
    assert "23 right on the first try, 2 fixed by the repair loop, 1.23 attempts per question" in text
    assert "Failed: `case_3`." in text and "not run yet" not in text


def test_is_idempotent(tmp_path):
    f = tmp_path / "README.md"
    f.write_text(README)
    update_readme(f, report(), "2026-02-01")
    first = f.read_text()
    update_readme(f, report(), "2026-02-01")
    assert f.read_text() == first and first.count(START) == 1


def test_perfect_run_says_no_failures():
    assert summarize(report(), "2026-02-01").endswith("No failures.")


def test_long_failure_lists_are_truncated():
    ids = {f"case_{i}" for i in range(12)}
    assert "and 4 more" in summarize(report(failed=ids), "d")


@pytest.mark.parametrize("model", ["replay:reference", "replay:naive", ""])
def test_refuses_to_present_a_replay_as_a_live_score(model):
    with pytest.raises(ScoreError, match="not a live model"):
        summarize(report(model=model), "d")


def test_missing_markers_are_an_error(tmp_path):
    f = tmp_path / "README.md"
    f.write_text("no markers here")
    with pytest.raises(ScoreError, match="not found"):
        update_readme(f, report(), "d")
    assert f.read_text() == "no markers here"


def test_cli_exit_codes(tmp_path, capsys):
    readme, rep = tmp_path / "README.md", tmp_path / "r.json"
    readme.write_text(README)
    rep.write_text(json.dumps(report()))
    assert main([str(rep), "--readme", str(readme), "--date", "2026-02-01"]) == 0
    rep.write_text(json.dumps(report(model="replay:reference")))
    assert main([str(rep), "--readme", str(readme)]) == 2
    assert "not a live model" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.json"), "--readme", str(readme)]) == 2


def test_the_shipped_readme_has_the_markers():
    from evals.readme_score import DEFAULT_README
    text = DEFAULT_README.read_text()
    assert START in text and END in text
