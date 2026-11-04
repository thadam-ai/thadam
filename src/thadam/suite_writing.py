"""Guarded suite writes shared by SDK, CLI, and dashboard actions."""

from __future__ import annotations

import hashlib
from pathlib import Path

from thadam._json import json_equal, read_json
from thadam.reporting import write_json_artifact
from thadam.suites import suite_from_dict


def file_fingerprint(path: str | Path) -> str | None:
    """Return a digest of exact bytes, or None for a new destination."""
    file = Path(path)
    return hashlib.sha256(file.read_bytes()).hexdigest() if file.exists() else None


def save_suite(data: dict, path: str | Path, *, expected_fingerprint: str | None = None) -> None:
    """Write a validated suite with optimistic concurrency and revision guards.

    A missing expected fingerprint means create only. This is not a filesystem
    transaction against unrelated programs; the dashboard serializes its writes.
    Reports and approved baselines cannot be replaced with suites.
    """
    destination = Path(path)
    if destination.suffix != ".json":
        raise ValueError("Save suites with a .json extension")
    suite_from_dict(data)
    if file_fingerprint(destination) != expected_fingerprint:
        raise ValueError("This file changed since you opened it. Reload it or use Save as.")
    if destination.exists():
        before = read_json(destination)
        try:
            suite_from_dict(before)
        except ValueError as error:
            raise ValueError("A suite cannot overwrite a report or baseline") from error
        if before.get("suite"):
            if before["suite"]["id"] != data.get("suite", {}).get("id"):
                raise ValueError(
                    "Keep the suite ID when editing; use Save as for a different suite"
                )
            if (
                not json_equal(before["cases"], data["cases"])
                and before["suite"]["revision"] == data["suite"]["revision"]
            ):
                raise ValueError("Change the suite revision before saving changed tests")
    write_json_artifact(data, destination)
