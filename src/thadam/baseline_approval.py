"""Explicit guarded filesystem promotion of reviewed baseline evidence."""

import os
from contextlib import suppress
from pathlib import Path

from thadam.baseline_review import (
    ApprovedBaseline,
    approved_from_dict,
    approved_to_dict,
    evaluation_to_dict,
    evidence_digest,
    load_evaluation,
)
from thadam.errors import ReportValidationError, ReportWriteError
from thadam.reporting import _replace_json_artifact


def write_approved_baseline(approval: ApprovedBaseline, path: str | Path) -> None:
    """Atomically promote exact reviewed evidence with its acknowledgement.

    A new baseline requires an absent destination. Replacement requires that the
    destination still contains the exact old evaluation embedded in the review.
    Symlink destinations and competing Thadam approval writers are refused.
    Validation/stale evidence raises ReportValidationError; filesystem failure
    raises ReportWriteError. Existing files survive either failure. This local
    coordination is not a transaction with unrelated external file writers.
    """
    approval = approved_from_dict(approved_to_dict(approval))
    destination = Path(path)
    lock = None
    owned = False
    try:
        if destination.is_symlink():
            raise ReportValidationError("Baseline destination must not be a symbolic link")
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = destination.with_name(destination.name + ".thadam-approval.lock")
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        owned = True
        os.close(descriptor)
        previous = approval.review.baseline
        if previous is None:
            if destination.exists():
                raise ReportValidationError(
                    "Initial approval cannot overwrite an existing baseline; review it first"
                )
        else:
            if not destination.exists():
                raise ReportValidationError(
                    "Reviewed baseline is missing; review the current destination again"
                )
            current = load_evaluation(destination)
            if evidence_digest(evaluation_to_dict(current)) != evidence_digest(
                evaluation_to_dict(previous)
            ):
                raise ReportValidationError(
                    "Baseline changed since review; generate and inspect a new review"
                )
        _replace_json_artifact(approved_to_dict(approval), destination)
    except OSError as error:
        raise ReportWriteError(f"Cannot approve baseline {destination}: {error}") from error
    finally:
        if owned and lock is not None:
            with suppress(OSError):
                lock.unlink()
