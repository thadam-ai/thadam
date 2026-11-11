"""Explicit trusted external-resource lifecycle hooks for fixture attempts."""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Callable

from thadam.errors import AgentConfigurationError


@dataclass(frozen=True)
class EnvironmentHooks:
    """Create, reset and release one external handle per fixture case attempt.

    ``setup()`` returns the trusted handle exposed as ``tools.environment``.
    Optional ``reset(handle)`` runs before factory construction; optional
    ``cleanup(handle)`` runs after execution, including reset/factory failures.
    If setup raises, no handle exists and cleanup is not called: setup must
    release its own partially allocated resources. Async runners await returned
    awaitables; synchronous runners reject async hooks before execution.
    Handles are never copied into reports or suite contracts. Hooks are trusted
    application code and must coordinate any external resources shared by cases.
    """

    setup: Callable[[], object]
    reset: Callable[[object], object] | None = None
    cleanup: Callable[[object], object] | None = None

    def validate(self, *, allow_async: bool = False) -> None:
        """Validate callable signatures without executing any hook."""
        for name, hook in (("setup", self.setup), ("reset", self.reset), ("cleanup", self.cleanup)):
            if hook is None and name != "setup":
                continue
            target = hook if inspect.isroutine(hook) else getattr(hook, "__call__", hook)
            if (
                not callable(hook)
                or inspect.isasyncgenfunction(target)
                or (inspect.iscoroutinefunction(target) and not allow_async)
            ):
                raise AgentConfigurationError(f"Environment {name} requires a compatible callable")
            try:
                inspect.signature(hook).bind(*(() if name == "setup" else (None,)))
            except (TypeError, ValueError) as error:
                raise AgentConfigurationError(f"Invalid environment {name} signature") from error


class EnvironmentLifecycleError(RuntimeError):
    """A failed external environment lifecycle hook."""


def call_hook(hook: Callable, *args: object, phase: str | None = None) -> object:
    """Call a synchronous hook and identify lifecycle stage failures."""
    try:
        result = hook(*args)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise AgentConfigurationError("Async environment hooks require an async runner")
        return result
    except (Exception, SystemExit) as error:
        if phase is None:
            raise
        raise EnvironmentLifecycleError(
            f"Environment {phase} failed: {type(error).__name__}: {error}"
        ) from error


async def call_hook_async(hook: Callable, *args: object, phase: str | None = None) -> object:
    try:
        result = hook(*args)
        return await result if inspect.isawaitable(result) else result
    except (Exception, SystemExit) as error:
        if phase is None:
            raise
        raise EnvironmentLifecycleError(
            f"Environment {phase} failed: {type(error).__name__}: {error}"
        ) from error


async def cleanup_async(hook: Callable, handle: object) -> object:
    """Drain cleanup even if cancellation arrives while it is running."""
    task = asyncio.create_task(call_hook_async(hook, handle))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


class TurnLimitExceeded(RuntimeError):
    """Execution stopped before exceeding the configured conversation turns."""
