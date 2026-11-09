"""Controlled recovery, lifecycle isolation, strict evidence and public entry points."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from thadam import (
    AgentConfigurationError,
    AgentResult,
    FixtureAgent,
    OutputEquals,
    ReportValidationError,
    ReportWriteError,
    SuiteIdentity,
    SuiteValidationError,
    ToolCallCount,
    ToolCallSequence,
    ToolRaise,
    ToolReturn,
    ToolScript,
    approve_review,
    compare_repeated,
    compare_reports,
    load_repeated,
    load_report,
    load_suite,
    report_to_dict,
    review_baseline,
    run_repeated,
    run_repeated_async,
    run_suite,
    run_suite_async,
    write_approved_baseline,
    write_report,
)
from thadam import TestCase as Case
from thadam.baseline_review import review_from_dict, review_to_dict
from thadam.fixtures import fixtures_to_dict, parse_fixtures
from thadam.repetition_loading import repeated_from_dict, validate_repeated
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict, validate_report
from thadam.suite_writing import file_fingerprint, save_suite

ROOT = Path(__file__).resolve().parents[1]


def test_controlled_example_distinguishes_recovery_retry_failure_and_unhandled_error():
    from examples.tool_failure_agent import create, create_buggy, create_excessive, create_unhandled

    cases = load_suite(ROOT / "examples/tool_failure_cases.json")
    good = run_suite(FixtureAgent(create), cases)
    assert good.summary.passed == 3
    assert run_suite(FixtureAgent(create_buggy), cases).summary.failed == 3
    excessive = run_suite(FixtureAgent(create_excessive), cases)
    assert excessive.summary.failed == 1
    assert excessive.cases[-1].assertions[-1].actual == {"calls": 4}
    unhandled = validate_report(run_suite(FixtureAgent(create_unhandled), cases))
    assert unhandled.summary.errors == 2 and unhandled.summary.failed == 1
    assert compare_reports(good, unhandled).exit_code == 1


def recovery_case():
    return Case(
        "recovers",
        {"order": "one"},
        (OutputEquals("result", {"amount": 25}), ToolCallCount("retry-bound", "lookup", 2, 2)),
        tool_fixtures={
            "lookup": ToolScript(
                (ToolRaise("ConnectionError", "offline"), ToolReturn({"amount": 25}))
            )
        },
    )


def create_recovering(tools):
    def agent(value):
        try:
            return tools["lookup"](value)
        except ConnectionError:
            return tools["lookup"](value)

    return agent


def suite_dict(case=None):
    case = case or recovery_case()
    return {
        "schema_version": 3,
        "suite": {"id": "recovery", "revision": "v1"},
        "cases": [
            {
                "id": case.id,
                "input": case.input,
                "assertions": [
                    {"id": "result", "type": "output_equals", "expected": {"amount": 25}},
                    {
                        "id": "retry-bound",
                        "type": "tool_call_count",
                        "tool": "lookup",
                        "min_calls": 2,
                        "max_calls": 2,
                    },
                ],
                "tool_fixtures": fixtures_to_dict(case.tool_fixtures),
            }
        ],
    }


def test_recovered_errors_pass_and_failed_attempts_count_with_evidence_roundtrip(tmp_path):
    report = run_suite(FixtureAgent(create_recovering), [recovery_case()])
    assert report.schema_version == 5 and report.summary.passed == 1
    case = report.cases[0]
    assert [event.status for event in case.events] == ["error", "completed"]
    assert case.assertions[1].actual == {"calls": 2}
    assert case.assertions[1].event_ids == tuple(event.id for event in case.events)
    assert case.events[0].error.type == "ConnectionError"
    write_report(report, tmp_path / "run.json")
    assert load_report(tmp_path / "run.json") == report


def test_fixture_calls_can_assert_exact_recovery_order():
    def create(tools):
        def agent(value):
            try:
                tools["primary"](value)
            except ConnectionError:
                return tools["fallback"](value)
            return {"unexpected": True}

        return agent

    case = Case(
        "ordered-recovery",
        {"order": "one"},
        (OutputEquals("result", {"amount": 25}), ToolCallSequence("path", ("primary", "fallback"))),
        tool_fixtures={
            "primary": ToolScript((ToolRaise("ConnectionError", "offline"),)),
            "fallback": ToolScript((ToolReturn({"amount": 25}),)),
        },
    )

    report = run_suite(FixtureAgent(create), [case])

    assert report.summary.passed == 1
    assert [event.name for event in report.cases[0].events] == ["primary", "fallback"]


@pytest.mark.parametrize(
    "name,script", [("lookup", ToolScript((ToolReturn(1),))), ("missing", None)]
)
def test_caught_missing_or_exhausted_script_is_still_fixture_error(name, script):
    def create(tools):
        def agent(value):
            for _ in range(2):
                try:
                    tools[name](value)
                except Exception:
                    pass
            return "looks fine"

        return agent

    case = Case(
        "sticky",
        {},
        (OutputEquals("out", "looks fine"),),
        tool_fixtures={} if script is None else {name: script},
    )
    result = validate_report(run_suite(FixtureAgent(create), [case])).cases[0]
    assert result.status == "error" and result.errors[0].source == "fixture"
    assert result.errors[0].type == "FixtureConfigurationError"
    assert not result.output_available and not result.assertions
    assert len(result.events) == 2


def test_repeat_final_error_allows_bounded_outage_and_excess_retry_fails_check():
    def create(attempts):
        def factory(tools):
            def agent(value):
                for _ in range(attempts):
                    try:
                        tools["lookup"](value)
                    except TimeoutError:
                        pass
                return {"unavailable": True}

            return agent

        return FixtureAgent(factory)

    case = Case(
        "outage",
        None,
        (OutputEquals("fallback", {"unavailable": True}), ToolCallCount("bound", "lookup", 1, 3)),
        tool_fixtures={
            "lookup": ToolScript((ToolRaise("TimeoutError", "scripted"),), repeat_last=True)
        },
    )
    good, excessive = run_suite(create(3), [case]), run_suite(create(4), [case])
    assert good.cases[0].status == "passed"
    assert excessive.cases[0].status == "failed" and not excessive.cases[0].errors
    assert compare_reports(good, excessive).exit_code == 1
    validate_report(excessive)


def test_unused_steps_allowed_and_returned_values_and_arguments_are_independent():
    held = []

    def create(tools):
        def agent(value):
            answer = tools["lookup"](value)
            value["order"] = "changed"
            answer["amount"] = 0
            held.append(answer)
            return 0

        return agent

    case = replace(
        recovery_case(),
        assertions=(OutputEquals("out", 0),),
        tool_fixtures={"lookup": ToolScript((ToolReturn({"amount": 25}), ToolReturn(99)))},
    )
    report = run_repeated(FixtureAgent(create), [case], attempts=3)
    assert not report.has_failures and len(held) == 3
    assert all(
        run.cases[0].events[0].input == {"order": "one"}
        and run.cases[0].events[0].output == {"amount": 25}
        for run in report.runs
    )
    assert case.tool_fixtures["lookup"].steps[0].value == {"amount": 25}
    assert validate_repeated(report) == report


def test_factory_and_uncaught_tool_errors_continue_and_retain_partial_events():
    calls = 0

    def create(tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("construction failed")
        return lambda value: tools["lookup"](value)

    cases = [replace(recovery_case(), id=str(i)) for i in range(3)]
    report = validate_report(run_suite(FixtureAgent(create), cases))
    assert report.summary.errors == 3
    assert report.cases[0].events == ()
    assert [result.errors[0].type for result in report.cases] == [
        "RuntimeError",
        "ConnectionError",
        "ConnectionError",
    ]
    assert len(report.cases[1].events) == 1


def test_plain_agent_cannot_silently_ignore_fixture_suite_and_invalid_factories_prevent_execution():
    called = []
    with pytest.raises(AgentConfigurationError, match="FixtureAgent"):
        run_suite(lambda value: called.append(value), [recovery_case()])
    with pytest.raises(AgentConfigurationError):
        run_suite(FixtureAgent(lambda: called.append(1)), [recovery_case()])
    assert called == []


@pytest.mark.parametrize(
    "scripts",
    [
        {"": ToolScript((ToolReturn(1),))},
        {"t": ToolScript(())},
        {"t": ToolScript((ToolReturn(float("nan")),))},
        {"t": ToolScript((ToolRaise("ValueError", "bad"),))},
        {"t": ToolScript((ToolReturn(1),), repeat_last=1)},
    ],
)
def test_invalid_scripts_rejected_before_factory(scripts):
    called = []
    with pytest.raises(SuiteValidationError):
        run_suite(
            FixtureAgent(lambda tools: called.append(tools)),
            [replace(recovery_case(), tool_fixtures=scripts)],
        )
    assert called == []


@pytest.mark.parametrize("minimum,maximum", [(True, 3), (-1, 3), (2, 1), (0, False), (0, 1.5)])
def test_invalid_call_bounds_rejected(minimum, maximum):
    with pytest.raises(SuiteValidationError):
        run_suite(
            lambda value: None,
            [Case("bad", None, (ToolCallCount("bound", "tool", minimum, maximum),))],
        )


def test_count_requires_complete_explicit_evidence():
    case = Case("count", None, (ToolCallCount("count", "tool", 0, 0),))
    assert run_suite(lambda _: None, [case]).cases[0].status == "error"
    assert run_suite(lambda _: AgentResult(None), [case]).cases[0].status == "passed"
    assert (
        run_suite(
            lambda _: AgentResult(None, trace_complete=False, trace_warnings=("partial",)), [case]
        )
        .cases[0]
        .status
        == "error"
    )


def test_invalid_child_trace_preserves_valid_fixture_evidence():
    def create(tools):
        def agent(value):
            tools["lookup"](value)
            return AgentResult(1, events=("invalid event",))

        return agent

    case = Case(
        "trace",
        {},
        (OutputEquals("out", 1),),
        tool_fixtures={"lookup": ToolScript((ToolReturn(1),))},
    )
    result = validate_report(run_suite(FixtureAgent(create), [case])).cases[0]
    assert result.errors[0].source == "trace" and result.trace_complete is False
    assert len(result.events) == 1 and result.events[0].name == "lookup"


def test_async_factories_overlap_and_reset_per_case_and_attempt():
    active, peak, created = 0, 0, 0

    async def create(tools):
        nonlocal created
        created += 1
        await asyncio.sleep(0)

        async def agent(value):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await tools["lookup"].ainvoke(value)
            except ConnectionError:
                await asyncio.sleep(0.001)
                return await tools["lookup"].ainvoke(value)
            finally:
                active -= 1

        return agent

    cases = [replace(recovery_case(), id=str(index)) for index in range(4)]
    report = asyncio.run(
        run_repeated_async(FixtureAgent(create), cases, attempts=3, max_concurrency=2)
    )
    assert not report.has_failures and peak == 2 and created == 12
    assert report.execution_mode == "fixtures" and report.schema_version == 2
    assert [case.id for case in report.runs[0].cases] == ["0", "1", "2", "3"]
    assert validate_repeated(report) == report


def test_async_cancellation_drains_agents_and_closes_handles():
    handles, finished = [], []

    async def scenario():
        entered = asyncio.Event()

        async def create(tools):
            handles.append(tools["lookup"])

            async def agent(value):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finished.append(True)

            return agent

        task = asyncio.create_task(run_suite_async(FixtureAgent(create), [recovery_case()]))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert finished == [True]
    with pytest.raises(ValueError, match="ended"):
        handles[0]()


def test_changed_scripts_incompatible_even_when_unexecuted_and_revision_review_guards(tmp_path):
    agent = FixtureAgent(lambda tools: lambda value: 1)
    case = replace(recovery_case(), assertions=(OutputEquals("out", 1),))
    changed = replace(case, tool_fixtures={"lookup": ToolScript((ToolReturn(100),))})
    identity = SuiteIdentity("recovery", "v1")
    before = run_suite(agent, [case], suite=identity)
    after = run_suite(agent, [changed], suite=identity)
    assert compare_reports(before, after).exit_code == 2
    review = review_baseline(after, before)
    assert any(change.scope == "tool_fixtures_changed" for change in review.changes)
    assert any("revision" in blocker for blocker in review.blockers)
    revised = run_suite(agent, [changed], suite=SuiteIdentity("recovery", "v2"))
    review = review_baseline(revised, before)
    assert not review.blockers and review_from_dict(review_to_dict(review)) == review
    old = run_repeated(agent, [case], attempts=2)
    new = run_repeated(agent, [changed], attempts=2)
    assert compare_repeated(old, new).exit_code == 2
    data = suite_dict()
    path = tmp_path / "suite.json"
    save_suite(data, path)
    data["cases"][0]["tool_fixtures"]["lookup"]["repeat_last"] = True
    with pytest.raises(ValueError, match="revision"):
        save_suite(data, path, expected_fingerprint=file_fingerprint(path))


@pytest.mark.parametrize("repeated", [False, True])
def test_fixture_approved_baselines_retain_scripts_and_refuse_errors_and_ordinary_writes(
    tmp_path, repeated
):
    options = {"suite": SuiteIdentity("recovery", "v1")}
    report = (
        run_repeated(FixtureAgent(create_recovering), [recovery_case()], attempts=2, **options)
        if repeated
        else run_suite(FixtureAgent(create_recovering), [recovery_case()], **options)
    )
    review = review_baseline(report)
    approval = approve_review(
        review,
        review_digest=review.digest,
        reviewer="Controlled test",
        reason="Reviewed full fixture evidence",
    )
    path = tmp_path / "approved.json"
    write_approved_baseline(approval, path)
    loaded = load_repeated(path) if repeated else load_report(path)
    assert loaded == report
    with pytest.raises(ReportWriteError):
        write_report(report.runs[0] if repeated else report, path)
    invalid = run_suite(
        FixtureAgent(lambda tools: lambda value: tools["missing"](value)),
        [recovery_case()],
        **options,
    )
    blocked = review_baseline(invalid)
    with pytest.raises(ReportValidationError):
        approve_review(
            blocked,
            review_digest=blocked.digest,
            reviewer="Controlled test",
            reason="Cannot accept errors",
            accept_failures=True,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw["cases"][0]["events"][1].update(output={"amount": 99}),
        lambda raw: raw["cases"][0]["events"][0]["error"].update(type="RuntimeError"),
        lambda raw: raw["cases"][0]["assertions"][1].update(passed=False),
        lambda raw: raw["cases"][0]["tool_fixtures"]["lookup"].update(repeat_last="yes"),
        lambda raw: raw.update(schema_version=4),
    ],
)
def test_loader_rejects_contradictory_scripts_events_counts_and_schema(mutation):
    raw = report_to_dict(run_suite(FixtureAgent(create_recovering), [recovery_case()]))
    mutation(raw)
    with pytest.raises(ReportValidationError):
        report_from_dict(raw)


def test_repeated_loader_rejects_changed_scripts_and_wrong_mode():
    raw = repeated_to_dict(
        run_repeated(FixtureAgent(create_recovering), [recovery_case()], attempts=2)
    )
    bad = deepcopy(raw)
    bad["runs"][1]["cases"][0]["tool_fixtures"]["lookup"]["repeat_last"] = True
    with pytest.raises(ReportValidationError, match="contracts differ"):
        repeated_from_dict(bad)
    raw["execution_mode"] = "factory"
    with pytest.raises(ReportValidationError):
        repeated_from_dict(raw)


def test_suite_version_gates_fixture_fields_and_roundtrips_declarations(tmp_path):
    data = suite_dict()
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(data))
    suite = load_suite(path)
    assert suite[0] == recovery_case()
    data["schema_version"] = 2
    path.write_text(json.dumps(data))
    with pytest.raises(SuiteValidationError):
        load_suite(path)
    with pytest.raises(SuiteValidationError):
        parse_fixtures(
            {
                "tool": {
                    "steps": [{"type": "raise", "error": "os.system", "message": "bad"}],
                    "repeat_last": False,
                }
            }
        )


@pytest.mark.parametrize(
    "command,extra",
    [("run", []), ("repeat", ["--attempts", "2"]), ("run", ["--async", "--max-concurrency", "2"])],
)
def test_cli_imports_user_factory_from_project_and_saves_evidence(tmp_path, command, extra):
    (tmp_path / "suite.json").write_text(json.dumps(suite_dict()))
    (tmp_path / "user_agent.py").write_text(
        "def create(tools):\n    def run(value):\n        try:\n            return tools['lookup'](value)\n        except ConnectionError:\n            return tools['lookup'](value)\n    return run\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thadam",
            command,
            "suite.json",
            "--fixture-factory",
            "user_agent:create",
            "--report",
            "result.json",
            *extra,
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    raw = json.loads((tmp_path / "result.json").read_text())
    assert raw["schema_version"] == (2 if command == "repeat" else 5)
    (tmp_path / "user_agent.py").write_text("raise RuntimeError('must not import')")
    result = subprocess.run(
        [sys.executable, "-m", "thadam", "run", "suite.json", "--agent", "user_agent:run"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2 and "--fixture-factory" in result.stderr
    assert "must not import" not in result.stderr
