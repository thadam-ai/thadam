"""Execution contracts: evidence, errors, snapshots, and explicit expectations."""

import math

import pytest

from thadam import (
    AgentConfigurationError,
    CheckResult,
    OutputEquals,
    OutputHasKeys,
    SuiteValidationError,
    Verifier,
    run_suite,
)
from thadam import (
    TestCase as AgentTestCase,
)


def case(case_id, value, expected):
    return AgentTestCase(case_id, value, (OutputEquals("answer", expected),))


@pytest.mark.parametrize(
    ("actual", "expected", "passed"),
    [
        ({"a": 1, "b": [None, False]}, {"b": [None, False], "a": 1}, True),
        (True, 1, False),
        ({"nested": [True]}, {"nested": [1]}, False),
        (1, 1.0, True),
        ("1", 1, False),
        ([1, 2], [2, 1], False),
        ({"a": 1, "extra": 2}, {"a": 1}, False),
        (None, None, True),
    ],
)
def test_json_equality_preserves_types_and_structure(actual, expected, passed):
    result = run_suite(lambda _: actual, [case("comparison", None, expected)]).cases[0]
    assert result.assertions[0].passed is passed
    assert result.status == ("passed" if passed else "failed")
    assert result.output_available is True


@pytest.mark.parametrize("output", [{"name": "Thadam"}, [], None, {"nested": {"name": "Thadam"}}])
def test_required_keys_are_top_level_object_keys(output):
    test_case = AgentTestCase("keys", None, (OutputHasKeys("name-required", ("name",)),))
    result = run_suite(lambda _: output, [test_case]).cases[0]
    assert result.status == (
        "passed" if isinstance(output, dict) and "name" in output else "failed"
    )
    assert result.assertions[0].expected == ["name"]


def test_agent_error_does_not_stop_cases_and_counts_stay_consistent():
    calls = []

    def agent(value):
        calls.append(value)
        if value == "crash":
            raise TimeoutError("service unavailable")
        return value

    report = run_suite(
        agent,
        [case("pass", "yes", "yes"), case("error", "crash", None), case("fail", "no", "yes")],
    )
    assert calls == ["yes", "crash", "no"]
    assert [result.status for result in report.cases] == ["passed", "error", "failed"]
    assert [result.id for result in report.cases] == ["pass", "error", "fail"]
    assert report.summary.total == 3
    assert (report.summary.passed, report.summary.failed, report.summary.errors) == (1, 1, 1)
    assert report.cases[1].errors[0].source == "agent"
    assert report.cases[1].errors[0].type == "TimeoutError"
    assert report.cases[1].errors[0].message == "service unavailable"
    assert report.cases[1].output_available is False
    assert all(result.duration_ms >= 0 for result in report.cases)
    assert report.has_failures


@pytest.mark.parametrize("output", [{"bad": {1, 2}}, {1: "key"}, (1, 2), math.nan, math.inf])
def test_invalid_agent_outputs_become_output_errors(output):
    result = run_suite(lambda _: output, [case("invalid-output", None, None)]).cases[0]
    assert result.status == "error"
    assert result.errors[0].source == "output"
    assert not result.output_available
    assert result.output is None


def test_cyclic_output_becomes_error():
    output = []
    output.append(output)
    result = run_suite(lambda _: output, [case("cycle", None, None)]).cases[0]
    assert result.status == "error"
    assert "cyclic" in result.errors[0].message


def test_invalid_later_case_prevents_every_agent_invocation():
    calls = []
    with pytest.raises(SuiteValidationError, match="at least one check"):
        run_suite(calls.append, [case("valid", 1, 1), AgentTestCase("invalid", 2)])
    assert calls == []


def test_inputs_and_expectations_are_snapshotted_before_execution():
    first = case("first", {"value": 1}, {"value": 1})
    second = case("second", {"value": 2}, {"value": 2})

    def agent(value):
        original = value.copy()
        value["value"] = 100
        second.assertions[0].expected["value"] = 999
        return original

    report = run_suite(agent, [first, second])
    assert [result.status for result in report.cases] == ["passed", "passed"]
    assert first.input == {"value": 1}
    assert report.cases[0].input == {"value": 1}
    assert report.cases[1].input == {"value": 2}


def test_verifiers_receive_private_snapshots_and_return_evidence():
    seen = []

    def mutating_check(value, output):
        value["amount"] = 999
        output["amount"] = 999
        return CheckResult(True, "fixture mutation must stay local", expected=999, actual=999)

    def budget_check(value, output):
        seen.append((value, output))
        return CheckResult(
            passed=output["amount"] <= value["amount"],
            message="Refund must stay within the order amount",
            expected=value["amount"],
            actual=output["amount"],
        )

    test_case = AgentTestCase(
        "refund",
        {"amount": 25},
        verifiers=(Verifier("mutator", mutating_check), Verifier("budget", budget_check)),
    )
    report = run_suite(lambda _: {"amount": 30}, [test_case])
    result = report.cases[0]
    assert result.status == "failed"
    assert result.output == {"amount": 30}
    assert seen == [({"amount": 25}, {"amount": 30})]
    assert result.assertions[1].id == "budget"
    assert result.assertions[1].actual == 30
    assert result.assertions[1].expected == 25


@pytest.mark.parametrize(
    "returned",
    [
        True,
        {"passed": True},
        CheckResult("yes", "bad bool"),
        CheckResult(True, ""),
        CheckResult(True, "bad evidence", actual={1, 2}),
    ],
)
def test_invalid_verifier_return_never_counts_as_a_pass(returned):
    test_case = AgentTestCase(
        "verify", None, verifiers=(Verifier("invalid", lambda _i, _o: returned),)
    )
    result = run_suite(lambda _: None, [test_case]).cases[0]
    assert result.status == "error"
    assert result.output_available
    assert result.assertions == ()
    assert result.errors[0].source == "verifier"
    assert result.errors[0].assertion_id == "invalid"


def test_verifier_error_retains_assertion_failures_and_evaluates_remaining_checks():
    def broken_verifier(_input, _output):
        raise RuntimeError("broken evaluator")

    test_case = AgentTestCase(
        "mixed",
        None,
        assertions=(OutputEquals("failed-expectation", 1),),
        verifiers=(
            Verifier("broken", broken_verifier),
            Verifier("still-runs", lambda _i, _o: CheckResult(True, "checked")),
        ),
    )
    result = run_suite(lambda _: 2, [test_case]).cases[0]
    assert result.status == "error"
    assert [item.passed for item in result.assertions] == [False, True]
    assert result.errors[0].message == "broken evaluator"


def test_keyboard_interrupt_propagates():
    def interrupted(_value):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_suite(interrupted, [case("interrupt", None, None)])


def test_exit_zero_from_tested_agent_or_verifier_is_an_error_and_remaining_cases_run():
    def exiting(value):
        if value == "exit":
            raise SystemExit(0)
        return value

    report = run_suite(exiting, [case("exit", "exit", None), case("next", "ok", "ok")])
    assert [result.status for result in report.cases] == ["error", "passed"]
    assert report.cases[0].errors[0].type == "SystemExit"

    def exiting_verifier(_input, _output):
        raise SystemExit(0)

    test_case = AgentTestCase(
        "verifier-exit", None, verifiers=(Verifier("exit", exiting_verifier),)
    )
    report = run_suite(lambda value: value, [test_case])
    assert report.cases[0].status == "error"
    assert report.cases[0].errors[0].source == "verifier"


def test_async_agent_rejected_before_running():
    async def agent(value):
        return value

    with pytest.raises(AgentConfigurationError, match="synchronous"):
        run_suite(agent, [case("async", None, None)])


def test_unexpected_coroutine_output_is_closed_and_reported():
    async def value():
        return 1

    result = run_suite(lambda _: value(), [case("coroutine", None, None)]).cases[0]
    assert result.status == "error"
    assert result.errors[0].source == "output"
    assert "coroutine" in result.errors[0].message


def test_async_callable_object_rejected():
    class AsyncAgent:
        async def __call__(self, value):
            return value

    with pytest.raises(AgentConfigurationError, match="synchronous"):
        run_suite(AsyncAgent(), [case("async-object", None, None)])


def test_agent_requires_one_positional_input():
    with pytest.raises(AgentConfigurationError, match="one positional"):
        run_suite(lambda: 1, [case("no-input", None, 1)])


def test_stateful_verifier_is_not_copied_with_the_case_data():
    class Counter:
        def __init__(self):
            self.calls = 0

        def __call__(self, _input, _output):
            self.calls += 1
            return CheckResult(True, "checked")

    counter = Counter()
    test_case = AgentTestCase("stateful", None, verifiers=(Verifier("counter", counter),))
    assert not run_suite(lambda value: value, [test_case]).has_failures
    assert counter.calls == 1


def test_async_verifier_object_is_configuration_error():
    class AsyncVerifier:
        async def __call__(self, _input, _output):
            return CheckResult(True, "checked")

    test_case = AgentTestCase("async-check", None, verifiers=(Verifier("async", AsyncVerifier()),))
    with pytest.raises(SuiteValidationError, match="synchronous"):
        run_suite(lambda value: value, [test_case])


def test_values_that_cannot_be_serialized_to_utf8_json_become_output_errors():
    for output in ["\ud800", {"\ud800": 1}]:
        result = run_suite(lambda _: output, [case("invalid-unicode", None, None)]).cases[0]
        assert result.status == "error"
        assert result.errors[0].source == "output"
