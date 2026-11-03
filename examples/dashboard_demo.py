"""Create a complete controlled local dashboard workspace, without model API keys."""

import argparse
from pathlib import Path

from thadam import (
    AgentResult,
    ExecutionEvent,
    OutputEquals,
    SuiteIdentity,
    ToolCalled,
    approve_review,
    compare_repeated,
    compare_reports,
    review_baseline,
    run_repeated,
    run_suite,
    write_approved_baseline,
    write_baseline_review,
    write_comparison,
    write_reliability_comparison,
    write_repeated,
    write_report,
)
from thadam import TestCase as Case
from thadam import TestSuite as Suite
from thadam.reporting import write_json_artifact


def create_demo(root: Path) -> None:
    """Write illustrative fixtures into an empty folder; preserve any existing files."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("Demo folder is not empty. Choose a fresh --output directory.")
    root.mkdir(parents=True, exist_ok=True)
    (root / "agent.py").write_text('''"""Controlled refund policy; no external services."""
def run(value):
    return {"approved": value["days"] <= 14}

def run_buggy(value):
    return {"approved": True}

def create():
    return run
''')
    cases = tuple(
        Case(name, {"days": days}, (OutputEquals("decision", {"approved": days <= 14}),))
        for name, days in (("within-policy", 7), ("changed-boundary", 20), ("expired-refund", 45))
    )
    suite = Suite(SuiteIdentity("refund-policy", "policy-14-days"), cases)
    raw = {
        "schema_version": 2,
        "suite": {"id": suite.identity.id, "revision": suite.identity.revision},
        "cases": [
            {
                "id": case.id,
                "input": case.input,
                "assertions": [
                    {
                        "id": "decision",
                        "type": "output_equals",
                        "expected": case.assertions[0].expected,
                    }
                ],
            }
            for case in cases
        ],
    }
    write_json_artifact(raw, root / "cases.json")

    def good(value):
        return {"approved": value["days"] <= 14}

    def buggy(value):
        return {"approved": True}

    baseline = run_suite(good, suite, agent_revision="reviewed-policy")
    candidate = run_suite(buggy, suite, agent_revision="illustrative-bug")
    write_report(baseline, root / "reports/baseline.json")
    write_report(candidate, root / "reports/candidate.json")
    write_comparison(compare_reports(baseline, candidate), root / "reports/comparison.json")
    repeated = run_repeated(good, suite, attempts=5, agent_revision="reviewed-policy")
    failing = run_repeated(buggy, suite, attempts=5, agent_revision="illustrative-bug")
    write_repeated(repeated, root / "reports/repeated-baseline.json")
    write_repeated(failing, root / "reports/repeated-candidate.json")
    write_reliability_comparison(
        compare_repeated(repeated, failing), root / "reports/reliability.json"
    )
    review = review_baseline(baseline)
    write_baseline_review(review, root / "reports/initial-review.json")
    write_approved_baseline(
        approve_review(
            review,
            review_digest=review.digest,
            reviewer="Controlled demo fixture",
            reason="Illustrative local fixture, not a production policy approval",
        ),
        root / "baselines/approved.json",
    )
    event = ExecutionEvent(
        "order-lookup",
        "tool",
        "get_order",
        "completed",
        0,
        duration_ms=1,
        input={"id": "example"},
        input_available=True,
        output={"found": True},
        output_available=True,
    )
    traced = run_suite(
        lambda _: AgentResult({"approved": True}, (event,)),
        Suite(
            SuiteIdentity("observable-tools", "v1"),
            (Case("required-lookup", {}, (ToolCalled("lookup", "get_order"),)),),
        ),
    )
    write_report(traced, root / "reports/instrumented.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/dashboard-demo"))
    arguments = parser.parse_args()
    try:
        create_demo(arguments.output)
    except (OSError, ValueError) as error:
        print(error)
        return 2
    print(
        f"Demo workspace ready. Launch:\n\n  python -m thadam dashboard {arguments.output}\n\nAgent reference: agent:run (shared), or agent:create (factory)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
