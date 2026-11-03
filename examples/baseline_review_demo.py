"""Review an intentional refund-policy change without model credentials.

Run from a checkout with python -m examples.baseline_review_demo. The demo writes
raw old/proposed evaluations and reviews, but never approves them. Follow the
printed approve-baseline commands after inspecting the evidence.
"""

import argparse
import shlex
import sys
from pathlib import Path

from thadam import (
    OutputEquals,
    ReportWriteError,
    SuiteIdentity,
    review_baseline,
    run_repeated,
    run_suite,
    write_baseline_review,
    write_repeated,
    write_report,
)
from thadam import TestCase as Case
from thadam import TestSuite as Suite
from thadam.baseline_reporting import format_baseline_review
from thadam.terminal import terminal_style


def _suite(revision: str, limit: int) -> Suite:
    return Suite(
        SuiteIdentity("refund-policy", revision),
        tuple(
            Case(name, {"days": days}, (OutputEquals("decision", {"approved": days <= limit}),))
            for name, days in (("within-policy", 7), ("changed-boundary", 20))
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Generate controlled evidence in a fresh directory; return 2 if files already exist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/baseline-review-demo"))
    arguments = parser.parse_args(argv)
    destination = arguments.output
    names = [
        f"{mode}-{kind}.json"
        for mode in ("single", "repeated")
        for kind in ("baseline", "candidate", "review")
    ]
    if any((destination / name).exists() for name in names):
        print(
            "Demo evidence already exists. Use --output with a fresh directory to preserve your review.",
            file=sys.stderr,
        )
        return 2
    try:
        for mode in ("single", "repeated"):
            execute = run_suite if mode == "single" else run_repeated
            settings = {} if mode == "single" else {"attempts": 5}
            baseline = execute(
                lambda value: {"approved": value["days"] <= 30},
                _suite("policy-30-days", 30),
                agent_revision="old-policy",
                **settings,
            )
            candidate = execute(
                lambda value: {"approved": value["days"] <= 14},
                _suite("policy-14-days", 14),
                agent_revision="new-policy",
                **settings,
            )
            writer = write_report if mode == "single" else write_repeated
            writer(baseline, destination / f"{mode}-baseline.json")
            writer(candidate, destination / f"{mode}-candidate.json")
            review = review_baseline(candidate, baseline)
            path = destination / f"{mode}-review.json"
            write_baseline_review(review, path)
            print(format_baseline_review(review, style=terminal_style("auto", sys.stdout)))
            print("\nAfter inspecting the review, approve this controlled example explicitly:\n")
            print(
                shlex.join(
                    [
                        "python",
                        "-m",
                        "thadam",
                        "approve-baseline",
                        str(path),
                        "--baseline",
                        str(destination / f"{mode}-baseline.json"),
                        "--review-digest",
                        review.digest,
                        "--reviewer",
                        "YourName",
                        "--reason",
                        "Reviewed 14-day refund policy",
                    ]
                )
                + "\n"
            )
        return 0
    except (OSError, ReportWriteError) as error:
        print(f"Cannot write demo evidence: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
