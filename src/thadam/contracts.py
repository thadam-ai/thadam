"""Snapshot declared checks separately from their observable outcomes."""

from copy import deepcopy
from dataclasses import asdict

from thadam._json import json_equal
from thadam.models import (
    Assertion,
    CheckDefinition,
    OutputEquals,
    OutputHasKeys,
    TestCase,
    ToolArgumentsMatch,
    ToolCalled,
    ToolNotCalled,
)
from thadam.suites import parse_assertion, validate_suite


def snapshot_definitions(case: TestCase) -> tuple[CheckDefinition, ...]:
    """Copy validated case declarations, retaining unversioned verifiers explicitly."""
    names = {
        OutputEquals: "output_equals",
        OutputHasKeys: "output_has_keys",
        ToolCalled: "tool_called",
        ToolNotCalled: "tool_not_called",
        ToolArgumentsMatch: "tool_arguments_match",
    }
    definitions = []
    for assertion in case.assertions:
        parameters = asdict(assertion)
        parameters.pop("id")
        if isinstance(assertion, OutputHasKeys):
            parameters["keys"] = list(assertion.keys)
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
    validate_suite([TestCase("contract", None, (assertion,))])
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
