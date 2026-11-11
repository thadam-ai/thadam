"""Snapshot declared checks separately from their observable outcomes."""

from copy import deepcopy
from dataclasses import asdict

from thadam._json import json_equal
from thadam.fixtures import fixtures_to_dict
from thadam.limits import limits_to_dict
from thadam.models import (
    Assertion,
    CaseResult,
    CheckDefinition,
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
)
from thadam.suites import parse_assertion, validate_suite


def suite_contract_issues(
    baseline: SuiteIdentity | None, candidate: SuiteIdentity | None
) -> list[str]:
    """Require identical explicit identities, or two legacy unidentified suites."""
    if baseline == candidate:
        return []
    if baseline is None or candidate is None:
        return ["Suite identity added or missing; review and approve a matching baseline"]
    if baseline.id != candidate.id:
        return ["Suite ID changed; review and approve a matching baseline"]
    return ["Suite revision changed; review and approve a matching baseline"]


def snapshot_definitions(case: TestCase) -> tuple[CheckDefinition, ...]:
    """Copy validated case declarations, retaining unversioned verifiers explicitly."""
    names = {
        OutputEquals: "output_equals",
        OutputHasKeys: "output_has_keys",
        ToolCalled: "tool_called",
        ToolNotCalled: "tool_not_called",
        ToolArgumentsMatch: "tool_arguments_match",
        ToolCallCount: "tool_call_count",
        ToolCallSequence: "tool_call_sequence",
        ConversationOutputEquals: "conversation_output_equals",
        StateEquals: "state_equals",
        StateChanges: "state_changes",
    }
    definitions = []
    for assertion in case.assertions:
        parameters = asdict(assertion)
        parameters.pop("id")
        if isinstance(assertion, OutputHasKeys):
            parameters["keys"] = list(assertion.keys)
        if isinstance(assertion, StateChanges):
            parameters["allowed_keys"] = list(assertion.allowed_keys)
        if isinstance(assertion, ToolCallSequence):
            parameters["tools"] = list(assertion.tools)
        definitions.append(CheckDefinition(assertion.id, names[type(assertion)], parameters))
    definitions.extend(
        CheckDefinition(verifier.id, "verifier", {"revision": verifier.revision})
        for verifier in case.verifiers
    )
    return tuple(deepcopy(definitions))


def definition_assertion(definition: CheckDefinition) -> Assertion:
    """Reconstruct a built-in contract; reject invalid parameters via suite validation."""
    if {"id", "type"} & definition.parameters.keys():
        raise ValueError("Check parameters cannot override id or type")
    assertion = parse_assertion(
        {**definition.parameters, "id": definition.id, "type": definition.type},
        f"check {definition.id!r}",
    )
    turns = (
        (ConversationTurn(assertion.turn_id, None),)
        if isinstance(assertion, ConversationOutputEquals)
        else ()
    )
    state = StateFixture(None) if isinstance(assertion, (StateEquals, StateChanges)) else None
    validate_suite(
        [TestCase("contract", None, (assertion,), conversation=turns, state_fixture=state)]
    )
    return assertion


def equivalent_definitions(left: CheckDefinition, right: CheckDefinition) -> bool:
    """Require matching declared semantics; a verifier needs an explicit revision."""
    if left.id != right.id or left.type != right.type:
        return False
    if left.type == "verifier" and not left.parameters["revision"]:
        return False
    if left.type == "output_has_keys":
        return set(left.parameters["keys"]) == set(right.parameters["keys"])
    return json_equal(left.parameters, right.parameters)


def case_contract_issues(baseline: CaseResult | None, candidate: CaseResult | None) -> list[str]:
    """Explain incompatible case/input/check contracts without evaluating any code."""
    if baseline is None:
        return ["Case added in candidate; review it and generate a matching baseline"]
    if candidate is None:
        return ["Case missing from candidate"]
    issues = []
    if not json_equal(
        limits_to_dict(baseline.execution_limits), limits_to_dict(candidate.execution_limits)
    ):
        issues.append("Execution limits changed")
    if not json_equal(
        None if baseline.tool_fixtures is None else fixtures_to_dict(baseline.tool_fixtures),
        None if candidate.tool_fixtures is None else fixtures_to_dict(candidate.tool_fixtures),
    ):
        issues.append("Tool fixture contract changed")
    if not json_equal(baseline.input, candidate.input):
        issues.append("Case input changed")
    if not json_equal(
        [asdict(turn) for turn in baseline.conversation],
        [asdict(turn) for turn in candidate.conversation],
    ):
        issues.append("Conversation script changed")
    if not json_equal(
        None if baseline.state_fixture is None else asdict(baseline.state_fixture),
        None if candidate.state_fixture is None else asdict(candidate.state_fixture),
    ):
        issues.append("Initial state fixture changed")
    old = {check.id: check for check in baseline.check_definitions}
    new = {check.id: check for check in candidate.check_definitions}
    for check_id, definition in old.items():
        if check_id not in new:
            issues.append(f"Check {check_id!r} missing from candidate")
        elif not equivalent_definitions(definition, new[check_id]):
            if definition.type == "verifier" and not definition.parameters["revision"]:
                issues.append(f"Verifier {check_id!r} requires an explicit revision")
            else:
                issues.append(f"Check {check_id!r} definition or verifier revision changed")
    issues.extend(
        f"Check {check_id!r} added in candidate" for check_id in new if check_id not in old
    )
    return issues
