"""Reload standalone reliability comparisons, recomputing policy decisions."""

from pathlib import Path

from thadam._json import read_json
from thadam.errors import ReportValidationError
from thadam.reliability import ReliabilityComparison, compare_repeated
from thadam.reliability_reporting import reliability_to_dict
from thadam.repetition_loading import repeated_from_dict, require_consistent


def load_reliability_comparison(path: str | Path) -> ReliabilityComparison:
    """Validate evidence and recompute a saved comparison, without executing user code.

    Raise ReportValidationError for unsupported schemas, changed decisions,
    inconsistent summaries, invalid policy, or malformed evidence.
    """
    try:
        data = read_json(path, max_depth=120)
        if not isinstance(data, dict) or set(data) != {
            "schema_version",
            "kind",
            "policy",
            "baseline",
            "candidate",
            "issues",
            "cases",
            "compatible",
            "summary",
            "exit_code",
        }:
            raise ValueError("Expected reliability_comparison fields")
        if not isinstance(data["policy"], dict) or set(data["policy"]) != {"max_pass_rate_drop"}:
            raise ValueError("Expected an explicit max_pass_rate_drop policy")
        report = compare_repeated(
            repeated_from_dict(data["baseline"]),
            repeated_from_dict(data["candidate"]),
            max_pass_rate_drop=data["policy"]["max_pass_rate_drop"],
        )
        require_consistent(data, reliability_to_dict(report))
        return report
    except (OSError, UnicodeError, TypeError, ValueError, RecursionError) as error:
        raise ReportValidationError(
            f"Cannot load reliability comparison {path}: {error}"
        ) from error
