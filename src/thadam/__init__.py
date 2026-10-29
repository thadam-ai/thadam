"""Open-source testing, evaluation, and reliability for AI agents."""

__version__ = "0.1.0"

from thadam.errors import AgentConfigurationError, ReportWriteError, SuiteValidationError
from thadam.models import (
    Agent,
    AssertionResult,
    CaseError,
    CaseResult,
    CheckResult,
    JSONValue,
    OutputEquals,
    OutputHasKeys,
    RunReport,
    RunSummary,
    TestCase,
    Verifier,
)
from thadam.reporting import report_to_dict, write_report
from thadam.runner import run_suite
from thadam.suites import load_suite

__all__ = [
    "Agent",
    "AgentConfigurationError",
    "AssertionResult",
    "CaseError",
    "CaseResult",
    "CheckResult",
    "JSONValue",
    "OutputEquals",
    "OutputHasKeys",
    "ReportWriteError",
    "RunReport",
    "RunSummary",
    "SuiteValidationError",
    "TestCase",
    "Verifier",
    "load_suite",
    "report_to_dict",
    "run_suite",
    "write_report",
]
