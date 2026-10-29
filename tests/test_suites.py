"""Suite validation is shared by files and programmatically constructed cases."""

import json
import math
from copy import deepcopy

import pytest

from thadam import (
    OutputEquals,
    OutputHasKeys,
    SuiteValidationError,
    Verifier,
    load_suite,
    run_suite,
)
from thadam import (
    TestCase as AgentTestCase,
)


@pytest.fixture
def suite():
    return {
        "schema_version": 1,
        "cases": [
            {
                "id": "one",
                "input": None,
                "assertions": [{"id": "answer", "type": "output_equals", "expected": None}],
            }
        ],
    }


def test_json_suite_loads_null_expectation_and_key_check(tmp_path, suite):
    suite["cases"][0]["assertions"].append(
        {"id": "fields", "type": "output_has_keys", "keys": ["name"]}
    )
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(suite))
    cases = load_suite(path)
    assert cases[0].assertions == (OutputEquals("answer", None), OutputHasKeys("fields", ("name",)))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(schema_version=True),
        lambda s: s.update(schema_version=2),
        lambda s: s.update(cases=[]),
        lambda s: s.update(cases={}),
        lambda s: s.update(typo=True),
        lambda s: s["cases"].append(deepcopy(s["cases"][0])),
        lambda s: s["cases"][0].update(id=" "),
        lambda s: s["cases"][0].pop("input"),
        lambda s: s["cases"][0].update(assertions=[]),
        lambda s: s["cases"][0].update(assertions={}),
        lambda s: s["cases"][0]["assertions"].append(deepcopy(s["cases"][0]["assertions"][0])),
        lambda s: s["cases"][0]["assertions"][0].update(type="unknown"),
        lambda s: s["cases"][0]["assertions"][0].pop("expected"),
        lambda s: s["cases"][0]["assertions"][0].update(unused="typo"),
    ],
)
def test_invalid_file_contracts_rejected(tmp_path, suite, mutate):
    mutate(suite)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(suite))
    with pytest.raises(SuiteValidationError):
        load_suite(path)


@pytest.mark.parametrize(
    "content",
    [
        "{",
        "[]",
        '{"schema_version":1,"schema_version":1}',
        '{"value": NaN}',
        '{"value": Infinity}',
        '{"value": 1e999}',
    ],
)
def test_malformed_or_nonstandard_json_is_rejected(tmp_path, content):
    path = tmp_path / "invalid.json"
    path.write_text(content)
    with pytest.raises(SuiteValidationError):
        load_suite(path)


def test_file_errors_are_useful_configuration_errors(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(SuiteValidationError, match="missing.json"):
        load_suite(path)
    path.write_bytes(b"\xff")
    with pytest.raises(SuiteValidationError, match="Cannot load suite"):
        load_suite(path)


@pytest.mark.parametrize("keys", [(), ("a", "a"), (1,), "name"])
def test_sdk_rejects_invalid_required_keys_before_invocation(keys):
    calls = []
    test_case = AgentTestCase("fields", None, (OutputHasKeys("keys", keys),))
    with pytest.raises(SuiteValidationError):
        run_suite(calls.append, [test_case])
    assert calls == []


@pytest.mark.parametrize("value", [math.nan, {1: "bad"}, {"nested": {1, 2}}, (1, 2)])
def test_sdk_checks_json_input_and_expected_values(value):
    with pytest.raises(SuiteValidationError):
        run_suite(lambda _: None, [AgentTestCase("input", value, (OutputEquals("check", None),))])
    with pytest.raises(SuiteValidationError):
        run_suite(
            lambda _: None, [AgentTestCase("expected", None, (OutputEquals("check", value),))]
        )


def test_duplicate_ids_across_builtin_and_verifier_are_rejected():
    test_case = AgentTestCase(
        "duplicate", None, (OutputEquals("check", None),), (Verifier("check", lambda _i, _o: True),)
    )
    with pytest.raises(SuiteValidationError, match="duplicate ID"):
        run_suite(lambda _: None, [test_case])


def test_invalid_verifier_signature_rejected_before_agent_execution():
    calls = []
    test_case = AgentTestCase("verifier", None, verifiers=(Verifier("bad", lambda: True),))
    with pytest.raises(SuiteValidationError, match="input and output"):
        run_suite(calls.append, [test_case])
    assert calls == []
