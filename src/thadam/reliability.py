"""Pure comparison of observed case/check reliability under an explicit CI policy."""

from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from typing import Literal

from thadam.contracts import case_contract_issues
from thadam.errors import ReportValidationError
from thadam.repetition import CaseReliability, OutcomeCounts, RepeatedReport
from thadam.repetition_loading import validate_repeated

RateChange = Literal["regression", "tolerated_drop", "improved", "unchanged", "error"]
ReliabilityChange = Literal[
    "regression", "tolerated_drop", "improved", "unchanged", "error", "incompatible"
]


@dataclass(frozen=True)
class RateComparison:
    """Observed counts and signed candidate-minus-baseline pass-rate difference."""

    id: str
    baseline: OutcomeCounts
    candidate: OutcomeCounts
    change: RateChange

    @property
    def pass_rate_delta(self) -> float:
        return (self.candidate.passed - self.baseline.passed) / self.baseline.total


@dataclass(frozen=True)
class CaseReliabilityComparison:
    """Case and individual-check changes, with explicit compatibility issues."""

    id: str
    change: ReliabilityChange
    baseline: CaseReliability | None
    candidate: CaseReliability | None
    case_rate: RateComparison | None = None
    checks: tuple[RateComparison, ...] = ()
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReliabilityComparison:
    """Standalone evidence and gate decision; comparison executes no application code."""

    baseline: RepeatedReport
    candidate: RepeatedReport
    max_pass_rate_drop: float
    cases: tuple[CaseReliabilityComparison, ...]
    issues: tuple[str, ...] = ()
    schema_version: int = field(default=1, init=False)
    kind: str = field(default="reliability_comparison", init=False)

    @property
    def compatible(self) -> bool:
        return not self.issues and not any(case.issues for case in self.cases)

    @property
    def exit_code(self) -> int:
        if not self.compatible:
            return 2
        return int(any(case.change in ("regression", "error") for case in self.cases))

    @property
    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.cases),
            **{
                change: sum(case.change == change for case in self.cases)
                for change in (
                    "regression",
                    "tolerated_drop",
                    "improved",
                    "unchanged",
                    "error",
                    "incompatible",
                )
            },
        }


def validate_tolerance(value: float) -> float:
    """Validate a finite fractional pass-rate drop, raising ReportValidationError."""
    if type(value) not in (int, float) or not 0 <= value <= 1 or not isfinite(value):
        raise ReportValidationError("max_pass_rate_drop must be a finite number from 0 to 1")
    return float(value)


def compare_repeated(
    baseline: RepeatedReport,
    candidate: RepeatedReport,
    *,
    max_pass_rate_drop: float = 0.0,
) -> ReliabilityComparison:
    """Compare every case/check pass rate, retaining both validated evidence snapshots.

    A drop strictly greater than max_pass_rate_drop (0..1) blocks the gate. Errors
    on either side always block. Unequal attempt counts/modes or changed contracts
    are incompatible. Custom verifiers require matching explicit revisions.
    Invalid reports/policy raise ReportValidationError. No agents, factories, or
    verifiers are executed; this is an observed-rate policy, not a significance test.
    """
    tolerance = validate_tolerance(max_pass_rate_drop)
    baseline = validate_repeated(baseline)
    candidate = validate_repeated(candidate)
    issues = []
    if baseline.attempts != candidate.attempts:
        issues.append("Attempt counts differ; generate reports with equal attempts")
    if baseline.execution_mode != candidate.execution_mode:
        issues.append("Execution modes differ; use matching shared/factory lifecycle contracts")
    old_contracts = {case.id: case for case in baseline.runs[0].cases}
    new_contracts = {case.id: case for case in candidate.runs[0].cases}
    old = {case.id: case for case in baseline.cases}
    new = {case.id: case for case in candidate.cases}
    case_ids = [*old, *(case_id for case_id in new if case_id not in old)]
    cases = []
    for case_id in case_ids:
        problems = case_contract_issues(old_contracts.get(case_id), new_contracts.get(case_id))
        left, right = old.get(case_id), new.get(case_id)
        if problems or issues:
            cases.append(
                CaseReliabilityComparison(
                    case_id, "incompatible", left, right, issues=tuple(problems or issues)
                )
            )
            continue
        rate = _rate(case_id, left.counts, right.counts, tolerance)
        right_checks = {check.id: check for check in right.checks}
        checks = tuple(
            _rate(check.id, check.counts, right_checks[check.id].counts, tolerance)
            for check in left.checks
        )
        changes = {rate.change, *(check.change for check in checks)}
        change = next(
            value
            for value in ("error", "regression", "tolerated_drop", "improved", "unchanged")
            if value in changes
        )
        cases.append(CaseReliabilityComparison(case_id, change, left, right, rate, checks))
    return ReliabilityComparison(baseline, candidate, tolerance, tuple(cases), tuple(issues))


def _rate(
    check_id: str, baseline: OutcomeCounts, candidate: OutcomeCounts, tolerance: float
) -> RateComparison:
    change: RateChange
    if baseline.errors or candidate.errors:
        change = "error"
    elif baseline.passed > candidate.passed:
        # Compare integer counts against a decimal policy boundary. Subtracting
        # two floating-point rates can incorrectly reject a drop equal to tolerance.
        allowed = Fraction(str(tolerance)) * baseline.total
        change = "regression" if baseline.passed - candidate.passed > allowed else "tolerated_drop"
    elif candidate.passed > baseline.passed:
        change = "improved"
    else:
        change = "unchanged"
    return RateComparison(check_id, baseline, candidate, change)
