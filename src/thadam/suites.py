"""Load versioned JSON suites and validate SDK cases before execution."""

import inspect
from collections.abc import Sequence
from pathlib import Path

from thadam._json import read_json, validate_json
from thadam.errors import SuiteValidationError
from thadam.models import (
    Assertion,
    OutputEquals,
    OutputHasKeys,
    TestCase,
    ToolArgumentsMatch,
    ToolCalled,
    ToolNotCalled,
    Verifier,
)


def load_suite(path: str | Path) -> tuple[TestCase, ...]:
    """Read a schema-version-1 JSON suite, raising SuiteValidationError on errors."""
    try:
        data = read_json(path)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise SuiteValidationError(f"Cannot load suite {path}: {error}") from error

    _require_fields(data, {"schema_version", "cases"}, "suite")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SuiteValidationError("suite.schema_version must be the integer 1")
    if not isinstance(data["cases"], list):
        raise SuiteValidationError("suite.cases must be an array")

    cases = []
    for index, raw in enumerate(data["cases"]):
        location = f"suite.cases[{index}]"
        _require_fields(raw, {"id", "input", "assertions"}, location)
        if not isinstance(raw["assertions"], list):
            raise SuiteValidationError(f"{location}.assertions must be an array")
        assertions = tuple(
            parse_assertion(assertion, f"{location}.assertions[{i}]")
            for i, assertion in enumerate(raw["assertions"])
        )
        cases.append(TestCase(id=raw["id"], input=raw["input"], assertions=assertions))
    return validate_suite(cases)


def validate_suite(cases: Sequence[TestCase]) -> tuple[TestCase, ...]:
    """Validate every case, including SDK verifiers, before the first invocation."""
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence) or not cases:
        raise SuiteValidationError("A suite must be a non-empty sequence of TestCase objects")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        location = f"cases[{index}]"
        if not isinstance(case, TestCase):
            raise SuiteValidationError(f"{location} must be a TestCase")
        _unique_id(case.id, seen, location)
        try:
            validate_json(case.input, f"{location}.input")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
        for name, checks in (("assertions", case.assertions), ("verifiers", case.verifiers)):
            if not isinstance(checks, (list, tuple)):
                raise SuiteValidationError(f"{location}.{name} must be a list or tuple")
        if not case.assertions and not case.verifiers:
            raise SuiteValidationError(f"{location} must contain at least one check")
        check_ids: set[str] = set()
        for assertion in case.assertions:
            _validate_assertion(assertion, location)
            _unique_id(assertion.id, check_ids, f"{location}.assertions")
        for verifier in case.verifiers:
            if not isinstance(verifier, Verifier):
                raise SuiteValidationError(f"{location}.verifiers must contain Verifier objects")
            _unique_id(verifier.id, check_ids, f"{location}.verifiers")
            _validate_verifier(verifier, location)
    return tuple(cases)


def _unique_id(value: object, seen: set[str], location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SuiteValidationError(f"{location}: IDs must be non-empty strings")
    if value in seen:
        raise SuiteValidationError(f"{location}: duplicate ID {value!r}")
    seen.add(value)


def _validate_assertion(assertion: object, location: str) -> None:
    if isinstance(assertion, OutputEquals):
        try:
            validate_json(assertion.expected, f"{location}.expected")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    elif isinstance(assertion, OutputHasKeys):
        keys = assertion.keys
        if (
            not isinstance(keys, (list, tuple))
            or not keys
            or any(not isinstance(key, str) for key in keys)
            or len(set(keys)) != len(keys)
        ):
            raise SuiteValidationError(
                f"{location}: keys must be a non-empty sequence of unique strings"
            )
    elif isinstance(assertion, (ToolCalled, ToolNotCalled, ToolArgumentsMatch)):
        if not isinstance(assertion.tool, str) or not assertion.tool.strip():
            raise SuiteValidationError(f"{location}: tool must be a non-empty string")
        try:
            validate_json(assertion.tool)
            if isinstance(assertion, ToolArgumentsMatch):
                if not isinstance(assertion.expected, dict) or not assertion.expected:
                    raise ValueError("Expected tool arguments must be a non-empty object")
                validate_json(assertion.expected)
        except ValueError as error:
            raise SuiteValidationError(f"{location}: {error}") from error
    else:
        raise SuiteValidationError(f"{location}: unsupported assertion {type(assertion).__name__}")


def _validate_verifier(verifier: Verifier, location: str) -> None:
    if verifier.revision is not None:
        if not isinstance(verifier.revision, str) or not verifier.revision.strip():
            raise SuiteValidationError(f"{location}: verifier revision must be non-empty or None")
        try:
            validate_json(verifier.revision)
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    callback = verifier.check
    target = callback if inspect.isroutine(callback) else getattr(callback, "__call__", callback)
    if (
        not callable(callback)
        or inspect.iscoroutinefunction(target)
        or inspect.isasyncgenfunction(target)
    ):
        raise SuiteValidationError(f"{location}: verifier {verifier.id!r} must be synchronous")
    try:
        inspect.signature(callback).bind(None, None)
    except (TypeError, ValueError) as error:
        raise SuiteValidationError(
            f"{location}: verifier {verifier.id!r} must accept input and output"
        ) from error


def parse_assertion(raw: object, location: str) -> Assertion:
    """Parse a built-in declaration, raising SuiteValidationError for invalid fields.

    Value and ID validation is completed by validate_suite before execution.
    """
    if not isinstance(raw, dict):
        raise SuiteValidationError(f"{location} must be an object")
    if not isinstance(raw.get("type"), str):
        raise SuiteValidationError(f"{location}: assertion type must be a string")
    if raw.get("type") == "output_equals":
        _require_fields(raw, {"id", "type", "expected"}, location)
        return OutputEquals(id=raw["id"], expected=raw["expected"])
    if raw.get("type") == "output_has_keys":
        _require_fields(raw, {"id", "type", "keys"}, location)
        if not isinstance(raw["keys"], list):
            raise SuiteValidationError(f"{location}.keys must be an array")
        return OutputHasKeys(id=raw["id"], keys=tuple(raw["keys"]))
    if raw.get("type") in {"tool_called", "tool_not_called"}:
        _require_fields(raw, {"id", "type", "tool"}, location)
        assertion_type = ToolCalled if raw["type"] == "tool_called" else ToolNotCalled
        return assertion_type(id=raw["id"], tool=raw["tool"])
    if raw.get("type") == "tool_arguments_match":
        _require_fields(raw, {"id", "type", "tool", "expected"}, location)
        return ToolArgumentsMatch(id=raw["id"], tool=raw["tool"], expected=raw["expected"])
    raise SuiteValidationError(f"{location}: unknown assertion type {raw.get('type')!r}")


def _require_fields(value: object, fields: set[str], location: str) -> None:
    if not isinstance(value, dict):
        raise SuiteValidationError(f"{location} must be an object")
    missing, extra = fields - value.keys(), value.keys() - fields
    if missing or extra:
        raise SuiteValidationError(
            f"{location}: missing fields {sorted(missing)}, unknown fields {sorted(extra)}"
        )
