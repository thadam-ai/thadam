"""Explicit, invocation-scoped scripted tools and fresh-agent construction.

No real tool is invoked. Factories connect handles to their own agents; only
those handles are controlled. Async tools return immediately without simulating
wall-clock delay. Fixture errors remain sticky even if application code catches
them. External resources and detached application work remain caller-owned.
"""

import inspect
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from time import perf_counter
from typing import Awaitable, Callable, TypeAlias
from uuid import uuid4

from thadam._json import json_equal, validate_json
from thadam.adapters.python import validate_agent
from thadam.errors import AgentConfigurationError, AgentExecutionError, SuiteValidationError
from thadam.events import snapshot_trace
from thadam.models import (
    Agent,
    AgentResult,
    AsyncAgent,
    EventError,
    ExecutionEvent,
    JSONValue,
    ToolRaise,
    ToolReturn,
    ToolScript,
)

ERROR_TYPES = {
    "TimeoutError": TimeoutError,
    "ConnectionError": ConnectionError,
    "RuntimeError": RuntimeError,
}


class FixtureConfigurationError(ValueError):
    """An unplanned fixture call; catching it cannot turn the case into a pass."""


class FixtureTraceError(ValueError):
    """An invalid child trace; valid fixture evidence is retained independently."""


def validate_fixtures(fixtures: dict[str, ToolScript] | None) -> None:
    """Validate SDK scripts before any factory or agent runs."""
    if fixtures is None:
        return
    if not isinstance(fixtures, dict):
        raise SuiteValidationError("tool_fixtures must be an object or None")
    for name, script in fixtures.items():
        if not isinstance(name, str) or not name.strip():
            raise SuiteValidationError("Fixture tool names must be non-empty strings")
        try:
            validate_json(name, "fixture name")
        except ValueError as error:
            raise SuiteValidationError(str(error)) from error
        if not isinstance(script, ToolScript) or type(script.repeat_last) is not bool:
            raise SuiteValidationError("Fixtures require ToolScript with boolean repeat_last")
        if not isinstance(script.steps, (tuple, list)) or not script.steps:
            raise SuiteValidationError("A tool script needs at least one step")
        for step in script.steps:
            if isinstance(step, ToolReturn):
                try:
                    validate_json(step.value, "tool return value")
                except ValueError as error:
                    raise SuiteValidationError(str(error)) from error
            elif isinstance(step, ToolRaise):
                if not isinstance(step.error, str) or step.error not in ERROR_TYPES:
                    raise SuiteValidationError("Unsupported simulated error type")
                if not isinstance(step.message, str):
                    raise SuiteValidationError("Simulated error message must be a string")
                try:
                    validate_json(step.message, "simulated error message")
                except ValueError as error:
                    raise SuiteValidationError(str(error)) from error
            else:
                raise SuiteValidationError("Tool script steps must be ToolReturn or ToolRaise")


def fixtures_to_dict(fixtures: dict[str, ToolScript]) -> dict:
    """Serialize declarations, including unused responses and explicit repetition."""
    return {
        name: {
            "steps": [
                {"type": "return", "value": deepcopy(step.value)}
                if isinstance(step, ToolReturn)
                else {"type": "raise", "error": step.error, "message": step.message}
                for step in script.steps
            ],
            "repeat_last": script.repeat_last,
        }
        for name, script in fixtures.items()
    }


def parse_fixtures(raw: object) -> dict[str, ToolScript]:
    """Strictly parse saved scripts without imports or application execution."""
    if not isinstance(raw, dict):
        raise SuiteValidationError("tool_fixtures must be an object")
    scripts = {}
    for name, data in raw.items():
        if not isinstance(data, dict) or data.keys() != {"steps", "repeat_last"}:
            raise SuiteValidationError("Tool scripts require exactly steps and repeat_last")
        if not isinstance(data["steps"], list):
            raise SuiteValidationError("Tool script steps must be an array")
        steps = []
        for step in data["steps"]:
            if (
                isinstance(step, dict)
                and step.get("type") == "return"
                and step.keys() == {"type", "value"}
            ):
                steps.append(ToolReturn(deepcopy(step["value"])))
            elif (
                isinstance(step, dict)
                and step.get("type") == "raise"
                and step.keys() == {"type", "error", "message"}
            ):
                steps.append(ToolRaise(step["error"], step["message"]))
            else:
                raise SuiteValidationError("Unknown tool step or missing/unknown step fields")
        scripts[name] = ToolScript(tuple(steps), data["repeat_last"])
    validate_fixtures(scripts)
    return scripts


class FixtureTool:
    """A named controlled tool. invoke/ainvoke accept one JSON argument value."""

    def __init__(self, owner: "FixtureTools", name: str) -> None:
        self._owner, self.name = owner, name

    def __call__(self, arguments: JSONValue = None) -> JSONValue:
        return self.invoke(arguments)

    def invoke(self, arguments: JSONValue = None) -> JSONValue:
        """Consume one scripted step; return a copy or raise the configured error."""
        return self._owner._invoke(self.name, arguments)

    async def ainvoke(self, arguments: JSONValue = None) -> JSONValue:
        """Consume a step without blocking or adding a real-time delay."""
        return self.invoke(arguments)


class FixtureTools:
    """Per-invocation tool handles supplied to an explicit fresh-agent factory.

    Access tools["name"] even for an unscripted tool; invoking that handle records
    an error. There is no real-service fallback. Do not retain handles beyond the
    invocation. The runner owns creation, evidence and closure.
    """

    def __init__(self, scripts: dict[str, ToolScript]) -> None:
        validate_fixtures(scripts)
        self._scripts = deepcopy(scripts)
        self._counts: dict[str, int] = {}
        self._events: list[ExecutionEvent] = []
        self._violations: list[str] = []
        self._lock = RLock()
        self._started = perf_counter()
        self._closed = False

    def __getitem__(self, name: str) -> FixtureTool:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool names must be non-empty strings")
        validate_json(name, "tool name")
        return FixtureTool(self, name)

    def _invoke(self, name: str, arguments: JSONValue) -> JSONValue:
        with self._lock:
            if self._closed:
                raise FixtureConfigurationError("Fixture tool used after its invocation ended")
            started = perf_counter()
            available = False
            value = None
            error = None
            try:
                validate_json(arguments, "tool arguments")
                arguments = deepcopy(arguments)
                available = True
                index = self._counts.get(name, 0)
                script = self._scripts.get(name)
                if script is None:
                    raise FixtureConfigurationError(f"No script configured for tool {name!r}")
                if index >= len(script.steps) and not script.repeat_last:
                    raise FixtureConfigurationError(f"Script exhausted for tool {name!r}")
                self._counts[name] = index + 1
                step = script.steps[min(index, len(script.steps) - 1)]
                if isinstance(step, ToolRaise):
                    raise ERROR_TYPES[step.error](step.message)
                value = deepcopy(step.value)
            except Exception as caught:
                error = caught
                if not available:
                    error = FixtureConfigurationError(
                        f"Invalid arguments for tool {name!r}: {caught}"
                    )
                if isinstance(error, FixtureConfigurationError):
                    self._violations.append(str(error))
            self._events.append(
                ExecutionEvent(
                    id="fixture:" + uuid4().hex,
                    kind="tool",
                    name=name,
                    status="error" if error else "completed",
                    started_at_ms=(started - self._started) * 1000,
                    duration_ms=(perf_counter() - started) * 1000,
                    input=arguments if available else None,
                    input_available=available,
                    output=deepcopy(value),
                    output_available=error is None,
                    error=None if error is None else EventError(type(error).__name__, str(error)),
                )
            )
            if error is not None:
                raise error
            return value

    def _finish(
        self, output: object, error: Exception | SystemExit | None, offset: float
    ) -> AgentResult:
        with self._lock:
            self._closed = True
            events = tuple(self._events)
            complete, warnings = True, ()
            if isinstance(output, AgentResult) or isinstance(error, AgentExecutionError):
                source = output if isinstance(output, AgentResult) else error
                try:
                    child = snapshot_trace(
                        source.events, source.trace_complete, source.trace_warnings
                    )
                    events += tuple(
                        replace(event, started_at_ms=event.started_at_ms + offset)
                        for event in child
                    )
                    complete, warnings = source.trace_complete, tuple(source.trace_warnings)
                    if isinstance(output, AgentResult):
                        output = output.output
                    else:
                        error = error.original
                except ValueError as invalid:
                    error = FixtureTraceError(str(invalid))
                    complete, warnings = (
                        False,
                        ("Invalid child trace; only fixture evidence retained",),
                    )
            events = tuple(sorted(events, key=lambda event: event.started_at_ms))
            try:
                events = snapshot_trace(events, complete, warnings)
            except ValueError as invalid:
                events = tuple(self._events)
                complete, warnings = False, ("Invalid child trace; only fixture evidence retained",)
                error = FixtureTraceError(str(invalid))
            if self._violations:
                error = FixtureConfigurationError("; ".join(self._violations))
            if error is not None:
                raise AgentExecutionError(
                    error, events=events, trace_complete=complete, trace_warnings=warnings
                ) from error
            return AgentResult(output, events, complete, warnings)


FixtureFactory: TypeAlias = Callable[
    [FixtureTools], Agent | AsyncAgent | Awaitable[Agent | AsyncAgent]
]


class FixtureAgent:
    """Opt into a fresh factory(tools) for every case invocation.

    Pass this wrapper to run_suite/run_repeated (or their async variants). The
    factory receives FixtureTools and returns a normal one-input agent. Async
    execution also accepts awaitable factories and agents. Factory construction
    is inside the case's timing/error boundary. No cleanup of application-owned
    resources or automatic retry/timeout is provided.
    """

    def __init__(self, factory: FixtureFactory) -> None:
        self.factory = factory

    def __call__(self, value: JSONValue) -> AgentResult:
        raise AgentConfigurationError("Use FixtureAgent through a Thadam runner")

    def validate(self, *, allow_async: bool = False) -> None:
        validate_agent(self.factory, allow_async=allow_async)

    def invoke_case(self, scripts: dict[str, ToolScript], value: JSONValue) -> AgentResult:
        tools = FixtureTools(scripts)
        offset = 0.0
        try:
            agent = self.factory(tools)
            if inspect.iscoroutine(agent):
                agent.close()
            validate_agent(agent)
            offset = (perf_counter() - tools._started) * 1000
            output = agent(value)
        except (Exception, SystemExit) as error:
            return tools._finish(None, error, offset)
        finally:
            tools._closed = True
        return tools._finish(output, None, offset)

    async def ainvoke_case(self, scripts: dict[str, ToolScript], value: JSONValue) -> AgentResult:
        tools = FixtureTools(scripts)
        offset = 0.0
        try:
            agent = self.factory(tools)
            if inspect.isawaitable(agent):
                agent = await agent
            validate_agent(agent, allow_async=True)
            offset = (perf_counter() - tools._started) * 1000
            output = agent(value)
            if inspect.isawaitable(output):
                output = await output
        except (Exception, SystemExit) as error:
            return tools._finish(None, error, offset)
        finally:
            tools._closed = True
        return tools._finish(output, None, offset)


def validate_fixture_evidence(
    scripts: dict[str, ToolScript], events: tuple[ExecutionEvent, ...] | None, fixture_error: bool
) -> None:
    """Check observed fixture steps against saved declarations without running code."""
    if events is None:
        # Factory errors before the first handle call can still retain an empty trace.
        raise ValueError("Fixture evaluations require explicit trace evidence")
    counts: dict[str, int] = {}
    violation = False
    for event in events:
        if not event.id.startswith("fixture:"):
            continue
        if event.kind != "tool":
            raise ValueError("Fixture events must be tool events")
        script = scripts.get(event.name)
        index = counts.get(event.name, 0)
        if event.error is not None and event.error.type == "FixtureConfigurationError":
            if (
                event.status != "error"
                or event.input_available
                and script is not None
                and (index < len(script.steps) or script.repeat_last)
            ):
                raise ValueError("Invalid fixture error event")
            violation = True
            continue
        if script is None or index >= len(script.steps) and not script.repeat_last:
            raise ValueError("Unplanned fixture call lacks an evaluation error")
        counts[event.name] = index + 1
        step = script.steps[min(index, len(script.steps) - 1)]
        if not event.input_available or event.output_available and isinstance(step, ToolRaise):
            raise ValueError("Fixture event has inconsistent value availability")
        if isinstance(step, ToolReturn):
            if (
                event.status != "completed"
                or not event.output_available
                or not json_equal(event.output, step.value)
            ):
                raise ValueError("Fixture output contradicts its scripted response")
        elif event.status != "error" or event.error != EventError(step.error, step.message):
            raise ValueError("Fixture error contradicts its scripted response")
    if violation and not fixture_error:
        raise ValueError("Fixture violations and case errors disagree")
