"""Optional LangGraph integration using public LangChain callback interfaces."""

import inspect
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from time import perf_counter
from typing import Any, Callable
from uuid import UUID, uuid4

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import BaseMessage
    from langchain_core.outputs import LLMResult
    from langchain_core.runnables import RunnableConfig
    from langchain_core.runnables.config import merge_configs
    from langgraph.graph.state import CompiledStateGraph
except ImportError as error:
    raise ImportError(
        "Install the optional integration with: pip install 'thadam[langgraph]'"
    ) from error

from thadam._json import validate_json
from thadam.errors import AgentConfigurationError, AgentExecutionError
from thadam.models import AgentResult, EventError, ExecutionEvent, JSONValue, TokenUsage


class LangGraphAgent:
    """Run a compiled StateGraph with per-invocation tracing and a fresh thread ID.

    Input/output mappers adapt JSON cases to framework state. Existing callbacks,
    tags, and configurable values are preserved. Explicit checkpoint resumption
    is unsupported; external tool state is the caller's responsibility to reset.
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        *,
        input_mapper: Callable[[JSONValue], Any] | None = None,
        output_mapper: Callable[[Any], JSONValue] | None = None,
        config: RunnableConfig | None = None,
    ) -> None:
        if not isinstance(graph, CompiledStateGraph):
            raise AgentConfigurationError("LangGraphAgent requires a compiled StateGraph")
        for mapper in (input_mapper, output_mapper):
            if mapper is None:
                continue
            target = mapper if inspect.isroutine(mapper) else getattr(mapper, "__call__", mapper)
            if (
                not callable(mapper)
                or inspect.iscoroutinefunction(target)
                or inspect.isasyncgenfunction(target)
            ):
                raise AgentConfigurationError("Graph mappers must be synchronous callables")
            try:
                inspect.signature(mapper).bind(None)
            except (TypeError, ValueError) as error:
                raise AgentConfigurationError(
                    "Graph mappers must accept one positional input"
                ) from error
        if config is not None and not isinstance(config, dict):
            raise AgentConfigurationError("Graph config must be a RunnableConfig dictionary")
        self.graph = graph
        self.input_mapper = input_mapper
        self.output_mapper = output_mapper
        self.config = dict(config or {})
        configurable = self.config.get("configurable") or {}
        if not isinstance(configurable, dict):
            raise AgentConfigurationError("Graph config.configurable must be a dictionary")
        if configurable.get("checkpoint_id") is not None:
            raise AgentConfigurationError(
                "Checkpoint resumption is unsupported; run each test fresh"
            )

    def __call__(self, value: JSONValue) -> AgentResult:
        collector = _EventCollector()
        configuration = merge_configs(
            self.config,
            {"callbacks": [collector], "configurable": {"thread_id": str(uuid4())}},
        )
        try:
            graph_input = self.input_mapper(value) if self.input_mapper else value
            _require_sync_value(graph_input)
            state = self.graph.invoke(graph_input, config=configuration)
            if isinstance(state, dict) and state.get("__interrupt__"):
                raise RuntimeError(
                    "Graph interrupted before completion; no test verdict can be produced"
                )
            output = self.output_mapper(state) if self.output_mapper else _json_value(state)
            _require_sync_value(output)
            # Output mapper errors retain the graph's events in the exception envelope.
            validate_json(output, "mapped graph output")
        except (Exception, SystemExit) as error:
            events, complete, warnings = collector.finish()
            raise AgentExecutionError(
                error,
                events=events,
                trace_complete=complete,
                trace_warnings=warnings,
            ) from error
        events, complete, warnings = collector.finish()
        return AgentResult(
            output=deepcopy(output), events=events, trace_complete=complete, trace_warnings=warnings
        )


class _EventCollector(BaseCallbackHandler):
    """Collect model/tool spans by run ID, including callbacks from parallel nodes."""

    run_inline = True
    raise_error = True

    def __init__(self) -> None:
        self._lock = RLock()
        self._started = perf_counter()
        self._events: dict[str, ExecutionEvent] = {}
        self._starts: dict[str, float] = {}
        self._warnings: list[str] = []

    def on_tool_start(
        self,
        serialized: dict | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        inputs: dict | None = None,
        **kwargs: Any,
    ) -> None:
        self._begin(
            "tool",
            serialized,
            inputs if inputs is not None else input_str,
            run_id,
            parent_run_id,
            kwargs,
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        error = None
        if isinstance(output, BaseMessage) and getattr(output, "status", None) == "error":
            error = EventError(type="ToolError", message=str(output.content))
        self._end(run_id, output=output, error=error)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id, error=EventError(type=type(error).__name__, message=str(error)))

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> None:
        self._begin("model", serialized, messages, run_id, parent_run_id, kwargs, metadata)

    def on_llm_start(
        self,
        serialized: dict,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> None:
        self._begin("model", serialized, prompts, run_id, parent_run_id, kwargs, metadata)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        outputs = [
            [getattr(generation, "message", generation.text) for generation in batch]
            for batch in response.generations
        ]
        self._end(run_id, output=outputs, usage=_token_usage(response))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id, error=EventError(type=type(error).__name__, message=str(error)))

    def _begin(
        self,
        kind: str,
        serialized: dict | None,
        value: Any,
        run_id: UUID,
        parent_id: UUID | None,
        options: dict,
        metadata: dict | None = None,
    ) -> None:
        started = perf_counter()
        name = options.get("name") or (metadata or {}).get("ls_model_name")
        if kind == "tool":
            name = (serialized or {}).get("name") or name
        else:
            name = name or (serialized or {}).get("name")
        if not name:
            identifiers = (serialized or {}).get("id", [])
            name = identifiers[-1] if isinstance(identifiers, list) and identifiers else None
        data, available = _snapshot(value)
        with self._lock:
            if str(run_id) in self._events:
                self._warnings.append(f"Duplicate start callback for {run_id}")
                return
            if not isinstance(name, str) or not name:
                self._warnings.append(f"A {kind} callback had no observable name")
                name = f"unnamed {kind}"
            self._starts[str(run_id)] = started
            self._events[str(run_id)] = ExecutionEvent(
                id=str(run_id),
                parent_id=str(parent_id) if parent_id else None,
                kind=kind,
                name=name,
                status="incomplete",
                started_at_ms=(started - self._started) * 1000,
                input=data,
                input_available=available,
            )

    def _end(
        self,
        run_id: UUID,
        *,
        output: Any = None,
        error: EventError | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        data, available = (
            _snapshot(output) if error is None or output is not None else (None, False)
        )
        with self._lock:
            event = self._events.get(str(run_id))
            if event is None or event.status != "incomplete":
                self._warnings.append(f"Unmatched end callback for {run_id}")
                return
            self._events[str(run_id)] = replace(
                event,
                status="error" if error else "completed",
                duration_ms=(perf_counter() - self._starts[str(run_id)]) * 1000,
                output=data,
                output_available=available,
                error=error,
                usage=usage,
            )

    def finish(self) -> tuple[tuple[ExecutionEvent, ...], bool, tuple[str, ...]]:
        with self._lock:
            events = tuple(sorted(self._events.values(), key=lambda event: event.started_at_ms))
            warnings = tuple(self._warnings) + tuple(
                f"No end callback observed for {event.kind} {event.name!r} [{event.id}]"
                for event in events
                if event.status == "incomplete"
            )
            return deepcopy(events), not warnings, warnings


def _json_value(value: Any) -> JSONValue:
    if isinstance(value, BaseMessage):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    validate_json(value)
    return deepcopy(value)


def _require_sync_value(value: Any) -> None:
    if inspect.isawaitable(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("Graph input/output mappers must return synchronous values")


def _snapshot(value: Any) -> tuple[JSONValue, bool]:
    try:
        data = _json_value(value)
        validate_json(data)
        return data, True
    except (TypeError, ValueError, RecursionError):
        return None, False


def _token_usage(response: LLMResult) -> TokenUsage | None:
    # Prefer aggregate provider usage. A single message's standardized metadata
    # is a safe fallback; multiple generations may duplicate or split usage.
    details = (response.llm_output or {}).get("token_usage") or (response.llm_output or {}).get(
        "usage"
    )
    if not isinstance(details, dict):
        generations = [generation for batch in response.generations for generation in batch]
        message = getattr(generations[0], "message", None) if len(generations) == 1 else None
        details = getattr(message, "usage_metadata", None)
    if not isinstance(details, dict):
        return None

    def count(primary: str, alternate: str) -> int | None:
        value = details.get(primary, details.get(alternate))
        return value if type(value) is int and value >= 0 else None

    usage = TokenUsage(
        input_tokens=count("input_tokens", "prompt_tokens"),
        output_tokens=count("output_tokens", "completion_tokens"),
        total_tokens=count("total_tokens", "total_tokens"),
    )
    return (
        usage
        if any(
            value is not None
            for value in (
                usage.input_tokens,
                usage.output_tokens,
                usage.total_tokens,
            )
        )
        else None
    )
