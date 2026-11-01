"""Machine-readable comparison artifacts and human-readable terminal evidence."""

import json
from dataclasses import asdict
from pathlib import Path

from thadam.comparison import ComparisonReport
from thadam.models import JSONValue
from thadam.reporting import write_json_artifact
from thadam.terminal import TerminalStyle
from thadam.terminal_reporting import ROLES, ReportView, assertion_evidence, error_evidence, label


def comparison_to_dict(report: ComparisonReport) -> dict[str, JSONValue]:
    """Return comparison schema 1, with JSON arrays, evidence, counts, and gate result."""
    data = {
        **asdict(report),
        "compatible": report.compatible,
        "summary": asdict(report.summary),
        "exit_code": report.exit_code,
    }
    return json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))


def write_comparison(report: ComparisonReport, path: str | Path) -> None:
    """Atomically write a comparison; raise ReportWriteError on destination failures."""
    write_json_artifact(comparison_to_dict(report), path)


def format_comparison(
    report: ComparisonReport,
    *,
    style: TerminalStyle | None = None,
    width: int = 88,
    verbose: bool = False,
) -> str:
    """Show comparison verdict first, case rows, and changed or all recorded checks."""
    view = ReportView(style, width)
    view.header("Regression comparison")
    summary = report.summary
    counts = [
        (
            f"{summary.regressions} {'regression' if summary.regressions == 1 else 'regressions'}",
            "failed" if summary.regressions else "muted",
        ),
        (f"{summary.fixed} fixed", "brand" if summary.fixed else "muted"),
        (
            f"{summary.existing_failures} existing failures",
            "failed" if summary.existing_failures else "muted",
        ),
        (f"{summary.unchanged_passes} unchanged", "muted"),
        (f"{summary.errors} errors", "error" if summary.errors else "muted"),
        (f"{summary.incompatible} incompatible", "error" if summary.incompatible else "muted"),
    ]
    view.summary(
        "INCOMPATIBLE" if not report.compatible else "BLOCKED" if report.exit_code else "PASSED",
        "error"
        if not report.compatible or summary.errors
        else "failed"
        if report.exit_code
        else "brand",
        counts,
    )
    view.field("Baseline", report.baseline_agent_revision or report.baseline_run_id)
    view.field("Candidate", report.candidate_agent_revision or report.candidate_run_id)
    if verbose:
        view.field("Baseline run", report.baseline_run_id)
        view.field("Candidate run", report.candidate_run_id)
    view.table(
        ("CASE", "BASELINE", "CANDIDATE", "CHANGE"),
        [
            (
                case.id,
                label(case.baseline_status) if case.baseline_status else "MISSING",
                label(case.candidate_status) if case.candidate_status else "MISSING",
                label(case.change),
            )
            for case in report.cases
        ],
        [
            (
                "info",
                ROLES.get(case.baseline_status, "muted"),
                ROLES.get(case.candidate_status, "muted"),
                ROLES[case.change],
            )
            for case in report.cases
        ],
    )
    for case in report.cases:
        if case.change != "unchanged_pass" or verbose:
            view.section(f"{label(case.change)}: {case.id}", ROLES[case.change])
        for issue in case.issues:
            view.add(issue, "error", indent=4)
        for check in case.checks:
            if check.change == "unchanged_pass" and not verbose:
                continue
            view.add(f"{check.id}: {label(check.change)}", ROLES[check.change], indent=4)
            for side, result in (("baseline", check.baseline), ("candidate", check.candidate)):
                view.add(
                    f"{side}: "
                    + (
                        "no verdict; see recorded errors"
                        if result is None
                        else "passed"
                        if result.passed
                        else "failed"
                    ),
                    ROLES[check.change],
                    indent=4,
                )
                if result is not None:
                    assertion_evidence(view, result)
        for side, errors in (
            ("baseline", case.baseline_errors),
            ("candidate", case.candidate_errors),
        ):
            for error in errors:
                view.add(side + " error", "error", indent=4)
                error_evidence(view, error)
    view.section(f"Comparison exit code: {report.exit_code}")
    return view.finish()
