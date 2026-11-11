"""Explicit, invocation-scoped scripted tools and fresh-agent construction.

No real tool is invoked. Factories connect handles to their own agents; only
those handles are controlled. Async tools return immediately without simulating
wall-clock delay. Fixture errors remain sticky even if application code catches
them. External lifecycle hooks are explicit; detached work remains caller-owned.
"""

import asyncio
import inspect
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from time import perf_counter
from typing import Awaitable, Callable, TypeAlias
from uuid import uuid4

from thadam._json import json_equal, validate_json
from thadam.adapters.python import validate_agent
from thadam.environment import (
    EnvironmentHooks,
    EnvironmentLifecycleError,
    call_hook,
    call_hook_async,
    cleanup_async,
)
from thadam.errors import (
    AgentConfigurationError,
    AgentExecutionError,
    ConversationOutputError,
    SuiteValidationError,
)
from thadam.events import snapshot_trace
from thadam.models import (
    Agent,
    AgentResult,
    AsyncAgent,
    ConversationTurn,
    ConversationTurnResult,
    EventError,
    ExecutionEvent,
    JSONValue,
    StateFixture,
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


class FixtureState:
    """Read or replace the JSON state owned by one fixture invocation."""

    def __init__(self, owner: "FixtureTools") -> None:
        self._owner = owner

    def read(self) -> JSONValue:
        """Return a copy of the current state."""
        return self._owner._read_state()

    def write(self, value: JSONValue) -> None:
        """Replace the state with an independent JSON snapshot."""
        self._owner._write_state(value)

    async def aread(self) -> JSONValue:
        return self.read()

    async def awrite(self, value: JSONValue) -> None:
        self.write(value)


class FixtureTools:
    """Per-invocation tool handles supplied to an explicit fresh-agent factory.

    Access tools["name"] even for an unscripted tool; invoking that handle records
    an error. There is no real-service fallback. Do not retain handles beyond the
    invocation. The runner owns creation, evidence and closure.
    """

    def __init__(
        self, scripts: dict[str, ToolScript], state_fixture: StateFixture | None = None
    ) -> None:
        validate_fixtures(scripts)
        self._scripts = deepcopy(scripts)
        self._state_fixture = deepcopy(state_fixture)
        self._state_initial = deepcopy(state_fixture.initial) if state_fixture is not None else None
        self._state = deepcopy(self._state_initial)
        self._counts: dict[str, int] = {}
        self._events: list[ExecutionEvent] = []
        self._violations: list[str] = []
        self._lock = RLock()
        self._started = perf_counter()
        self._closed = False
        self._environment = None
        self._environment_available = False
        self._lifecycle_warnings = []
        self._on_snapshot = None
        self._conversation_results = ()
        self._child_events = ()
        self._snapshot_output = None

    @property
    def environment(self) -> object:
        """Return this attempt's trusted external handle, without copying it."""
        if self._closed or not self._environment_available:
            message = "No active external environment is available"
            self._violations.append(message)
            raise FixtureConfigurationError(message)
        return self._environment

    def _snapshot(self) -> None:
        if self._on_snapshot is not None:
            initial, final = self.state_snapshot()
            self._on_snapshot(
                AgentResult(
                    deepcopy(self._snapshot_output),
                    tuple(
                        sorted(
                            tuple(self._events) + self._child_events, key=lambda e: e.started_at_ms
                        )
                    ),
                    False,
                    ("Execution in progress",) + tuple(self._lifecycle_warnings),
                    self._conversation_results,
                    initial,
                    final,
                )
            )

    @property
    def state(self) -> "FixtureState":
        """Return this attempt's state handle, recording misuse as a sticky error."""
        with self._lock:
            if self._closed:
                raise FixtureConfigurationError("State fixture used after its invocation ended")
            if self._state_fixture is None:
                message = "No state fixture is configured for this case"
                self._violations.append(message)
                raise FixtureConfigurationError(message)
        return FixtureState(self)

    def _read_state(self) -> JSONValue:
        with self._lock:
            if self._closed:
                raise FixtureConfigurationError("State fixture used after its invocation ended")
            return deepcopy(self._state)

    def _write_state(self, value: JSONValue) -> None:
        with self._lock:
            if self._closed:
                raise FixtureConfigurationError("State fixture used after its invocation ended")
            try:
                validate_json(value, "fixture state")
            except ValueError as error:
                self._violations.append(str(error))
                raise FixtureConfigurationError(str(error)) from error
            self._state = deepcopy(value)
            self._snapshot()

    def state_snapshot(self) -> tuple[JSONValue, JSONValue]:
        """Return independent initial and final state snapshots for the report."""
        return deepcopy(self._state_initial), deepcopy(self._state)

    def __getitem__(self, name: str) -> FixtureTool:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool names must be non-empty strings")
        validate_json(name, "tool name")
        return FixtureTool(self, name)

    def _invoke(self, name: str, arguments: JSONValue) -> JSONValue:
        with self._lock:
            if self._closed:
                raise FixtureConfigurationError("Fixture tool used after its invocation ended")
            self._snapshot()
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
            self._snapshot()
            if error is not None:
                raise error
            return value

    def _finish(
        self, output: object, error: Exception | SystemExit | None, offset: float
    ) -> AgentResult:
        with self._lock:
            self._closed = True
            events = tuple(self._events)
            conversation_results = (
                output.conversation_results if isinstance(output, AgentResult) else ()
            )
            if isinstance(error, AgentExecutionError):
                conversation_results = error.conversation_results
            state_initial, state_final = self.state_snapshot()
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
            warnings = tuple(warnings) + tuple(self._lifecycle_warnings)
            if self._violations:
                error = FixtureConfigurationError("; ".join(self._violations))
            if error is not None:
                raise AgentExecutionError(
                    error,
                    events=events,
                    trace_complete=complete,
                    trace_warnings=warnings,
                    conversation_results=conversation_results,
                    state_initial=state_initial,
                    state_final=state_final,
                ) from error
            return AgentResult(
                output,
                events,
                complete,
                warnings,
                conversation_results,
                state_initial,
                state_final,
            )


FixtureFactory: TypeAlias = Callable[
    [FixtureTools], Agent | AsyncAgent | Awaitable[Agent | AsyncAgent]
]


class FixtureAgent:
    """Opt into a fresh factory(tools) for every case invocation.

    Pass this wrapper to run_suite/run_repeated (or their async variants). The
    factory receives FixtureTools and returns a normal one-input agent. Async
    execution also accepts awaitable factories and agents. Factory construction
    is inside the case's timing/error boundary. No cleanup of application-owned
    resources is provided unless explicit EnvironmentHooks are supplied.
    """

    def __init__(
        self, factory: FixtureFactory, *, environment: EnvironmentHooks | None = None
    ) -> None:
        self.factory = factory
        self.environment = environment

    def __call__(self, value: JSONValue) -> AgentResult:
        raise AgentConfigurationError("Use FixtureAgent through a Thadam runner")

    def validate(self, *, allow_async: bool = False) -> None:
        validate_agent(self.factory, allow_async=allow_async)
        if self.environment is not None:
            if not isinstance(self.environment, EnvironmentHooks):
                raise AgentConfigurationError("environment must be EnvironmentHooks or None")
            self.environment.validate(allow_async=allow_async)

    def invoke_case(
        self,
        scripts: dict[str, ToolScript],
        value: JSONValue,
        *,
        state_fixture: StateFixture | None = None,
        conversation: tuple[ConversationTurn, ...] = (),
        on_snapshot: Callable[[AgentResult], None] | None = None,
        max_turns: int | None = None,
    ) -> AgentResult:
        """Execute one case with fresh tools and optional external lifecycle hooks.

        Internal snapshot observers receive partial evidence; max_turns stops
        before the next excess turn. Execution failures retain evidence through
        AgentExecutionError. Async hooks require ainvoke_case.
        """
        self.validate()
        tools = FixtureTools(scripts, state_fixture)
        tools._on_snapshot = on_snapshot
        tools._max_turns = max_turns
        output, error = None, None
        hooks = self.environment
        try:
            tools._snapshot()
            if hooks is not None:
                tools._environment = call_hook(hooks.setup, phase="setup")
                tools._environment_available = True
                tools._snapshot()
                if hooks.reset is not None:
                    call_hook(hooks.reset, tools._environment, phase="reset")
                    tools._snapshot()
            output = self._invoke_case(
                scripts, value, state_fixture=state_fixture, conversation=conversation, _tools=tools
            )
        except (Exception, SystemExit) as caught:
            error = caught
        finally:
            try:
                if isinstance(output, AgentResult):
                    tools._snapshot_output = output.output
                    tools._child_events = tuple(
                        e
                        for e in output.events
                        if e.id not in {owned.id for owned in tools._events}
                    )
                elif isinstance(error, AgentExecutionError):
                    tools._child_events = tuple(
                        e for e in error.events if e.id not in {owned.id for owned in tools._events}
                    )
                try:
                    tools._snapshot()
                except (Exception, SystemExit) as snapshot_error:
                    if error is None:
                        error = snapshot_error
                    else:
                        tools._lifecycle_warnings.append(
                            f"Evidence snapshot also failed: {type(snapshot_error).__name__}: {snapshot_error}"
                        )
                tools._closed = False
                if hooks is not None and tools._environment_available and hooks.cleanup is not None:
                    call_hook(hooks.cleanup, tools._environment)
                    tools._snapshot()
            except (Exception, SystemExit) as cleanup_error:
                if error is None:
                    error = EnvironmentLifecycleError(
                        f"Environment cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}"
                    )
                else:
                    tools._lifecycle_warnings.append(
                        f"Environment cleanup also failed: {type(cleanup_error).__name__}: {cleanup_error}"
                    )
            finally:
                try:
                    tools._snapshot()
                except (Exception, SystemExit) as snapshot_error:
                    if error is None:
                        error = snapshot_error
                    else:
                        tools._lifecycle_warnings.append(
                            f"Evidence snapshot also failed: {type(snapshot_error).__name__}: {snapshot_error}"
                        )
                tools._closed = True
        if isinstance(output, AgentResult):
            output = replace(
                output,
                events=tuple(
                    e for e in output.events if e.id not in {owned.id for owned in tools._events}
                ),
            )
        if isinstance(error, AgentExecutionError):
            error.events = tuple(
                e for e in error.events if e.id not in {owned.id for owned in tools._events}
            )
        return tools._finish(output, error, 0.0)

    async def ainvoke_case(
        self,
        scripts: dict[str, ToolScript],
        value: JSONValue,
        *,
        state_fixture: StateFixture | None = None,
        conversation: tuple[ConversationTurn, ...] = (),
        on_snapshot: Callable[[AgentResult], None] | None = None,
        max_turns: int | None = None,
    ) -> AgentResult:
        """Await a fresh case attempt and drain configured cleanup on cancellation."""
        self.validate(allow_async=True)
        tools = FixtureTools(scripts, state_fixture)
        tools._on_snapshot = on_snapshot
        tools._max_turns = max_turns
        output, error, cancelled = None, None, None
        hooks = self.environment
        try:
            tools._snapshot()
            if hooks is not None:
                tools._environment = await call_hook_async(hooks.setup, phase="setup")
                tools._environment_available = True
                tools._snapshot()
                if hooks.reset is not None:
                    await call_hook_async(hooks.reset, tools._environment, phase="reset")
                    tools._snapshot()
            output = await self._ainvoke_case(
                scripts, value, state_fixture=state_fixture, conversation=conversation, _tools=tools
            )
        except asyncio.CancelledError as caught:
            cancelled = caught
        except (Exception, SystemExit) as caught:
            error = caught
        finally:
            try:
                if isinstance(output, AgentResult):
                    tools._snapshot_output = output.output
                    tools._child_events = tuple(
                        e
                        for e in output.events
                        if e.id not in {owned.id for owned in tools._events}
                    )
                elif isinstance(error, AgentExecutionError):
                    tools._child_events = tuple(
                        e for e in error.events if e.id not in {owned.id for owned in tools._events}
                    )
                try:
                    tools._snapshot()
                except (Exception, SystemExit) as snapshot_error:
                    if error is None:
                        error = snapshot_error
                    else:
                        tools._lifecycle_warnings.append(
                            f"Evidence snapshot also failed: {type(snapshot_error).__name__}: {snapshot_error}"
                        )
                tools._closed = False
                if hooks is not None and tools._environment_available and hooks.cleanup is not None:
                    await cleanup_async(hooks.cleanup, tools._environment)
                    tools._snapshot()
            except asyncio.CancelledError as caught:
                cancelled = caught
            except (Exception, SystemExit) as cleanup_error:
                if cancelled is not None:
                    tools._lifecycle_warnings.append(
                        f"Environment cleanup failed during cancellation: {type(cleanup_error).__name__}: {cleanup_error}"
                    )
                if error is None:
                    error = EnvironmentLifecycleError(
                        f"Environment cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}"
                    )
                else:
                    tools._lifecycle_warnings.append(
                        f"Environment cleanup also failed: {type(cleanup_error).__name__}: {cleanup_error}"
                    )
            finally:
                try:
                    tools._snapshot()
                except (Exception, SystemExit) as snapshot_error:
                    if error is None:
                        error = snapshot_error
                    else:
                        tools._lifecycle_warnings.append(
                            f"Evidence snapshot also failed: {type(snapshot_error).__name__}: {snapshot_error}"
                        )
                tools._closed = True
        if cancelled is not None:
            raise cancelled
        if isinstance(output, AgentResult):
            output = replace(
                output,
                events=tuple(
                    e for e in output.events if e.id not in {owned.id for owned in tools._events}
                ),
            )
        if isinstance(error, AgentExecutionError):
            error.events = tuple(
                e for e in error.events if e.id not in {owned.id for owned in tools._events}
            )
        return tools._finish(output, error, 0.0)

    def _invoke_case(
        self,
        scripts: dict[str, ToolScript],
        value: JSONValue,
        *,
        state_fixture: StateFixture | None = None,
        conversation: tuple[ConversationTurn, ...] = (),
        _tools: FixtureTools | None = None,
    ) -> AgentResult:
        tools = _tools if _tools is not None else FixtureTools(scripts, state_fixture)
        offset = 0.0
        try:
            agent = self.factory(tools)
            if inspect.iscoroutine(agent):
                agent.close()
            validate_agent(agent)
            offset = (perf_counter() - tools._started) * 1000
            tools._agent_started = perf_counter()
            output = (
                _sync_conversation(agent, value, conversation, tools)
                if conversation
                else agent(value)
            )
        except (Exception, SystemExit) as error:
            return tools._finish(None, error, offset)
        finally:
            tools._closed = True
        return tools._finish(output, None, offset)

    async def _ainvoke_case(
        self,
        scripts: dict[str, ToolScript],
        value: JSONValue,
        *,
        state_fixture: StateFixture | None = None,
        conversation: tuple[ConversationTurn, ...] = (),
        _tools: FixtureTools | None = None,
    ) -> AgentResult:
        tools = _tools if _tools is not None else FixtureTools(scripts, state_fixture)
        offset = 0.0
        try:
            agent = self.factory(tools)
            if inspect.isawaitable(agent):
                agent = await agent
            validate_agent(agent, allow_async=True)
            offset = (perf_counter() - tools._started) * 1000
            tools._agent_started = perf_counter()
            if conversation:
                output = await _async_conversation(agent, value, conversation, tools)
            else:
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


def _conversation_input(value: JSONValue, turn: ConversationTurn, history: list) -> dict:
    return {
        "case_input": deepcopy(value),
        "turn_id": turn.id,
        "message": deepcopy(turn.message),
        "history": deepcopy(history),
    }


def _sync_conversation(agent: Agent, value: JSONValue, turns, tools: FixtureTools) -> AgentResult:
    outputs = []
    events = []
    warnings = []
    complete = True
    history = []
    for turn_index, turn in enumerate(turns):
        if getattr(tools, "_max_turns", None) is not None and turn_index >= tools._max_turns:
            from thadam.environment import TurnLimitExceeded

            raise AgentExecutionError(
                TurnLimitExceeded("Conversation turn limit exceeded"),
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            )
        turn_started = perf_counter()
        try:
            output = agent(_conversation_input(value, turn, history))
            if inspect.isawaitable(output):
                if inspect.iscoroutine(output):
                    output.close()
                raise AgentConfigurationError("Async conversation agents require run_suite_async")
            output, child, child_complete, child_warnings = _conversation_output(
                output, turn_started, tools, turn_index
            )
        except AgentExecutionError as error:
            offset = (turn_started - getattr(tools, "_agent_started", tools._started)) * 1000
            current_events = _namespace_events(error.events, turn_index, offset)
            raise AgentExecutionError(
                error.original,
                events=tuple(events) + current_events,
                trace_complete=complete and error.trace_complete,
                trace_warnings=tuple(warnings) + error.trace_warnings,
                conversation_results=tuple(outputs),
            ) from error
        except FixtureTraceError as error:
            warning = (
                f"Invalid trace evidence from conversation turn {turn.id!r} was discarded: {error}"
            )
            raise AgentExecutionError(
                error,
                events=tuple(events),
                trace_complete=False,
                trace_warnings=tuple(warnings) + (warning,),
                conversation_results=tuple(outputs),
            ) from error
        except (Exception, SystemExit) as error:
            raise AgentExecutionError(
                error,
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            ) from error
        events.extend(child)
        complete = complete and child_complete
        warnings.extend(child_warnings)
        try:
            validate_json(output, "conversation response")
            output = deepcopy(output)
        except Exception as error:
            raise AgentExecutionError(
                ConversationOutputError(str(error)),
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            ) from error
        outputs.append(ConversationTurnResult(turn.id, deepcopy(turn.message), deepcopy(output)))
        tools._child_events = tuple(events)
        tools._conversation_results = tuple(outputs)
        tools._snapshot()
        history.extend(
            (
                {"role": "user", "content": deepcopy(turn.message)},
                {"role": "assistant", "content": deepcopy(output)},
            )
        )
    return AgentResult(outputs[-1].output, tuple(events), complete, tuple(warnings), tuple(outputs))


async def _async_conversation(agent, value, turns, tools: FixtureTools) -> AgentResult:
    outputs = []
    events = []
    warnings = []
    complete = True
    history = []
    for turn_index, turn in enumerate(turns):
        if getattr(tools, "_max_turns", None) is not None and turn_index >= tools._max_turns:
            from thadam.environment import TurnLimitExceeded

            raise AgentExecutionError(
                TurnLimitExceeded("Conversation turn limit exceeded"),
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            )
        turn_started = perf_counter()
        try:
            output = agent(_conversation_input(value, turn, history))
            if inspect.isawaitable(output):
                output = await output
            output, child, child_complete, child_warnings = _conversation_output(
                output, turn_started, tools, turn_index
            )
        except AgentExecutionError as error:
            offset = (turn_started - getattr(tools, "_agent_started", tools._started)) * 1000
            current_events = _namespace_events(error.events, turn_index, offset)
            raise AgentExecutionError(
                error.original,
                events=tuple(events) + current_events,
                trace_complete=complete and error.trace_complete,
                trace_warnings=tuple(warnings) + error.trace_warnings,
                conversation_results=tuple(outputs),
            ) from error
        except FixtureTraceError as error:
            warning = (
                f"Invalid trace evidence from conversation turn {turn.id!r} was discarded: {error}"
            )
            raise AgentExecutionError(
                error,
                events=tuple(events),
                trace_complete=False,
                trace_warnings=tuple(warnings) + (warning,),
                conversation_results=tuple(outputs),
            ) from error
        except (Exception, SystemExit) as error:
            raise AgentExecutionError(
                error,
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            ) from error
        events.extend(child)
        complete = complete and child_complete
        warnings.extend(child_warnings)
        try:
            validate_json(output, "conversation response")
            output = deepcopy(output)
        except Exception as error:
            raise AgentExecutionError(
                ConversationOutputError(str(error)),
                events=tuple(events),
                trace_complete=complete,
                trace_warnings=tuple(warnings),
                conversation_results=tuple(outputs),
            ) from error
        outputs.append(ConversationTurnResult(turn.id, deepcopy(turn.message), deepcopy(output)))
        tools._child_events = tuple(events)
        tools._conversation_results = tuple(outputs)
        tools._snapshot()
        history.extend(
            (
                {"role": "user", "content": deepcopy(turn.message)},
                {"role": "assistant", "content": deepcopy(output)},
            )
        )
    return AgentResult(outputs[-1].output, tuple(events), complete, tuple(warnings), tuple(outputs))


def _conversation_output(output, turn_started: float, tools: FixtureTools, turn_index: int):
    events = ()
    complete = True
    warnings = ()
    if isinstance(output, AgentResult):
        try:
            events = snapshot_trace(output.events, output.trace_complete, output.trace_warnings)
        except ValueError as error:
            raise FixtureTraceError(str(error)) from error
        offset = (turn_started - getattr(tools, "_agent_started", tools._started)) * 1000
        events = _namespace_events(events, turn_index, offset)
        complete, warnings = output.trace_complete, output.trace_warnings
        output = output.output
    return output, events, complete, warnings


def _namespace_events(events: tuple[ExecutionEvent, ...], turn_index: int, offset: float):
    prefix = f"conversation-turn-{turn_index}:"
    return tuple(
        replace(
            event,
            id=prefix + event.id,
            parent_id=None if event.parent_id is None else prefix + event.parent_id,
            started_at_ms=event.started_at_ms + offset,
        )
        for event in events
    )
