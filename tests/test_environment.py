"""Controlled external lifecycle checks, without hosted resources."""

import asyncio

import pytest

from thadam import FixtureAgent, OutputEquals, run_repeated, run_suite, run_suite_async
from thadam import TestCase as Case
from thadam.environment import EnvironmentHooks
from thadam.errors import AgentConfigurationError
from thadam.models import ConversationTurn, StateFixture


def case(**kwargs):
    return Case("one", None, assertions=(OutputEquals("ok", "ok"),), tool_fixtures={}, **kwargs)


def test_hooks_are_fresh_per_attempt_and_span_conversation():
    log = []
    handles = []

    def setup():
        handle = []
        handles.append(handle)
        log.append("setup")
        return handle

    def factory(tools):
        log.append("factory")

        def agent(value):
            tools.environment.append(value["turn_id"])
            log.append("turn")
            return "ok"

        return agent

    hooks = EnvironmentHooks(setup, lambda h: log.append("reset"), lambda h: log.append(tuple(h)))
    report = run_repeated(
        FixtureAgent(factory, environment=hooks),
        [case(conversation=(ConversationTurn("a", "first"), ConversationTurn("b", "second")))],
        attempts=2,
    )
    assert not report.has_failures
    assert handles == [["a", "b"], ["a", "b"]] and handles[0] is not handles[1]
    assert log == ["setup", "reset", "factory", "turn", "turn", ("a", "b")] * 2


def test_cleanup_preserves_primary_failure_and_partial_state():
    def fail_cleanup(handle):
        raise RuntimeError("cleanup broke")

    def factory(tools):
        def agent(value):
            tools.state.write({"seen": True})
            raise ValueError("agent broke")

        return agent

    report = run_suite(
        FixtureAgent(factory, environment=EnvironmentHooks(lambda: None, cleanup=fail_cleanup)),
        [case(state_fixture=StateFixture({}))],
    )
    result = report.cases[0]
    assert result.errors[0].type == "ValueError"
    assert result.errors[0].message == "agent broke"
    assert result.state_final == {"seen": True}
    assert "cleanup broke" in result.trace_warnings[-1]


@pytest.mark.parametrize("stage", ["setup", "reset", "factory", "cleanup"])
def test_lifecycle_errors_never_pass(stage):
    calls = []

    def fail(*args):
        raise RuntimeError(stage)

    hooks = EnvironmentHooks(
        fail if stage == "setup" else lambda: None,
        fail if stage == "reset" else None,
        fail if stage == "cleanup" else lambda h: calls.append("cleanup"),
    )
    agent = FixtureAgent(
        fail if stage == "factory" else lambda tools: lambda value: "ok", environment=hooks
    )
    report = run_suite(agent, [case()])
    assert report.summary.errors == 1
    if stage != "factory":
        assert report.cases[0].errors[0].type == "EnvironmentLifecycleError"
        assert (
            f"Environment {stage} failed: RuntimeError: {stage}"
            in report.cases[0].errors[0].message
        )
    assert calls == ([] if stage in ("setup", "cleanup") else ["cleanup"])


def test_sync_rejects_async_cleanup_before_setup():
    calls = []

    async def cleanup(handle):
        pass

    agent = FixtureAgent(
        lambda tools: lambda value: "ok",
        environment=EnvironmentHooks(lambda: calls.append("setup"), cleanup=cleanup),
    )
    with pytest.raises(AgentConfigurationError):
        run_suite(agent, [case()])
    assert calls == []


def test_async_cancellation_drains_cleanup():
    async def check():
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def agent(value):
            started.set()
            await asyncio.Event().wait()

        async def cleanup(handle):
            await asyncio.sleep(0)
            cleaned.set()

        hooks = EnvironmentHooks(lambda: None, cleanup=cleanup)
        task = asyncio.create_task(
            run_suite_async(FixtureAgent(lambda tools: agent, environment=hooks), [case()])
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()

    asyncio.run(check())


def test_turn_limit_preserves_completed_turns_and_state():
    from thadam.environment import TurnLimitExceeded
    from thadam.errors import AgentExecutionError

    snapshots = []
    calls = []

    def factory(tools):
        def agent(value):
            calls.append(value["turn_id"])
            tools.state.write({"last": value["turn_id"]})
            return "ok"

        return agent

    with pytest.raises(AgentExecutionError) as caught:
        FixtureAgent(factory).invoke_case(
            {},
            None,
            state_fixture=StateFixture({}),
            conversation=(ConversationTurn("a", "one"), ConversationTurn("b", "two")),
            max_turns=1,
            on_snapshot=snapshots.append,
        )
    assert isinstance(caught.value.original, TurnLimitExceeded)
    assert calls == ["a"]
    assert caught.value.conversation_results[0].id == "a"
    assert caught.value.state_final == {"last": "a"}
    assert snapshots[-1].conversation_results[0].id == "a"


def test_sqlite_example_repeats_resets_and_disposes_resources(monkeypatch):
    import sqlite3
    from pathlib import Path

    from examples import environment_agent as demo
    from thadam import load_suite
    from thadam.repetition_loading import repeated_from_dict
    from thadam.repetition_reporting import repeated_to_dict

    handles = []

    def setup():
        handle = demo.setup()
        handles.append((handle, Path(handle.directory.name)))
        return handle

    agent = FixtureAgent(demo.create, environment=EnvironmentHooks(setup, demo.reset, demo.cleanup))
    cases = load_suite(Path(demo.__file__).with_name("environment_cases.json"))
    report = run_repeated(agent, cases, attempts=3)
    assert not repeated_from_dict(repeated_to_dict(report)).has_failures
    assert len(handles) == 3
    for handle, path in handles:
        assert not path.exists()
        with pytest.raises(sqlite3.ProgrammingError):
            handle.connection.execute("SELECT 1")


def test_sqlite_cleanup_after_factory_failure():
    from pathlib import Path

    from examples import environment_agent as demo

    handles = []

    def setup():
        handle = demo.setup()
        handles.append(Path(handle.directory.name))
        return handle

    def factory(tools):
        raise ValueError("factory failed")

    report = run_suite(
        FixtureAgent(factory, environment=EnvironmentHooks(setup, demo.reset, demo.cleanup)),
        [case()],
    )
    assert report.summary.errors == 1
    assert not handles[0].exists()


def test_sqlite_deadline_example_roundtrips():
    from pathlib import Path

    from examples import environment_agent as demo
    from thadam import ExecutionLimits, load_suite
    from thadam.repetition_loading import repeated_from_dict
    from thadam.repetition_reporting import repeated_to_dict
    from thadam.report_loading import report_from_dict
    from thadam.reporting import report_to_dict

    cases = load_suite(Path(demo.__file__).with_name("environment_cases.json"))
    limits = ExecutionLimits(timeout_seconds=5)
    report = run_suite(demo.AGENT, cases, limits=limits)
    assert not report_from_dict(report_to_dict(report)).has_failures
    repeated = run_repeated(demo.AGENT, cases, attempts=2, limits=limits)
    assert not repeated_from_dict(repeated_to_dict(repeated)).has_failures


def test_observer_failure_does_not_skip_cleanup():
    calls = []

    def observer(snapshot):
        raise ValueError("observer failed")

    hooks = EnvironmentHooks(lambda: None, cleanup=lambda h: calls.append("cleanup"))
    # Fail only once setup succeeded, rather than before setup allocated a handle.
    count = 0

    def after_setup(snapshot):
        nonlocal count
        count += 1
        if count > 1:
            observer(snapshot)

    from thadam.errors import AgentExecutionError

    with pytest.raises(AgentExecutionError) as caught:
        FixtureAgent(lambda tools: lambda v: "ok", environment=hooks).invoke_case(
            {}, None, on_snapshot=after_setup
        )
    assert calls == ["cleanup"]
    assert caught.value.original.args == ("observer failed",)


def test_cancellation_cleanup_failure_is_in_partial_evidence():
    async def check():
        started = asyncio.Event()
        snapshots = []

        async def agent(value):
            started.set()
            await asyncio.Event().wait()

        async def cleanup(handle):
            raise RuntimeError("cleanup failed")

        hooks = EnvironmentHooks(lambda: None, cleanup=cleanup)
        task = asyncio.create_task(
            FixtureAgent(lambda tools: agent, environment=hooks).ainvoke_case(
                {}, None, on_snapshot=snapshots.append
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "cleanup failed" in snapshots[-1].trace_warnings[-1]

    asyncio.run(check())


@pytest.mark.parametrize("async_execution", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_lifecycle_preserves_child_event_with_fixture_prefix(async_execution, raises):
    from thadam import AgentResult, ExecutionEvent
    from thadam.errors import AgentExecutionError

    event = ExecutionEvent(
        id="fixture:application-owned",
        kind="model",
        name="child",
        status="completed",
        started_at_ms=0,
        duration_ms=1,
    )

    def factory(tools):
        def agent(value):
            if raises:
                raise AgentExecutionError(
                    ValueError("child error"), events=(event,), trace_complete=True
                )
            return AgentResult("ok", events=(event,))

        return agent

    hooks = EnvironmentHooks(lambda: None)
    agent = FixtureAgent(factory, environment=hooks)
    report = (
        asyncio.run(run_suite_async(agent, [case()]))
        if async_execution
        else run_suite(agent, [case()])
    )
    assert report.cases[0].events[0].id == "fixture:application-owned"
    assert len(report.cases[0].events) == 1
    assert report.cases[0].errors[0].type == "ValueError" if raises else not report.has_failures
