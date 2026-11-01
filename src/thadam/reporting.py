"""Readable summaries and atomic, versioned JSON report artifacts."""

import json
import tempfile
import textwrap
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from thadam.errors import ReportWriteError
from thadam.models import JSONValue, RunReport
from thadam.terminal import TerminalStyle, display_text
from thadam.terminal_reporting import ROLES, ReportView, case_evidence, run_counts


def report_to_dict(report: RunReport) -> dict[str, JSONValue]:
    """Return the JSON report contract, including computed summary counts."""
    return {
        "schema_version": report.schema_version,
        "evaluation_version": report.evaluation_version,
        "agent_revision": report.agent_revision,
        "run_id": report.run_id,
        "summary": asdict(report.summary),
        "cases": [
            {
                "id": case.id,
                "status": case.status,
                "duration_ms": case.duration_ms,
                "input": deepcopy(case.input),
                "output": deepcopy(case.output),
                "output_available": case.output_available,
                "assertions": [
                    {**asdict(assertion), "event_ids": list(assertion.event_ids)}
                    for assertion in case.assertions
                ],
                "errors": [asdict(error) for error in case.errors],
                "events": None if case.events is None else [asdict(event) for event in case.events],
                "trace_complete": case.trace_complete,
                "trace_warnings": list(case.trace_warnings),
                "check_definitions": [asdict(check) for check in case.check_definitions],
            }
            for case in report.cases
        ],
    }


def write_report(report: RunReport, path: str | Path) -> None:
    """Write a UTF-8 report atomically, creating parent directories if needed.

    Raises ReportWriteError and preserves any existing artifact if writing fails.
    """
    write_json_artifact(report_to_dict(report), path)


def write_json_artifact(data: dict[str, JSONValue], path: str | Path) -> None:
    """Atomically write JSON data; raise ReportWriteError and preserve old artifacts."""
    destination = Path(path)
    temporary: Path | None = None
    try:
        content = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content + "\n")
        temporary.replace(destination)
    except (OSError, ValueError, TypeError) as error:
        raise ReportWriteError(f"Cannot write report {destination}: {error}") from error
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def format_summary(
    report: RunReport,
    *,
    style: TerminalStyle | None = None,
    width: int = 88,
    suite: str | None = None,
    agent: str | None = None,
    verbose: bool = False,
) -> str:
    """Render verdict/counts, adaptive case rows, and failure or full case evidence.

    Verbose expands passing checks and all available trace evidence. Formatting
    does not execute application code or modify the report. SDK output is plain
    unless a style is explicitly supplied.
    """
    view = ReportView(style, width)
    view.header("Agent evaluation")
    view.summary(
        "FAILED" if report.has_failures else "PASSED",
        "error" if report.summary.errors else "failed" if report.has_failures else "brand",
        run_counts(report),
    )
    for name, value in (("Suite", suite), ("Agent", agent), ("Revision", report.agent_revision)):
        if value is not None:
            view.field(name, value)
    if verbose:
        view.field("Run", report.run_id)
    view.table(
        ("CASE", "RESULT", "DURATION"),
        [(case.id, case.status.upper(), f"{case.duration_ms:.2f} ms") for case in report.cases],
        [("info", ROLES[case.status], "muted") for case in report.cases],
    )
    for case in report.cases:
        case_evidence(view, case, verbose=verbose)
    return view.finish()


def _wrapped(value: str, width: int) -> list[str]:
    return textwrap.wrap(display_text(value), width=max(1, width), break_on_hyphens=False) or [""]


def format_report_path(path: str, *, style: TerminalStyle, width: int) -> str:
    """Display the written artifact location using the report's context hierarchy."""
    return "\n".join(_field("Report:", path, style, max(20, min(width, 96))))


def _field(label: str, value: str, style: TerminalStyle, width: int) -> list[str]:
    label = f"  {label:<8}"
    lines = []
    for index, part in enumerate(_wrapped(value, width - len(label) - 2)):
        prefix = style.paint(label, "muted") if index == 0 else " " * len(label)
        lines.append(prefix + style.paint(part, "info"))
    return lines
