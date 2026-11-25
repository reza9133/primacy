"""Verdict rules of the end-to-end report, independent of any network."""

from scripts import live_e2e as live
from scripts.e2e_report import ALIGNED, DIVERGED, ERROR, FAIL, HARD, PASS, SOFT, Report, Step


def step(status, kind=HARD):
    return Step("S", "t", kind, status)


def test_clean_report_passes():
    report = Report()
    report.add(step(PASS))
    assert report.verdict() == "PASS"


def test_hard_failures_and_errors_fail_the_run_even_with_gaps():
    for status in (FAIL, ERROR):
        report = Report()
        report.add(step(PASS))
        report.add(step(status))
        report.coverage_gaps.append("gap")
        assert report.verdict() == "FAIL"


def test_model_divergence_alone_does_not_fail_the_run():
    report = Report()
    report.add(step(PASS))
    report.add(step(DIVERGED, SOFT))
    report.add(step(ALIGNED, SOFT))
    assert report.verdict() == "PASS"


def test_a_run_that_never_exercised_the_reward_paths_is_incomplete_not_a_pass(tmp_path):
    args = live.parse_args(["--sim", "--out", str(tmp_path)])
    for statuses, gaps in (
        ([], 2),
        (["revealed", "unresolved"], 2),
        (["distinct"], 1),
        (["duplicate", "invalid"], 1),
        (["distinct", "duplicate"], 0),
        (["distinct", "invalid"], 0),
    ):
        runner = live.E2E(args)
        runner.report.table("Adjudications", [{"status": status} for status in statuses])
        runner.report.add(step(PASS))
        runner.check_coverage()
        assert len(runner.report.coverage_gaps) == gaps, (statuses, runner.report.coverage_gaps)
        assert runner.report.verdict() == ("INCOMPLETE" if gaps else "PASS")


def test_aborted_run_is_incomplete():
    report = Report()
    report.add(step(PASS))
    report.aborted = "network unreachable"
    assert report.verdict() == "INCOMPLETE"
    assert "Run aborted" in report.markdown()


def test_markdown_lists_coverage_gaps():
    report = Report()
    report.add(step(PASS))
    report.coverage_gaps.append("no finding was ever accepted as distinct")
    assert "Coverage gaps" in report.markdown() and "INCOMPLETE" in report.markdown()
