"""Complete reliability comparison with scripted variation; no model service.

Run: python -m examples.reliability_demo
The resulting gate exits 1 because the candidate drops from 80% to 60% passing.
The sequences and revision labels are fixtures, not measurements of an LLM.
"""

import shutil
import sys
from itertools import cycle
from pathlib import Path

from thadam import (
    OutputEquals,
    TestCase,
    compare_repeated,
    run_repeated,
    write_reliability_comparison,
    write_repeated,
)
from thadam.reliability_reporting import format_reliability_comparison
from thadam.terminal import terminal_style


def main() -> int:
    """Save both evaluations and a standalone comparison for inspecting the drop."""
    cases = [TestCase("refund-decision", {"eligible": True}, (OutputEquals("approved", True),))]
    before = cycle([True, True, True, True, False])
    after = cycle([True, True, True, False, False])
    baseline = run_repeated(
        lambda _: next(before), cases, attempts=10, agent_revision="scripted-baseline"
    )
    candidate = run_repeated(
        lambda _: next(after), cases, attempts=10, agent_revision="scripted-candidate"
    )
    destination = Path("artifacts/reliability-demo")
    write_repeated(baseline, destination / "baseline.json")
    write_repeated(candidate, destination / "candidate.json")
    comparison = compare_repeated(baseline, candidate)
    write_reliability_comparison(comparison, destination / "comparison.json")
    print(
        format_reliability_comparison(
            comparison,
            style=terminal_style("auto", sys.stdout),
            width=shutil.get_terminal_size().columns,
        )
    )
    return comparison.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
