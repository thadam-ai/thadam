"""Load versioned JSON suites and validate SDK cases before execution."""

import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import overload

from thadam._json import read_json, validate_json
from thadam.errors import SuiteValidationError
from thadam.fixtures import parse_fixtures, validate_fixtures
from thadam.models import (
    Assertion,
    ConversationOutputEquals,
    ConversationTurn,
    OutputEquals,
    OutputHasKeys,
    StateChanges,
    StateEquals,
    StateFixture,
    SuiteIdentity,
    TestCase,
    ToolArgumentsMatch,
    ToolCallCount,
    ToolCalled,
    ToolCallSequence,
    ToolNotCalled,
    Verifier,
)


@dataclass(frozen=True)
class TestSuite(Sequence[TestCase]):
    """A versioned SDK suite; sequence access preserves existing runner usage."""

    identity: SuiteIdentity
    cases: tuple[TestCase, ...]

    @overload
    def __getitem__(self, index: int) -> TestCase: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[TestCase, ...]: ...

    def __getitem__(self, index: int | slice) -> TestCase | tuple[TestCase, ...]:
        return self.cases[index]

    def __len__(self) -> int:
        return len(self.cases)


def suite_identity(
    cases: Sequence[TestCase], explicit: SuiteIdentity | None = None
) -> SuiteIdentity | None:
    """Validate identity before execution; reject conflicting explicit metadata."""
    embedded = cases.identity if isinstance(cases, TestSuite) else None
    if isinstance(cases, TestSuite) and not isinstance(embedded, SuiteIdentity):
        raise SuiteValidationError("TestSuite.identity must be a SuiteIdentity")
    if embedded is not None and explicit is not None and embedded != explicit:
        raise SuiteValidationError("Explicit suite identity conflicts with TestSuite.identity")
    identity = embedded if embedded is not None else explicit
    if identity is not None:
        if not isinstance(identity, SuiteIdentity):
            raise SuiteValidationError("suite must be a SuiteIdentity or None")
        for name, value in (("id", identity.id), ("revision", identity.revision)):
            if not isinstance(value, str) or not value.strip():
                raise SuiteValidationError(f"suite.{name} must be a non-empty string")
            try:
                validate_json(value, f"suite.{name}")
            except ValueError as error:
                raise SuiteValidationError(str(error)) from error
    return identity


def load_suite(path: str | Path) -> tuple[TestCase, ...] | TestSuite:
    """Read legacy, identified or fixture suites; raise SuiteValidationError."""
    try:
        data = read_json(path)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise SuiteValidationError(f"Cannot load suite {path}: {error}") from error

    return suite_from_dict(data)


def suite_from_dict(data: object) -> tuple[TestCase, ...] | TestSuite:
    """Validate a saved suite object without file access or application imports."""

    version = data.get("schema_version") if isinstance(data, dict) else None
    if type(version) is not int or version not in (1, 2, 3, 4):
        raise SuiteValidationError("suite.schema_version must be the integer 1, 2, 3, or 4")
    _require_fields(
        data, {"schema_version", "cases"} | ({"suite"} if version >= 2 else set()), "suite"
    )
    identity = None
    if version >= 2:
        _require_fields(data["suite"], {"id", "revision"}, "suite.suite")
        identity = suite_identity((), SuiteIdentity(**data["suite"]))
    if not isinstance(data["cases"], list):
        raise SuiteValidationError("suite.cases must be an array")

    cases = []
    for index, raw in enumerate(data["cases"]):
        location = f"suite.cases[{index}]"
        _require_fields(
            raw,
            {"id", "input", "assertions"}
            | ({"tool_fixtures"} if version == 3 else set())
            | ({"tool_fixtures", "conversation", "state_fixture"} if version == 4 else set()),
            location,
        )
        if not isinstance(raw["assertions"], list):
            raise SuiteValidationError(f"{location}.assertions must be an array")
        assertions = tuple(
            parse_assertion(assertion, f"{location}.assertions[{i}]")
            for i, assertion in enumerate(raw["assertions"])
        )
        cases.append(
            TestCase(
                id=raw["id"],
                input=raw["input"],
                assertions=assertions,
                tool_fixtures=parse_fixtures(raw["tool_fixtures"]) if version in (3, 4) else None,
                conversation=(
                    _parse_conversation(raw["conversation"], f"{location}.conversation")
                    if version == 4
                    else ()
                ),
                state_fixture=(
                    _parse_state_fixture(raw["state_fixture"], f"{location}.state_fixture")
                    if version == 4 and raw["state_fixture"] is not None
                    else None
                ),
            )
        )
    validated = validate_suite(cases)
    return TestSuite(identity, validated) if identity is not None else validated


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
        validate_fixtures(case.tool_fixtures)
        try:
            validate_json(case.input, f"{location}.input")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
        for name, checks in (("assertions", case.assertions), ("verifiers", case.verifiers)):
            if not isinstance(checks, (list, tuple)):
                raise SuiteValidationError(f"{location}.{name} must be a list or tuple")
        if not case.assertions and not case.verifiers:
            raise SuiteValidationError(f"{location} must contain at least one check")
        if not isinstance(case.conversation, (list, tuple)):
            raise SuiteValidationError(f"{location}.conversation must be a list or tuple")
        turn_ids: set[str] = set()
        for turn in case.conversation:
            if not isinstance(turn, ConversationTurn):
                raise SuiteValidationError(
                    f"{location}.conversation must contain ConversationTurn values"
                )
            _unique_id(turn.id, turn_ids, f"{location}.conversation")
            try:
                validate_json(turn.message, f"{location}.conversation[{turn.id}].message")
            except ValueError as error:
                raise SuiteValidationError(str(error)) from error
        if case.state_fixture is not None:
            if not isinstance(case.state_fixture, StateFixture):
                raise SuiteValidationError(
                    f"{location}.state_fixture must be a StateFixture or None"
                )
            try:
                validate_json(case.state_fixture.initial, f"{location}.state_fixture.initial")
            except ValueError as error:
                raise SuiteValidationError(str(error)) from error
        check_ids: set[str] = set()
        for assertion in case.assertions:
            _validate_assertion(assertion, location)
            _unique_id(assertion.id, check_ids, f"{location}.assertions")
            if (
                isinstance(assertion, ConversationOutputEquals)
                and assertion.turn_id not in turn_ids
            ):
                raise SuiteValidationError(
                    f"{location}: conversation check references unknown turn {assertion.turn_id!r}"
                )
            if isinstance(assertion, (StateEquals, StateChanges)) and case.state_fixture is None:
                raise SuiteValidationError(f"{location}: state checks require state_fixture")
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
    elif isinstance(assertion, ConversationOutputEquals):
        if not isinstance(assertion.turn_id, str) or not assertion.turn_id.strip():
            raise SuiteValidationError(f"{location}: turn_id must be a non-empty string")
        try:
            validate_json(assertion.expected, f"{location}.expected")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    elif isinstance(assertion, StateEquals):
        try:
            validate_json(assertion.expected, f"{location}.expected")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    elif isinstance(assertion, StateChanges):
        keys = assertion.allowed_keys
        if (
            not isinstance(keys, (list, tuple))
            or any(not isinstance(key, str) or not key for key in keys)
            or len(set(keys)) != len(keys)
        ):
            raise SuiteValidationError(f"{location}: allowed_keys must be unique non-empty strings")
    elif isinstance(
        assertion,
        (ToolCalled, ToolNotCalled, ToolArgumentsMatch, ToolCallCount, ToolCallSequence),
    ):
        if isinstance(assertion, ToolCallSequence):
            tools = assertion.tools
            if (
                not isinstance(tools, (list, tuple))
                or not tools
                or any(not isinstance(tool, str) or not tool.strip() for tool in tools)
            ):
                raise SuiteValidationError(
                    f"{location}: tools must be a non-empty sequence of tool names"
                )
            try:
                validate_json(list(tools), f"{location}.tools")
            except ValueError as error:
                raise SuiteValidationError(str(error)) from error
            return
        if not isinstance(assertion.tool, str) or not assertion.tool.strip():
            raise SuiteValidationError(f"{location}: tool must be a non-empty string")
        try:
            validate_json(assertion.tool)
            if isinstance(assertion, ToolArgumentsMatch):
                if not isinstance(assertion.expected, dict) or not assertion.expected:
                    raise ValueError("Expected tool arguments must be a non-empty object")
                validate_json(assertion.expected)
            if isinstance(assertion, ToolCallCount):
                if type(assertion.min_calls) is not int or assertion.min_calls < 0:
                    raise ValueError("min_calls must be a non-negative integer")
                if assertion.max_calls is not None and (
                    type(assertion.max_calls) is not int
                    or assertion.max_calls < assertion.min_calls
                ):
                    raise ValueError("max_calls must be None or an integer at least min_calls")
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
    if raw.get("type") == "conversation_output_equals":
        _require_fields(raw, {"id", "type", "turn_id", "expected"}, location)
        return ConversationOutputEquals(raw["id"], raw["turn_id"], raw["expected"])
    if raw.get("type") == "state_equals":
        _require_fields(raw, {"id", "type", "expected"}, location)
        return StateEquals(raw["id"], raw["expected"])
    if raw.get("type") == "state_changes":
        _require_fields(raw, {"id", "type", "allowed_keys"}, location)
        if not isinstance(raw["allowed_keys"], list):
            raise SuiteValidationError(f"{location}.allowed_keys must be an array")
        return StateChanges(raw["id"], tuple(raw["allowed_keys"]))
    if raw.get("type") in {"tool_called", "tool_not_called"}:
        _require_fields(raw, {"id", "type", "tool"}, location)
        assertion_type = ToolCalled if raw["type"] == "tool_called" else ToolNotCalled
        return assertion_type(id=raw["id"], tool=raw["tool"])
    if raw.get("type") == "tool_arguments_match":
        _require_fields(raw, {"id", "type", "tool", "expected"}, location)
        return ToolArgumentsMatch(id=raw["id"], tool=raw["tool"], expected=raw["expected"])
    if raw.get("type") == "tool_call_count":
        _require_fields(raw, {"id", "type", "tool", "min_calls", "max_calls"}, location)
        return ToolCallCount(raw["id"], raw["tool"], raw["min_calls"], raw["max_calls"])
    if raw.get("type") == "tool_call_sequence":
        _require_fields(raw, {"id", "type", "tools"}, location)
        if not isinstance(raw["tools"], list):
            raise SuiteValidationError(f"{location}.tools must be an array")
        return ToolCallSequence(raw["id"], tuple(raw["tools"]))
    raise SuiteValidationError(f"{location}: unknown assertion type {raw.get('type')!r}")


def _require_fields(value: object, fields: set[str], location: str) -> None:
    if not isinstance(value, dict):
        raise SuiteValidationError(f"{location} must be an object")
    missing, extra = fields - value.keys(), value.keys() - fields
    if missing or extra:
        raise SuiteValidationError(
            f"{location}: missing fields {sorted(missing)}, unknown fields {sorted(extra)}"
        )


def _parse_conversation(raw: object, location: str) -> tuple[ConversationTurn, ...]:
    if not isinstance(raw, list):
        raise SuiteValidationError(f"{location} must be an array")
    turns = []
    for index, turn in enumerate(raw):
        item_location = f"{location}[{index}]"
        _require_fields(turn, {"id", "message"}, item_location)
        turns.append(ConversationTurn(turn["id"], turn["message"]))
    return tuple(turns)


def _parse_state_fixture(raw: object, location: str) -> StateFixture:
    _require_fields(raw, {"initial"}, location)
    return StateFixture(raw["initial"])
