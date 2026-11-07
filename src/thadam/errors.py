"""Public errors for configuration, execution evidence, and report artifacts."""

from thadam.models import ConversationTurnResult, ExecutionEvent, JSONValue


class SuiteValidationError(ValueError):
    """The suite does not satisfy Thadam's case format or check contracts."""


class AgentConfigurationError(ValueError):
    """The selected agent cannot be called synchronously with one input."""


class ReportWriteError(OSError):
    """A run report could not be written to its destination."""


class ReportValidationError(ValueError):
    """A saved or SDK report is invalid or lacks comparable evaluation contracts."""


class TraceUnavailableError(ValueError):
    """A tool assertion lacks the execution evidence needed to reach a verdict."""


class ConversationOutputError(ValueError):
    """A conversation agent returned a response outside the JSON contract."""


class AgentExecutionError(Exception):
    """Preserve observed events when an instrumented agent raises an exception."""

    def __init__(
        self,
        original: Exception | SystemExit,
        *,
        events: tuple[ExecutionEvent, ...],
        trace_complete: bool,
        trace_warnings: tuple[str, ...] = (),
        conversation_results: tuple[ConversationTurnResult, ...] = (),
        state_initial: JSONValue = None,
        state_final: JSONValue = None,
    ) -> None:
        super().__init__(str(original))
        self.original = original
        self.events = events
        self.trace_complete = trace_complete
        self.trace_warnings = trace_warnings
        self.conversation_results = conversation_results
        self.state_initial = state_initial
        self.state_final = state_final
