"""Sequential case execution shared by Python callers and the CLI."""

import inspect
from collections.abc import Sequence
from copy import deepcopy
from time import perf_counter
from typing import Literal

from thadam._json import validate_json
from thadam.adapters.python import validate_agent
from thadam.assertions import evaluate_assertion, evaluate_verifier
from thadam.errors import AgentExecutionError, TraceUnavailableError
from thadam.events import snapshot_trace
from thadam.models import (
    Agent,
    AgentResult,
    CaseError,
    CaseResult,
    CaseStatus,
    ExecutionEvent,
    RunReport,
    TestCase,
)
from thadam.suites import validate_suite


def run_suite(agent: Agent, cases: Sequence[TestCase]) -> RunReport:
    """Validate the whole suite, then execute each case exactly once in input order.

    Raises SuiteValidationError or AgentConfigurationError before agent execution
    for invalid configuration. Agent/output/verifier errors are recorded per case;
    KeyboardInterrupt propagates. SystemExit from tested code is a case error,
    including exit(0), so an aborted case cannot masquerade as a passing run.
    No retries or timeouts are imposed.
    """
    validated = tuple(
        TestCase(
            id=case.id,
            input=deepcopy(case.input),
            assertions=tuple(deepcopy(case.assertions)),
            verifiers=tuple(case.verifiers),
        )
        for case in validate_suite(cases)
    )
    validate_agent(agent)
    return RunReport(cases=tuple(_run_case(agent, case) for case in validated))


def _run_case(agent: Agent, case: TestCase) -> CaseResult:
    started = perf_counter()
    try:
        output = agent(deepcopy(case.input))
    except (Exception, SystemExit) as error:
        if isinstance(error, AgentExecutionError):
            try:
                events = snapshot_trace(error.events, error.trace_complete, error.trace_warnings)
            except ValueError as trace_error:
                return _execution_error(case, started, "trace", trace_error)
            return _execution_error(
                case,
                started,
                "agent",
                error.original,
                events=events,
                trace_complete=error.trace_complete,
                trace_warnings=tuple(error.trace_warnings),
            )
        return _execution_error(case, started, "agent", error)

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
    )


def _execution_error(
    case: TestCase,
    started: float,
    source: Literal["agent", "output", "trace"],
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
    )
