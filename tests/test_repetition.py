"""Repeated execution, lifecycle isolation, complete evidence, and strict artifacts."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from thadam import (
    AgentConfigurationError,
    AgentExecutionError,
    AgentResult,
    CheckResult,
    ExecutionEvent,
    OutputEquals,
    ReportValidationError,
    SuiteValidationError,
    ToolCalled,
    Verifier,
    load_repeated,
    repeated_to_dict,
    run_repeated,
    write_repeated,
)
from thadam import TestCase as AgentCase
from thadam.repetition_loading import repeated_from_dict, validate_repeated


def suite():
    return [AgentCase("echo", {"value": 1}, (OutputEquals("answer", {"value": 1}),))]


def test_every_attempt_and_check_outcome_is_preserved(tmp_path):
    answers = iter([{"value": 1}, {"value": 0}, RuntimeError("unavailable"), {"value": 1}])

    def agent(_):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    report = run_repeated(agent, suite(), attempts=4, agent_revision="candidate")
    assert len({run.run_id for run in report.runs}) == 4
    case = report.cases[0]
    assert (case.counts.passed, case.counts.failed, case.counts.errors) == (2, 1, 1)
    assert case.counts.total == 4 and case.counts.pass_rate == 0.5
    assert case.checks[0].counts == case.counts
    assert case.variable and report.has_failures
    assert report.runs[2].cases[0].errors[0].message == "unavailable"
    path = tmp_path / "report.json"
    write_repeated(report, path)
    assert repeated_to_dict(load_repeated(path)) == repeated_to_dict(report)
    assert report.agent_revision == "candidate"
    assert all(run.agent_revision == "candidate" for run in report.runs)


def test_attempt_order_factory_lifecycle_and_shared_state():
    inputs = []

    class Counter:
        def __init__(self):
            self.calls = 0

        def __call__(self, value):
            inputs.append(value)
            self.calls += 1
            return self.calls

    cases = [AgentCase(name, name, (OutputEquals("first", 1),)) for name in ("a", "b")]
    shared = run_repeated(Counter(), cases, attempts=2)
    assert inputs == ["a", "b", "a", "b"]
    assert [[case.output for case in run.cases] for run in shared.runs] == [[1, 2], [3, 4]]
    created = []

    def factory():
        agent = Counter()
        created.append(agent)
        return agent

    fresh = run_repeated(cases=cases, agent_factory=factory, attempts=2)
    assert len(created) == 4 and len({id(agent) for agent in created}) == 4
    assert fresh.execution_mode == "factory" and not fresh.has_failures
    assert shared.execution_mode == "shared"


@pytest.mark.parametrize("bad", [None, 1, "2", True, 0, -1, 1.5])
def test_invalid_counts_do_not_construct_agents(bad):
    calls = []
    with pytest.raises(SuiteValidationError, match="at least 2"):
        run_repeated(cases=suite(), attempts=bad, agent_factory=lambda: calls.append(1))
    assert not calls


def test_configuration_is_validated_before_factory_construction():
    calls = []

    def factory():
        return calls.append(1)

    with pytest.raises(SuiteValidationError):
        run_repeated(cases=[], agent_factory=factory)
    for revision in ("", " ", 2, "\ud800"):
        with pytest.raises(SuiteValidationError):
            run_repeated(cases=suite(), agent_factory=factory, agent_revision=revision)
    with pytest.raises(AgentConfigurationError, match="exactly one"):
        run_repeated(cases=suite())
    with pytest.raises(AgentConfigurationError, match="exactly one"):
        run_repeated(lambda value: value, suite(), agent_factory=factory)
    with pytest.raises(AgentConfigurationError):
        run_repeated(cases=suite(), agent_factory=lambda required: required)

    async def async_factory():
        calls.append(1)

    with pytest.raises(AgentConfigurationError):
        run_repeated(cases=suite(), agent_factory=async_factory)
    assert calls == []


def test_factory_and_returned_agent_errors_continue_through_later_attempts():
    calls = []

    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise SystemExit(0)
        if len(calls) == 2:
            return None
        return lambda value: value

    report = run_repeated(cases=suite(), attempts=3, agent_factory=factory)
    assert [run.cases[0].status for run in report.runs] == ["error", "error", "passed"]
    assert report.runs[0].cases[0].errors[0].type == "SystemExit"
    assert report.runs[1].cases[0].errors[0].type == "AgentConfigurationError"


def test_keyboard_interrupt_propagates_from_factory():
    def factory():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_repeated(cases=suite(), agent_factory=factory)


def test_original_cases_and_outputs_are_snapshotted_before_user_code():
    cases = suite()
    original_output = {"value": 1}

    def agent(value):
        cases[0].input["value"] = 99
        cases[0].assertions[0].expected["value"] = 99
        value["value"] = 99
        return original_output

    report = run_repeated(agent, cases, attempts=2)
    original_output["value"] = 99
    assert not report.has_failures
    assert all(run.cases[0].input == {"value": 1} for run in report.runs)
    assert all(run.cases[0].output == {"value": 1} for run in report.runs)
    snapshot = validate_repeated(report)
    report.runs[0].cases[0].output["value"] = 999
    assert snapshot.runs[0].cases[0].output == {"value": 1}


def test_individual_check_variation_is_visible_in_always_failed_cases():
    values = iter([1, 0])
    cases = [AgentCase("case", None, (OutputEquals("always-fails", 9), OutputEquals("varies", 1)))]
    report = run_repeated(lambda _: next(values), cases, attempts=2)
    assert report.cases[0].counts.failed == 2
    assert not report.cases[0].counts.variable and report.cases[0].variable
    assert report.cases[0].checks[1].counts.passed == 1


def test_verifier_errors_keep_other_check_verdicts_and_denominators():
    def broken(*_):
        raise ValueError("broken evaluator")

    cases = [AgentCase("case", None, (OutputEquals("answer", 1),), (Verifier("custom", broken),))]
    report = run_repeated(lambda _: 1, cases, attempts=2)
    assert report.cases[0].counts.errors == 2
    assert report.cases[0].checks[0].counts.passed == 2
    assert report.cases[0].checks[1].counts.errors == 2
    assert repeated_from_dict(repeated_to_dict(report)).cases == report.cases


def test_partial_trace_evidence_is_retained_in_each_attempt():
    event = ExecutionEvent("tool-1", "tool", "lookup", "completed", 0, duration_ms=1)
    calls = []

    def agent(_):
        calls.append(1)
        if len(calls) == 1:
            raise AgentExecutionError(
                RuntimeError("graph failed"), events=(event,), trace_complete=False
            )
        return AgentResult(1, (event,))

    report = run_repeated(
        agent, [AgentCase("case", None, (ToolCalled("lookup", "lookup"),))], attempts=2
    )
    assert all(run.cases[0].events == (event,) for run in report.runs)
    assert report.runs[1].cases[0].assertions[0].event_ids == ("tool-1",)
    assert repeated_from_dict(repeated_to_dict(report)).runs == report.runs


def test_runtime_summary_uses_all_attempts_including_errors():
    report = run_repeated(lambda value: value, suite(), attempts=3)
    runs = tuple(
        replace(run, cases=(replace(run.cases[0], duration_ms=value),))
        for run, value in zip(report.runs, (1.0, 3.0, 8.0))
    )
    runtime = replace(report, runs=runs).cases[0].runtime
    assert (
        runtime.total_ms,
        runtime.min_ms,
        runtime.max_ms,
        runtime.mean_ms,
        runtime.median_ms,
    ) == (12, 1, 8, 4, 3)


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda data: data.update(attempts=True),
        lambda data: data.update(attempts=3),
        lambda data: data.update(kind="comparison"),
        lambda data: data.update(schema_version=2),
        lambda data: data.update(execution_mode="unknown"),
        lambda data: data.update(extra="unknown"),
        lambda data: data["summary"].update(passed=999),
        lambda data: data["summary"].update(passed=2.0),
        lambda data: data["cases"][0]["counts"].update(pass_rate=0),
        lambda data: data["cases"][0]["runtime"].update(mean_ms=999),
        lambda data: data["runs"][1].update(run_id=data["runs"][0]["run_id"]),
        lambda data: data["runs"][1].update(agent_revision="different"),
        lambda data: data["runs"][1]["cases"][0].update(input={"different": True}),
        lambda data: data["runs"][0]["cases"][0]["assertions"][0].update(passed=False),
    ],
)
def test_loader_rejects_invalid_evidence_and_forged_summaries(corrupt):
    data = deepcopy(repeated_to_dict(run_repeated(lambda value: value, suite(), attempts=2)))
    corrupt(data)
    with pytest.raises(ReportValidationError):
        repeated_from_dict(data)


def test_file_loader_rejects_duplicate_keys_and_missing_files(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"kind":"repeated_run","kind":"repeated_run"}')
    with pytest.raises(ReportValidationError, match="Duplicate"):
        load_repeated(path)
    path.write_text(json.dumps({"kind": "repeated_run"}))
    with pytest.raises(ReportValidationError):
        load_repeated(path)
    with pytest.raises(ReportValidationError):
        load_repeated(tmp_path / "missing.json")


def test_unrepresentable_runtime_aggregates_are_report_validation_errors():
    data = repeated_to_dict(run_repeated(lambda value: value, suite(), attempts=2))
    data["runs"][0]["cases"][0]["duration_ms"] = 10**400
    with pytest.raises(ReportValidationError):
        repeated_from_dict(data)


def test_loader_and_summaries_never_execute_verifiers(tmp_path):
    calls = []

    def check(*_):
        calls.append(1)
        return CheckResult(True, "accepted")

    cases = [AgentCase("custom", None, verifiers=(Verifier("custom", check, revision="v1"),))]
    report = run_repeated(lambda _: None, cases, attempts=2)
    path = tmp_path / "report.json"
    write_repeated(report, path)
    load_repeated(path)
    validate_repeated(report)
    assert len(calls) == 2
