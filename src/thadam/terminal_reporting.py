"""Shared report layout and observable evidence presentation; no evaluation rules."""

import json
import textwrap
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

from thadam.models import AssertionResult, CaseError, CaseResult, RunReport
from thadam.terminal import ColorRole, TerminalStyle, display_text

ROLES: dict[str, ColorRole] = {
    "passed": "brand",
    "failed": "failed",
    "error": "error",
    "regression": "failed",
    "fixed": "brand",
    "improved": "brand",
    "existing_failure": "failed",
    "unchanged_pass": "brand",
    "unchanged": "brand",
    "tolerated_drop": "failed",
    "incompatible": "error",
}


def label(value: str) -> str:
    """Return a readable status label independent of color."""
    return value.replace("_", " ").upper()


def _columns(text: str) -> int:
    """Measure terminal cells, accounting for wide glyphs and combining marks."""
    return sum(
        0
        if unicodedata.category(char).startswith("M") or char == "\u200d"
        else 2
        if unicodedata.east_asian_width(char) in ("W", "F")
        else 1
        for char in text
    )


def _wrap(text: str, width: int) -> list[str]:
    """Wrap escaped text, additionally splitting lines that contain wide glyphs."""
    lines = []
    for part in textwrap.wrap(text, width=width, break_on_hyphens=False) or [""]:
        chunk = ""
        for char in part:
            if chunk and _columns(chunk + char) > width:
                lines.append(chunk)
                chunk = ""
            chunk += char
        lines.append(chunk)
    return lines


class ReportView:
    """Build a scrollable report, wrapping plain text before applying color."""

    def __init__(self, style: TerminalStyle | None = None, width: int = 88) -> None:
        self.style = style or TerminalStyle()
        self.width = max(20, min(width, 96))
        self.lines: list[str] = [""]

    def add(
        self, text: str, role: ColorRole = "muted", *, indent: int = 2, bold: bool = False
    ) -> None:
        for part in _wrap(display_text(text), self.width - indent):
            self.lines.append(" " * indent + self.style.paint(part, role, bold=bold))

    def header(self, title: str) -> None:
        self.add("THADAM", "brand", bold=True)
        self.add(title, "info")
        self.add("-" * (self.width - 4))

    def summary(
        self, status: str, role: ColorRole, counts: Sequence[tuple[str, ColorRole]]
    ) -> None:
        self.add(status, role, bold=True)
        if len(" / ".join(text for text, _ in counts)) <= self.width - 4:
            self.lines.append(
                "  " + " / ".join(self.style.paint(text, color) for text, color in counts)
            )
        else:
            for text, color in counts:
                self.add(text, color)
        self.lines.append("")

    def field(self, name: str, value: str, role: ColorRole = "info", *, indent: int = 2) -> None:
        self.add(f"{name:<10} {value}", role, indent=indent)

    def section(self, title: str, role: ColorRole = "info") -> None:
        self.lines.append("")
        self.add(title, role)

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[tuple[str, ...]],
        roles: Sequence[tuple[ColorRole, ...]],
    ) -> None:
        """Use columns if they fit; otherwise retain every value in stacked rows."""
        self.lines.append("")
        escaped = [tuple(display_text(value) for value in row) for row in rows]
        sizes = [
            max([_columns(head), *(_columns(row[i]) for row in escaped)])
            for i, head in enumerate(headers)
        ]
        if self.width >= 60 and sum(sizes) + 2 * (len(headers) - 1) <= self.width - 4:
            self.add("  ".join(head.ljust(size) for head, size in zip(headers, sizes)).rstrip())
            for row, colors in zip(escaped, roles):
                cells = [
                    self.style.paint(value, color, bold=color in ("brand", "failed", "error"))
                    + " " * (size - _columns(value))
                    for value, size, color in zip(row, sizes, colors)
                ]
                self.lines.append("  " + "  ".join(cells).rstrip())
        else:
            for row, colors in zip(rows, roles):
                self.add(row[0], colors[0])
                for head, value, color in zip(headers[1:], row[1:], colors[1:]):
                    self.field(head.title(), value, color, indent=4)
                self.lines.append("")

    def finish(self) -> str:
        return "\n".join(self.lines)


def run_counts(report: RunReport) -> list[tuple[str, ColorRole]]:
    """Counts of mutually exclusive case outcomes for a completed run."""
    summary = report.summary
    return [
        (f"{summary.passed} passed", "brand" if summary.passed else "muted"),
        (f"{summary.failed} failed", "failed" if summary.failed else "muted"),
        (
            f"{summary.errors} {'error' if summary.errors == 1 else 'errors'}",
            "error" if summary.errors else "muted",
        ),
    ]


def assertion_evidence(view: ReportView, result: AssertionResult) -> None:
    """Show a recorded check's explanation, expected/actual evidence, and event links."""
    role: ColorRole = "brand" if result.passed else "failed"
    view.add(result.message, role, indent=4)
    view.add("expected: " + json.dumps(result.expected, ensure_ascii=False), indent=4)
    view.add("actual:   " + json.dumps(result.actual, ensure_ascii=False), role, indent=4)
    if result.event_ids:
        view.add("events: " + ", ".join(result.event_ids), indent=4)


def error_evidence(view: ReportView, error: CaseError) -> None:
    """Keep error source and check identity distinct from failed expectations."""
    check = f" [{error.assertion_id}]" if error.assertion_id is not None else ""
    view.add(f"{error.source}{check}: {error.type}: {error.message}", "error", indent=4)


def trace_evidence(
    view: ReportView, case: CaseResult, *, verbose: bool = False, warnings: bool = True
) -> None:
    """Display explicit trace availability; verbose includes every available span field."""
    if case.events is None:
        if verbose:
            view.field("Trace", "unavailable", indent=4)
    else:
        view.field("Trace", "complete" if case.trace_complete else "incomplete", indent=4)
        if not case.events:
            view.add("No events observed in the instrumented scope", indent=4)
        for event in case.events:
            role: ColorRole = "error" if event.status == "error" else "muted"
            duration = (
                "unknown duration" if event.duration_ms is None else f"{event.duration_ms:.2f} ms"
            )
            view.add(
                f"{event.kind} {event.name}: {event.status} ({duration}) [{event.id}]",
                role,
                indent=4,
            )
            if verbose:
                view.add(
                    f"parent: {event.parent_id}; started: {event.started_at_ms:g} ms", indent=6
                )
            if event.input_available and (verbose or event.kind == "tool"):
                view.add("arguments: " + json.dumps(event.input, ensure_ascii=False), indent=6)
            if verbose:
                if not event.input_available:
                    view.add("input: unavailable", indent=6)
                view.add(
                    "output: "
                    + (
                        json.dumps(event.output, ensure_ascii=False)
                        if event.output_available
                        else "unavailable"
                    ),
                    indent=6,
                )
                view.add(
                    "usage: "
                    + (
                        json.dumps(asdict(event.usage))
                        if event.usage is not None
                        else "unavailable"
                    ),
                    indent=6,
                )
            if event.error:
                view.add(f"{event.error.type}: {event.error.message}", "error", indent=6)
    if warnings:
        for warning in case.trace_warnings:
            view.add("trace: " + warning, "failed", indent=4)


def case_evidence(view: ReportView, case: CaseResult, *, verbose: bool = False) -> None:
    """Show failures/errors by default, or full available case evidence in verbose mode."""
    if verbose:
        view.section(f"{label(case.status)}: {case.id}", ROLES[case.status])
        view.field("Duration", f"{case.duration_ms:.2f} ms", indent=4)
        view.add("input: " + json.dumps(case.input, ensure_ascii=False), indent=4)
        view.add(
            "output: "
            + (
                json.dumps(case.output, ensure_ascii=False)
                if case.output_available
                else "unavailable"
            ),
            indent=4,
        )
        view.add(
            "declared checks: "
            + json.dumps([asdict(item) for item in case.check_definitions], ensure_ascii=False),
            indent=4,
        )
    for result in case.assertions:
        if verbose or not result.passed:
            view.section(
                f"{label('passed' if result.passed else 'failed')}: {case.id} / {result.id}",
                "brand" if result.passed else "failed",
            )
            assertion_evidence(view, result)
    for error in case.errors:
        view.section(f"ERROR: {case.id}", "error")
        error_evidence(view, error)
    if verbose or case.status != "passed" or case.trace_warnings:
        trace_evidence(view, case, verbose=verbose)


def attempt_ranges(attempts: Sequence[int]) -> str:
    """Compress consecutive one-based attempt numbers without losing occurrences."""
    ranges = []
    numbers = sorted(set(attempts))
    if not numbers:
        return ""
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number != previous + 1:
            ranges.append(str(start) if start == previous else f"{start}-{previous}")
            start = number
        previous = number
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


@dataclass
class _Finding:
    case: CaseResult
    result: AssertionResult | CaseError | str
    occurrences: list[tuple[int, str]] = field(default_factory=list)


def grouped_evidence(view: ReportView, runs: Sequence[RunReport], *, side: str = "") -> None:
    """Group identical failure evidence per side/case/check, preserving occurrence links.

    IDs/timings of traces do not split groups. The representative trace is labeled;
    all distinct expected/actual/error evidence remains in separate groups.
    """
    groups: dict[str, _Finding] = {}
    for attempt, run in enumerate(runs, 1):
        for case in run.cases:
            findings: list[AssertionResult | CaseError | str] = [
                *(check for check in case.assertions if not check.passed),
                *case.errors,
                *case.trace_warnings,
            ]
            for result in findings:
                evidence = result if isinstance(result, str) else asdict(result)
                if isinstance(result, AssertionResult):
                    evidence.pop("event_ids")
                key = json.dumps(
                    [case.id, type(result).__name__, evidence], sort_keys=True, ensure_ascii=False
                )
                group = groups.setdefault(key, _Finding(case, result))
                group.occurrences.append((attempt, run.run_id))
    for group in groups.values():
        result = group.result
        role: ColorRole = "error" if isinstance(result, CaseError) else "failed"
        check_id = (
            result.id
            if isinstance(result, AssertionResult)
            else result.assertion_id
            if isinstance(result, CaseError)
            else None
        )
        name = group.case.id + (f" / {check_id}" if check_id is not None else "")
        finding_label = (
            "ERROR"
            if isinstance(result, CaseError)
            else "FAILED"
            if isinstance(result, AssertionResult)
            else "TRACE WARNING"
        )
        view.section(f"{finding_label}: {name}", role)
        prefix = f"{side} " if side else ""
        view.add(
            f"{prefix}attempts {attempt_ranges([item[0] for item in group.occurrences])} / {len(group.occurrences)} {'occurrence' if len(group.occurrences) == 1 else 'occurrences'}",
            "info",
            indent=4,
        )
        if isinstance(result, AssertionResult):
            assertion_evidence(view, result)
        elif isinstance(result, CaseError):
            error_evidence(view, result)
        else:
            view.add("trace: " + result, "failed", indent=4)
        attempt, run_id = group.occurrences[0]
        view.add(f"Representative {prefix}attempt {attempt} / run {run_id}", indent=4)
        if group.case.events is not None:
            trace_evidence(view, group.case, warnings=False)
    if groups:
        view.section("Details: use --verbose for every attempt, run ID, and available trace.")


def verbose_attempts(view: ReportView, runs: Sequence[RunReport], *, side: str = "") -> None:
    """Expand every attempt while keeping the report's single top-level heading."""
    for attempt, run in enumerate(runs, 1):
        view.section(f"{side + ' ' if side else ''}Attempt {attempt} / run {run.run_id}")
        for case in run.cases:
            case_evidence(view, case, verbose=True)
