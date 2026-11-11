"""Reviewable regression drafts made from saved-run or recorded-example evidence."""

from copy import deepcopy
from uuid import uuid4

from thadam._json import validate_json
from thadam.report_loading import report_from_dict
from thadam.suites import suite_from_dict


def validate_regression_draft(value: dict) -> dict:
    """Validate and snapshot a draft without running application code.

    Unreviewed drafts may have no assertions. Reviewed drafts must be runnable
    cases. Source evidence is a snapshot, not proof of origin or authenticity.
    """
    data = deepcopy(value)
    validate_json(data)
    if not isinstance(data, dict) or data.keys() != {
        "schema_version",
        "kind",
        "id",
        "source",
        "case",
        "reviewed",
    }:
        raise ValueError("Invalid regression draft fields")
    if type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2):
        raise ValueError("Unsupported regression draft schema")
    if data["kind"] != "regression_draft" or not isinstance(data["id"], str) or not data["id"]:
        raise ValueError("Invalid regression draft identity")
    source = data["source"]
    if not isinstance(source, dict):
        raise ValueError("Invalid regression source")
    source_fields = (
        {"path", "fingerprint", "case_id", "attempt", "run"}
        if data["schema_version"] == 1
        else {
            "kind",
            "path",
            "fingerprint",
            "format",
            "row",
            "source_id",
            "record",
            "mapping",
            "masked_fields",
            "duplicate_of",
            "duplicate_reasons",
        }
    )
    if source.keys() != source_fields:
        raise ValueError("Invalid regression source")
    if not isinstance(source["path"], str) or not source["path"]:
        raise ValueError("Record the source artifact path")
    digest = source["fingerprint"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Record the source artifact fingerprint")
    if data["schema_version"] == 1:
        if source.keys() != {"path", "fingerprint", "case_id", "attempt", "run"}:
            raise ValueError("Invalid regression source")
        attempt = source["attempt"]
        if attempt is not None and (type(attempt) is not int or attempt < 1):
            raise ValueError("Attempt must be a positive integer or null")
        report = report_from_dict(source["run"])
        if not isinstance(source["case_id"], str) or source["case_id"] not in {
            case.id for case in report.cases
        }:
            raise ValueError("Source case is absent from the recorded run")
    else:
        _validate_import_source(source)
    case = data["case"]
    allowed_case_fields = {
        "id",
        "input",
        "assertions",
        "tool_fixtures",
        "conversation",
        "state_fixture",
    }
    if (
        not isinstance(case, dict)
        or not {"id", "input", "assertions"} <= case.keys()
        or case.keys() - allowed_case_fields
    ):
        raise ValueError("A draft case needs id, input, assertions, and supported setup fields")
    has_simulation_fields = bool({"conversation", "state_fixture"} & case.keys())
    if (
        has_simulation_fields
        and not {
            "tool_fixtures",
            "conversation",
            "state_fixture",
        }
        <= case.keys()
    ):
        raise ValueError(
            "Simulation draft cases need tool_fixtures, conversation, and state_fixture"
        )
    if (
        not isinstance(case["id"], str)
        or not case["id"].strip()
        or not isinstance(case["assertions"], list)
    ):
        raise ValueError("Supply a case ID and an assertions array")
    if type(data["reviewed"]) is not bool:
        raise ValueError("Review status must be boolean")
    if case["assertions"] or data["reviewed"]:
        schema_version = 4 if has_simulation_fields else 3 if "tool_fixtures" in case else 1
        suite = {"schema_version": schema_version, "cases": [case]}
        if schema_version >= 2:
            suite["suite"] = {"id": "regression-draft", "revision": "draft"}
        suite_from_dict(suite)
    return data


def _validate_import_source(source: dict) -> None:
    if source.keys() != {
        "kind",
        "path",
        "fingerprint",
        "format",
        "row",
        "source_id",
        "record",
        "mapping",
        "masked_fields",
        "duplicate_of",
        "duplicate_reasons",
    }:
        raise ValueError("Invalid recorded-example source")
    if source["kind"] != "recorded_example" or source["format"] not in ("jsonl", "csv"):
        raise ValueError("Invalid recorded-example source identity")
    if type(source["row"]) is not int or source["row"] < 1:
        raise ValueError("Recorded-example row must be a positive integer")
    if (
        not isinstance(source["source_id"], str)
        or not source["source_id"].strip()
        or len(source["source_id"]) > 512
    ):
        raise ValueError("Recorded examples need a source ID up to 512 characters")
    record = source["record"]
    allowed_fields = {"source_id", "input", "actual", "expected", "context", "events", "tags"}
    if (
        not isinstance(record, dict)
        or not {"source_id", "input"} <= record.keys()
        or record.keys() - allowed_fields
        or record["source_id"] != source["source_id"]
    ):
        raise ValueError("Recorded-example evidence needs its source ID and mapped input")
    mapping = source["mapping"]
    mapping_fields = {"source_id", "input", "actual", "expected", "context", "events", "tags"}
    if not isinstance(mapping, dict) or mapping.keys() != mapping_fields:
        raise ValueError("Invalid recorded-example field mapping")
    if not isinstance(mapping["input"], str) or not mapping["input"]:
        raise ValueError("Recorded-example input mapping is required")
    if any(
        value is not None and (not isinstance(value, str) or not value.strip())
        for value in mapping.values()
    ):
        raise ValueError("Recorded-example mappings must be non-empty field paths or null")
    if any(mapping[field] is None and field in record for field in allowed_fields - {"source_id"}):
        raise ValueError("Recorded-example evidence includes an unmapped field")
    if "tags" in record and (
        not isinstance(record["tags"], list)
        or any(not isinstance(tag, str) or not tag.strip() for tag in record["tags"])
        or len(set(record["tags"])) != len(record["tags"])
    ):
        raise ValueError("Recorded-example tags must be unique, non-empty strings")
    masked_fields = source["masked_fields"]
    if (
        not isinstance(masked_fields, list)
        or any(not isinstance(field, str) or not field for field in masked_fields)
        or len(set(masked_fields)) != len(masked_fields)
        or any(
            field.split(".", 1)[0] not in allowed_fields - {"source_id"}
            or any(not part for part in field.split("."))
            or mapping[field.split(".", 1)[0]] is None
            for field in masked_fields
        )
    ):
        raise ValueError("Recorded-example masks must be unique field paths and keep source IDs")
    duplicate_of = source["duplicate_of"]
    if duplicate_of is not None and (
        type(duplicate_of) is not int or duplicate_of < 1 or duplicate_of >= source["row"]
    ):
        raise ValueError("Duplicate source row must be a positive row number or null")
    reasons = source["duplicate_reasons"]
    if (
        not isinstance(reasons, list)
        or any(reason not in ("source_id", "input") for reason in reasons)
        or len(set(reasons)) != len(reasons)
        or (duplicate_of is None) != (not reasons)
    ):
        raise ValueError("Invalid duplicate review evidence")


def regression_draft(
    run: dict, *, path: str, fingerprint: str, case_id: str, attempt: int | None = None
) -> dict:
    """Create an unreviewed draft with input, no expected answer, and full source evidence."""
    report_from_dict(run)
    case = next((case for case in run["cases"] if case["id"] == case_id), None)
    if case is None:
        raise ValueError("Choose a case in the source run")
    draft_case = {"id": case_id + "-regression", "input": case["input"], "assertions": []}
    if case.get("tool_fixtures") is not None:
        draft_case["tool_fixtures"] = deepcopy(case["tool_fixtures"])
    if run["schema_version"] == 6 or (
        run["schema_version"] == 7
        and (case.get("conversation") or case.get("state_fixture") is not None)
    ):
        draft_case.update(
            tool_fixtures=deepcopy(case["tool_fixtures"]),
            conversation=deepcopy(case["conversation"]),
            state_fixture=deepcopy(case["state_fixture"]),
        )
    return validate_regression_draft(
        {
            "schema_version": 1,
            "kind": "regression_draft",
            "id": str(uuid4()),
            "source": {
                "path": path,
                "fingerprint": fingerprint,
                "case_id": case_id,
                "attempt": attempt,
                "run": run,
            },
            "case": draft_case,
            "reviewed": False,
        }
    )
