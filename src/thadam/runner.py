"""Sequential case execution shared by Python callers and the CLI."""

import inspect
from collections.abc import Sequence
from copy import deepcopy
from time import perf_counter
from typing import Literal

from thadam._json import validate_json
from thadam.adapters.python import validate_agent
from thadam.assertions import evaluate_assertion, evaluate_verifier
from thadam.models import Agent, CaseError, CaseResult, CaseStatus, RunReport, TestCase
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
        return _execution_error(case, started, "agent", error)

    try:
        if inspect.iscoroutine(output):
            output.close()
        validate_json(output, "agent output")
        output = deepcopy(output)
    except Exception as error:
        return _execution_error(case, started, "output", error)

    assertions = [evaluate_assertion(assertion, output) for assertion in case.assertions]
    errors = []
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
    )


def _execution_error(
    case: TestCase,
    started: float,
    source: Literal["agent", "output"],
    error: Exception | SystemExit,
) -> CaseResult:
    return CaseResult(
        id=case.id,
        status="error",
        duration_ms=(perf_counter() - started) * 1000,
        input=deepcopy(case.input),
        errors=(CaseError(source=source, type=type(error).__name__, message=str(error)),),
    )
