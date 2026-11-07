"""Deterministic checks and validation of custom verifier results."""

import inspect
from copy import deepcopy

from thadam._json import json_equal, validate_json
from thadam.errors import TraceUnavailableError
from thadam.models import (
    Assertion,
    AssertionResult,
    CheckResult,
    ConversationOutputEquals,
    ConversationTurnResult,
    ExecutionEvent,
    JSONValue,
    OutputEquals,
    StateChanges,
    StateEquals,
    ToolArgumentsMatch,
    ToolCallCount,
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
    conversation_results: tuple[ConversationTurnResult, ...] = (),
    state_initial: JSONValue = None,
    state_final: JSONValue = None,
) -> AssertionResult:
    """Evaluate a validated built-in assertion without executing an agent."""
    if isinstance(assertion, (ToolCalled, ToolNotCalled, ToolArgumentsMatch, ToolCallCount)):
        return _evaluate_tool(assertion, events, trace_complete)
    if isinstance(assertion, ConversationOutputEquals):
        turn = next((item for item in conversation_results if item.id == assertion.turn_id), None)
        actual = None if turn is None else deepcopy(turn.output)
        passed = (
            turn is not None and turn.output_available and json_equal(assertion.expected, actual)
        )
        return AssertionResult(
            assertion.id,
            passed,
            "Conversation response matches expected JSON"
            if passed
            else f"Conversation response for turn {assertion.turn_id!r} differs or is unavailable",
            deepcopy(assertion.expected),
            actual,
        )
    if isinstance(assertion, StateEquals):
        passed = json_equal(assertion.expected, state_final)
        return AssertionResult(
            assertion.id,
            passed,
            "Final fixture state matches expected JSON"
            if passed
            else "Final fixture state differs from expected JSON",
            deepcopy(assertion.expected),
            deepcopy(state_final),
        )
    if isinstance(assertion, StateChanges):
        changed = _changed_top_level_keys(state_initial, state_final)
        allowed = set(assertion.allowed_keys)
        unexpected = [key for key in changed if key not in allowed]
        passed = not unexpected
        return AssertionResult(
            assertion.id,
            passed,
            "Observed state changes stay within the allowed keys"
            if passed
            else f"Unexpected state changes: {', '.join(unexpected)}",
            {"allowed_keys": list(assertion.allowed_keys)},
            {"changed_keys": changed, "unexpected_keys": unexpected},
        )
    if isinstance(assertion, OutputEquals):
        passed = json_equal(assertion.expected, output)
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


def _changed_top_level_keys(initial: JSONValue, final: JSONValue) -> list[str]:
    if not isinstance(initial, dict) or not isinstance(final, dict):
        return [] if json_equal(initial, final) else ["$"]
    return sorted(
        key
        for key in initial.keys() | final.keys()
        if key not in initial or key not in final or not json_equal(initial[key], final[key])
    )


def _evaluate_tool(
    assertion: ToolCalled | ToolNotCalled | ToolArgumentsMatch | ToolCallCount,
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
                key in call.input and json_equal(value, call.input[key])
                for key, value in assertion.expected.items()
            )
            for call in calls
        )
        expected = {"tool": assertion.tool, "arguments_subset": deepcopy(assertion.expected)}
        actual = [{"event_id": call.id, "arguments": deepcopy(call.input)} for call in calls]
        message = f"Every call to {assertion.tool!r} must match the selected arguments"
    elif isinstance(assertion, ToolCallCount):
        passed = len(calls) >= assertion.min_calls and (
            assertion.max_calls is None or len(calls) <= assertion.max_calls
        )
        expected = {
            "tool": assertion.tool,
            "min_calls": assertion.min_calls,
            "max_calls": assertion.max_calls,
        }
        actual = {"calls": len(calls)}
        message = f"Tool {assertion.tool!r} was called {len(calls)} time(s)"
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
