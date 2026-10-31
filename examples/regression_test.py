"""Use Thadam's saved baseline as a normal pytest gate for your application."""

from pathlib import Path

from examples.refund_agent import run
from thadam import (
    compare_repeated,
    compare_reports,
    load_repeated,
    load_report,
    load_suite,
    run_repeated,
    run_suite,
)
from thadam.comparison_reporting import format_comparison
from thadam.reliability_reporting import format_reliability_comparison

ROOT = Path(__file__).resolve().parents[1]


def test_refund_agent_has_no_regressions():
    """Compare the candidate with reviewed evidence; keep baseline updates explicit."""
    baseline = load_report(ROOT / "examples/baselines/refund-report.json")
    candidate = run_suite(run, load_suite(ROOT / "examples/refund_cases.json"))
    comparison = compare_reports(baseline, candidate)
    assert comparison.exit_code == 0, format_comparison(comparison)


def test_refund_agent_reliability_has_no_regressions():
    """Compare equal repeated evaluations with an explicitly reviewed fixture baseline."""
    baseline = load_repeated(ROOT / "examples/baselines/refund-repeated.json")
    candidate = run_repeated(
        run,
        load_suite(ROOT / "examples/refund_cases.json"),
        attempts=baseline.attempts,
        agent_revision="local-candidate",
    )
    comparison = compare_repeated(baseline, candidate)
    assert comparison.exit_code == 0, format_reliability_comparison(comparison)
