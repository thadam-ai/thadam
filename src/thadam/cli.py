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
from thadam.errors import AgentConfigurationError, ReportWriteError, SuiteValidationError
from thadam.models import Agent
from thadam.reporting import format_report_path, format_summary, write_report
from thadam.runner import run_suite
from thadam.suites import load_suite
from thadam.terminal import display_text, terminal_style


def main(argv: Sequence[str] | None = None) -> int:
    """Run a suite; return 0 for passes, 1 for case failures/errors, or 2 for setup errors."""
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
        "--color",
        choices=("auto", "always", "never"),
        default=argparse.SUPPRESS,
        help="Terminal color policy (default: auto)",
    )
    arguments = parser.parse_args(argv)
    style = terminal_style(arguments.color, sys.stdout)

    try:
        if arguments.report and arguments.report.resolve() == arguments.suite.resolve():
            raise SuiteValidationError("Report destination must differ from the suite file")
        cases = load_suite(arguments.suite)
        # Agent imports and execution may print; keep those logs out of the summary.
        with redirect_stdout(sys.stderr):
            agent = _load_agent(arguments.agent)
            report = run_suite(agent, cases)
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
    except (SuiteValidationError, AgentConfigurationError, ReportWriteError, OSError) as error:
        error_style = terminal_style(arguments.color, sys.stderr)
        print(error_style.paint(f"thadam: {display_text(str(error))}", "error"), file=sys.stderr)
        return 2


def _load_agent(reference: str) -> Agent:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute or ":" in attribute:
        raise AgentConfigurationError("Use --agent module:callable, for example my_agent:run")
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
    validate_agent(agent)
    return agent
