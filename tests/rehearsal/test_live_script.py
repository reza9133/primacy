"""Run scripts/live_e2e.py against the local simulator, including under bad model behavior.

The simulator answers with scripted model output, so these tests prove that the live script and the
contract stay consistent when the model misbehaves. They say nothing about Studionet itself.
"""

import json
import re

import pytest

from scripts import live_e2e as live

pytestmark = pytest.mark.rehearsal


def run_script(tmp_path, *extra):
    args = live.parse_args(["--sim", "--out", str(tmp_path), *extra])
    code = live.E2E(args).run()
    report_json = next(tmp_path.glob("rehearsal-*.json"))
    report_md = next(tmp_path.glob("rehearsal-*.md"))
    return code, json.loads(report_json.read_text()), report_md.read_text()


def failing(data):
    return [s["title"] for s in data["steps"] if s["status"] in ("FAIL", "ERROR")]


def steps(data, fragment):
    return [s for s in data["steps"] if fragment in s["title"]]


def test_clean_run_passes_every_hard_check_and_writes_a_report(tmp_path):
    code, data, markdown = run_script(tmp_path)
    assert code == 0 and data["verdict"] == "PASS", failing(data)
    assert data["counts"]["hard_fail"] == 0 and data["counts"]["errors"] == 0
    assert data["counts"]["hard_pass"] >= 150 and len(data["transactions"]) >= 70
    scenarios = {s["scenario"][:3] for s in data["steps"]}
    assert scenarios == {"S00", "S01", "S02", "S03", "S04", "S05", "S06", "S07"}
    assert "not** a Studionet result" in markdown or "not a Studionet result" in markdown
    assert re.search(r"Ledger reconciliation \(after withdrawals\)", markdown)
    assert not list(tmp_path.glob("*.partial.json"))
    rows = data["tables"]["Adjudications"]
    assert [r["status"] for r in rows] == ["distinct", "duplicate", "distinct", "invalid", "duplicate", "invalid"]
    copy_row = rows[4]
    assert copy_row["attempts"] == 0 and copy_row["confidence"] == 100


def test_fast_mode_skips_only_the_time_gated_phase(tmp_path):
    code, data, _ = run_script(tmp_path, "--fast")
    assert code == 0, failing(data)
    skipped = [s for s in data["steps"] if s["status"] == "SKIP" and s["scenario"].startswith("S06")]
    assert len(skipped) == 1
    assert [s for s in data["steps"] if s["scenario"].startswith("S06")] == skipped
    assert not any(t["method"] in ("void_unrevealed", "close_bounty") for t in data["transactions"])


def test_a_model_fooled_by_the_injection_never_breaks_the_accounting(tmp_path, monkeypatch):
    monkeypatch.setitem(live.SIM_ANSWERS, "injection", live._analysis())  # the model obeys the injected text
    code, data, _ = run_script(tmp_path)
    assert code == 1
    assert any("injection" in title for title in failing(data))
    assert not [t for t in failing(data) if "Ledger reconciliation" in t or "credit change" in t]
    reconciliations = steps(data, "Ledger reconciliation")
    assert reconciliations and all(s["status"] == "PASS" or s["status"] == "SKIP" for s in reconciliations)
    # Filling the last slot closes the bounty, so the time-gated phase has nothing left to do.
    assert any(s["status"] == "SKIP" and "no longer open" in s["note"] for s in data["steps"])


def test_inconclusive_model_answers_are_retried_and_end_without_losing_funds(tmp_path, monkeypatch):
    monkeypatch.setitem(live.SIM_ANSWERS, "retry", live._analysis(confidence=40))
    code, data, _ = run_script(tmp_path)
    assert code == 1  # the soft expectation 'distinct' diverged
    assert failing(data) == ["model verdict for 'retry'"]
    row = next(r for r in data["tables"]["Adjudications"] if "retry" in r["finding"])
    assert row["status"] == "unresolved" and row["attempts"] == 3
    reconciliations = steps(data, "Ledger reconciliation")
    assert reconciliations and all(s["status"] in ("PASS", "SKIP") for s in reconciliations)


def test_an_unreachable_network_is_reported_as_incomplete_not_as_a_pass(tmp_path):
    args = live.parse_args(["--rpc", "http://127.0.0.1:9/api", "--out", str(tmp_path)])
    code = live.E2E(args).run()
    data = json.loads(next(tmp_path.glob("live-e2e-*.json")).read_text())
    assert code == 2 and data["verdict"] == "INCOMPLETE"
    assert "not reachable" in data["aborted"]


def test_an_unavailable_model_stops_the_waiting_and_keeps_the_ledger_exact(tmp_path, monkeypatch):
    for topic in list(live.SIM_ANSWERS):
        monkeypatch.setitem(live.SIM_ANSWERS, topic, {"unrelated": True})  # every answer is unusable
    code, data, _ = run_script(tmp_path)
    assert code == 1
    assert all(title.startswith("model verdict for") for title in failing(data)), failing(data)
    # The first finding never resolves, so the queue never moves: later findings are skipped, not mis-attributed.
    skipped = [s for s in data["steps"] if s["status"] == "SKIP" and "the queue is at finding" in s["note"]]
    assert len(skipped) >= 3, "later adjudications should be skipped while an earlier finding is stuck"
    assert any(s["status"] == "SKIP" and "still pending" in s["note"] for s in data["steps"])
    reconciliations = steps(data, "Ledger reconciliation")
    assert reconciliations and all(s["status"] in ("PASS", "SKIP") for s in reconciliations)
