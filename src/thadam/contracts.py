"""Snapshot declared checks separately from their observable outcomes."""

from copy import deepcopy
from dataclasses import asdict

from thadam._json import json_equal
from thadam.models import (
    Assertion,
    CaseResult,
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


def case_contract_issues(baseline: CaseResult | None, candidate: CaseResult | None) -> list[str]:
    """Explain incompatible case/input/check contracts without evaluating any code."""
    if baseline is None:
        return ["Case added in candidate; review it and generate a matching baseline"]
    if candidate is None:
        return ["Case missing from candidate"]
    issues = []
    if not json_equal(baseline.input, candidate.input):
        issues.append("Case input changed")
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
