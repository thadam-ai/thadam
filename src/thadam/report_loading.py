"""Strict parsing of run reports and consistency of their recorded evidence."""

from dataclasses import asdict
from pathlib import Path

from thadam._json import json_equal, read_json, validate_json
from thadam.assertions import evaluate_assertion
from thadam.contracts import definition_assertion
from thadam.errors import ReportValidationError, TraceUnavailableError
from thadam.events import snapshot_trace
from thadam.fixtures import parse_fixtures, validate_fixture_evidence
from thadam.models import (
    AssertionResult,
    CaseError,
    CaseResult,
    CheckDefinition,
    ConversationTurn,
    ConversationTurnResult,
    EventError,
    ExecutionEvent,
    JSONValue,
    RunReport,
    StateFixture,
    SuiteIdentity,
    TokenUsage,
)
from thadam.reporting import report_to_dict
from thadam.suites import suite_identity


def load_report(path: str | Path) -> RunReport:
    """Load schema-3/4/5 evidence or an approved baseline; raise ReportValidationError.

    Legacy reports need fresh runs because they lack declared check contracts.
    Agent modules and custom verifiers are never imported or executed.
    """
    try:
        # Leave room for report/check wrappers around separately bounded payloads.
        data = read_json(path, max_depth=125)
        if isinstance(data, dict) and data.get("kind") == "approved_baseline":
            from thadam.baseline_review import approved_from_dict

            report = approved_from_dict(data).review.candidate
            if not isinstance(report, RunReport):
                raise ReportValidationError("Expected a single-run approved baseline")
            return report
        return report_from_dict(data)
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
        version = data.get("schema_version") if isinstance(data, dict) else None
        fields = (set(RunReport.__dataclass_fields__) - {"suite"}) | {"summary"}
        _fields(data, fields | ({"suite"} if version in (4, 5, 6) else set()), "report")
        if type(version) is not int or version not in (3, 4, 5, 6):
            raise ValueError("report.schema_version must be the integer 3, 4, 5, or 6")
        identity = None
        if version == 4 or version in (5, 6) and data["suite"] is not None:
            _fields(data["suite"], {"id", "revision"}, "report.suite")
            identity = suite_identity((), SuiteIdentity(**data["suite"]))
        if type(data["evaluation_version"]) is not int or data["evaluation_version"] != 1:
            raise ValueError("Unsupported evaluation_version; this build requires integer 1")
        _text(data["run_id"], "report.run_id")
        if data["agent_revision"] is not None:
            _text(data["agent_revision"], "report.agent_revision")
        cases = tuple(
            _case(raw, fixture_run=version in (5, 6), simulation_run=version == 6)
            for raw in _array(data["cases"], "report.cases")
        )
        if not cases:
            raise ValueError("A run report must contain at least one case")
        _unique([case.id for case in cases], "case IDs")
        report = RunReport(cases, data["run_id"], data["agent_revision"], suite=identity)
        expected = asdict(report.summary)
        _fields(data["summary"], set(expected), "report.summary")
        if any(type(value) is not int for value in data["summary"].values()):
            raise ValueError("Summary counts must be integers")
        if data["summary"] != expected:
            raise ValueError("Summary counts disagree with the case results")
        return report
    except (ValueError, TypeError, RecursionError) as error:
        raise ReportValidationError(str(error)) from error


def _case(raw: object, *, fixture_run: bool = False, simulation_run: bool = False) -> CaseResult:
    expected_fields = set(CaseResult.__dataclass_fields__) - {
        "tool_fixtures",
        "conversation",
        "conversation_results",
        "state_fixture",
        "state_initial",
        "state_final",
    }
    if fixture_run:
        expected_fields.add("tool_fixtures")
    if simulation_run:
        expected_fields.update(
            {
                "conversation",
                "conversation_results",
                "state_fixture",
                "state_initial",
                "state_final",
            }
        )
    _fields(raw, expected_fields, "case")
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
    if any(error.source == "fixture" for error in errors) and not fixture_run:
        raise ValueError("Fixture errors require schema-5 fixture evidence")
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
    conversation = ()
    conversation_results = ()
    state_fixture = None
    state_initial = state_final = None
    if simulation_run:
        if not isinstance(raw["conversation"], list) or not isinstance(
            raw["conversation_results"], list
        ):
            raise ValueError("Conversation and conversation_results must be arrays")
        conversation = tuple(
            ConversationTurn(**_checked_object(turn, {"id", "message"}, "conversation turn"))
            for turn in raw["conversation"]
        )
        conversation_results = tuple(
            ConversationTurnResult(
                **_checked_object(
                    turn,
                    {"id", "message", "output", "output_available"},
                    "conversation result",
                )
            )
            for turn in raw["conversation_results"]
        )
        if raw["state_fixture"] is not None:
            state_data = _checked_object(raw["state_fixture"], {"initial"}, "state fixture")
            state_fixture = StateFixture(state_data["initial"])
        state_initial, state_final = raw["state_initial"], raw["state_final"]
        validate_json(state_initial, "state_initial")
        validate_json(state_final, "state_final")
        _validate_conversation_evidence(
            conversation, conversation_results, state_fixture, state_initial, state_final
        )
    case = CaseResult(
        **{
            **raw,
            "assertions": assertions,
            "errors": errors,
            "events": events,
            "trace_warnings": tuple(warnings),
            "check_definitions": definitions,
            "tool_fixtures": parse_fixtures(raw["tool_fixtures"]) if fixture_run else None,
            "conversation": conversation,
            "conversation_results": conversation_results,
            "state_fixture": state_fixture,
            "state_initial": state_initial,
            "state_final": state_final,
        }
    )
    _outcomes(case)
    if fixture_run:
        validate_fixture_evidence(
            case.tool_fixtures, case.events, any(error.source == "fixture" for error in errors)
        )
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
    if raw["source"] not in ("agent", "output", "trace", "assertion", "verifier", "fixture"):
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
    if case.output_available and len(case.conversation_results) != len(case.conversation):
        raise ValueError("A completed conversation must retain every turn response")
    if case.output_available and case.conversation:
        final_turn = case.conversation_results[-1]
        if not final_turn.output_available or not json_equal(case.output, final_turn.output):
            raise ValueError("Case output disagrees with the final conversation response")
    if not case.conversation and case.conversation_results:
        raise ValueError("Conversation results require a declared conversation")
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
                conversation_results=case.conversation_results,
                state_initial=case.state_initial,
                state_final=case.state_final,
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


def _checked_object(raw: object, fields: set[str], location: str) -> dict:
    if not isinstance(raw, dict) or raw.keys() != fields:
        raise ValueError(f"{location} has missing or unknown fields")
    return raw


def _validate_conversation_evidence(
    turns: tuple[ConversationTurn, ...],
    results: tuple[ConversationTurnResult, ...],
    state_fixture: StateFixture | None,
    state_initial: JSONValue,
    state_final: JSONValue,
) -> None:
    if len(results) > len(turns):
        raise ValueError("Conversation results exceed the scripted turn count")
    for turn in turns:
        _text(turn.id, "conversation turn ID")
        validate_json(turn.message, "conversation message")
    _unique([turn.id for turn in turns], "conversation turn IDs")
    for turn, result in zip(turns, results):
        _text(result.id, "conversation result ID")
        if result.id != turn.id or not json_equal(result.message, turn.message):
            raise ValueError("Conversation result does not match its scripted turn")
        if type(result.output_available) is not bool:
            raise ValueError("Conversation output availability must be a boolean")
        validate_json(result.output, "conversation response")
        if not result.output_available and result.output is not None:
            raise ValueError("Unavailable conversation output must be null")
    if state_fixture is None:
        if state_initial is not None or state_final is not None:
            raise ValueError("State evidence requires a declared state fixture")
    elif not json_equal(state_fixture.initial, state_initial):
        raise ValueError("Recorded initial state differs from the fixture declaration")
