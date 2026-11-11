"""Validation for explicit execution limits, independent of application code."""

import math
from dataclasses import asdict

from thadam.errors import SuiteValidationError
from thadam.models import ExecutionLimits


def validate_limits(limits: ExecutionLimits | None) -> None:
    """Reject invalid policy before executing agents, factories or hooks."""
    if limits is None:
        return
    if not isinstance(limits, ExecutionLimits):
        raise SuiteValidationError("limits must be ExecutionLimits or None")
    if limits.max_turns is not None and (type(limits.max_turns) is not int or limits.max_turns < 1):
        raise SuiteValidationError("max_turns must be a positive integer or None")
    for name, value in (
        ("timeout_seconds", limits.timeout_seconds),
        ("cleanup_timeout_seconds", limits.cleanup_timeout_seconds),
    ):
        if name == "timeout_seconds" and value is None:
            continue
        if (
            type(value) not in (float, int)
            or not math.isfinite(value)
            or (value <= 0 if name == "timeout_seconds" else value < 0)
        ):
            raise SuiteValidationError(
                f"{name} must be finite and "
                + ("positive" if name == "timeout_seconds" else "non-negative")
            )
    if limits.max_turns is None and limits.timeout_seconds is None:
        raise SuiteValidationError("limits must specify max_turns or timeout_seconds")


def limits_from_dict(raw: object) -> ExecutionLimits | None:
    """Parse the strict JSON policy used in reports and dashboard requests."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.keys() != {
        "max_turns",
        "timeout_seconds",
        "cleanup_timeout_seconds",
    }:
        raise SuiteValidationError("execution_limits has missing or unknown fields")
    limits = ExecutionLimits(**raw)
    validate_limits(limits)
    return limits


def limits_to_dict(limits: ExecutionLimits | None) -> dict | None:
    """Snapshot the policy for compatibility and baseline review."""
    return None if limits is None else asdict(limits)
