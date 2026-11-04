"""Async lifecycle, isolation, evidence and CLI contracts without external services."""

import asyncio
import json

import pytest

from thadam import (
    AgentExecutionError,
    AgentResult,
    OutputEquals,
    SuiteValidationError,
    compare_reports,
    load_report,
    run_repeated_async,
    run_suite_async,
    write_report,
)
from thadam import (
    TestCase as Case,
)
from thadam.cli import main


def cases(count=4):
    return [Case(str(i), {"n": i}, (OutputEquals("answer", i),)) for i in range(count)]


def test_bounded_overlap_order_snapshots_and_round_trip(tmp_path):
    async def exercise():
        active = peak = 0
        pair = asyncio.Event()
        finished = []

        async def agent(value):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                pair.set()
            await pair.wait()
            if value["n"] == 0:
                await asyncio.sleep(0.01)
            result = value["n"]
            value["n"] = -1
            active -= 1
            return result

        def observer(result):
            finished.append(result.id)
            result.input["n"] = "observer mutation"

        report = await asyncio.wait_for(
            run_suite_async(agent, cases(), max_concurrency=2, on_case_complete=observer), 2
        )
        assert peak == 2
        assert finished[0] != "0"
        assert [case.id for case in report.cases] == ["0", "1", "2", "3"]
        assert [case.input["n"] for case in report.cases] == list(range(4))
        assert not report.has_failures
        write_report(report, tmp_path / "run.json")
        assert compare_reports(report, load_report(tmp_path / "run.json")).exit_code == 0

    asyncio.run(exercise())


def test_errors_system_exit_trace_and_output_continue():
    async def agent(value):
        if value["n"] == 0:
            raise SystemExit(0)
        if value["n"] == 1:
            raise AgentExecutionError(
                ValueError("failed"), events=(), trace_complete=False, trace_warnings=("partial",)
            )
        if value["n"] == 2:
            return object()
        return AgentResult(3)

    report = asyncio.run(run_suite_async(agent, cases(), max_concurrency=2))
    assert [case.status for case in report.cases] == ["error", "error", "error", "passed"]
    assert report.cases[1].events == ()
    assert report.cases[1].trace_complete is False
    assert report.cases[2].errors[0].source == "output"
    assert report.cases[3].events == ()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2"])
def test_invalid_concurrency_before_agent(limit):
    calls = []
    with pytest.raises(SuiteValidationError):
        asyncio.run(
            run_suite_async(lambda value: calls.append(value), cases(), max_concurrency=limit)
        )
    assert calls == []


def test_cancel_and_observer_error_drain_workers():
    async def exercise(observer_error):
        entered = asyncio.Event()
        cleaned = []

        async def agent(value):
            try:
                if observer_error and value["n"] == 0:
                    await entered.wait()
                    return 0
                entered.set()
                await asyncio.Event().wait()
            finally:
                cleaned.append(value["n"])

        def observer(_):
            raise RuntimeError("observer failed")

        task = asyncio.create_task(
            run_suite_async(
                agent,
                cases(2),
                max_concurrency=2,
                on_case_complete=observer if observer_error else None,
            )
        )
        await entered.wait()
        if not observer_error:
            task.cancel()
        with pytest.raises(RuntimeError if observer_error else asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert sorted(cleaned) == [0, 1]

    asyncio.run(exercise(False))
    asyncio.run(exercise(True))


def test_async_factory_each_invocation_and_sequential_attempts():
    constructed = []

    async def factory():
        constructed.append(object())

        async def agent(value):
            await asyncio.sleep(0)
            return value["n"]

        return agent

    report = asyncio.run(
        run_repeated_async(cases=cases(3), agent_factory=factory, attempts=2, max_concurrency=2)
    )
    assert len(constructed) == 6
    assert report.execution_mode == "factory"
    assert report.attempts == 2
    assert not report.has_failures
    assert all(case.counts.total == 2 for case in report.cases)


def test_cli_async_and_configuration_rejected_before_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "async_example.py").write_text("async def run(value):\n    return value\n")
    (tmp_path / "cases.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "echo",
                        "input": 1,
                        "assertions": [{"id": "echo", "type": "output_equals", "expected": 1}],
                    }
                ],
            }
        )
    )
    assert (
        main(
            [
                "run",
                "cases.json",
                "--agent",
                "async_example:run",
                "--async",
                "--max-concurrency",
                "2",
                "--report",
                "result.json",
            ]
        )
        == 0
    )
    assert not load_report(tmp_path / "result.json").has_failures
    assert main(["run", "cases.json", "--agent", "never_import:run", "--max-concurrency", "2"]) == 2


def test_repeated_factory_errors_continue_without_losing_attempts():
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("construction failed")
        return lambda value: value["n"]

    report = asyncio.run(
        run_repeated_async(cases=cases(2), attempts=2, agent_factory=factory, max_concurrency=2)
    )
    assert calls == 4
    assert report.runs[0].cases[0].errors[0].source == "agent"
    assert [case.status for case in report.runs[1].cases] == ["passed", "passed"]


def test_repeated_cli_async_factory(tmp_path, monkeypatch):
    from thadam import load_repeated

    monkeypatch.chdir(tmp_path)
    (tmp_path / "async_repeat_example.py").write_text(
        "async def run(value):\n    return value\nasync def create():\n    return run\n"
    )
    (tmp_path / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "echo",
                        "input": None,
                        "assertions": [{"id": "out", "type": "output_equals", "expected": None}],
                    }
                ],
            }
        )
    )
    assert (
        main(
            [
                "repeat",
                "suite.json",
                "--agent-factory",
                "async_repeat_example:create",
                "--attempts",
                "2",
                "--async",
                "--max-concurrency",
                "2",
                "--report",
                "repeat.json",
            ]
        )
        == 0
    )
    assert load_repeated(tmp_path / "repeat.json").execution_mode == "factory"
