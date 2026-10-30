"""Shared JSON boundary rules; no execution or file access."""

import json
import math
from pathlib import Path

from thadam.models import JSONValue


def read_json(path: str | Path, *, max_depth: int = 100) -> JSONValue:
    """Read strict JSON, rejecting duplicate keys, invalid numbers, and Unicode.

    Raises OSError for file failures and ValueError for invalid JSON data.
    """
    data = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    validate_json(data, max_depth=max_depth)
    return data


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant {value!r}")


def json_equal(expected: JSONValue, actual: JSONValue) -> bool:
    """Compare JSON structurally, equating numbers but distinguishing booleans."""
    if type(expected) in (int, float) and type(actual) in (int, float):
        return expected == actual
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(
            json_equal(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            json_equal(left, right) for left, right in zip(expected, actual)
        )
    return expected == actual


def validate_json(value: object, location: str = "value", *, max_depth: int = 100) -> None:
    """Reject non-JSON types, non-finite numbers, cycles, and excessive nesting.

    Container nesting defaults to 100 levels. Report envelopes reserve a small
    additional wrapper budget and validate their payloads separately at 100.
    Copying and serialization remain within ordinary Python recursion limits.
    """
    _validate(value, location, set(), 0, max_depth)


def _validate(
    value: object, location: str, ancestors: set[int], depth: int, max_depth: int
) -> None:
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
    if depth >= max_depth:
        raise ValueError(f"{location}: JSON container nesting exceeds {max_depth} levels")
    if id(value) in ancestors:
        raise ValueError(f"{location}: cyclic JSON containers are not supported")
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError(f"{location}: object keys must be strings")
                _validate(key, f"{location} object key", ancestors, depth + 1, max_depth)
                _validate(item, f"{location}.{key}", ancestors, depth + 1, max_depth)
        else:
            for index, item in enumerate(value):
                _validate(item, f"{location}[{index}]", ancestors, depth + 1, max_depth)
    finally:
        ancestors.remove(id(value))
