"""Cooperative async execution using the existing validation and evidence pipeline."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from copy import deepcopy
from dataclasses import replace
from time import perf_counter

from thadam.adapters.python import validate_agent
from thadam.errors import AgentConfigurationError, SuiteValidationError
from thadam.fixtures import FixtureAgent
from thadam.models import Agent, AsyncAgent, CaseResult, RunReport, SuiteIdentity, TestCase
from thadam.repetition import RepeatedReport, validate_factory
from thadam.runner import _agent_error, _finish_case, _prepare_run

AsyncAgentFactory = Callable[[], AsyncAgent | Agent | Awaitable[AsyncAgent | Agent]]


def validate_concurrency(max_concurrency: int) -> None:
    """Reject non-positive or non-integer limits before application code runs."""
    if type(max_concurrency) is not int or max_concurrency < 1:
        raise SuiteValidationError("max_concurrency must be a positive integer")


async def run_suite_async(
    agent: AsyncAgent | Agent,
    cases: Sequence[TestCase],
    *,
    max_concurrency: int = 1,
    agent_revision: str | None = None,
    suite: SuiteIdentity | None = None,
    on_case_complete: Callable[[CaseResult], None] | None = None,
) -> RunReport:
    """Await an agent with at most max_concurrency in-flight case invocations.

    Validate/snapshot the entire suite before calling application code. Results
    retain suite order; synchronous observers receive independent snapshots in
    completion order. Agent/output/verifier errors retain the synchronous runner's
    semantics. Cancellation and observer failures cancel and await all workers and
    propagate without returning a completed report. No retries, timeout, threads,
    or automatic resource cleanup are introduced. Sync callables may participate
    but block the event loop until they return; verifiers remain synchronous.

    Shared agents and external resources must support the requested overlap.
    Scheduling settings are caller-owned and are not encoded in report schemas;
    use matching settings when generating baselines/candidates.
    """
    validate_concurrency(max_concurrency)
    if on_case_complete is not None:
        observer = (
            on_case_complete
            if inspect.isroutine(on_case_complete)
            else getattr(on_case_complete, "__call__", on_case_complete)
        )
        if inspect.iscoroutinefunction(observer) or inspect.isasyncgenfunction(observer):
            raise SuiteValidationError("on_case_complete must be synchronous")
    identity, prepared, definitions = _prepare_run(
        agent, cases, agent_revision, suite, on_case_complete, allow_async=True
    )
    results: dict[int, CaseResult] = {}
    pending = iter(enumerate(prepared))

    async def worker():
        for index, case in pending:
            started = perf_counter()
            try:
                output = (
                    agent.ainvoke_case(
                        case.tool_fixtures,
                        deepcopy(case.input),
                        state_fixture=case.state_fixture,
                        conversation=case.conversation,
                    )
                    if isinstance(agent, FixtureAgent)
                    else agent(deepcopy(case.input))
                )
                if inspect.isawaitable(output):
                    output = await output
            except (Exception, SystemExit) as error:
                result = _agent_error(case, started, error)
            else:
                result = _finish_case(output, case, started)
            result = replace(result, check_definitions=definitions[index])
            results[index] = result
            if on_case_complete is not None:
                on_case_complete(deepcopy(result))

    workers = [asyncio.create_task(worker()) for _ in range(min(max_concurrency, len(prepared)))]
    try:
        await asyncio.gather(*workers)
    except BaseException:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    return RunReport(
        cases=tuple(results[index] for index in range(len(prepared))),
        agent_revision=agent_revision,
        suite=identity,
    )


async def run_repeated_async(
    agent: AsyncAgent | Agent | None = None,
    cases: Sequence[TestCase] = (),
    *,
    attempts: int = 10,
    agent_factory: AsyncAgentFactory | None = None,
    max_concurrency: int = 1,
    agent_revision: str | None = None,
    suite: SuiteIdentity | None = None,
    on_case_complete: Callable[[CaseResult], None] | None = None,
) -> RepeatedReport:
    """Run ordered async suite attempts, bounding overlap within each attempt.

    Supply exactly one shared agent or a zero-argument sync/async factory. A
    factory constructs one agent per case invocation inside its error/timing
    boundary. Attempts never overlap. Errors continue; cancellation/observer
    failure propagates with no completed evaluation. The caller owns agent and
    verifier state, external resources, scheduling consistency and cleanup.
    Existing shared/factory report modes and schemas are preserved.
    """
    validate_concurrency(max_concurrency)
    if type(attempts) is not int or attempts < 2:
        raise SuiteValidationError("attempts must be an integer of at least 2")
    if (agent is None) == (agent_factory is None):
        raise AgentConfigurationError("Supply exactly one of agent or agent_factory")
    if agent_factory is not None:
        validate_factory(agent_factory, allow_async=True)

        async def selected(value):
            fresh = agent_factory()
            if inspect.isawaitable(fresh):
                fresh = await fresh
            validate_agent(fresh, allow_async=True)
            output = fresh(value)
            return await output if inspect.isawaitable(output) else output
    else:
        selected = agent
    # Snapshot once before the first invocation/factory, including later attempts.
    identity, prepared, _ = _prepare_run(
        selected, cases, agent_revision, suite, on_case_complete, allow_async=True
    )
    runs = []
    for _ in range(attempts):
        runs.append(
            await run_suite_async(
                selected,
                prepared,
                max_concurrency=max_concurrency,
                agent_revision=agent_revision,
                suite=identity,
                on_case_complete=on_case_complete,
            )
        )
    return RepeatedReport(
        tuple(runs),
        "simulations"
        if isinstance(agent, FixtureAgent)
        and any(case.conversation or case.state_fixture is not None for case in prepared)
        else "fixtures"
        if isinstance(agent, FixtureAgent)
        else "factory"
        if agent_factory is not None
        else "shared",
    )
