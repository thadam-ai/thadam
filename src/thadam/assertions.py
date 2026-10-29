"""Deterministic checks and validation of custom verifier results."""

import inspect
from copy import deepcopy

from thadam._json import validate_json
from thadam.errors import TraceUnavailableError
from thadam.models import (
    Assertion,
    AssertionResult,
    CheckResult,
    ExecutionEvent,
    JSONValue,
    OutputEquals,
    ToolArgumentsMatch,
    ToolCalled,
    ToolNotCalled,
    Verifier,
)


def evaluate_assertion(
    assertion: Assertion,
    output: JSONValue,
    *,
    events: tuple[ExecutionEvent, ...] | None = None,
    trace_complete: bool | None = None,
) -> AssertionResult:
    """Evaluate a validated built-in assertion without executing an agent."""
    if isinstance(assertion, (ToolCalled, ToolNotCalled, ToolArgumentsMatch)):
        return _evaluate_tool(assertion, events, trace_complete)
    if isinstance(assertion, OutputEquals):
        passed = _json_equal(assertion.expected, output)
        return AssertionResult(
            id=assertion.id,
            passed=passed,
            expected=deepcopy(assertion.expected),
            actual=deepcopy(output),
            message="Output matches expected JSON"
            if passed
            else "Output differs from expected JSON",
        )
    missing = [key for key in assertion.keys if not isinstance(output, dict) or key not in output]
    message = "Output contains all required keys"
    if not isinstance(output, dict):
        message = "Expected an object output containing the required keys"
    elif missing:
        message = f"Output is missing keys: {', '.join(missing)}"
    return AssertionResult(
        id=assertion.id,
        passed=not missing,
        expected=list(assertion.keys),
        actual=deepcopy(output),
        message=message,
    )


def _evaluate_tool(
    assertion: ToolCalled | ToolNotCalled | ToolArgumentsMatch,
    events: tuple[ExecutionEvent, ...] | None,
    trace_complete: bool | None,
) -> AssertionResult:
    if events is None or trace_complete is not True:
        raise TraceUnavailableError(
            "Tool assertions require a complete, explicitly instrumented trace"
        )
    calls = [event for event in events if event.kind == "tool" and event.name == assertion.tool]
    if isinstance(assertion, ToolArgumentsMatch):
        if any(not call.input_available or not isinstance(call.input, dict) for call in calls):
            raise TraceUnavailableError(
                f"Structured arguments for {assertion.tool!r} are unavailable"
            )
        passed = bool(calls) and all(
            all(
                key in call.input and _json_equal(value, call.input[key])
                for key, value in assertion.expected.items()
            )
            for call in calls
        )
        expected = {"tool": assertion.tool, "arguments_subset": deepcopy(assertion.expected)}
        actual = [{"event_id": call.id, "arguments": deepcopy(call.input)} for call in calls]
        message = f"Every call to {assertion.tool!r} must match the selected arguments"
    else:
        passed = bool(calls) if isinstance(assertion, ToolCalled) else not calls
        expected = {"tool": assertion.tool, "called": isinstance(assertion, ToolCalled)}
        actual = {"calls": len(calls)}
        message = f"Tool {assertion.tool!r} was called {len(calls)} time(s)"
    return AssertionResult(
        id=assertion.id,
        passed=passed,
        message=message,
        expected=expected,
        actual=actual,
        event_ids=tuple(call.id for call in calls),
    )


def evaluate_verifier(
    verifier: Verifier, case_input: JSONValue, output: JSONValue
) -> AssertionResult:
    """Invoke a verifier on private snapshots; propagate errors for the runner to record."""
    result = verifier.check(deepcopy(case_input), deepcopy(output))
    if inspect.iscoroutine(result):
        result.close()
    if not isinstance(result, CheckResult):
        raise TypeError("A verifier must return a CheckResult")
    if type(result.passed) is not bool:
        raise TypeError("CheckResult.passed must be a bool")
    if not isinstance(result.message, str) or not result.message.strip():
        raise ValueError("CheckResult.message must be a non-empty string")
    validate_json(result.expected, "verifier.expected")
    validate_json(result.actual, "verifier.actual")
    return AssertionResult(
        id=verifier.id,
        passed=result.passed,
        message=result.message,
        expected=deepcopy(result.expected),
        actual=deepcopy(result.actual),
    )


def _json_equal(expected: JSONValue, actual: JSONValue) -> bool:
    # JSON has one number category; Python bool is deliberately excluded from it.
    if type(expected) in (int, float) and type(actual) in (int, float):
        return expected == actual
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(
            _json_equal(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _json_equal(left, right) for left, right in zip(expected, actual)
        )
    return expected == actual
