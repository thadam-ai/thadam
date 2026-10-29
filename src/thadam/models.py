"""Typed inputs and results shared by the SDK, runner, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, TypeAlias, Union
from uuid import uuid4

JSONValue: TypeAlias = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]
Agent: TypeAlias = Callable[[JSONValue], JSONValue]
CaseStatus: TypeAlias = Literal["passed", "failed", "error"]


@dataclass(frozen=True)
class OutputEquals:
    """Require exact JSON equality; JSON numbers compare by numeric value."""

    id: str
    expected: JSONValue


@dataclass(frozen=True)
class OutputHasKeys:
    """Require the given top-level keys in an object output."""

    id: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    """A verifier's decision and the evidence that explains it."""

    passed: bool
    message: str
    expected: JSONValue = None
    actual: JSONValue = None


@dataclass(frozen=True)
class Verifier:
    """Check independent input/output snapshots and return a CheckResult.

    Exceptions and invalid return values become per-case verifier errors.
    """

    id: str
    check: Callable[[JSONValue, JSONValue], CheckResult]


@dataclass(frozen=True)
class TestCase:
    """One independent invocation with at least one assertion or verifier."""

    id: str
    input: JSONValue
    assertions: tuple[OutputEquals | OutputHasKeys, ...] = ()
    verifiers: tuple[Verifier, ...] = ()


@dataclass(frozen=True)
class AssertionResult:
    """A named check result suitable for display and JSON serialization."""

    id: str
    passed: bool
    message: str
    expected: JSONValue
    actual: JSONValue


@dataclass(frozen=True)
class CaseError:
    """An execution or evaluation error, distinct from a failed expectation."""

    source: Literal["agent", "output", "verifier"]
    type: str
    message: str
    assertion_id: str | None = None


@dataclass(frozen=True)
class CaseResult:
    """The output, check evidence, and errors for a completed case."""

    id: str
    status: CaseStatus
    duration_ms: float
    input: JSONValue
    output: JSONValue = None
    output_available: bool = False
    assertions: tuple[AssertionResult, ...] = ()
    errors: tuple[CaseError, ...] = ()


@dataclass(frozen=True)
class RunSummary:
    """Counts of the three mutually exclusive case states."""

    total: int
    passed: int
    failed: int
    errors: int


@dataclass(frozen=True)
class RunReport:
    """A versioned run result; contains no agent or verifier callables."""

    cases: tuple[CaseResult, ...]
    run_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = field(default=1, init=False)

    @property
    def summary(self) -> RunSummary:
        return RunSummary(
            total=len(self.cases),
            passed=sum(case.status == "passed" for case in self.cases),
            failed=sum(case.status == "failed" for case in self.cases),
            errors=sum(case.status == "error" for case in self.cases),
        )

    @property
    def has_failures(self) -> bool:
        return any(case.status != "passed" for case in self.cases)
