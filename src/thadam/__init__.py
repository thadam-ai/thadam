"""Open-source testing, evaluation, and reliability for AI agents."""

__version__ = "0.2.0"

from thadam.errors import (
    AgentConfigurationError,
    AgentExecutionError,
    ReportWriteError,
    SuiteValidationError,
)
from thadam.models import (
    Agent,
    AgentResult,
    AssertionResult,
    CaseError,
    CaseResult,
    CheckResult,
    EventError,
    ExecutionEvent,
    JSONValue,
    OutputEquals,
    OutputHasKeys,
    RunReport,
    RunSummary,
    TestCase,
    TokenUsage,
    ToolArgumentsMatch,
    ToolCalled,
    ToolNotCalled,
    Verifier,
)
from thadam.reporting import report_to_dict, write_report
from thadam.runner import run_suite
from thadam.suites import load_suite

__all__ = [
    "Agent",
    "AgentResult",
    "AgentExecutionError",
    "AgentConfigurationError",
    "AssertionResult",
    "CaseError",
    "CaseResult",
    "CheckResult",
    "EventError",
    "ExecutionEvent",
    "JSONValue",
    "OutputEquals",
    "OutputHasKeys",
    "ReportWriteError",
    "RunReport",
    "RunSummary",
    "SuiteValidationError",
    "TestCase",
    "TokenUsage",
    "ToolArgumentsMatch",
    "ToolCalled",
    "ToolNotCalled",
    "Verifier",
    "load_suite",
    "report_to_dict",
    "run_suite",
    "write_report",
]
