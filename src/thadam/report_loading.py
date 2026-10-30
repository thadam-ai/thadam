"""Strict parsing of run reports and consistency of their recorded evidence."""

from dataclasses import asdict
from pathlib import Path

from thadam._json import json_equal, read_json, validate_json
from thadam.assertions import evaluate_assertion
from thadam.contracts import definition_assertion
from thadam.errors import ReportValidationError, TraceUnavailableError
from thadam.events import snapshot_trace
from thadam.models import (
    AssertionResult,
    CaseError,
    CaseResult,
    CheckDefinition,
    EventError,
    ExecutionEvent,
    RunReport,
    TokenUsage,
)
from thadam.reporting import report_to_dict


def load_report(path: str | Path) -> RunReport:
    """Load a schema-3 run report; raise ReportValidationError for invalid evidence.

    Legacy reports need fresh runs because they lack declared check contracts.
    Agent modules and custom verifiers are never imported or executed.
    """
    try:
        # Leave room for report/check wrappers around separately bounded payloads.
        return report_from_dict(read_json(path, max_depth=110))
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReportValidationError(f"Cannot load report {path}: {error}") from error


def validate_report(report: RunReport) -> RunReport:
    """Return a validated independent SDK report snapshot or raise ReportValidationError."""
    try:
        if not isinstance(report, RunReport):
            raise ValueError("Expected a RunReport")
        return report_from_dict(report_to_dict(report))
    except (AttributeError, TypeError, ValueError, RecursionError) as error:
        raise ReportValidationError(f"Invalid SDK report: {error}") from error


def report_from_dict(data: object) -> RunReport:
    """Parse stored report fields and cross-check evidence; raise ReportValidationError."""
    try:
        validate_json(data, "report", max_depth=110)
        if isinstance(data, dict) and data.get("schema_version") in (1, 2):
            raise ValueError("Legacy reports cannot be compared; generate fresh schema-3 reports")
        _fields(data, set(RunReport.__dataclass_fields__) | {"summary"}, "report")
        if type(data["schema_version"]) is not int or data["schema_version"] != 3:
            raise ValueError("report.schema_version must be the integer 3")
        if type(data["evaluation_version"]) is not int or data["evaluation_version"] != 1:
            raise ValueError("Unsupported evaluation_version; this build requires integer 1")
        _text(data["run_id"], "report.run_id")
        if data["agent_revision"] is not None:
            _text(data["agent_revision"], "report.agent_revision")
        cases = tuple(_case(raw) for raw in _array(data["cases"], "report.cases"))
        if not cases:
            raise ValueError("A run report must contain at least one case")
        _unique([case.id for case in cases], "case IDs")
        report = RunReport(cases, data["run_id"], data["agent_revision"])
        expected = asdict(report.summary)
        _fields(data["summary"], set(expected), "report.summary")
        if any(type(value) is not int for value in data["summary"].values()):
            raise ValueError("Summary counts must be integers")
        if data["summary"] != expected:
            raise ValueError("Summary counts disagree with the case results")
        return report
    except (ValueError, TypeError, RecursionError) as error:
        raise ReportValidationError(str(error)) from error


def _case(raw: object) -> CaseResult:
    _fields(raw, set(CaseResult.__dataclass_fields__), "case")
    _text(raw["id"], "case.id")
    if raw["status"] not in ("passed", "failed", "error"):
        raise ValueError("Unknown case status")
    _duration(raw["duration_ms"])
    validate_json(raw["input"], "case input")
    validate_json(raw["output"], "case output")
    if type(raw["output_available"]) is not bool:
        raise ValueError("output_available must be a boolean")
    if not raw["output_available"] and raw["output"] is not None:
        raise ValueError("Unavailable output must be null")
    definitions = tuple(
        _definition(check) for check in _array(raw["check_definitions"], "check_definitions")
    )
    if not definitions:
        raise ValueError(f"Case {raw['id']!r} has no declared checks")
    _unique([check.id for check in definitions], "check definition IDs")
    assertions = tuple(_assertion(item) for item in _array(raw["assertions"], "assertions"))
    _unique([item.id for item in assertions], "assertion result IDs")
    errors = tuple(_error(item) for item in _array(raw["errors"], "errors"))
    warnings = _array(raw["trace_warnings"], "trace_warnings")
    if any(not isinstance(warning, str) for warning in warnings):
        raise ValueError("Trace warnings must be strings")
    events = None
    if raw["events"] is None:
        if raw["trace_complete"] is not None or warnings:
            raise ValueError("Unknown tracing must have null completeness and no warnings")
    else:
        events = snapshot_trace(
            tuple(_event(item) for item in _array(raw["events"], "events")),
            raw["trace_complete"],
            tuple(warnings),
        )
    case = CaseResult(
        **{
            **raw,
            "assertions": assertions,
            "errors": errors,
            "events": events,
            "trace_warnings": tuple(warnings),
            "check_definitions": definitions,
        }
    )
    _outcomes(case)
    return case


def _definition(raw: object) -> CheckDefinition:
    _fields(raw, {"id", "type", "parameters"}, "check definition")
    _text(raw["id"], "check.id")
    _text(raw["type"], "check.type")
    if not isinstance(raw["parameters"], dict):
        raise ValueError("Check parameters must be an object")
    definition = CheckDefinition(**raw)
    if definition.type == "verifier":
        _fields(definition.parameters, {"revision"}, "verifier parameters")
        revision = definition.parameters["revision"]
        if revision is not None:
            _text(revision, "verifier revision")
    else:
        definition_assertion(definition)
    return definition


def _assertion(raw: object) -> AssertionResult:
    _fields(raw, set(AssertionResult.__dataclass_fields__), "assertion result")
    _text(raw["id"], "assertion.id")
    _text(raw["message"], "assertion.message")
    if type(raw["passed"]) is not bool:
        raise ValueError("Assertion passed must be a boolean")
    links = _array(raw["event_ids"], "event_ids")
    for link in links:
        _text(link, "event ID")
    _unique(links, "assertion event IDs")
    return AssertionResult(**{**raw, "event_ids": tuple(links)})


def _error(raw: object) -> CaseError:
    _fields(raw, set(CaseError.__dataclass_fields__), "case error")
    if raw["source"] not in ("agent", "output", "trace", "assertion", "verifier"):
        raise ValueError("Unknown case error source")
    _text(raw["type"], "error.type")
    if not isinstance(raw["message"], str):
        raise ValueError("Error message must be a string")
    if raw["source"] in ("assertion", "verifier"):
        _text(raw["assertion_id"], "error.assertion_id")
    elif raw["assertion_id"] is not None:
        raise ValueError("Execution errors cannot identify a completed check")
    return CaseError(**raw)


def _event(raw: object) -> ExecutionEvent:
    _fields(raw, set(ExecutionEvent.__dataclass_fields__), "event")
    error = raw["error"]
    usage = raw["usage"]
    if error is not None:
        _fields(error, set(EventError.__dataclass_fields__), "event error")
        error = EventError(**error)
    if usage is not None:
        _fields(usage, set(TokenUsage.__dataclass_fields__), "token usage")
        usage = TokenUsage(**usage)
    return ExecutionEvent(**{**raw, "error": error, "usage": usage})


def _outcomes(case: CaseResult) -> None:
    definitions = {item.id: item for item in case.check_definitions}
    results = {item.id: item for item in case.assertions}
    check_errors = {item.assertion_id: item for item in case.errors if item.assertion_id}
    execution_errors = [item for item in case.errors if item.assertion_id is None]
    if len(check_errors) != sum(item.assertion_id is not None for item in case.errors):
        raise ValueError("Duplicate check errors")
    if execution_errors:
        if len(case.errors) != 1 or case.assertions or case.output_available:
            raise ValueError("Execution errors must omit output and check verdicts")
    else:
        if not case.output_available:
            raise ValueError("A completed evaluation requires available output")
        if results.keys() & check_errors.keys():
            raise ValueError("A check cannot have both a verdict and an error")
        if results.keys() | check_errors.keys() != definitions.keys():
            raise ValueError("Every declared check requires exactly one verdict or error")
        for check_id, error in check_errors.items():
            expected_source = (
                "verifier" if definitions[check_id].type == "verifier" else "assertion"
            )
            if error.source != expected_source:
                raise ValueError("Check error source disagrees with its definition")
        _builtin_outcomes(case, results, check_errors)
    event_ids = {event.id for event in case.events or ()}
    if any(set(item.event_ids) - event_ids for item in case.assertions):
        raise ValueError("Assertion references an unknown event ID")
    expected_status = (
        "error"
        if case.errors
        else ("failed" if any(not result.passed for result in case.assertions) else "passed")
    )
    if case.status != expected_status:
        raise ValueError("Case status disagrees with its recorded checks/errors")


def _builtin_outcomes(
    case: CaseResult, results: dict[str, AssertionResult], errors: dict[str, CaseError]
) -> None:
    for definition in case.check_definitions:
        if definition.type == "verifier":
            if definition.id in results:
                validate_json(results[definition.id].expected, "verifier.expected")
                validate_json(results[definition.id].actual, "verifier.actual")
            if definition.id in results and results[definition.id].event_ids:
                raise ValueError("Verifier results do not declare tool event links")
            continue
        try:
            expected = evaluate_assertion(
                definition_assertion(definition),
                case.output,
                events=case.events,
                trace_complete=case.trace_complete,
            )
        except TraceUnavailableError:
            if definition.id not in errors:
                raise ValueError("Unavailable tool evidence must produce a check error") from None
            continue
        actual = results.get(definition.id)
        if actual is None or (
            actual.passed != expected.passed
            or not json_equal(actual.expected, expected.expected)
            or not json_equal(actual.actual, expected.actual)
            or actual.event_ids != expected.event_ids
        ):
            raise ValueError(f"Check {definition.id!r} contradicts its recorded evidence")


def _fields(raw: object, expected: set[str], location: str) -> None:
    if not isinstance(raw, dict):
        raise ValueError(f"{location} must be an object")
    if raw.keys() != expected:
        raise ValueError(
            f"{location}: missing fields {sorted(expected - raw.keys())}, "
            f"unknown fields {sorted(raw.keys() - expected)}"
        )


def _array(raw: object, location: str) -> list:
    if not isinstance(raw, list):
        raise ValueError(f"{location} must be an array")
    return raw


def _text(raw: object, location: str) -> None:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{location} must be a non-empty string")


def _unique(values: list[str], location: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {location}")


def _duration(raw: object) -> None:
    if type(raw) not in (int, float) or raw < 0:
        raise ValueError("Case duration must be finite and non-negative")
