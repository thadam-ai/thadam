"""Strict loading of saved single comparisons without executing application code."""

from thadam._json import validate_json
from thadam.comparison import CaseComparison, CheckComparison, ComparisonReport, _check_change
from thadam.comparison_reporting import comparison_to_dict
from thadam.contracts import suite_contract_issues
from thadam.errors import ReportValidationError
from thadam.models import SuiteIdentity
from thadam.repetition_loading import require_consistent
from thadam.report_loading import _array, _assertion, _error, _fields, _text, _unique
from thadam.suites import suite_identity


def comparison_from_dict(data: object) -> ComparisonReport:
    """Validate recorded verdicts, classifications and counts, not source-run authenticity.

    Single-comparison artifacts retain assertion event links, not full run traces
    or contracts. Source reports are still required to re-evaluate compatibility.
    """
    try:
        validate_json(data, "comparison", max_depth=115)
        if not isinstance(data, dict):
            raise ValueError("Expected a comparison object")
        version = data.get("schema_version")
        if type(version) is not int or version not in (1, 2) or data.get("kind") != "comparison":
            raise ValueError("Expected comparison schema 1 or 2")
        fields = {
            "schema_version",
            "kind",
            "baseline_run_id",
            "candidate_run_id",
            "baseline_agent_revision",
            "candidate_agent_revision",
            "cases",
            "compatible",
            "summary",
            "exit_code",
        }
        _fields(
            data,
            fields | ({"baseline_suite", "candidate_suite"} if version == 2 else set()),
            "comparison",
        )
        for key in ("baseline_run_id", "candidate_run_id"):
            _text(data[key], key)
        for key in ("baseline_agent_revision", "candidate_agent_revision"):
            if data[key] is not None:
                _text(data[key], key)
        identities = []
        for key in ("baseline_suite", "candidate_suite"):
            raw = data.get(key)
            if raw is not None:
                _fields(raw, {"id", "revision"}, key)
                identities.append(suite_identity((), SuiteIdentity(**raw)))
            else:
                identities.append(None)
        cases = []
        for raw in _array(data["cases"], "cases"):
            _fields(raw, set(CaseComparison.__dataclass_fields__), "case comparison")
            _text(raw["id"], "case id")
            issues = tuple(_array(raw["issues"], "issues"))
            for issue in issues:
                _text(issue, "issue")
            checks = []
            for check in _array(raw["checks"], "checks"):
                _fields(check, set(CheckComparison.__dataclass_fields__), "check comparison")
                _text(check["id"], "check id")
                before = None if check["baseline"] is None else _assertion(check["baseline"])
                after = None if check["candidate"] is None else _assertion(check["candidate"])
                if any(
                    result.id != check["id"] for result in (before, after) if result is not None
                ):
                    raise ValueError("Check evidence IDs disagree")
                if check["change"] != _check_change(before, after):
                    raise ValueError("Check classification contradicts verdicts")
                checks.append(CheckComparison(check["id"], check["change"], before, after))
            _unique([check.id for check in checks], "check IDs")
            errors = []
            for side in ("baseline", "candidate"):
                found = tuple(_error(item) for item in _array(raw[side + "_errors"], "errors"))
                status = raw[side + "_status"]
                if status not in (None, "passed", "failed", "error"):
                    raise ValueError("Unknown case status")
                if bool(found) != (status == "error"):
                    raise ValueError("Case error status contradicts evidence")
                if status is None and not issues:
                    raise ValueError("Missing cases require compatibility issues")
                if not issues:
                    verdicts = [getattr(check, side) for check in checks]
                    if status != "error" and any(item is None for item in verdicts):
                        raise ValueError("Missing verdict without a recorded error")
                    if status in ("passed", "failed") and (status == "failed") != any(
                        not item.passed for item in verdicts if item
                    ):
                        raise ValueError("Case status contradicts check evidence")
                errors.append(found)
            if issues:
                expected = "incompatible"
                if checks:
                    raise ValueError("Incompatible cases cannot contain comparable checks")
            else:
                if not checks:
                    raise ValueError("Comparable cases need checks")
                changes = {check.change for check in checks}
                expected = (
                    "error"
                    if any(errors)
                    else next(
                        (
                            name
                            for name in ("regression", "existing_failure", "fixed")
                            if name in changes
                        ),
                        "unchanged_pass",
                    )
                )
            if raw["change"] != expected:
                raise ValueError("Case classification contradicts evidence")
            cases.append(
                CaseComparison(
                    raw["id"],
                    raw["change"],
                    raw["baseline_status"],
                    raw["candidate_status"],
                    tuple(checks),
                    issues,
                    errors[0],
                    errors[1],
                )
            )
        if not cases:
            raise ValueError("A comparison needs cases")
        _unique([case.id for case in cases], "case IDs")
        if suite_contract_issues(*identities) and any(
            case.change != "incompatible" for case in cases
        ):
            raise ValueError("Suite identities disagree with comparison compatibility")
        result = ComparisonReport(
            data["baseline_run_id"],
            data["candidate_run_id"],
            data["baseline_agent_revision"],
            data["candidate_agent_revision"],
            tuple(cases),
            *identities,
        )
        require_consistent(data, comparison_to_dict(result))
        return result
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ReportValidationError(f"Invalid comparison: {error}") from error
