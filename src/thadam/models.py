"""Typed inputs and results shared by the SDK, runner, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, TypeAlias, Union
from uuid import uuid4

JSONValue: TypeAlias = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]
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
class ToolCalled:
    """Require at least one observed invocation of the named tool, including errors."""

    id: str
    tool: str


@dataclass(frozen=True)
class ToolNotCalled:
    """Forbid any observed attempt to invoke the named tool."""

    id: str
    tool: str


@dataclass(frozen=True)
class ToolArgumentsMatch:
    """Require every invocation of a tool to match selected top-level arguments."""

    id: str
    tool: str
    expected: dict[str, JSONValue]


@dataclass(frozen=True)
class ToolCallCount:
    """Bound total observed tool attempts, including attempts that raise."""

    id: str
    tool: str
    min_calls: int = 0
    max_calls: int | None = None


@dataclass(frozen=True)
class ToolCallSequence:
    """Require every observed tool call to follow this exact start order."""

    id: str
    tools: tuple[str, ...]


@dataclass(frozen=True)
class ConversationOutputEquals:
    """Require an exact response for one named conversation turn."""

    id: str
    turn_id: str
    expected: JSONValue


@dataclass(frozen=True)
class StateEquals:
    """Require the final observable fixture state to equal a JSON value."""

    id: str
    expected: JSONValue


@dataclass(frozen=True)
class StateChanges:
    """Require every changed top-level state key to be explicitly allowed."""

    id: str
    allowed_keys: tuple[str, ...]


@dataclass(frozen=True)
class ToolReturn:
    """Return an independent JSON value from a scripted tool invocation."""

    value: JSONValue


@dataclass(frozen=True)
class ToolRaise:
    """Raise a built-in TimeoutError, ConnectionError, or RuntimeError."""

    error: Literal["TimeoutError", "ConnectionError", "RuntimeError"]
    message: str


@dataclass(frozen=True)
class ToolScript:
    """Ordered fixture responses; exhaustion errors unless repeat_last is explicit."""

    steps: tuple[ToolReturn | ToolRaise, ...]
    repeat_last: bool = False


Assertion: TypeAlias = (
    OutputEquals
    | OutputHasKeys
    | ToolCalled
    | ToolNotCalled
    | ToolArgumentsMatch
    | ToolCallCount
    | ToolCallSequence
    | ConversationOutputEquals
    | StateEquals
    | StateChanges
)


@dataclass(frozen=True)
class TokenUsage:
    """Provider-reported counts. None means unavailable; zero is a reported value."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class EventError:
    """An error observed inside a tool or model call."""

    type: str
    message: str


@dataclass(frozen=True)
class ExecutionEvent:
    """An observed tool/model span, in start order, correlated by framework run IDs."""

    id: str
    kind: Literal["tool", "model"]
    name: str
    status: Literal["completed", "error", "incomplete"]
    started_at_ms: float
    parent_id: str | None = None
    duration_ms: float | None = None
    input: JSONValue = None
    input_available: bool = False
    output: JSONValue = None
    output_available: bool = False
    error: EventError | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class AgentResult:
    """An explicitly instrumented result; plain Python results have unknown tracing."""

    output: JSONValue
    events: tuple[ExecutionEvent, ...] = ()
    trace_complete: bool = True
    trace_warnings: tuple[str, ...] = ()
    conversation_results: tuple["ConversationTurnResult", ...] = ()
    state_initial: JSONValue = None
    state_final: JSONValue = None


@dataclass(frozen=True)
class ConversationTurn:
    """One scripted user message in a sequential conversation case."""

    id: str
    message: JSONValue


@dataclass(frozen=True)
class StateFixture:
    """Initial JSON state for one isolated case attempt."""

    initial: JSONValue


@dataclass(frozen=True)
class ConversationTurnResult:
    """A user message and the corresponding available agent response."""

    id: str
    message: JSONValue
    output: JSONValue
    output_available: bool = True


Agent: TypeAlias = Callable[[JSONValue], JSONValue | AgentResult]
AsyncAgent: TypeAlias = Callable[[JSONValue], Awaitable[JSONValue | AgentResult]]


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
    Comparison requires a non-empty revision; change it when evaluation criteria change.
    """

    id: str
    check: Callable[[JSONValue, JSONValue], CheckResult]
    revision: str | None = None


@dataclass(frozen=True)
class CheckDefinition:
    """Declared evaluation contract, independent of a particular check outcome."""

    id: str
    type: str
    parameters: dict[str, JSONValue]


@dataclass(frozen=True)
class TestCase:
    """One independent invocation with at least one assertion or verifier."""

    id: str
    input: JSONValue
    assertions: tuple[Assertion, ...] = ()
    verifiers: tuple[Verifier, ...] = ()
    tool_fixtures: dict[str, ToolScript] | None = None
    conversation: tuple[ConversationTurn, ...] = ()
    state_fixture: StateFixture | None = None


@dataclass(frozen=True)
class SuiteIdentity:
    """Explicit suite identity/revision; labels never replace contract validation."""

    id: str
    revision: str


@dataclass(frozen=True)
class AssertionResult:
    """A named check result suitable for display and JSON serialization."""

    id: str
    passed: bool
    message: str
    expected: JSONValue
    actual: JSONValue
    event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseError:
    """An execution or evaluation error, distinct from a failed expectation."""

    source: Literal["agent", "output", "verifier", "assertion", "trace", "fixture"]
    type: str
    message: str
    assertion_id: str | None = None


@dataclass(frozen=True)
class ExecutionLimits:
    """Opt-in per-case turn/deadline policy; deadlines use fresh spawned processes.

    timeout_seconds includes startup, hooks, agent and verifiers. After expiry,
    cleanup_timeout_seconds allows cooperative cleanup before forced termination.
    max_turns stops a scripted conversation before invoking the next excess turn.
    """

    max_turns: int | None = None
    timeout_seconds: float | None = None
    cleanup_timeout_seconds: float = 1.0


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
    events: tuple[ExecutionEvent, ...] | None = None
    trace_complete: bool | None = None
    trace_warnings: tuple[str, ...] = ()
    check_definitions: tuple[CheckDefinition, ...] = ()
    tool_fixtures: dict[str, ToolScript] | None = None
    conversation: tuple[ConversationTurn, ...] = ()
    conversation_results: tuple[ConversationTurnResult, ...] = ()
    state_fixture: StateFixture | None = None
    state_initial: JSONValue = None
    state_final: JSONValue = None
    execution_limits: ExecutionLimits | None = None


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
    agent_revision: str | None = None
    evaluation_version: int = 1
    suite: SuiteIdentity | None = None
    schema_version: int = field(default=3, init=False)

    def __post_init__(self) -> None:
        if any(case.execution_limits is not None for case in self.cases):
            object.__setattr__(self, "schema_version", 7)
        elif any(case.conversation or case.state_fixture is not None for case in self.cases):
            object.__setattr__(self, "schema_version", 6)
        elif any(case.tool_fixtures is not None for case in self.cases):
            object.__setattr__(self, "schema_version", 5)
        elif self.suite is not None:
            object.__setattr__(self, "schema_version", 4)

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
