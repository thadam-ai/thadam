"""Open-source testing, evaluation, and reliability for AI agents."""

__version__ = "0.3.0"

from thadam.comparison import (
    CaseComparison,
    CheckComparison,
    ComparisonReport,
    ComparisonSummary,
    compare_reports,
)
from thadam.comparison_reporting import comparison_to_dict, write_comparison
from thadam.errors import (
    AgentConfigurationError,
    AgentExecutionError,
    ReportValidationError,
    ReportWriteError,
    SuiteValidationError,
)
from thadam.models import (
    Agent,
    AgentResult,
    AssertionResult,
    CaseError,
    CaseResult,
    CheckDefinition,
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
from thadam.report_loading import load_report
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
    "CaseComparison",
    "CaseResult",
    "CheckResult",
    "CheckComparison",
    "CheckDefinition",
    "ComparisonReport",
    "ComparisonSummary",
    "EventError",
    "ExecutionEvent",
    "JSONValue",
    "OutputEquals",
    "OutputHasKeys",
    "ReportWriteError",
    "ReportValidationError",
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
    "load_report",
    "compare_reports",
    "comparison_to_dict",
    "report_to_dict",
    "run_suite",
    "write_report",
    "write_comparison",
]
