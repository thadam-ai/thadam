"""Shared JSON boundary rules; no execution or file access."""

import math


def validate_json(value: object, location: str = "value") -> None:
    """Reject non-JSON types, non-finite numbers, cycles, and excessive nesting.

    Container nesting is limited to 100 levels so copying and serializing a
    validated value remain within ordinary Python recursion limits.
    """
    _validate(value, location, set(), 0)


def _validate(value: object, location: str, ancestors: set[int], depth: int) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise ValueError(f"{location}: strings must contain valid Unicode") from error
        return
    if type(value) is int:
        try:
            str(value)
        except ValueError as error:
            raise ValueError(
                f"{location}: integer exceeds Python's JSON serialization limit"
            ) from error
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{location}: numbers must be finite")
        return
    if type(value) not in (list, dict):
        raise ValueError(f"{location}: {type(value).__name__} is not a JSON type")
    if depth >= 100:
        raise ValueError(f"{location}: JSON container nesting exceeds 100 levels")
    if id(value) in ancestors:
        raise ValueError(f"{location}: cyclic JSON containers are not supported")
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError(f"{location}: object keys must be strings")
                _validate(key, f"{location} object key", ancestors, depth + 1)
                _validate(item, f"{location}.{key}", ancestors, depth + 1)
        else:
            for index, item in enumerate(value):
                _validate(item, f"{location}[{index}]", ancestors, depth + 1)
    finally:
        ancestors.remove(id(value))
