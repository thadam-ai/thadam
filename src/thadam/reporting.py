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
from thadam.terminal import ColorRole, TerminalStyle, display_text


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
) -> str:
    """Render a compact report with optional color, explicit statuses, and wrapping.

    The SDK defaults to plain text. Styling never changes the JSON report or
    evaluation rules. Width is measured in text columns before adding ANSI codes.
    """
    style = style or TerminalStyle()
    width = max(20, min(width, 96))
    rule = style.paint("  " + "-" * (width - 4), "muted")
    heading = "  " + style.paint("THADAM", "brand", bold=True)
    heading += "  Agent test report" if width >= 28 else "\n  Agent test report"
    lines = ["", heading, rule]
    for label, value in (("Suite", suite), ("Agent", agent)):
        if value is not None:
            lines.extend(_field(label, value, style, width))
    lines.append("")
    for case in report.cases:
        role: ColorRole = {"passed": "brand", "failed": "failed", "error": "error"}[case.status]
        label = style.paint(f"{case.status.upper():6}", role, bold=True)
        duration = f"{case.duration_ms:.2f} ms"
        names = _wrapped(case.id, width - 12)
        for index, name in enumerate(names):
            prefix = "  " + label + "  " if index == 0 else " " * 10
            padding = width - 12 - len(name) - len(duration)
            if index == 0 and padding >= 2:
                lines.append(prefix + name + " " * padding + style.paint(duration, "muted"))
            else:
                lines.append(prefix + name)
        if width - 12 - len(names[0]) - len(duration) < 2:
            lines.append(" " * 10 + style.paint(duration, "muted"))
        for assertion in case.assertions:
            if not assertion.passed:
                lines.extend(
                    _detail(f"{assertion.id}: {assertion.message}", style, "failed", width)
                )
                lines.extend(
                    _detail(
                        f"expected: {json.dumps(assertion.expected, ensure_ascii=False)}",
                        style,
                        "muted",
                        width,
                    )
                )
                lines.extend(
                    _detail(
                        f"actual:   {json.dumps(assertion.actual, ensure_ascii=False)}",
                        style,
                        "failed",
                        width,
                    )
                )
                if assertion.event_ids:
                    lines.extend(
                        _detail("events: " + ", ".join(assertion.event_ids), style, "muted", width)
                    )
        for error in case.errors:
            check = f" [{error.assertion_id}]" if error.assertion_id is not None else ""
            lines.extend(
                _detail(
                    f"{error.source}{check}: {error.type}: {error.message}", style, "error", width
                )
            )
        if case.status != "passed" and case.events is not None:
            for event in case.events:
                event_role: ColorRole = "error" if event.status == "error" else "muted"
                duration = (
                    "unknown duration"
                    if event.duration_ms is None
                    else f"{event.duration_ms:.2f} ms"
                )
                lines.extend(
                    _detail(
                        f"{event.kind} {event.name}: {event.status} ({duration}) [{event.id}]",
                        style,
                        event_role,
                        width,
                    )
                )
                if event.kind == "tool" and event.input_available:
                    lines.extend(
                        _detail(
                            "arguments: " + json.dumps(event.input, ensure_ascii=False),
                            style,
                            event_role,
                            width,
                        )
                    )
                if event.error:
                    lines.extend(
                        _detail(f"{event.error.type}: {event.error.message}", style, "error", width)
                    )
        for warning in case.trace_warnings:
            lines.extend(_detail("trace: " + warning, style, "failed", width))
        if case.errors or any(not item.passed for item in case.assertions):
            lines.append("")
    counts = report.summary
    case_noun = "case" if counts.total == 1 else "cases"
    error_noun = "error" if counts.errors == 1 else "errors"
    lines.extend([rule, ""])
    totals = [
        style.paint(f"{counts.passed} passed", "brand" if counts.passed else "muted", bold=True),
        style.paint(f"{counts.failed} failed", "failed" if counts.failed else "muted", bold=True),
        style.paint(
            f"{counts.errors} {error_noun}", "error" if counts.errors else "muted", bold=True
        ),
    ]
    summary_length = len(
        f"  {counts.total} {case_noun}: {counts.passed} passed, "
        f"{counts.failed} failed, {counts.errors} {error_noun}"
    )
    if summary_length <= width:
        lines.append(f"  {counts.total} {case_noun}: " + ", ".join(totals))
    else:
        lines.extend([f"  {counts.total} {case_noun}", *("  " + total for total in totals)])
    return "\n".join(lines)


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


def _detail(value: str, style: TerminalStyle, role: ColorRole, width: int) -> list[str]:
    return [" " * 10 + style.paint(part, role) for part in _wrapped(value, width - 12)]
