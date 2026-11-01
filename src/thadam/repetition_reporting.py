"""Repeated-run JSON and terminal summaries, preserving complete attempt evidence."""

from dataclasses import asdict
from pathlib import Path

from thadam.models import JSONValue
from thadam.repetition import OutcomeCounts, RepeatedReport
from thadam.reporting import report_to_dict, write_json_artifact
from thadam.terminal import TerminalStyle
from thadam.terminal_reporting import ReportView, grouped_evidence, verbose_attempts


def counts_to_dict(counts: OutcomeCounts) -> dict[str, JSONValue]:
    """Serialize counts with their observed denominator and pass rate."""
    return {**asdict(counts), "total": counts.total, "pass_rate": counts.pass_rate}


def repeated_to_dict(report: RepeatedReport) -> dict[str, JSONValue]:
    """Return repeated-run schema 1 with full runs and derived case/check summaries."""
    cases = report.cases
    return {
        "schema_version": report.schema_version,
        "kind": report.kind,
        "report_id": report.report_id,
        "execution_mode": report.execution_mode,
        "agent_revision": report.agent_revision,
        "attempts": report.attempts,
        "summary": {
            "total_cases": len(cases),
            "total_invocations": report.attempts * len(cases),
            "passed": sum(case.counts.passed for case in cases),
            "failed": sum(case.counts.failed for case in cases),
            "errors": sum(case.counts.errors for case in cases),
            "variable_cases": sum(case.variable for case in cases),
            "duration_ms": sum(case.runtime.total_ms for case in cases),
        },
        "cases": [
            {
                "id": case.id,
                "counts": counts_to_dict(case.counts),
                "variable": case.variable,
                "runtime": asdict(case.runtime),
                "checks": [
                    {"id": check.id, "counts": counts_to_dict(check.counts)}
                    for check in case.checks
                ],
            }
            for case in cases
        ],
        "runs": [report_to_dict(run) for run in report.runs],
    }


def write_repeated(report: RepeatedReport, path: str | Path) -> None:
    """Atomically write repeated-run evidence; raise ReportWriteError on failure."""
    write_json_artifact(repeated_to_dict(report), path)


def format_repeated(
    report: RepeatedReport,
    *,
    style: TerminalStyle | None = None,
    width: int = 88,
    verbose: bool = False,
) -> str:
    """Show outcome/runtime tables and grouped failures, or full attempt evidence."""
    view = ReportView(style, width)
    view.header("Repeated evaluation")
    cases = report.cases
    counts = {
        "passed": sum(case.counts.passed for case in cases),
        "failed": sum(case.counts.failed for case in cases),
        "errors": sum(case.counts.errors for case in cases),
        "total_invocations": report.attempts * len(cases),
    }
    view.summary(
        "FAILED" if report.has_failures else "PASSED",
        "error" if counts["errors"] else "failed" if report.has_failures else "brand",
        [
            (f"{counts['passed']} passed", "brand" if counts["passed"] else "muted"),
            (f"{counts['failed']} failed", "failed" if counts["failed"] else "muted"),
            (
                f"{counts['errors']} {'error' if counts['errors'] == 1 else 'errors'}",
                "error" if counts["errors"] else "muted",
            ),
        ],
    )
    view.field(
        "Attempts",
        f"{report.attempts} per case / {counts['total_invocations']} invocations / {report.execution_mode} agent",
    )
    if report.agent_revision is not None:
        view.field("Revision", report.agent_revision)
    if verbose:
        view.field("Report ID", report.report_id)
    view.table(
        ("CASE", "PASSED", "FAILED", "ERRORS", "MEDIAN"),
        [
            (
                case.id,
                f"{case.counts.passed}/{case.counts.total} ({case.counts.pass_rate:.1%})",
                str(case.counts.failed),
                str(case.counts.errors),
                f"{case.runtime.median_ms:.2f} ms",
            )
            for case in cases
        ],
        [
            (
                "info",
                "brand" if case.counts.passed else "muted",
                "failed" if case.counts.failed else "muted",
                "error" if case.counts.errors else "muted",
                "muted",
            )
            for case in cases
        ],
    )
    view.add("Runtime ms: median per case", indent=4)
    for case in cases:
        if case.variable:
            view.section(f"VARIABLE: {case.id}", "error" if case.counts.errors else "failed")
        if verbose or case.variable:
            for check in case.checks:
                counts = check.counts
                view.add(
                    f"check {check.id}: {counts.passed}/{counts.total} passed, {counts.failed} failed, {counts.errors} errors",
                    indent=4,
                )
        if verbose:
            runtime = case.runtime
            view.add(
                f"Runtime ms / {case.id}: mean {runtime.mean_ms:.2f}, median {runtime.median_ms:.2f}, min {runtime.min_ms:.2f}, max {runtime.max_ms:.2f}, total {runtime.total_ms:.2f}",
                indent=4,
            )
    if verbose:
        verbose_attempts(view, report.runs)
    else:
        grouped_evidence(view, report.runs)
    view.section(
        "Observed rates describe these attempts; they are not causal or significance tests."
    )
    return view.finish()
