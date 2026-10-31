"""Standalone reliability artifacts and terminal evidence for change review."""

import json
from dataclasses import asdict
from pathlib import Path

from thadam.models import JSONValue
from thadam.reliability import RateComparison, ReliabilityComparison
from thadam.repetition_reporting import append_line, counts_to_dict, repeated_to_dict
from thadam.reporting import format_summary, write_json_artifact
from thadam.terminal import ColorRole, TerminalStyle


def reliability_to_dict(report: ReliabilityComparison) -> dict[str, JSONValue]:
    """Return reliability-comparison schema 1 including both full evidence reports."""

    def rate(value: RateComparison | None) -> dict | None:
        if value is None:
            return None
        return {
            "id": value.id,
            "change": value.change,
            "baseline": counts_to_dict(value.baseline),
            "candidate": counts_to_dict(value.candidate),
            "pass_rate_delta": value.pass_rate_delta,
        }

    data = {
        "schema_version": report.schema_version,
        "kind": report.kind,
        "policy": {"max_pass_rate_drop": report.max_pass_rate_drop},
        "baseline": repeated_to_dict(report.baseline),
        "candidate": repeated_to_dict(report.candidate),
        "issues": list(report.issues),
        "cases": [
            {
                "id": case.id,
                "change": case.change,
                "baseline": None if case.baseline is None else asdict(case.baseline),
                "candidate": None if case.candidate is None else asdict(case.candidate),
                "case_rate": rate(case.case_rate),
                "checks": [rate(check) for check in case.checks],
                "issues": list(case.issues),
            }
            for case in report.cases
        ],
        "compatible": report.compatible,
        "summary": report.summary,
        "exit_code": report.exit_code,
    }
    return json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))


def write_reliability_comparison(report: ReliabilityComparison, path: str | Path) -> None:
    """Atomically write comparison/evidence; raise ReportWriteError for write failures."""
    write_json_artifact(reliability_to_dict(report), path)


def format_reliability_comparison(
    report: ReliabilityComparison, *, style: TerminalStyle | None = None, width: int = 88
) -> str:
    """Show case/check rates, tolerated changes, policy, and failing attempt evidence."""
    style = style or TerminalStyle()
    width = max(20, min(width, 96))
    lines = ["", style.paint("  THADAM", "brand", bold=True)]
    append_line(lines, "Reliability comparison", style, width, "info")
    for side, evidence in (("Baseline", report.baseline), ("Candidate", report.candidate)):
        append_line(
            lines,
            f"{side}: {evidence.report_id}; revision {evidence.agent_revision}; "
            f"{evidence.attempts} attempts; {evidence.execution_mode}",
            style,
            width,
            "info",
        )
    append_line(
        lines,
        f"Allowed pass-rate drop: {report.max_pass_rate_drop * 100:g} percentage points",
        style,
        width,
        "info",
    )
    for issue in report.issues:
        append_line(lines, issue, style, width, "error")
    roles: dict[str, ColorRole] = {
        "regression": "failed",
        "tolerated_drop": "failed",
        "improved": "brand",
        "unchanged": "brand",
        "error": "error",
        "incompatible": "error",
    }
    for case in report.cases:
        append_line(
            lines,
            f"{case.change.replace('_', ' ').upper()}: {case.id}",
            style,
            width,
            roles[case.change],
        )
        for issue in case.issues:
            append_line(lines, issue, style, width, "error", indent=4)
        for label, rate in [("case", case.case_rate), *(("check", check) for check in case.checks)]:
            if rate is None:
                continue
            left, right = rate.baseline, rate.candidate
            role = roles[rate.change]
            if rate.change == "unchanged" and (left.failed or right.failed):
                role = "failed"
            append_line(
                lines,
                f"{label} {rate.id}: {left.passed}/{left.total} ({left.pass_rate:.1%}) -> "
                f"{right.passed}/{right.total} ({right.pass_rate:.1%}); "
                f"{rate.pass_rate_delta * 100:+.2f} pp; {rate.change.replace('_', ' ').upper()}; "
                f"errors {left.errors} -> {right.errors}",
                style,
                width,
                role,
                indent=4,
            )
    # Print every unsuccessful attempt on both sides, including already accepted
    # failures. Do not hide evidence behind case-level precedence or tolerance.
    for side, evidence in (("Baseline", report.baseline), ("Candidate", report.candidate)):
        for attempt, run in enumerate(evidence.runs, 1):
            if run.has_failures:
                append_line(
                    lines, f"{side} attempt {attempt} / run {run.run_id}", style, width, "info"
                )
                lines.append(format_summary(run, style=style, width=width))
    for label, count in report.summary.items():
        append_line(lines, f"{label}: {count}", style, width)
    append_line(lines, f"Comparison exit code: {report.exit_code}", style, width, "info")
    append_line(
        lines,
        "Observed rates are not a significance test or proof that the change caused a difference.",
        style,
        width,
    )
    return "\n".join(lines)
