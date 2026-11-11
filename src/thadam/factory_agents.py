"""Picklable factory adapters so construction remains inside a case boundary."""

import inspect
from dataclasses import dataclass
from typing import Callable

from thadam.adapters.python import validate_agent


@dataclass(frozen=True)
class SyncFactoryAgent:
    factory: Callable

    def __call__(self, value):
        fresh = self.factory()
        if inspect.iscoroutine(fresh):
            fresh.close()
        validate_agent(fresh)
        return fresh(value)


@dataclass(frozen=True)
class AsyncFactoryAgent:
    factory: Callable

    async def __call__(self, value):
        fresh = self.factory()
        if inspect.isawaitable(fresh):
            fresh = await fresh
        validate_agent(fresh, allow_async=True)
        output = fresh(value)
        return await output if inspect.isawaitable(output) else output
