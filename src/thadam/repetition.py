"""Sequential repeated evaluation and summaries of complete attempt evidence."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from statistics import median
from typing import Literal
from uuid import uuid4

from thadam._json import validate_json
from thadam.adapters.python import validate_agent
from thadam.errors import AgentConfigurationError, SuiteValidationError
from thadam.models import Agent, AgentResult, JSONValue, RunReport, TestCase
from thadam.runner import run_suite
from thadam.suites import validate_suite

AgentFactory = Callable[[], Agent]
ExecutionMode = Literal["shared", "factory"]


@dataclass(frozen=True)
class OutcomeCounts:
    """Mutually exclusive outcomes; unavailable check verdicts count as errors."""

    passed: int
    failed: int
    errors: int

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total

    @property
    def variable(self) -> bool:
        return sum(count > 0 for count in (self.passed, self.failed, self.errors)) > 1


@dataclass(frozen=True)
class RuntimeSummary:
    """Observed case execution/evaluation milliseconds, including factory creation."""

    total_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float


@dataclass(frozen=True)
class CheckReliability:
    """Observed outcomes of one declared check across every attempt."""

    id: str
    counts: OutcomeCounts


@dataclass(frozen=True)
class CaseReliability:
    """Case and check reliability, including variation hidden by case totals."""

    id: str
    counts: OutcomeCounts
    checks: tuple[CheckReliability, ...]
    runtime: RuntimeSummary

    @property
    def variable(self) -> bool:
        return self.counts.variable or any(check.counts.variable for check in self.checks)


@dataclass(frozen=True)
class RepeatedReport:
    """Full ordered suite attempts; summaries are derived rather than trusted input."""

    runs: tuple[RunReport, ...]
    execution_mode: ExecutionMode
    report_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = field(default=1, init=False)
    kind: str = field(default="repeated_run", init=False)

    @property
    def attempts(self) -> int:
        return len(self.runs)

    @property
    def agent_revision(self) -> str | None:
        return self.runs[0].agent_revision

    @property
    def cases(self) -> tuple[CaseReliability, ...]:
        by_run = [{case.id: case for case in run.cases} for run in self.runs]
        results = []
        for first in self.runs[0].cases:
            cases = [run[first.id] for run in by_run]
            outcomes = [case.status for case in cases]
            checks = []
            verdicts = [{check.id: check.passed for check in case.assertions} for case in cases]
            for definition in first.check_definitions:
                values = [verdict.get(definition.id) for verdict in verdicts]
                checks.append(
                    CheckReliability(
                        definition.id,
                        OutcomeCounts(values.count(True), values.count(False), values.count(None)),
                    )
                )
            times = [case.duration_ms for case in cases]
            total = sum(times)
            results.append(
                CaseReliability(
                    first.id,
                    OutcomeCounts(
                        outcomes.count("passed"), outcomes.count("failed"), outcomes.count("error")
                    ),
                    tuple(checks),
                    RuntimeSummary(
                        total, min(times), max(times), total / len(times), median(times)
                    ),
                )
            )
        return tuple(results)

    @property
    def has_failures(self) -> bool:
        return any(run.has_failures for run in self.runs)


def run_repeated(
    agent: Agent | None = None,
    cases: Sequence[TestCase] = (),
    *,
    attempts: int = 10,
    agent_factory: AgentFactory | None = None,
    agent_revision: str | None = None,
) -> RepeatedReport:
    """Run complete suites in order, retaining all case errors and attempt evidence.

    Supply exactly one synchronous agent or zero-argument agent_factory. Factory
    mode constructs an agent for every case invocation; external and verifier
    state are the caller's responsibility. Invalid configuration raises
    SuiteValidationError or AgentConfigurationError before execution. Construction
    and invocation exceptions become per-case agent errors; KeyboardInterrupt
    propagates. There are no retries, enforced timeouts, or implicit cleanup hooks.
    """
    if type(attempts) is not int or attempts < 2:
        raise SuiteValidationError("attempts must be an integer of at least 2")
    if (agent is None) == (agent_factory is None):
        raise AgentConfigurationError("Supply exactly one of agent or agent_factory")
    if agent_revision is not None:
        if not isinstance(agent_revision, str) or not agent_revision.strip():
            raise SuiteValidationError("agent_revision must be a non-empty string or None")
        try:
            validate_json(agent_revision, "agent_revision")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    # Snapshot before any user code runs, including factory construction. Keep
    # verifier identity just as run_suite does; never deepcopy application objects.
    prepared = tuple(
        TestCase(
            case.id, deepcopy(case.input), tuple(deepcopy(case.assertions)), tuple(case.verifiers)
        )
        for case in validate_suite(cases)
    )
    if agent_factory is not None:
        validate_factory(agent_factory)

        def invoke(value: JSONValue) -> JSONValue | AgentResult:
            fresh = agent_factory()
            if inspect.iscoroutine(fresh):
                fresh.close()
            validate_agent(fresh)
            return fresh(value)

        selected = invoke
    else:
        validate_agent(agent)
        selected = agent
    return RepeatedReport(
        runs=tuple(
            run_suite(selected, prepared, agent_revision=agent_revision) for _ in range(attempts)
        ),
        execution_mode="factory" if agent_factory is not None else "shared",
    )


def validate_factory(factory: AgentFactory) -> None:
    """Require an inspectable synchronous factory accepting no arguments."""
    target = factory if inspect.isroutine(factory) else getattr(factory, "__call__", factory)
    if (
        not callable(factory)
        or inspect.iscoroutinefunction(target)
        or inspect.isasyncgenfunction(target)
    ):
        raise AgentConfigurationError("agent_factory must be a synchronous zero-argument callable")
    try:
        inspect.signature(factory).bind()
    except (TypeError, ValueError) as error:
        raise AgentConfigurationError("agent_factory must accept no arguments") from error
