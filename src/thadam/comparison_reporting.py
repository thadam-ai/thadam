"""Machine-readable comparison artifacts and human-readable terminal evidence."""

import json
import textwrap
from dataclasses import asdict
from pathlib import Path

from thadam.comparison import ComparisonReport
from thadam.models import JSONValue
from thadam.reporting import write_json_artifact
from thadam.terminal import ColorRole, TerminalStyle, display_text


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
    report: ComparisonReport, *, style: TerminalStyle | None = None, width: int = 88
) -> str:
    """Render wrapped, escaped status labels and evidence with optional semantic color."""
    style = style or TerminalStyle()
    width = max(20, min(width, 96))
    lines = ["", style.paint("  THADAM", "brand", bold=True)]

    def add(value: str, role: ColorRole = "muted", *, indent: int = 4) -> None:
        for line in textwrap.wrap(
            display_text(value), width=width - indent, break_on_hyphens=False
        ) or [""]:
            lines.append(" " * indent + style.paint(line, role))

    add("Regression comparison", "info", indent=2)
    lines.append("")
    add(f"Baseline: {report.baseline_run_id}", "info", indent=2)
    add(f"Candidate: {report.candidate_run_id}", "info", indent=2)
    for label, revision in (
        ("Baseline revision", report.baseline_agent_revision),
        ("Candidate revision", report.candidate_agent_revision),
    ):
        if revision is not None:
            add(f"{label}: {revision}", "info", indent=2)
    lines.append("")
    roles: dict[str, ColorRole] = {
        "regression": "failed",
        "fixed": "brand",
        "existing_failure": "failed",
        "unchanged_pass": "brand",
        "error": "error",
        "incompatible": "error",
    }
    for case in report.cases:
        add(f"{case.change.replace('_', ' ').upper()}: {case.id}", roles[case.change], indent=2)
        for issue in case.issues:
            add(issue, "error")
        for check in case.checks:
            if check.change == "unchanged_pass":
                continue
            add(f"{check.id}: {check.change.replace('_', ' ').upper()}", roles[check.change])
            for label, result in (("baseline", check.baseline), ("candidate", check.candidate)):
                if result is None:
                    add(f"{label}: no verdict; see recorded errors", "error", indent=6)
                    continue
                add(
                    f"{label}: {'passed' if result.passed else 'failed'} — {result.message}",
                    roles[check.change],
                    indent=6,
                )
                add(f"expected: {json.dumps(result.expected, ensure_ascii=False)}", indent=6)
                add(f"actual: {json.dumps(result.actual, ensure_ascii=False)}", indent=6)
                if result.event_ids:
                    add(f"events: {', '.join(result.event_ids)}", indent=6)
        for label, errors in (
            ("baseline", case.baseline_errors),
            ("candidate", case.candidate_errors),
        ):
            for error in errors:
                check_id = f" [{error.assertion_id}]" if error.assertion_id else ""
                add(f"{label} {error.source}{check_id}: {error.type}: {error.message}", "error")
    lines.append("")
    summary = report.summary
    for count, singular, plural, role in (
        (summary.regressions, "regression", "regressions", "failed"),
        (summary.fixed, "fixed case", "fixed cases", "brand"),
        (summary.existing_failures, "existing failure", "existing failures", "failed"),
        (summary.unchanged_passes, "unchanged pass", "unchanged passes", "brand"),
        (summary.errors, "error", "errors", "error"),
        (summary.incompatible, "incompatible case", "incompatible cases", "error"),
    ):
        add(f"{count} {singular if count == 1 else plural}", role if count else "muted", indent=2)
    add(f"Comparison exit code: {report.exit_code}", "info", indent=2)
    return "\n".join(lines)
