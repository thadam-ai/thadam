"""Baseline review terminal presentation and saved review artifacts."""

import json
from pathlib import Path

from thadam.baseline_review import BaselineReview, review_to_dict
from thadam.models import RunReport
from thadam.repetition import RepeatedReport
from thadam.reporting import write_json_artifact
from thadam.terminal import TerminalStyle
from thadam.terminal_reporting import ReportView, case_evidence, grouped_evidence, verbose_attempts


def write_baseline_review(review: BaselineReview, path: str | Path) -> None:
    """Atomically save review evidence; raise ReportWriteError on write failure."""
    write_json_artifact(review_to_dict(review), path)


def format_baseline_review(
    review: BaselineReview,
    *,
    style: TerminalStyle | None = None,
    width: int = 88,
    verbose: bool = False,
) -> str:
    """Render contract changes, outcome counts, blockers, and the exact approval digest."""
    view = ReportView(style, width)
    view.header("Baseline review")
    view.summary(
        "BLOCKED" if review.blockers else "REVIEW REQUIRED",
        "error" if review.blockers else "failed",
        [
            (f"{len(review.changes)} contract/settings changes", "info"),
            (f"{len(review.blockers)} blockers", "error" if review.blockers else "muted"),
        ],
    )
    view.field(
        "Purpose", "Initial baseline" if review.baseline is None else "Replace reviewed baseline"
    )
    view.field("Review SHA-256", review.digest)
    for side, report in (("Baseline", review.baseline), ("Candidate", review.candidate)):
        if report is None:
            continue
        runs = report.runs if isinstance(report, RepeatedReport) else (report,)
        passed = sum(run.summary.passed for run in runs)
        failed = sum(run.summary.failed for run in runs)
        errors = sum(run.summary.errors for run in runs)
        view.field(side + " outcomes", f"{passed} passed / {failed} failed / {errors} errors")
        if report.suite is not None:
            view.field(side + " suite", f"{report.suite.id} @ {report.suite.revision}")
        view.field(side + " revision", report.agent_revision or "unavailable")
        if isinstance(report, RepeatedReport):
            view.field(side + " execution", f"{report.attempts} attempts / {report.execution_mode}")
    for change in review.changes:
        name = " / ".join(part for part in (change.case_id, change.check_id) if part is not None)
        view.section(change.scope.replace("_", " ").upper() + (": " + name if name else ""), "info")
        for side, value in (("Before", change.before), ("After", change.after)):
            view.field(side, json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))
    if not review.changes:
        view.add("No declared contract/settings changes; review the new outcomes before approval.")

    # Do not invent rate differences for changed checks. Display complete per-side
    # case/check counts so improvements cannot conceal individual failures.
    def rows(report: RunReport | RepeatedReport) -> list[tuple[str, str, str, str, str]]:
        if isinstance(report, RepeatedReport):
            return [
                (
                    case.id,
                    check.id,
                    f"{check.counts.passed}/{check.counts.total}",
                    str(check.counts.failed),
                    str(check.counts.errors),
                )
                for case in report.cases
                for check in case.checks
            ]
        data = []
        for case in report.cases:
            verdicts = {check.id: check.passed for check in case.assertions}
            for definition in case.check_definitions:
                verdict = verdicts.get(definition.id)
                data.append(
                    (
                        case.id,
                        definition.id,
                        str(int(verdict is True)),
                        str(int(verdict is False)),
                        str(int(verdict is None)),
                    )
                )
        return data

    for side, report in (("Baseline", review.baseline), ("Candidate", review.candidate)):
        if report is None:
            continue
        view.section(side + " check outcomes", "info")
        data = rows(report)
        view.table(
            ("CASE", "CHECK", "PASSED", "FAILED", "ERRORS"),
            data,
            [
                (
                    "info",
                    "info",
                    "brand",
                    "failed" if row[3] != "0" else "muted",
                    "error" if row[4] != "0" else "muted",
                )
                for row in data
            ],
        )
        runs = report.runs if isinstance(report, RepeatedReport) else (report,)
        if verbose:
            verbose_attempts(view, runs, side=side)
        elif isinstance(report, RepeatedReport):
            grouped_evidence(view, runs, side=side)
        else:
            for case in report.cases:
                case_evidence(view, case, verbose=False)
    for blocker in review.blockers:
        view.section("BLOCKER", "error")
        view.add(blocker, "error", indent=4)
    if review.has_failures:
        view.section("FAILED EXPECTATIONS REQUIRE ACKNOWLEDGEMENT", "failed")
        view.add(
            "Approval requires --accept-failures. These failures remain visible in future comparisons."
        )
    view.section("Next step", "info")
    view.add(
        "Inspect this review and the saved evidence. approve-baseline requires the exact review digest, reviewer, reason, and destination. Commit the approved baseline through a reviewed pull request."
    )
    return view.finish()
