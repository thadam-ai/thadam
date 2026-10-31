"""Strict repeated-run parsing without importing or executing application code."""

from dataclasses import asdict
from pathlib import Path

from thadam._json import json_equal, read_json, validate_json
from thadam.contracts import equivalent_definitions
from thadam.errors import ReportValidationError
from thadam.models import RunReport
from thadam.repetition import RepeatedReport
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict


def load_repeated(path: str | Path) -> RepeatedReport:
    """Load repeated-run schema 1, validating every attempt and derived summary.

    Raise ReportValidationError for malformed, inconsistent, or unsupported data.
    No agents, factories, or custom verifiers are executed.
    """
    try:
        return repeated_from_dict(read_json(path, max_depth=115))
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReportValidationError(f"Cannot load repeated report {path}: {error}") from error


def validate_repeated(report: RepeatedReport) -> RepeatedReport:
    """Validate and independently snapshot an SDK repeated report, or raise ReportValidationError."""
    try:
        if not isinstance(report, RepeatedReport):
            raise ValueError("Expected a RepeatedReport")
        return repeated_from_dict(repeated_to_dict(report))
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
    ) as error:
        raise ReportValidationError(f"Invalid SDK repeated report: {error}") from error


def repeated_from_dict(data: object) -> RepeatedReport:
    """Parse full repeated-run evidence and reject fabricated or inconsistent summaries."""
    try:
        validate_json(data, "repeated report", max_depth=115)
        fields = {
            "schema_version",
            "kind",
            "report_id",
            "execution_mode",
            "agent_revision",
            "attempts",
            "summary",
            "cases",
            "runs",
        }
        if not isinstance(data, dict) or data.keys() != fields:
            raise ValueError("Repeated report has missing or unknown fields; expected repeated_run")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported repeated-run schema_version; expected integer 1")
        if data["kind"] != "repeated_run":
            raise ValueError("Expected kind repeated_run")
        if not isinstance(data["report_id"], str) or not data["report_id"].strip():
            raise ValueError("report_id must be a non-empty string")
        if data["execution_mode"] not in ("shared", "factory"):
            raise ValueError("execution_mode must be shared or factory")
        if type(data["attempts"]) is not int or data["attempts"] < 2:
            raise ValueError("attempts must be an integer of at least 2")
        if not isinstance(data["runs"], list) or len(data["runs"]) != data["attempts"]:
            raise ValueError("runs must contain exactly the declared number of attempts")
        runs = tuple(report_from_dict(run) for run in data["runs"])
        if len({run.run_id for run in runs}) != len(runs):
            raise ValueError("Attempt run IDs must be unique")
        for run in runs[1:]:
            _same_contract(runs[0], run)
        report = RepeatedReport(runs, data["execution_mode"], data["report_id"])
        require_consistent(data, repeated_to_dict(report))
        return report
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ReportValidationError(str(error)) from error


def _same_contract(first: RunReport, other: RunReport) -> None:
    if first.agent_revision != other.agent_revision:
        raise ValueError("Agent revisions differ between attempts")
    old = {case.id: case for case in first.cases}
    new = {case.id: case for case in other.cases}
    if old.keys() != new.keys():
        raise ValueError("Case IDs differ between attempts")
    for case_id, left in old.items():
        right = new[case_id]
        a = {check.id: check for check in left.check_definitions}
        b = {check.id: check for check in right.check_definitions}
        if not json_equal(left.input, right.input) or a.keys() != b.keys():
            raise ValueError(f"Case {case_id!r} contracts differ between attempts")
        for check_id, definition in a.items():
            # Unversioned verifiers may run repeatedly, but cannot establish
            # comparison compatibility across separately selected reports.
            if not equivalent_definitions(definition, b[check_id]) and not json_equal(
                asdict(definition), asdict(b[check_id])
            ):
                raise ValueError(f"Check {check_id!r} contracts differ between attempts")


def require_consistent(actual: object, expected: object) -> None:
    """Require exact fields, counts, and JSON types with numeric runtime flexibility."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError("Report contains missing or unknown summary/evidence fields")
        for key in expected:
            require_consistent(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("Report array disagrees with recorded evidence")
        for left, right in zip(actual, expected):
            require_consistent(left, right)
    elif type(expected) is float:
        if type(actual) not in (int, float) or actual != expected:
            raise ValueError("Report rate/runtime disagrees with recorded evidence")
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("Report metadata/counts disagree with recorded evidence")
