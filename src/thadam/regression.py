"""Reviewable regression drafts made from strictly validated saved run evidence."""

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
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported regression draft schema")
    if data["kind"] != "regression_draft" or not isinstance(data["id"], str) or not data["id"]:
        raise ValueError("Invalid regression draft identity")
    source = data["source"]
    if not isinstance(source, dict) or source.keys() != {
        "path",
        "fingerprint",
        "case_id",
        "attempt",
        "run",
    }:
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
    attempt = source["attempt"]
    if attempt is not None and (type(attempt) is not int or attempt < 1):
        raise ValueError("Attempt must be a positive integer or null")
    report = report_from_dict(source["run"])
    if not isinstance(source["case_id"], str) or source["case_id"] not in {
        case.id for case in report.cases
    }:
        raise ValueError("Source case is absent from the recorded run")
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


def regression_draft(
    run: dict, *, path: str, fingerprint: str, case_id: str, attempt: int | None = None
) -> dict:
    """Create an unreviewed draft with input, no expected answer, and full source evidence."""
    report_from_dict(run)
    case = next((case for case in run["cases"] if case["id"] == case_id), None)
    if case is None:
        raise ValueError("Choose a case in the source run")
    draft_case = {"id": case_id + "-regression", "input": case["input"], "assertions": []}
    if "tool_fixtures" in case:
        draft_case["tool_fixtures"] = deepcopy(case["tool_fixtures"])
    if run["schema_version"] == 6:
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
