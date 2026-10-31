"""Compare validated, equivalent evaluation contracts without executing agents."""

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from thadam.contracts import case_contract_issues
from thadam.models import AssertionResult, CaseError, CaseResult, CaseStatus, RunReport
from thadam.report_loading import validate_report

Change: TypeAlias = Literal[
    "regression", "fixed", "existing_failure", "unchanged_pass", "error", "incompatible"
]


@dataclass(frozen=True)
class CheckComparison:
    """Both recorded verdicts for a stable check ID, including their evidence links."""

    id: str
    change: Change
    baseline: AssertionResult | None
    candidate: AssertionResult | None


@dataclass(frozen=True)
class CaseComparison:
    """A case's compatibility issues, check changes, and original run errors."""

    id: str
    change: Change
    baseline_status: CaseStatus | None
    candidate_status: CaseStatus | None
    checks: tuple[CheckComparison, ...] = ()
    issues: tuple[str, ...] = ()
    baseline_errors: tuple[CaseError, ...] = ()
    candidate_errors: tuple[CaseError, ...] = ()


@dataclass(frozen=True)
class ComparisonSummary:
    """Mutually exclusive case counts; individual assertion changes remain available."""

    total: int
    regressions: int
    fixed: int
    existing_failures: int
    unchanged_passes: int
    errors: int
    incompatible: int


@dataclass(frozen=True)
class ComparisonReport:
    """A comparison artifact; exit_code is the SDK and CLI gate decision."""

    baseline_run_id: str
    candidate_run_id: str
    baseline_agent_revision: str | None
    candidate_agent_revision: str | None
    cases: tuple[CaseComparison, ...]
    schema_version: int = field(default=1, init=False)
    kind: str = field(default="comparison", init=False)

    @property
    def summary(self) -> ComparisonSummary:
        counts = {
            change: sum(case.change == change for case in self.cases)
            for change in (
                "regression",
                "fixed",
                "existing_failure",
                "unchanged_pass",
                "error",
                "incompatible",
            )
        }
        return ComparisonSummary(
            len(self.cases),
            counts["regression"],
            counts["fixed"],
            counts["existing_failure"],
            counts["unchanged_pass"],
            counts["error"],
            counts["incompatible"],
        )

    @property
    def compatible(self) -> bool:
        return not any(case.change == "incompatible" for case in self.cases)

    @property
    def exit_code(self) -> int:
        if not self.compatible:
            return 2
        return int(any(case.change in ("regression", "error") for case in self.cases))


def compare_reports(baseline: RunReport, candidate: RunReport) -> ComparisonReport:
    """Compare selected reports, raising ReportValidationError for invalid run data.

    Both reports are validated and snapshotted. Case/input/check contract changes
    produce explicit incompatibilities. Errors on either side block a clean gate.
    Selecting a baseline acknowledges its existing assertion failures; no baseline
    is chosen or updated automatically. Agents and verifiers are never invoked.
    """
    baseline = validate_report(baseline)
    candidate = validate_report(candidate)
    old = {case.id: case for case in baseline.cases}
    new = {case.id: case for case in candidate.cases}
    case_ids = [*old, *(case_id for case_id in new if case_id not in old)]
    return ComparisonReport(
        baseline.run_id,
        candidate.run_id,
        baseline.agent_revision,
        candidate.agent_revision,
        tuple(_compare_case(case_id, old.get(case_id), new.get(case_id)) for case_id in case_ids),
    )


def _compare_case(
    case_id: str, baseline: CaseResult | None, candidate: CaseResult | None
) -> CaseComparison:
    issues = case_contract_issues(baseline, candidate)
    if issues:
        return CaseComparison(
            id=case_id,
            change="incompatible",
            baseline_status=None if baseline is None else baseline.status,
            candidate_status=None if candidate is None else candidate.status,
            issues=tuple(issues),
            baseline_errors=() if baseline is None else baseline.errors,
            candidate_errors=() if candidate is None else candidate.errors,
        )
    old = {check.id: check for check in baseline.assertions}
    new = {check.id: check for check in candidate.assertions}
    checks = tuple(
        CheckComparison(
            definition.id,
            _check_change(old.get(definition.id), new.get(definition.id)),
            old.get(definition.id),
            new.get(definition.id),
        )
        for definition in baseline.check_definitions
    )
    change: Change = "unchanged_pass"
    if baseline.errors or candidate.errors:
        change = "error"
    elif any(check.change == "regression" for check in checks):
        change = "regression"
    elif any(check.change == "existing_failure" for check in checks):
        change = "existing_failure"
    elif any(check.change == "fixed" for check in checks):
        change = "fixed"
    return CaseComparison(
        case_id,
        change,
        baseline.status,
        candidate.status,
        checks,
        baseline_errors=baseline.errors,
        candidate_errors=candidate.errors,
    )


def _check_change(left: AssertionResult | None, right: AssertionResult | None) -> Change:
    if left is None or right is None:
        return "error"
    if left.passed:
        return "unchanged_pass" if right.passed else "regression"
    return "fixed" if right.passed else "existing_failure"
