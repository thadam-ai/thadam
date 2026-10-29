"""Validate explicit tracing evidence before it participates in assertions or reports."""

import math
from copy import deepcopy

from thadam._json import validate_json
from thadam.models import EventError, ExecutionEvent, TokenUsage


def snapshot_trace(
    events: tuple[ExecutionEvent, ...], complete: bool, warnings: tuple[str, ...]
) -> tuple[ExecutionEvent, ...]:
    """Validate and copy adapter-owned evidence; never infer unknown data as empty."""
    if not isinstance(events, (tuple, list)) or type(complete) is not bool:
        raise ValueError("Tracing requires an event sequence and a boolean completeness flag")
    if not isinstance(warnings, (tuple, list)) or any(
        not isinstance(item, str) for item in warnings
    ):
        raise ValueError("Trace warnings must be strings")
    validate_json(list(warnings), "trace warnings")
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, ExecutionEvent):
            raise ValueError("Trace entries must be ExecutionEvent objects")
        for name in (event.id, event.name):
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Event IDs and names must be non-empty strings")
            validate_json(name)
        if event.id in seen:
            raise ValueError(f"Duplicate event ID {event.id!r}")
        seen.add(event.id)
        if event.kind not in ("tool", "model") or event.status not in (
            "completed",
            "error",
            "incomplete",
        ):
            raise ValueError("Unknown event kind or status")
        if event.parent_id is not None and not isinstance(event.parent_id, str):
            raise ValueError("Event parent_id must be a string or None")
        validate_json(event.parent_id)
        _duration(event.started_at_ms)
        if event.duration_ms is not None:
            _duration(event.duration_ms)
        elif event.status != "incomplete":
            raise ValueError("Finished events require a duration")
        if complete and event.status == "incomplete":
            raise ValueError("A complete trace cannot contain unfinished events")
        for value, available in (
            (event.input, event.input_available),
            (event.output, event.output_available),
        ):
            if type(available) is not bool or (not available and value is not None):
                raise ValueError("Unavailable event values must be None with a boolean flag")
            validate_json(value)
        if event.error is not None:
            if not isinstance(event.error, EventError):
                raise ValueError("Event errors must be EventError objects")
            if not isinstance(event.error.type, str) or not isinstance(event.error.message, str):
                raise ValueError("Event error details must be strings")
            validate_json([event.error.type, event.error.message])
        if (event.status == "error") != (event.error is not None):
            raise ValueError("Only errored events may contain an EventError")
        if event.usage is not None:
            if not isinstance(event.usage, TokenUsage) or event.kind != "model":
                raise ValueError("Token usage must belong to a model event")
            for value in (
                event.usage.input_tokens,
                event.usage.output_tokens,
                event.usage.total_tokens,
            ):
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError("Token counts must be non-negative integers or None")
                validate_json(value)
    return tuple(deepcopy(events))


def _duration(value: object) -> None:
    if (
        type(value) not in (int, float)
        or value < 0
        or (type(value) is float and not math.isfinite(value))
    ):
        raise ValueError("Event timing must be finite and non-negative")
    validate_json(value, "event timing")
