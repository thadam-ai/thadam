"""Pure baseline review snapshots, contract diffs, and strict review artifact loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from thadam._json import json_equal, read_json, validate_json
from thadam.contracts import equivalent_definitions
from thadam.errors import ReportValidationError
from thadam.models import CaseResult, JSONValue, RunReport
from thadam.repetition import RepeatedReport
from thadam.repetition_loading import repeated_from_dict, require_consistent, validate_repeated
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict, validate_report
from thadam.reporting import report_to_dict

Evaluation = RunReport | RepeatedReport


@dataclass(frozen=True)
class ContractChange:
    """One reviewable metadata, case, input, or check change with both declarations."""

    scope: str
    case_id: str | None
    check_id: str | None
    before: JSONValue
    after: JSONValue


@dataclass(frozen=True)
class BaselineReview:
    """Independent saved evidence; approval is bound to its complete SHA-256 digest."""

    baseline: Evaluation | None
    candidate: Evaluation
    changes: tuple[ContractChange, ...]
    blockers: tuple[str, ...]

    @property
    def digest(self) -> str:
        return evidence_digest(review_to_dict(self))

    @property
    def has_failures(self) -> bool:
        runs = (
            self.candidate.runs if isinstance(self.candidate, RepeatedReport) else (self.candidate,)
        )
        return any(
            not check.passed for run in runs for case in run.cases for check in case.assertions
        )

    @property
    def exit_code(self) -> int:
        return 1 if self.blockers else 0


def evaluation_to_dict(report: Evaluation) -> dict[str, JSONValue]:
    """Serialize a single or repeated evaluation without approval wrappers."""
    return (
        repeated_to_dict(report) if isinstance(report, RepeatedReport) else report_to_dict(report)
    )


def evidence_digest(data: dict[str, JSONValue]) -> str:
    """Hash canonical JSON including all outputs, attempts, traces, and durations."""
    content = json.dumps(
        data, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def evaluation_from_dict(data: object) -> Evaluation:
    """Validate raw evaluation evidence; nested review/approval wrappers are disallowed."""
    if isinstance(data, dict) and data.get("kind") == "repeated_run":
        return repeated_from_dict(data)
    return report_from_dict(data)


def load_evaluation(path: str | Path) -> Evaluation:
    """Read saved single/repeated evidence or an approved baseline, without executing code."""
    try:
        data = read_json(path, max_depth=125)
        if isinstance(data, dict) and data.get("kind") == "approved_baseline":
            return approved_from_dict(data).review.candidate
        return evaluation_from_dict(data)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReportValidationError(f"Cannot load evaluation {path}: {error}") from error


def _first(report: Evaluation) -> RunReport:
    return report.runs[0] if isinstance(report, RepeatedReport) else report


def _validated(report: Evaluation) -> Evaluation:
    return (
        validate_repeated(report) if isinstance(report, RepeatedReport) else validate_report(report)
    )


def _declaration(case: CaseResult | None) -> JSONValue:
    if case is None:
        return None
    return {"input": case.input, "checks": [asdict(check) for check in case.check_definitions]}


def review_baseline(candidate: Evaluation, baseline: Evaluation | None = None) -> BaselineReview:
    """Snapshot evidence and explain intentional changes; never run or approve anything.

    Candidate errors, unversioned verifiers, missing suite identity, a changed
    contract without a revision change, and switching evaluation kind block
    approval. An errored old baseline may be replaced by usable new evidence.
    Invalid evidence raises ReportValidationError. Existing failed assertions
    remain visible and require a separate acknowledgement at approval time.
    """
    candidate = _validated(candidate)
    baseline = None if baseline is None else _validated(baseline)
    current = _first(candidate)
    previous = None if baseline is None else _first(baseline)
    changes: list[ContractChange] = []
    blockers = []
    if current.suite is None:
        blockers.append("Candidate needs an explicit suite ID and revision (suite schema 2)")
    if baseline is not None and type(baseline) is not type(candidate):
        blockers.append("Evaluation kind changed; create a separate baseline for this workflow")
    if previous and previous.suite and current.suite and previous.suite.id != current.suite.id:
        blockers.append("Suite ID changed; create a separate baseline for a different suite")
    old = {} if previous is None else {case.id: case for case in previous.cases}
    new = {case.id: case for case in current.cases}
    for case_id in [*old, *(key for key in new if key not in old)]:
        left, right = old.get(case_id), new.get(case_id)
        if left is None or right is None:
            changes.append(
                ContractChange(
                    "case_added" if left is None else "case_removed",
                    case_id,
                    None,
                    _declaration(left),
                    _declaration(right),
                )
            )
            continue
        if not json_equal(left.input, right.input):
            changes.append(ContractChange("input_changed", case_id, None, left.input, right.input))
        a = {check.id: check for check in left.check_definitions}
        b = {check.id: check for check in right.check_definitions}
        for check_id in [*a, *(key for key in b if key not in a)]:
            before, after = a.get(check_id), b.get(check_id)
            if before is not None and after is not None:
                # Identical unversioned verifiers are still reported as a blocker
                # below; they do not manufacture a declaration change here.
                if equivalent_definitions(before, after) or json_equal(
                    asdict(before), asdict(after)
                ):
                    continue
            scope = (
                "check_added"
                if before is None
                else "check_removed"
                if after is None
                else "check_changed"
            )
            changes.append(
                ContractChange(
                    scope,
                    case_id,
                    check_id,
                    None if before is None else asdict(before),
                    None if after is None else asdict(after),
                )
            )
    if changes and previous and previous.suite == current.suite and current.suite is not None:
        blockers.append(
            "Contracts changed without a new suite revision; update the revision and rerun"
        )
    metadata = [
        (
            "suite",
            None if previous is None or previous.suite is None else asdict(previous.suite),
            None if current.suite is None else asdict(current.suite),
        )
    ]
    if isinstance(candidate, RepeatedReport):
        for name in ("attempts", "execution_mode"):
            metadata.append((name, getattr(baseline, name, None), getattr(candidate, name)))
    for name, before, after in metadata:
        if before != after:
            changes.insert(0, ContractChange(name, None, None, before, after))
    runs = candidate.runs if isinstance(candidate, RepeatedReport) else (candidate,)
    if any(run.summary.errors for run in runs):
        blockers.append(
            "Candidate has execution/evaluation errors; generate error-free evidence before approval"
        )
    for case in current.cases:
        for check in case.check_definitions:
            if check.type == "verifier" and not check.parameters["revision"]:
                blockers.append(
                    f"Case {case.id!r}, verifier {check.id!r} needs an explicit revision"
                )
    return BaselineReview(baseline, candidate, tuple(changes), tuple(blockers))


def review_to_dict(review: BaselineReview) -> dict[str, JSONValue]:
    """Return review schema 1, embedding complete old and proposed evaluations."""
    return {
        "schema_version": 1,
        "kind": "baseline_review",
        "baseline": None if review.baseline is None else evaluation_to_dict(review.baseline),
        "candidate": evaluation_to_dict(review.candidate),
        "changes": [asdict(change) for change in review.changes],
        "blockers": list(review.blockers),
        "has_failures": review.has_failures,
        "exit_code": review.exit_code,
    }


def review_from_dict(data: object) -> BaselineReview:
    """Strictly reload and recompute a review; reject altered summaries and blockers."""
    try:
        validate_json(data, "baseline review", max_depth=125)
        _fields(
            data,
            {
                "schema_version",
                "kind",
                "baseline",
                "candidate",
                "changes",
                "blockers",
                "has_failures",
                "exit_code",
            },
        )
        if (
            type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["kind"] != "baseline_review"
        ):
            raise ValueError("Expected baseline_review schema 1")
        review = review_baseline(
            evaluation_from_dict(data["candidate"]),
            None if data["baseline"] is None else evaluation_from_dict(data["baseline"]),
        )
        require_consistent(data, review_to_dict(review))
        return review
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ReportValidationError(f"Invalid baseline review: {error}") from error


def load_baseline_review(path: str | Path) -> BaselineReview:
    """Read a strict saved review; raise ReportValidationError without executing code."""
    try:
        return review_from_dict(read_json(path, max_depth=125))
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReportValidationError(f"Cannot load baseline review {path}: {error}") from error


def _fields(data: object, fields: set[str]) -> None:
    if not isinstance(data, dict) or data.keys() != fields:
        raise ValueError("Missing or unknown review/approval fields")


@dataclass(frozen=True)
class ApprovedBaseline:
    """Review evidence plus explicit local acknowledgement; not an identity signature."""

    review: BaselineReview
    review_digest: str
    reviewer: str
    reason: str
    accepted_failures: bool


def approve_review(
    review: BaselineReview,
    *,
    review_digest: str,
    reviewer: str,
    reason: str,
    accept_failures: bool = False,
) -> ApprovedBaseline:
    """Validate exact reviewed content and acknowledgement, returning an approval snapshot.

    This pure operation writes nothing. Raises ReportValidationError for stale
    digests, invalid metadata, blockers, or unacknowledged failed expectations.
    A reviewer name is supplied metadata, not authentication or a CI permission.
    """
    review = review_from_dict(review_to_dict(review))
    if review_digest != review.digest:
        raise ReportValidationError(
            "Review digest does not match; inspect the current review before approving"
        )
    for name, value in (("reviewer", reviewer), ("reason", reason)):
        if not isinstance(value, str) or not value.strip():
            raise ReportValidationError(f"{name} must be a non-empty string")
        try:
            validate_json(value, name)
        except ValueError as error:
            raise ReportValidationError(str(error)) from error
    if type(accept_failures) is not bool:
        raise ReportValidationError("accept_failures must be a boolean")
    if review.blockers:
        raise ReportValidationError("Approval blocked: " + "; ".join(review.blockers))
    if review.has_failures and not accept_failures:
        raise ReportValidationError(
            "Candidate has failed expectations; inspect them and explicitly accept failures"
        )
    return ApprovedBaseline(review, review_digest, reviewer, reason, accept_failures)


def approved_to_dict(approval: ApprovedBaseline) -> dict[str, JSONValue]:
    """Return approved_baseline schema 1 with the full review and acknowledgement."""
    return {
        "schema_version": 1,
        "kind": "approved_baseline",
        "review": review_to_dict(approval.review),
        "review_digest": approval.review_digest,
        "reviewer": approval.reviewer,
        "reason": approval.reason,
        "accepted_failures": approval.accepted_failures,
    }


def approved_from_dict(data: object) -> ApprovedBaseline:
    """Validate an approval and its embedded review; never trust a stored decision alone."""
    try:
        validate_json(data, "approved baseline", max_depth=125)
        _fields(
            data,
            {
                "schema_version",
                "kind",
                "review",
                "review_digest",
                "reviewer",
                "reason",
                "accepted_failures",
            },
        )
        if (
            type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or data["kind"] != "approved_baseline"
        ):
            raise ValueError("Expected approved_baseline schema 1")
        return approve_review(
            review_from_dict(data["review"]),
            review_digest=data["review_digest"],
            reviewer=data["reviewer"],
            reason=data["reason"],
            accept_failures=data["accepted_failures"],
        )
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ReportValidationError(f"Invalid approved baseline: {error}") from error
