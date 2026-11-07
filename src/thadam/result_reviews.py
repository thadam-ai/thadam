"""Independent human labels for saved evaluation results."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

from thadam._json import validate_json

VERDICTS = ("good", "bad", "needs_review")


def review_path(source_path: str) -> str:
    """Return the legacy path-only sidecar path for a saved result."""
    digest = sha256(source_path.encode("utf-8")).hexdigest()[:24]
    return f"review-labels/{digest}.json"


def revision_review_path(source_path: str, fingerprint: str, kind: str, source_id: str) -> str:
    """Return a sidecar path scoped to one exact saved result revision."""
    identity = json.dumps(
        [source_path, fingerprint, kind, source_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"review-labels/{digest}.json"


def result_reviews(
    source: dict, *, path: str, fingerprint: str, reviews: list[dict] | None = None
) -> dict:
    """Create a label artifact linked to one exact saved run or repeated run."""
    report_id = source.get("report_id") or source.get("run_id")
    if not isinstance(report_id, str) or not report_id:
        raise ValueError("Source result has no stable ID")
    return validate_result_reviews(
        {
            "schema_version": 1,
            "kind": "result_reviews",
            "id": uuid4().hex,
            "source": {
                "path": path,
                "fingerprint": fingerprint,
                "kind": source["kind"],
                "id": report_id,
            },
            "reviews": [] if reviews is None else reviews,
        },
        source=source,
    )


def validate_result_reviews(value: dict, *, source: dict | None = None) -> dict:
    """Strictly validate review labels without changing or evaluating source evidence."""
    data = deepcopy(value)
    validate_json(data)
    if not isinstance(data, dict) or data.keys() != {
        "schema_version",
        "kind",
        "id",
        "source",
        "reviews",
    }:
        raise ValueError("Invalid result review fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported result review schema")
    if data["kind"] != "result_reviews" or not isinstance(data["id"], str) or not data["id"]:
        raise ValueError("Invalid result review identity")
    origin = data["source"]
    if not isinstance(origin, dict) or origin.keys() != {"path", "fingerprint", "kind", "id"}:
        raise ValueError("Invalid result review source")
    if not isinstance(origin["path"], str) or not origin["path"]:
        raise ValueError("Record the source result path")
    if (
        not isinstance(origin["fingerprint"], str)
        or len(origin["fingerprint"]) != 64
        or any(character not in "0123456789abcdef" for character in origin["fingerprint"])
    ):
        raise ValueError("Record the source result fingerprint")
    if origin["kind"] not in ("run", "repeated_run"):
        raise ValueError("Labels must link to a run or repeated run")
    if not isinstance(origin["id"], str) or not origin["id"]:
        raise ValueError("Record the source result ID")
    if not isinstance(data["reviews"], list):
        raise ValueError("Result reviews must be an array")
    seen: set[tuple[str, int | None]] = set()
    valid_cases: dict[int | None, set[str]] | None = None
    if source is not None:
        expected_id = source.get("report_id") or source.get("run_id")
        if source.get("kind") != origin["kind"] or expected_id != origin["id"]:
            raise ValueError("Result labels do not match the selected source")
        runs = source.get("runs") if source["kind"] == "repeated_run" else [source]
        if not isinstance(runs, list):
            raise ValueError("Source result has invalid attempts")
        valid_cases = {}
        for index, run in enumerate(runs, start=1):
            cases = run.get("cases") if isinstance(run, dict) else None
            if not isinstance(cases, list):
                raise ValueError("Source result has invalid cases")
            attempt = index if source["kind"] == "repeated_run" else None
            valid_cases[attempt] = {
                case["id"]
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("id"), str)
            }
    for review in data["reviews"]:
        if not isinstance(review, dict) or review.keys() != {
            "case_id",
            "attempt",
            "verdict",
            "notes",
            "tags",
        }:
            raise ValueError("Each label needs case_id, attempt, verdict, notes, and tags")
        case_id, attempt = review["case_id"], review["attempt"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Review case IDs must be non-empty strings")
        if origin["kind"] == "run":
            if attempt is not None:
                raise ValueError("Single-run labels use a null attempt")
        elif type(attempt) is not int or attempt < 1:
            raise ValueError("Repeated-run labels need a positive attempt number")
        key = (case_id, attempt)
        if key in seen:
            raise ValueError("A case attempt can have only one review label")
        seen.add(key)
        if review["verdict"] not in VERDICTS:
            raise ValueError("Choose good, bad, or needs_review")
        if not isinstance(review["notes"], str) or len(review["notes"]) > 4000:
            raise ValueError("Review notes must be text up to 4000 characters")
        tags = review["tags"]
        if (
            not isinstance(tags, list)
            or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 80 for tag in tags)
            or len(tags) > 30
            or len(set(tags)) != len(tags)
        ):
            raise ValueError("Use up to 30 unique non-empty tags per label")
        if valid_cases is not None:
            attempt_cases = valid_cases.get(attempt)
            if attempt_cases is None or case_id not in attempt_cases:
                raise ValueError("Review label refers to a case absent from the source attempt")
    return data
