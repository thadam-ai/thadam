"""Repeated-run JSON and terminal summaries, preserving complete attempt evidence."""

import textwrap
from dataclasses import asdict
from pathlib import Path

from thadam.models import JSONValue
from thadam.repetition import OutcomeCounts, RepeatedReport
from thadam.reporting import format_summary, report_to_dict, write_json_artifact
from thadam.terminal import ColorRole, TerminalStyle, display_text


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


def append_line(
    lines: list[str],
    value: str,
    style: TerminalStyle,
    width: int,
    role: ColorRole = "muted",
    indent: int = 2,
) -> None:
    """Append wrapped terminal text, escaping control characters before coloring."""
    for part in textwrap.wrap(
        display_text(value), width=width - indent, break_on_hyphens=False
    ) or [""]:
        lines.append(" " * indent + style.paint(part, role))


def format_repeated(
    report: RepeatedReport, *, style: TerminalStyle | None = None, width: int = 88
) -> str:
    """Display counts, runtime, variability, and all failing/errored attempt evidence."""
    style = style or TerminalStyle()
    width = max(20, min(width, 96))
    lines = ["", style.paint("  THADAM", "brand", bold=True)]
    append_line(lines, f"Repeated evaluation: {report.attempts} attempts", style, width, "info")
    append_line(lines, f"Report: {report.report_id}; mode: {report.execution_mode}", style, width)
    if report.agent_revision is not None:
        append_line(lines, f"Agent revision: {report.agent_revision}", style, width, "info")
    for case in report.cases:
        counts = case.counts
        role: ColorRole = "error" if counts.errors else "failed" if counts.failed else "brand"
        append_line(
            lines,
            f"{case.id}: {counts.passed}/{counts.total} passed ({counts.pass_rate:.1%}), "
            f"{counts.failed} failed, {counts.errors} errors; "
            f"{'VARIABLE' if case.variable else 'STABLE'} observed outcomes",
            style,
            width,
            role,
        )
        for check in case.checks:
            append_line(
                lines,
                f"check {check.id}: {check.counts.passed}/{check.counts.total} passed, "
                f"{check.counts.failed} failed, {check.counts.errors} errors",
                style,
                width,
                indent=4,
            )
        runtime = case.runtime
        append_line(
            lines,
            f"Runtime ms: mean {runtime.mean_ms:.2f}, median {runtime.median_ms:.2f}, "
            f"min {runtime.min_ms:.2f}, max {runtime.max_ms:.2f}, total {runtime.total_ms:.2f}",
            style,
            width,
            indent=4,
        )
    for attempt, run in enumerate(report.runs, 1):
        if run.has_failures:
            append_line(lines, f"Attempt {attempt} / run {run.run_id}", style, width, "info")
            # Existing formatting includes expectations, errors, trace warnings,
            # and event IDs. Keep the original case/run identity for investigation.
            lines.append(format_summary(run, style=style, width=width))
    append_line(
        lines,
        "Observed rates describe these attempts; they are not causal or significance tests.",
        style,
        width,
    )
    return "\n".join(lines)
