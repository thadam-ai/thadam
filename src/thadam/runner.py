"""Sequential execution and case-evidence helpers shared with the async runner."""

import inspect
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
from time import perf_counter
from typing import Callable, Literal

from thadam._json import validate_json
from thadam.adapters.python import validate_agent
from thadam.assertions import evaluate_assertion, evaluate_verifier
from thadam.contracts import snapshot_definitions
from thadam.errors import (
    AgentConfigurationError,
    AgentExecutionError,
    SuiteValidationError,
    TraceUnavailableError,
)
from thadam.events import snapshot_trace
from thadam.fixtures import FixtureAgent, FixtureConfigurationError, FixtureTraceError
from thadam.models import (
    Agent,
    AgentResult,
    AsyncAgent,
    CaseError,
    CaseResult,
    CaseStatus,
    CheckDefinition,
    ExecutionEvent,
    RunReport,
    SuiteIdentity,
    TestCase,
)
from thadam.suites import suite_identity, validate_suite


def run_suite(
    agent: Agent,
    cases: Sequence[TestCase],
    *,
    agent_revision: str | None = None,
    suite: SuiteIdentity | None = None,
    on_case_complete: Callable[[CaseResult], None] | None = None,
) -> RunReport:
    """Validate the whole suite, then execute each case exactly once in input order.

    Raises SuiteValidationError or AgentConfigurationError before agent execution
    for invalid configuration. Agent/output/verifier errors are recorded per case;
    KeyboardInterrupt propagates. SystemExit from tested code is a case error,
    including exit(0), so an aborted case cannot masquerade as a passing run.
    No retries or timeouts are imposed.
    agent_revision is optional explicit application metadata, not an inferred Git revision.
    suite supplies explicit identity/revision for plain case sequences; TestSuite
    carries it automatically. Conflicting identities are rejected before execution.
    on_case_complete receives an independent completed-case snapshot after each
    invocation. Callback exceptions propagate; they do not become agent errors.
    """
    identity, validated, definitions = _prepare_run(
        agent, cases, agent_revision, suite, on_case_complete
    )
    results = []
    for case, checks in zip(validated, definitions):
        result = replace(_run_case(agent, case), check_definitions=checks)
        results.append(result)
        if on_case_complete is not None:
            on_case_complete(deepcopy(result))
    return RunReport(
        cases=tuple(results),
        agent_revision=agent_revision,
        suite=identity,
    )


def _prepare_run(
    agent: Agent | AsyncAgent,
    cases: Sequence[TestCase],
    agent_revision: str | None,
    suite: SuiteIdentity | None,
    on_case_complete: Callable[[CaseResult], None] | None,
    *,
    allow_async: bool = False,
) -> tuple[SuiteIdentity | None, tuple[TestCase, ...], tuple[tuple[CheckDefinition, ...], ...]]:
    identity = suite_identity(cases, suite)
    if on_case_complete is not None and not callable(on_case_complete):
        raise SuiteValidationError("on_case_complete must be callable or None")
    if agent_revision is not None:
        if not isinstance(agent_revision, str) or not agent_revision.strip():
            raise SuiteValidationError("agent_revision must be a non-empty string or None")
        try:
            validate_json(agent_revision, "agent_revision")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
    validated = tuple(
        TestCase(
            id=case.id,
            input=deepcopy(case.input),
            assertions=tuple(deepcopy(case.assertions)),
            verifiers=tuple(case.verifiers),
            tool_fixtures=deepcopy(
                case.tool_fixtures
                if case.tool_fixtures is not None
                else {}
                if isinstance(agent, FixtureAgent)
                else None
            ),
        )
        for case in validate_suite(cases)
    )
    validate_agent(agent, allow_async=allow_async)
    if isinstance(agent, FixtureAgent):
        agent.validate(allow_async=allow_async)
    elif any(case.tool_fixtures is not None for case in validated):
        raise AgentConfigurationError(
            "Tool fixture suites require FixtureAgent or --fixture-factory"
        )
    definitions = tuple(snapshot_definitions(case) for case in validated)
    return identity, validated, definitions


def _run_case(agent: Agent, case: TestCase) -> CaseResult:
    started = perf_counter()
    try:
        output = (
            agent.invoke_case(case.tool_fixtures, deepcopy(case.input))
            if isinstance(agent, FixtureAgent)
            else agent(deepcopy(case.input))
        )
    except (Exception, SystemExit) as error:
        return _agent_error(case, started, error)
    return _finish_case(output, case, started)


def _agent_error(case: TestCase, started: float, error: Exception | SystemExit) -> CaseResult:
    if isinstance(error, AgentExecutionError):
        try:
            events = snapshot_trace(error.events, error.trace_complete, error.trace_warnings)
        except ValueError as trace_error:
            return _execution_error(case, started, "trace", trace_error)
        return _execution_error(
            case,
            started,
            "fixture"
            if isinstance(error.original, FixtureConfigurationError)
            else "trace"
            if isinstance(error.original, FixtureTraceError)
            else "agent",
            error.original,
            events=events,
            trace_complete=error.trace_complete,
            trace_warnings=tuple(error.trace_warnings),
        )
    return _execution_error(case, started, "agent", error)


def _finish_case(output: object, case: TestCase, started: float) -> CaseResult:
    events = None
    trace_complete = None
    trace_warnings = ()
    if isinstance(output, AgentResult):
        try:
            events = snapshot_trace(output.events, output.trace_complete, output.trace_warnings)
        except ValueError as error:
            return _execution_error(case, started, "trace", error)
        trace_complete, trace_warnings = output.trace_complete, tuple(output.trace_warnings)
        output = output.output

    try:
        if inspect.iscoroutine(output):
            output.close()
        validate_json(output, "agent output")
        output = deepcopy(output)
    except Exception as error:
        return _execution_error(
            case,
            started,
            "output",
            error,
            events=events,
            trace_complete=trace_complete,
            trace_warnings=trace_warnings,
        )

    assertions = []
    errors = []
    for assertion in case.assertions:
        try:
            assertions.append(
                evaluate_assertion(
                    assertion,
                    output,
                    events=events,
                    trace_complete=trace_complete,
                )
            )
        except TraceUnavailableError as error:
            errors.append(
                CaseError(
                    source="assertion",
                    type=type(error).__name__,
                    message=str(error),
                    assertion_id=assertion.id,
                )
            )
    for verifier in case.verifiers:
        try:
            assertions.append(evaluate_verifier(verifier, case.input, output))
        except (Exception, SystemExit) as error:
            errors.append(
                CaseError(
                    source="verifier",
                    type=type(error).__name__,
                    message=str(error),
                    assertion_id=verifier.id,
                )
            )
    status: CaseStatus = "passed"
    if errors:
        status = "error"
    elif any(not item.passed for item in assertions):
        status = "failed"
    return CaseResult(
        id=case.id,
        status=status,
        duration_ms=(perf_counter() - started) * 1000,
        input=deepcopy(case.input),
        output=output,
        output_available=True,
        assertions=tuple(assertions),
        errors=tuple(errors),
        events=events,
        trace_complete=trace_complete,
        trace_warnings=trace_warnings,
        tool_fixtures=deepcopy(case.tool_fixtures),
    )


def _execution_error(
    case: TestCase,
    started: float,
    source: Literal["agent", "output", "trace", "fixture"],
    error: Exception | SystemExit,
    *,
    events: tuple[ExecutionEvent, ...] | None = None,
    trace_complete: bool | None = None,
    trace_warnings: tuple[str, ...] = (),
) -> CaseResult:
    return CaseResult(
        id=case.id,
        status="error",
        duration_ms=(perf_counter() - started) * 1000,
        input=deepcopy(case.input),
        errors=(CaseError(source=source, type=type(error).__name__, message=str(error)),),
        events=events,
        trace_complete=trace_complete,
        trace_warnings=trace_warnings,
        tool_fixtures=deepcopy(case.tool_fixtures),
    )
