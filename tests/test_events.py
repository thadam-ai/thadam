"""Evidence must be present and trustworthy before tool checks can pass."""

import json
from dataclasses import replace

import pytest

from thadam import (
    AgentExecutionError,
    AgentResult,
    EventError,
    ExecutionEvent,
    OutputEquals,
    RunReport,
    SuiteValidationError,
    TokenUsage,
    ToolArgumentsMatch,
    ToolCalled,
    ToolNotCalled,
    load_suite,
    report_to_dict,
    run_suite,
)
from thadam import (
    TestCase as AgentTestCase,
)


def event(event_id="call", **changes):
    return replace(
        ExecutionEvent(
            id=event_id,
            kind="tool",
            name="get_order",
            status="completed",
            started_at_ms=0,
            duration_ms=1,
            input={"order_id": "one", "extra": 2},
            input_available=True,
        ),
        **changes,
    )


def result(assertion, events=None, *, complete=True):
    def agent(_value):
        return "ok" if events is None else AgentResult("ok", events, trace_complete=complete)

    return run_suite(agent, [AgentTestCase("test", None, (assertion,))]).cases[0]


@pytest.mark.parametrize(
    "assertion",
    [
        ToolCalled("check", "get_order"),
        ToolNotCalled("check", "get_order"),
        ToolArgumentsMatch("check", "get_order", {"order_id": "one"}),
    ],
)
def test_unknown_or_incomplete_traces_cannot_pass(assertion):
    for events, complete in [(None, True), ((event(),), False)]:
        case = result(assertion, events, complete=complete)
        assert case.status == "error"
        assert case.errors[0].source == "assertion"
        assert case.errors[0].assertion_id == "check"


def test_observed_empty_trace_is_different_from_unknown():
    assert result(ToolNotCalled("no-tool", "get_order"), ()).status == "passed"
    assert result(ToolCalled("required", "get_order"), ()).status == "failed"
    assert result(ToolNotCalled("unknown", "get_order")).events is None


def test_failed_tool_attempt_counts_as_called_and_forbidden_attempt_fails():
    call = event(status="error", error=EventError("TimeoutError", "service unavailable"))
    assert result(ToolCalled("required", "get_order"), (call,)).status == "passed"
    case = result(ToolNotCalled("forbidden", "get_order"), (call,))
    assert case.status == "failed"
    assert case.assertions[0].event_ids == ("call",)


def test_argument_subset_must_match_every_call_with_strict_json_types():
    assertion = ToolArgumentsMatch("correct-order", "get_order", {"order_id": "one"})
    assert result(assertion, (event(),)).status == "passed"
    calls = (event(), event("second", input={"order_id": "two"}))
    case = result(assertion, calls)
    assert case.status == "failed"
    assert case.assertions[0].event_ids == ("call", "second")
    assert case.assertions[0].actual[1]["arguments"] == {"order_id": "two"}
    assert (
        result(
            ToolArgumentsMatch("bool", "get_order", {"value": 1}), (event(input={"value": True}),)
        ).status
        == "failed"
    )
    assert result(assertion, ()).status == "failed"


def test_missing_argument_evidence_is_error_not_a_verdict():
    for call in [event(input=None, input_available=False), event(input="raw input")]:
        case = result(ToolArgumentsMatch("args", "get_order", {"order_id": "one"}), (call,))
        assert case.status == "error"
        assert "unavailable" in case.errors[0].message


@pytest.mark.parametrize(
    "bad",
    [
        event(duration_ms=-1),
        event(started_at_ms=float("nan")),
        event(input={"bad": {1, 2}}),
        event(status="incomplete"),
        event(status="error"),
        event(kind="wrong"),
        event(usage=TokenUsage(1, 2, 3)),
        event(kind="model", usage=TokenUsage(input_tokens=-1)),
    ],
)
def test_invalid_evidence_is_a_trace_error_and_remains_serializable(bad):
    case = result(ToolNotCalled("test", "other_tool"), (bad,))
    assert case.status == "error"
    assert case.errors[0].source == "trace"
    assert case.events is None
    json.dumps(report_to_dict(RunReport(cases=(case,))), allow_nan=False)


def test_duplicate_event_ids_are_rejected():
    assert result(ToolCalled("check", "get_order"), (event(), event())).errors[0].source == "trace"


def test_agent_failure_preserves_events_and_later_cases_run():
    def agent(value):
        if value == "break":
            raise AgentExecutionError(
                ValueError("agent broke"), events=(event(),), trace_complete=True
            )
        return "ok"

    cases = [
        AgentTestCase("broken", "break", (OutputEquals("out", "ok"),)),
        AgentTestCase("next", "next", (OutputEquals("out", "ok"),)),
    ]
    report = run_suite(agent, cases)
    assert [case.status for case in report.cases] == ["error", "passed"]
    assert report.cases[0].events[0].id == "call"
    assert report.cases[0].errors[0].type == "ValueError"
    assert report.cases[1].events is None


@pytest.mark.parametrize(
    "assertion",
    [
        ToolCalled("empty", ""),
        ToolNotCalled("wrong", None),
        ToolArgumentsMatch("args", "tool", {}),
        ToolArgumentsMatch("args", "tool", {"bad": {1}}),
    ],
)
def test_invalid_tool_checks_rejected_before_agent_execution(assertion):
    calls = []
    with pytest.raises(SuiteValidationError):
        run_suite(calls.append, [AgentTestCase("invalid", None, (assertion,))])
    assert calls == []


@pytest.mark.parametrize(
    "assertion",
    [
        {"id": "check", "type": ["tool_called"], "tool": "tool"},
        {"id": "check", "type": "tool_called", "tool": ""},
        {"id": "check", "type": "tool_not_called", "tool": 3},
        {"id": "check", "type": "tool_arguments_match", "tool": "tool", "expected": None},
        {"id": "check", "type": "tool_arguments_match", "tool": "tool", "expected": {}},
        {"id": "check", "type": "tool_called", "tool": "tool", "typo": True},
    ],
)
def test_invalid_json_tool_assertions_are_configuration_errors(tmp_path, assertion):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {"id": "invalid", "input": None, "assertions": [assertion]},
                ],
            }
        )
    )
    with pytest.raises(SuiteValidationError):
        load_suite(path)
