"""Command-line entry point; delegates execution and evaluation to the SDK."""

import argparse
import importlib
import shutil
import sys
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path

from thadam import __version__
from thadam.adapters.python import validate_agent
from thadam.comparison import compare_reports
from thadam.comparison_reporting import format_comparison, write_comparison
from thadam.errors import (
    AgentConfigurationError,
    ReportValidationError,
    ReportWriteError,
    SuiteValidationError,
)
from thadam.models import Agent
from thadam.reliability import compare_repeated
from thadam.reliability_reporting import format_reliability_comparison, write_reliability_comparison
from thadam.repetition import run_repeated, validate_factory
from thadam.repetition_loading import load_repeated
from thadam.repetition_reporting import format_repeated, write_repeated
from thadam.report_loading import load_report
from thadam.reporting import format_report_path, format_summary, write_report
from thadam.runner import run_suite
from thadam.suites import load_suite
from thadam.terminal import display_text, terminal_style


def main(argv: Sequence[str] | None = None) -> int:
    """Run or compare; return the documented gate code, or 2 for invalid configuration."""
    parser = argparse.ArgumentParser(prog="thadam", description="Test your Python agent locally.")
    parser.add_argument("--version", action="version", version=f"thadam {__version__}")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Terminal color policy (default: auto)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a saved JSON suite against a Python callable")
    run.add_argument("suite", type=Path, help="Path to a schema-version-1 JSON suite")
    run.add_argument("--agent", required=True, help="Agent reference: module:callable")
    run.add_argument("--report", type=Path, help="Write a JSON report to this path")
    run.add_argument(
        "--agent-revision", help="Explicit application revision recorded in the report"
    )
    compare = commands.add_parser("compare", help="Compare two schema-3 saved run reports")
    compare.add_argument("baseline", type=Path, help="Reviewed baseline run report")
    compare.add_argument("candidate", type=Path, help="Candidate run report")
    compare.add_argument("--report", type=Path, help="Write a JSON comparison artifact")
    repeat = commands.add_parser("repeat", help="Evaluate case/check reliability across attempts")
    repeat.add_argument("suite", type=Path, help="Path to a schema-version-1 JSON suite")
    selection = repeat.add_mutually_exclusive_group(required=True)
    selection.add_argument("--agent", help="Shared synchronous agent: module:callable")
    selection.add_argument(
        "--agent-factory", help="Fresh agent per case: module:zero_argument_factory"
    )
    repeat.add_argument(
        "--attempts",
        type=_attempt_count,
        default=10,
        help="Suite attempts (at least 2; default: 10)",
    )
    repeat.add_argument("--agent-revision", help="Explicit application revision")
    repeat.add_argument("--report", type=Path, help="Write complete repeated-run evidence")
    reliability = commands.add_parser(
        "compare-repeated", help="Gate a change on case/check pass-rate drops"
    )
    reliability.add_argument("baseline", type=Path, help="Reviewed repeated-run baseline")
    reliability.add_argument("candidate", type=Path, help="Candidate repeated-run evidence")
    reliability.add_argument(
        "--max-pass-rate-drop",
        type=float,
        default=0.0,
        help="Allowed drop per case/check, fraction 0..1 (default: 0)",
    )
    reliability.add_argument(
        "--report", type=Path, help="Write a standalone reliability comparison"
    )
    for command in (run, compare, repeat, reliability):
        command.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default=argparse.SUPPRESS,
            help="Terminal color policy (default: auto)",
        )
    arguments = parser.parse_args(argv)
    style = terminal_style(arguments.color, sys.stdout)

    try:
        if arguments.command in ("compare", "compare-repeated"):
            for source in (arguments.baseline, arguments.candidate):
                if arguments.report and _same_file(arguments.report, source):
                    raise ReportValidationError(
                        "Comparison destination must differ from both reports"
                    )
            if arguments.command == "compare-repeated":
                comparison = compare_repeated(
                    load_repeated(arguments.baseline),
                    load_repeated(arguments.candidate),
                    max_pass_rate_drop=arguments.max_pass_rate_drop,
                )
                formatter, writer = format_reliability_comparison, write_reliability_comparison
            else:
                comparison = compare_reports(
                    load_report(arguments.baseline), load_report(arguments.candidate)
                )
                formatter, writer = format_comparison, write_comparison
            print(formatter(comparison, style=style, width=shutil.get_terminal_size().columns))
            if arguments.report:
                writer(comparison, arguments.report)
                print(
                    "\n"
                    + format_report_path(
                        str(arguments.report), style=style, width=shutil.get_terminal_size().columns
                    )
                )
            return comparison.exit_code
        if arguments.report and _same_file(arguments.report, arguments.suite):
            raise SuiteValidationError("Report destination must differ from the suite file")
        cases = load_suite(arguments.suite)
        # Agent imports and execution may print; keep those logs out of the summary.
        with redirect_stdout(sys.stderr):
            if arguments.command == "repeat":
                factory = None
                agent = None
                if arguments.agent_factory:
                    factory = _load_reference(arguments.agent_factory)
                    validate_factory(factory)
                else:
                    agent = _load_agent(arguments.agent)
                report = run_repeated(
                    agent,
                    cases,
                    attempts=arguments.attempts,
                    agent_factory=factory,
                    agent_revision=arguments.agent_revision,
                )
            else:
                agent = _load_agent(arguments.agent)
                report = run_suite(agent, cases, agent_revision=arguments.agent_revision)
        if arguments.command == "repeat":
            print(format_repeated(report, style=style, width=shutil.get_terminal_size().columns))
        else:
            print(
                format_summary(
                    report,
                    style=style,
                    width=shutil.get_terminal_size().columns,
                    suite=str(arguments.suite),
                    agent=arguments.agent,
                )
            )
        if arguments.report:
            if arguments.command == "repeat":
                write_repeated(report, arguments.report)
            else:
                write_report(report, arguments.report)
            print(
                "\n"
                + format_report_path(
                    str(arguments.report),
                    style=style,
                    width=shutil.get_terminal_size().columns,
                )
            )
        return 1 if report.has_failures else 0
    except (
        SuiteValidationError,
        AgentConfigurationError,
        ReportValidationError,
        ReportWriteError,
        OSError,
    ) as error:
        error_style = terminal_style(arguments.color, sys.stderr)
        print(error_style.paint(f"thadam: {display_text(str(error))}", "error"), file=sys.stderr)
        return 2


def _same_file(destination: Path, source: Path) -> bool:
    return destination.resolve() == source.resolve() or (
        destination.exists() and source.exists() and destination.samefile(source)
    )


def _load_agent(reference: str) -> Agent:
    agent = _load_reference(reference)
    validate_agent(agent)
    return agent


def _attempt_count(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("attempts must be an integer of at least 2") from error
    if result < 2:
        raise argparse.ArgumentTypeError("attempts must be an integer of at least 2")
    return result


def _load_reference(reference: str) -> object:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute or ":" in attribute:
        raise AgentConfigurationError("Use a module:callable reference, for example my_agent:run")
    # Installed console scripts start in their bin directory; user modules live in cwd.
    directory = str(Path.cwd())
    if directory not in sys.path:
        sys.path.insert(0, directory)
    try:
        agent = importlib.import_module(module_name)
        for name in attribute.split("."):
            agent = getattr(agent, name)
    except (Exception, SystemExit) as error:
        raise AgentConfigurationError(f"Cannot load agent {reference!r}: {error}") from error
    return agent
