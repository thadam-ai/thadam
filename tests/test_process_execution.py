"""Real spawned workers exercise hard deadlines without model services."""

import asyncio
import multiprocessing
import os
import time

import pytest

from thadam.errors import AgentConfigurationError
from thadam.models import OutputEquals
from thadam.models import TestCase as Case
from thadam.process_execution import (
    execute_case,
    execute_case_async,
    validate_process_inputs,
)


def identity(value):
    return value


def hang(value):
    while True:
        time.sleep(0.02)


def crash(value):
    os._exit(0)


def exit_cleanly(value):
    raise SystemExit(0)


async def ignore_cancellation(value):
    try:
        await asyncio.sleep(30)
    finally:
        while True:
            await asyncio.sleep(0.01)


def slow_verifier(value, output):
    time.sleep(30)


def case():
    return Case("one", "ok", assertions=(OutputEquals("expected", "ok"),))


def test_spawn_success_and_unpicklable_preflight():
    validate_process_inputs(identity, [case()])
    assert execute_case(identity, case(), 5, 0.2).status == "passed"
    with pytest.raises(AgentConfigurationError, match="picklable"):
        validate_process_inputs(lambda value: value, [case()])


@pytest.mark.parametrize("agent", [hang, ignore_cancellation])
def test_hard_deadline_bounds_worker_and_cleanup(agent):
    started = time.monotonic()
    before = {child.pid for child in multiprocessing.active_children()}
    result = execute_case(agent, case(), 0.5, 0.2, async_mode=agent is ignore_cancellation)
    assert time.monotonic() - started < 3
    assert result.status == "error"
    assert result.errors[0].type == "TimeoutError"
    assert not result.output_available
    assert result.events is None
    assert {child.pid for child in multiprocessing.active_children()} <= before


@pytest.mark.parametrize("agent", [crash, exit_cleanly])
def test_worker_exit_never_passes(agent):
    result = execute_case(agent, case(), 5, 0.2)
    assert result.status == "error"
    assert result.errors[0].type in {"SystemExit", "WorkerProcessError"}


def test_async_cancellation_terminates_uncooperative_worker():
    async def exercise():
        task = asyncio.create_task(execute_case_async(ignore_cancellation, case(), 30, 0.2))
        await asyncio.sleep(0.5)
        task.cancel()
        started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 2

    asyncio.run(exercise())


def fixture_then_hang(tools):
    def agent(value):
        tools["lookup"].invoke(value)
        tools.state.write({"observed": True})
        hang(value)

    return agent


def conversation_then_hang(tools):
    def agent(value):
        if value["turn_id"] == "second":
            hang(value)
        return "ok"

    return agent


def test_timeout_retains_fixture_and_state_snapshots():
    from thadam.fixtures import FixtureAgent
    from thadam.models import StateFixture, ToolReturn, ToolScript

    configured = Case(
        "partial",
        "ok",
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={"lookup": ToolScript((ToolReturn("found"),))},
        state_fixture=StateFixture({"observed": False}),
    )
    result = execute_case(FixtureAgent(fixture_then_hang), configured, 0.7, 0.2)
    assert result.status == "error"
    assert result.errors[0].type == "TimeoutError"
    assert result.events[0].name == "lookup"
    assert result.events[0].output == "found"
    assert result.trace_complete is False
    assert result.state_initial == {"observed": False}
    assert result.state_final == {"observed": True}


def test_timeout_retains_completed_conversation_turns():
    from thadam.fixtures import FixtureAgent
    from thadam.models import ConversationTurn

    configured = Case(
        "partial",
        None,
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={},
        conversation=(ConversationTurn("first", "hello"), ConversationTurn("second", "wait")),
    )
    result = execute_case(FixtureAgent(conversation_then_hang), configured, 0.7, 0.2)
    assert result.status == "error"
    assert [turn.id for turn in result.conversation_results] == ["first"]


def environment_setup():
    return "unused"


def setup_marker():
    return os.environ["THADAM_TEST_CLEANUP_MARKER"]


def cleanup_marker(path):
    with open(path, "w") as output:
        output.write("cleaned")


def cleanup_hangs(handle):
    hang(None)


async def async_wait_factory(tools):
    async def agent(value):
        await asyncio.sleep(30)

    return agent


def test_async_timeout_permits_cooperative_environment_cleanup(tmp_path, monkeypatch):
    from thadam.environment import EnvironmentHooks
    from thadam.fixtures import FixtureAgent

    marker = tmp_path / "cleanup"
    monkeypatch.setenv("THADAM_TEST_CLEANUP_MARKER", str(marker))
    agent = FixtureAgent(
        async_wait_factory, environment=EnvironmentHooks(setup_marker, cleanup=cleanup_marker)
    )
    result = execute_case(agent, case(), 0.7, 0.5, async_mode=True)
    assert result.errors[0].type == "TimeoutError"
    assert marker.read_text() == "cleaned"


def test_blocking_cleanup_and_verifier_are_inside_deadline():
    from thadam.environment import EnvironmentHooks
    from thadam.fixtures import FixtureAgent
    from thadam.models import Verifier

    agent = FixtureAgent(
        conversation_then_hang,
        environment=EnvironmentHooks(environment_setup, cleanup=cleanup_hangs),
    )
    # A plain controlled fixture callable finishes; its cleanup is the hang.
    configured = Case(
        "cleanup",
        {"turn_id": "first"},
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={},
    )
    result = execute_case(agent, configured, 0.7, 0.2)
    assert result.errors[0].type == "TimeoutError"
    configured = Case("verifier", "ok", verifiers=(Verifier("hang", slow_verifier),))
    result = execute_case(identity, configured, 0.7, 0.2)
    assert result.errors[0].type == "TimeoutError"


def test_startup_timeout_retains_declared_initial_state():
    from thadam.fixtures import FixtureAgent
    from thadam.models import StateFixture

    configured = Case(
        "startup",
        "ok",
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={},
        state_fixture=StateFixture({"initial": True}),
    )
    result = execute_case(FixtureAgent(fixture_then_hang), configured, 0.00001, 0.1)
    assert result.errors[0].type == "TimeoutError"
    assert result.state_initial == {"initial": True}
    assert result.state_final is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-state inspection")
def test_worker_exits_when_owning_process_dies(tmp_path):
    import signal
    import subprocess
    import sys
    from pathlib import Path

    script = tmp_path / "parent.py"
    marker = tmp_path / "worker-pid"
    script.write_text("""
import os
import signal
import time
from thadam import ExecutionLimits, OutputEquals, TestCase, run_suite

def agent(value):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open(value, "w") as output:
        output.write(str(os.getpid()))
    while True:
        time.sleep(0.02)

if __name__ == "__main__":
    import sys
    run_suite(agent, [TestCase("owned", sys.argv[1], assertions=(OutputEquals("unused", None),))], limits=ExecutionLimits(timeout_seconds=30))
""")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    parent = subprocess.Popen(
        [sys.executable, str(script), str(marker)], env=environment, start_new_session=True
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        worker_pid = int(marker.read_text())
        parent.terminate()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                break
            # Minimal Linux containers may leave an adopted zombie until their
            # init process reaps it; a zombie has already stopped executing.
            status = Path(f"/proc/{worker_pid}/stat")
            try:
                if status.exists() and status.read_text().split(") ", 1)[1].startswith("Z"):
                    break
            except FileNotFoundError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("Case worker survived the death of its owning parent")
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.wait(timeout=3)
