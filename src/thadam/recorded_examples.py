"""Strict, reviewable imports from recorded JSONL and CSV examples."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from copy import deepcopy

from thadam._json import validate_json
from thadam.regression import validate_regression_draft

MAPPING_FIELDS = ("source_id", "input", "actual", "expected", "context", "events", "tags")
MASKABLE_FIELDS = frozenset({"input", "actual", "expected", "context", "events", "tags"})
MASK_TOKEN = "[REDACTED]"
MAX_IMPORT_BYTES = 8 * 1024 * 1024
MAX_IMPORT_ROWS = 500
_MISSING = object()


def normalize_mapping(value: object) -> dict[str, str | None]:
    """Validate a logical-field to source-field mapping."""
    if not isinstance(value, dict) or value.keys() - set(MAPPING_FIELDS):
        raise ValueError("Field mapping must be an object with supported fields")
    if not isinstance(value.get("input"), str) or not value["input"].strip():
        raise ValueError("Map the required input field")
    mapping = {field: value.get(field) for field in MAPPING_FIELDS}
    if any(
        field is not None and (not isinstance(field, str) or not field.strip())
        for field in mapping.values()
    ):
        raise ValueError("Field mappings must be non-empty paths or null")
    return mapping


def normalize_masks(value: object, mapping: dict[str, str | None]) -> list[str]:
    """Validate logical projection paths to replace before preview and import."""
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError("Supply up to 50 field masks")
    masks: list[str] = []
    for field in value:
        if not isinstance(field, str) or not field.strip() or len(field) > 512:
            raise ValueError("Field masks must be non-empty paths up to 512 characters")
        field = field.strip()
        root = field.split(".", 1)[0]
        if root not in MASKABLE_FIELDS:
            raise ValueError(
                "Mask paths must start with input, actual, expected, context, events, or tags"
            )
        if mapping[root] is None:
            raise ValueError(f"Cannot mask {root}; no source field is mapped for it")
        if any(not part for part in field.split(".")):
            raise ValueError("Field masks cannot contain empty path segments")
        if field in masks:
            raise ValueError("Field masks must be unique")
        masks.append(field)
    for index, left in enumerate(masks):
        for right in masks[index + 1 :]:
            if _mask_paths_overlap(left, right):
                raise ValueError("Field masks must not overlap")
    return sorted(masks)


def parse_recorded_examples(
    content: bytes,
    *,
    format: str,
    path: str,
    fingerprint: str,
    mapping: object,
    mask_fields: object,
    already_imported: set[int] | None = None,
) -> dict:
    """Parse, validate, mask, and summarize a bounded examples file."""
    if format not in ("jsonl", "csv"):
        raise ValueError("Choose JSONL or CSV format")
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("Recorded examples exceed the 8 MiB import limit")
    field_map = normalize_mapping(mapping)
    masks = normalize_masks(mask_fields, field_map)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Recorded examples must use UTF-8 text") from error
    parsed = _jsonl_rows(text) if format == "jsonl" else _csv_rows(text)
    if len(parsed) > MAX_IMPORT_ROWS:
        raise ValueError(f"Import up to {MAX_IMPORT_ROWS} recorded examples at a time")
    existing = already_imported or set()
    rows = []
    seen_ids: dict[str, int] = {}
    seen_inputs: dict[str, int] = {}
    for line, record, parse_error in parsed:
        row = _project_row(line, record, parse_error, format, field_map, masks)
        if row["valid"]:
            input_digest = _digest_json(row["unmasked_input"])
            reasons, duplicate_of = [], None
            if row["source_id"] in seen_ids:
                reasons.append("source_id")
                duplicate_of = seen_ids[row["source_id"]]
            if input_digest in seen_inputs:
                reasons.append("input")
                duplicate_of = duplicate_of or seen_inputs[input_digest]
            seen_ids.setdefault(row["source_id"], line)
            seen_inputs.setdefault(input_digest, line)
            row["duplicate_of"] = duplicate_of
            row["duplicate_reasons"] = reasons
        row.pop("unmasked_input", None)
        row["already_imported"] = line in existing
        rows.append(row)
    return {
        "path": path,
        "fingerprint": fingerprint,
        "format": format,
        "mapping": field_map,
        "mask_fields": masks,
        "summary": {
            "total": len(rows),
            "valid": sum(row["valid"] for row in rows),
            "invalid": sum(not row["valid"] for row in rows),
            "duplicates": sum(bool(row["duplicate_reasons"]) for row in rows),
            "already_imported": sum(row["already_imported"] for row in rows),
        },
        "rows": rows,
    }


def recorded_example_draft(preview: dict, row: dict) -> dict:
    """Create an unreviewed regression draft with masked imported provenance."""
    source_id = row["source_id"]
    identifier = recorded_example_draft_id(
        preview["path"],
        preview["fingerprint"],
        preview["format"],
        row["line"],
        preview["mapping"],
        preview["mask_fields"],
    )
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_id).strip("-_").lower()[:48] or "example"
    assertions = []
    expected_masked = any(
        field == "expected" or field.startswith("expected.") for field in preview["mask_fields"]
    )
    if row["has_expected"] and not expected_masked:
        assertions.append(
            {
                "id": "recorded-expected-output",
                "type": "output_equals",
                "expected": row["record"]["expected"],
            }
        )
    data = {
        "schema_version": 2,
        "kind": "regression_draft",
        "id": identifier,
        "source": {
            "kind": "recorded_example",
            "path": preview["path"],
            "fingerprint": preview["fingerprint"],
            "format": preview["format"],
            "row": row["line"],
            "source_id": source_id,
            "record": row["record"],
            "mapping": preview["mapping"],
            "masked_fields": preview["mask_fields"],
            "duplicate_of": row["duplicate_of"],
            "duplicate_reasons": row["duplicate_reasons"],
        },
        "case": {
            "id": f"imported-{row['line']}-{slug}",
            "input": row["record"]["input"],
            "assertions": assertions,
        },
        "reviewed": False,
    }
    return validate_regression_draft(data)


def recorded_example_draft_id(
    path: str,
    fingerprint: str,
    format: str,
    line: int,
    mapping: dict[str, str | None],
    mask_fields: list[str],
) -> str:
    """Make a stable destination for one exact source row and import setup."""
    payload = json.dumps(
        [path, fingerprint, format, line, mapping, mask_fields],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _jsonl_rows(text: str) -> list[tuple[int, dict | None, str | None]]:
    rows = []
    for line, source in enumerate(text.splitlines(), start=1):
        if not source.strip():
            continue
        try:
            record = json.loads(
                source,
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
            validate_json(record)
            if not isinstance(record, dict):
                raise ValueError("Each JSONL row must be an object")
            rows.append((line, record, None))
        except (ValueError, RecursionError) as error:
            rows.append((line, None, str(error)))
    if not rows:
        raise ValueError("The examples file has no non-empty rows")
    return rows


def _csv_rows(text: str) -> list[tuple[int, dict | None, str | None]]:
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or any(not header or not header.strip() for header in headers):
            raise ValueError("CSV needs a header row with non-empty field names")
        if len(set(headers)) != len(headers):
            raise ValueError("CSV header names must be unique")
        rows = []
        for line, record in enumerate(reader, start=2):
            if None in record or None in record.values():
                rows.append((line, None, "CSV row has a different number of cells than its header"))
            else:
                rows.append((line, record, None))
    except csv.Error as error:
        raise ValueError(f"Invalid CSV structure: {error}") from error
    if not rows:
        raise ValueError("CSV has a header but no data rows")
    return rows


def _project_row(
    line: int,
    raw_record: dict | None,
    parse_error: str | None,
    format: str,
    mapping: dict[str, str | None],
    masks: list[str],
) -> dict:
    base = {
        "line": line,
        "source_id": f"row-{line}",
        "record": {},
        "has_expected": False,
        "expected_masked": False,
        "valid": False,
        "errors": [parse_error] if parse_error else [],
        "warnings": [],
        "duplicate_of": None,
        "duplicate_reasons": [],
    }
    if raw_record is None:
        return base
    source_value = _mapped_value(raw_record, mapping["source_id"], format)
    if source_value not in (_MISSING, None, ""):
        if isinstance(source_value, (dict, list)):
            base["errors"].append("Mapped source ID must be a string or number")
            return base
        base["source_id"] = str(source_value)
        if not base["source_id"].strip() or len(base["source_id"]) > 512:
            base["errors"].append("Mapped source ID must be non-empty and up to 512 characters")
            return base
    else:
        base["warnings"].append("No source ID was mapped; the source row number is used.")
    projection = {"source_id": base["source_id"]}
    for field in MAPPING_FIELDS[1:]:
        selector = mapping[field]
        value = _mapped_value(raw_record, selector, format)
        if selector is None or value is _MISSING:
            if field == "input":
                base["errors"].append("Mapped input is missing from this row")
            elif field == "expected" and selector is not None:
                base["warnings"].append(
                    "Mapped expected value is missing; this draft starts without an assertion."
                )
            continue
        if field == "tags":
            try:
                value = _normalize_tags(value)
            except ValueError as error:
                base["errors"].append(str(error))
                return base
        projection[field] = value
    if base["errors"]:
        return base
    try:
        validate_json(projection, "recorded example")
    except ValueError as error:
        base["errors"].append(str(error))
        return base
    base["has_expected"] = "expected" in projection
    base["expected_masked"] = any(
        field == "expected" or field.startswith("expected.") for field in masks
    )
    unmasked_input = deepcopy(projection["input"])
    masked = deepcopy(projection)
    for path in masks:
        parts = path.split(".")
        if parts[0] in masked:
            masked_value, matched = _mask_path(masked[parts[0]], parts[1:])
            if not matched:
                base["errors"].append(f"Mask path {path!r} does not match this row")
                continue
            if parts[0] == "tags":
                if not parts[1:]:
                    masked_value = [MASK_TOKEN]
                if isinstance(masked_value, list):
                    masked_value = list(dict.fromkeys(masked_value))
            masked[parts[0]] = masked_value
    if base["errors"]:
        return base
    if "expected" in masked and base["expected_masked"]:
        # Keep the preview and retained evidence redacted; do not treat redaction as an expectation.
        base["warnings"].append(
            "The expected value is masked and will not seed an output assertion."
        )
    base.update(record=masked, valid=True, unmasked_input=unmasked_input)
    return base


def _mapped_value(record: dict, selector: str | None, format: str):
    if selector is None:
        return _MISSING
    if format == "csv":
        return record.get(selector, _MISSING)
    value = record
    for part in selector.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return _MISSING
    return value


def _normalize_tags(value: object) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        raise ValueError("Mapped failure tags must be text or an array of strings")
    if any(not isinstance(tag, str) for tag in values):
        raise ValueError("Mapped failure tags must contain only text")
    return list(dict.fromkeys(tag.strip() for tag in values if tag.strip()))


def _mask_path(value, parts: list[str]):
    if value is _MISSING:
        return value, False
    if not parts:
        return MASK_TOKEN, True
    part, *rest = parts
    if isinstance(value, dict):
        if part == "*":
            found = False
            updated = {}
            for key, item in value.items():
                updated[key], matched = _mask_path(item, rest)
                found |= matched
            return updated, found
        if part in value:
            updated = deepcopy(value)
            updated[part], matched = _mask_path(value[part], rest)
            return updated, matched
    if isinstance(value, list):
        if part == "*":
            found = False
            updated = []
            for item in value:
                masked_item, matched = _mask_path(item, rest)
                updated.append(masked_item)
                found |= matched
            return updated, found
        if part.isdigit() and int(part) < len(value):
            updated = deepcopy(value)
            updated[int(part)], matched = _mask_path(value[int(part)], rest)
            return updated, matched
    return deepcopy(value), False


def _mask_paths_overlap(left: str, right: str) -> bool:
    left_parts, right_parts = left.split("."), right.split(".")
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part and "*" not in (left_part, right_part):
            return False
    return True


def _digest_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError(f"Non-finite JSON constant {value!r}")
