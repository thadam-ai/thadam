"""Explicit spawned case workers with parent-owned wall deadlines and cleanup."""

import asyncio
import inspect
import multiprocessing
import os
import pickle
import queue
import threading
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
from multiprocessing.connection import Connection, wait
from time import monotonic, perf_counter

from thadam.errors import AgentConfigurationError
from thadam.fixtures import FixtureAgent
from thadam.models import Agent, AgentResult, AsyncAgent, CaseResult, TestCase


class WorkerProcessError(RuntimeError):
    """A case worker exited without delivering a completed result."""


def validate_process_inputs(agent: Agent | AsyncAgent, cases: Sequence[TestCase]) -> None:
    """Reject agents, factories or verifiers unsupported by Python spawn.

    Application callables must be importable module-level objects. Validation
    serializes configuration only and never invokes the tested agent.
    """
    try:
        pickle.dumps((agent, tuple(cases)))
    except Exception as error:
        raise AgentConfigurationError(
            "Process execution requires importable, picklable agents, factories and verifiers; "
            "nested functions and lambdas are unsupported"
        ) from error


def _receive(connection: Connection, messages: queue.Queue) -> None:
    # Reading on a daemon thread keeps a truncated IPC message from preventing a
    # deadline or cancellation from terminating the parent invocation.
    try:
        while True:
            messages.put(connection.recv())
    except (EOFError, OSError, ValueError):
        pass
    finally:
        messages.put(("closed", None))


def _stop(process, grace: float) -> None:
    stop_at = monotonic() + grace
    if process.is_alive():
        process.terminate()
        process.join(max(0, grace / 2))
    if process.is_alive():
        process.kill()
        process.join(max(0, stop_at - monotonic()))
    if not process.is_alive():
        process.close()


def _worker(
    connection: Connection, agent, case: TestCase, async_mode: bool, cancel, max_turns
) -> None:
    from thadam.runner import _agent_error, _finish_case

    parent = multiprocessing.parent_process()
    if parent is not None:

        def watch_parent():
            wait([parent.sentinel])
            # The owner disappeared, so no receiver remains to coordinate hooks
            # or termination. Exit even if tested code ignores termination.
            os._exit(2)

        threading.Thread(target=watch_parent, daemon=True).start()
    started = perf_counter()

    def snapshot(evidence: AgentResult) -> None:
        connection.send(("snapshot", evidence))

    async def invoke_async():
        if isinstance(agent, FixtureAgent):
            return await agent.ainvoke_case(
                case.tool_fixtures,
                deepcopy(case.input),
                state_fixture=case.state_fixture,
                conversation=case.conversation,
                on_snapshot=snapshot,
                max_turns=max_turns,
            )
        output = agent(deepcopy(case.input))
        return await output if inspect.isawaitable(output) else output

    async def cancellable():
        task = asyncio.create_task(invoke_async())

        async def monitor():
            while not cancel.is_set():
                await asyncio.sleep(0.01)
            task.cancel()

        watcher = asyncio.create_task(monitor())
        try:
            return await task
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

    try:
        if async_mode:
            output = asyncio.run(cancellable())
        elif isinstance(agent, FixtureAgent):
            output = agent.invoke_case(
                case.tool_fixtures,
                deepcopy(case.input),
                state_fixture=case.state_fixture,
                conversation=case.conversation,
                on_snapshot=snapshot,
                max_turns=max_turns,
            )
        else:
            output = agent(deepcopy(case.input))
        result = _finish_case(output, case, started)
    except BaseException as error:
        # KeyboardInterrupt and cancellation inside an isolated worker must not
        # abort the parent suite or permit an aborted invocation to pass.
        if not isinstance(error, (Exception, SystemExit)):
            error = WorkerProcessError(f"Worker raised {type(error).__name__}: {error}")
        result = _agent_error(case, started, error)
    try:
        connection.send(("result", result))
    finally:
        connection.close()


class _Invocation:
    def __init__(
        self, agent, case, timeout_seconds, cleanup_timeout_seconds, async_mode, max_turns
    ):
        self.case = case
        self.started = perf_counter()
        self.deadline = monotonic() + timeout_seconds
        self.cleanup = cleanup_timeout_seconds
        self.timed_out = False
        self.stop_at = None
        self.evidence = None
        self.messages = queue.Queue()
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        self.connection = receive
        self.cancel = context.Event()
        self.process = context.Process(
            target=_worker, args=(send, agent, case, async_mode, self.cancel, max_turns)
        )
        try:
            self.process.start()
        except Exception as error:
            receive.close()
            send.close()
            raise AgentConfigurationError(f"Could not start case worker: {error}") from error
        send.close()
        threading.Thread(target=_receive, args=(receive, self.messages), daemon=True).start()

    def poll(self):
        if monotonic() >= self.deadline and not self.timed_out:
            self.timed_out = True
            self.cancel.set()
            self.stop_at = monotonic() + self.cleanup
        # A busy snapshot producer must not keep this loop from rechecking the
        # wall deadline or yielding to cancellation.
        for _ in range(128):
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                self.evidence = value
            elif kind == "result":
                if self.timed_out:
                    if value.events is not None:
                        self.evidence = AgentResult(
                            None,
                            value.events,
                            False,
                            value.trace_warnings,
                            value.conversation_results,
                            value.state_initial,
                            value.state_final,
                        )
                    return self.timeout_error()
                return replace(value, duration_ms=(perf_counter() - self.started) * 1000)
            elif kind == "closed":
                if self.timed_out:
                    return self.timeout_error()
                return self.error(WorkerProcessError("Case worker exited without a result"))
        if monotonic() >= self.deadline and not self.timed_out:
            self.timed_out = True
            self.cancel.set()
            self.stop_at = monotonic() + self.cleanup
        if self.timed_out and monotonic() >= self.stop_at - self.cleanup / 2:
            return self.timeout_error()
        # The receiver drains buffered results before reporting EOF, so a worker
        # exit alone is insufficient to decide that its result was lost.
        return None

    def timeout_error(self):
        return self.error(TimeoutError("Case execution exceeded its wall-clock deadline"))

    def error(self, error):
        from thadam.runner import _execution_error

        evidence = self.evidence
        if evidence is None and self.case.state_fixture is not None:
            error = type(error)(f"{error}. No worker evidence received; final state unavailable")
        return _execution_error(
            self.case,
            self.started,
            "agent",
            error,
            events=evidence.events if evidence else None,
            trace_complete=False if evidence else None,
            trace_warnings=evidence.trace_warnings
            + ("Worker interrupted; execution evidence may be incomplete",)
            if evidence
            else (),
            conversation_results=evidence.conversation_results if evidence else (),
            state_initial=evidence.state_initial
            if evidence
            else deepcopy(self.case.state_fixture.initial)
            if self.case.state_fixture is not None
            else None,
            state_final=evidence.state_final if evidence else None,
        )

    def close(self):
        self.cancel.set()
        stop_at = monotonic() + self.cleanup if self.stop_at is None else self.stop_at
        self.process.join(max(0, (stop_at - monotonic()) / 2))
        _stop(self.process, max(0, stop_at - monotonic()))
        self.connection.close()


def execute_case(
    agent: Agent | AsyncAgent,
    case: TestCase,
    timeout_seconds: float,
    cleanup_timeout_seconds: float,
    *,
    async_mode: bool = False,
    max_turns: int | None = None,
) -> CaseResult:
    """Execute a validated case in a fresh spawned process with a wall deadline.

    The deadline includes process startup, application hooks and verification.
    Cleanup waits at most cleanup_timeout_seconds before returning. Only explicit
    worker snapshots survive termination; arbitrary agent state is unavailable.
    """
    invocation = _Invocation(
        agent, case, timeout_seconds, cleanup_timeout_seconds, async_mode, max_turns
    )
    try:
        while True:
            result = invocation.poll()
            if result is not None:
                return result
            threading.Event().wait(min(0.01, max(0.001, invocation.deadline - monotonic())))
    finally:
        invocation.close()


async def execute_case_async(
    agent: Agent | AsyncAgent,
    case: TestCase,
    timeout_seconds: float,
    cleanup_timeout_seconds: float,
    *,
    async_mode: bool = True,
    max_turns: int | None = None,
) -> CaseResult:
    """Await an isolated case; cancellation terminates its worker and propagates."""
    invocation = _Invocation(
        agent, case, timeout_seconds, cleanup_timeout_seconds, async_mode, max_turns
    )
    try:
        while True:
            result = invocation.poll()
            if result is not None:
                return result
            await asyncio.sleep(min(0.01, max(0.001, invocation.deadline - monotonic())))
    finally:
        invocation.close()
