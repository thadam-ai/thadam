"""Validate synchronous Python callables without importing a framework."""

import inspect

from thadam.errors import AgentConfigurationError
from thadam.models import Agent


def validate_agent(agent: Agent, *, allow_async: bool = False) -> None:
    """Require an inspectable callable accepting one positional input.

    Async functions and async callable objects require allow_async=True, used only
    by the explicit asynchronous execution APIs.
    """
    target = agent if inspect.isroutine(agent) else getattr(agent, "__call__", agent)
    if (
        not callable(agent)
        or (inspect.iscoroutinefunction(target) and not allow_async)
        or inspect.isasyncgenfunction(target)
    ):
        raise AgentConfigurationError("The agent must be a synchronous Python callable")
    try:
        inspect.signature(agent).bind(None)
    except (TypeError, ValueError) as error:
        raise AgentConfigurationError("The agent must accept one positional JSON input") from error
