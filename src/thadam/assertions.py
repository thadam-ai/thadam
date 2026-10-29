"""Deterministic checks and validation of custom verifier results."""

import inspect
from copy import deepcopy

from thadam._json import validate_json
from thadam.models import (
    AssertionResult,
    CheckResult,
    JSONValue,
    OutputEquals,
    OutputHasKeys,
    Verifier,
)


def evaluate_assertion(
    assertion: OutputEquals | OutputHasKeys, output: JSONValue
) -> AssertionResult:
    """Evaluate a validated built-in assertion without executing an agent."""
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
