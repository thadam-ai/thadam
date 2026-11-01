"""Standalone reliability artifacts and terminal evidence for change review."""

import json
from dataclasses import asdict
from pathlib import Path

from thadam.models import JSONValue
from thadam.reliability import RateComparison, ReliabilityComparison
from thadam.repetition import CaseReliability
from thadam.repetition_reporting import counts_to_dict, repeated_to_dict
from thadam.reporting import write_json_artifact
from thadam.terminal import TerminalStyle
from thadam.terminal_reporting import ROLES, ReportView, grouped_evidence, label, verbose_attempts


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
    report: ReliabilityComparison,
    *,
    style: TerminalStyle | None = None,
    width: int = 88,
    verbose: bool = False,
) -> str:
    """Show reliability verdict/rates and grouped evidence, or every recorded attempt."""
    view = ReportView(style, width)
    view.header("Reliability comparison")
    summary = report.summary
    nouns = {
        "regression": ("regression", "regressions"),
        "tolerated_drop": ("tolerated drop", "tolerated drops"),
        "improved": ("improved", "improved"),
        "unchanged": ("unchanged", "unchanged"),
        "error": ("error", "errors"),
        "incompatible": ("incompatible", "incompatible"),
    }
    view.summary(
        "INCOMPATIBLE" if not report.compatible else "BLOCKED" if report.exit_code else "PASSED",
        "error"
        if not report.compatible or summary["error"]
        else "failed"
        if report.exit_code
        else "brand",
        [
            (f"{count} {nouns[name][0 if count == 1 else 1]}", ROLES[name] if count else "muted")
            for name, count in summary.items()
            if name != "total"
        ],
    )
    for side, evidence in (("Baseline", report.baseline), ("Candidate", report.candidate)):
        view.field(
            side,
            f"{evidence.agent_revision or evidence.report_id} / {evidence.attempts} attempts / {evidence.execution_mode} agent",
        )
        if verbose:
            view.field(side + " ID", evidence.report_id)
    view.field(
        "Policy",
        f"Allow a drop of up to {report.max_pass_rate_drop * 100:g} percentage points per case/check",
    )
    for issue in report.issues:
        view.add(issue, "error", indent=4)

    def rate_text(case: CaseReliability | None) -> str:
        return (
            "MISSING"
            if case is None
            else f"{case.counts.passed}/{case.counts.total} ({case.counts.pass_rate:.1%})"
        )

    view.table(
        ("CASE", "BASELINE", "CANDIDATE", "CHANGE"),
        [
            (
                case.id,
                rate_text(case.baseline),
                rate_text(case.candidate),
                label(case.change)
                + (f" / {case.case_rate.pass_rate_delta * 100:+.1f} pp" if case.case_rate else ""),
            )
            for case in report.cases
        ],
        [
            (
                "info",
                "error" if case.baseline and case.baseline.counts.errors else "muted",
                "error" if case.candidate and case.candidate.counts.errors else "muted",
                "failed"
                if case.change == "unchanged"
                and (
                    (case.baseline and case.baseline.counts.failed)
                    or (case.candidate and case.candidate.counts.failed)
                )
                else ROLES[case.change],
            )
            for case in report.cases
        ],
    )
    for case in report.cases:
        if case.change != "unchanged" or verbose:
            view.section(f"{label(case.change)}: {case.id}", ROLES[case.change])
        for issue in case.issues:
            view.add(issue, "error", indent=4)
        for scope, rate in [("case", case.case_rate), *(("check", check) for check in case.checks)]:
            if rate is None or (
                not verbose
                and rate.change == "unchanged"
                and not rate.baseline.failed
                and not rate.candidate.failed
            ):
                continue
            left, right = rate.baseline, rate.candidate
            role = ROLES[rate.change]
            if rate.change == "unchanged" and (left.failed or right.failed):
                role = "failed"
            view.add(
                f"{scope} {rate.id}: {left.passed}/{left.total} ({left.pass_rate:.1%}) -> {right.passed}/{right.total} ({right.pass_rate:.1%}); {rate.pass_rate_delta * 100:+.2f} pp; {label(rate.change)}; errors {left.errors} -> {right.errors}",
                role,
                indent=4,
            )
    for side, evidence in (("Baseline", report.baseline), ("Candidate", report.candidate)):
        if verbose:
            verbose_attempts(view, evidence.runs, side=side)
        else:
            grouped_evidence(view, evidence.runs, side=side)
    view.section(f"Comparison exit code: {report.exit_code}")
    view.add(
        "Observed rates are not a significance test or proof that the change caused a difference."
    )
    return view.finish()
