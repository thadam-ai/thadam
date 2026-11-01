"""Command-line entry point; delegates execution and evaluation to the SDK."""

import argparse
import importlib
import shutil
import sys
from collections.abc import Sequence
from contextlib import redirect_stdout
from functools import partial
from pathlib import Path

from thadam import __version__
from thadam.adapters.python import validate_agent
from thadam.cli_help import HelpParser, help_color_mode
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
    """Show help or execute a command; return 2 for invalid command arguments.

    With no arguments, display the overview and return 0 without loading suites
    or application code. Execution and comparison retain their documented codes.
    """
    supplied = list(sys.argv[1:] if argv is None else argv)
    help_style = terminal_style(help_color_mode(supplied), sys.stdout)
    parser = HelpParser(
        prog="thadam",
        help_style=help_style,
        description=(
            "Test your agent against expected behavior, inspect failures, and\n"
            "check whether a change reduces reliability. Runs execute locally.\n"
            "You supply the test cases and expected outcomes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Getting started\n"
            "  1. Save your test cases and expected outcomes in cases.json.\n"
            "  2. Expose a synchronous Python callable, such as my_agent:run.\n"
            "  3. Run it and save the evidence:\n\n"
            "  thadam run cases.json --agent my_agent:run --report artifacts/run.json\n\n"
            "Choose a workflow\n"
            "  run -> compare                 Check results before and after a change.\n"
            "  repeat -> compare-repeated     Check reliability across many attempts.\n\n"
            "Learn more\n"
            "  thadam run --help\n"
            "  thadam compare --help\n"
            "  thadam repeat --help\n"
            "  thadam compare-repeated --help\n\n"
            "You can also use: python -m thadam <command>\n"
            "Color is automatic in interactive terminals."
        ),
    )
    parser.add_argument("--version", action="version", version=f"thadam {__version__}")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all checks, attempts, and available trace evidence",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Terminal color policy (default: auto)",
    )
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=partial(HelpParser, help_style=help_style)
    )
    run = commands.add_parser(
        "run",
        help="Test each case once and explain failures",
        description=(
            "Run each saved test case once against your Python agent.\n"
            "Inspect outputs, failed checks, and execution errors.\n"
            "Save a report to compare against a later version."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (replace cases.json and my_agent with your own files)\n"
            "  thadam run cases.json --agent my_agent:run\n"
            "  thadam run cases.json --agent my_agent:run --report artifacts/run.json\n\n"
            "Repository example (requires a Thadam checkout; no model API key)\n"
            "  thadam run examples/refund_cases.json --agent examples.refund_agent:run\n\n"
            "Next: review a baseline report, then use thadam compare --help.\n"
            "Exit codes: 0 all passed; 1 failed checks/errors; 2 invalid configuration."
        ),
    )
    run.add_argument("suite", type=Path, help="Path to a schema-version-1 JSON suite")
    run.add_argument("--agent", required=True, help="Agent reference: module:callable")
    run.add_argument("--report", type=Path, help="Write a JSON report to this path")
    run.add_argument(
        "--agent-revision", help="Explicit application revision recorded in the report"
    )
    compare = commands.add_parser(
        "compare",
        help="Find new failures between two saved runs",
        description=(
            "Compare a reviewed baseline report with a candidate report.\n"
            "Show new failures, fixes, existing failures, and errors.\n"
            "This reads saved reports; it does not execute your agent."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (use reports saved by thadam run)\n"
            "  thadam compare baseline.json candidate.json\n"
            "  thadam compare baseline.json candidate.json --report artifacts/comparison.json\n\n"
            "Reports must have matching cases, inputs, and check definitions.\n"
            "Custom verifiers need matching explicit revisions.\n"
            "Review baseline updates explicitly; errors on either side block the gate.\n"
            "Exit codes: 0 no regressions/errors; 1 regression/error; 2 invalid/incompatible."
        ),
    )
    compare.add_argument("baseline", type=Path, help="Reviewed baseline run report")
    compare.add_argument("candidate", type=Path, help="Candidate run report")
    compare.add_argument("--report", type=Path, help="Write a JSON comparison artifact")
    repeat = commands.add_parser(
        "repeat",
        help="Measure consistency across repeated attempts",
        description=(
            "Run your suite repeatedly to see how consistently each case/check passes.\n"
            "Inspect pass rates, varying outcomes, errors, and runtime.\n"
            "Every attempt is retained in the saved report. Execution is sequential."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (replace cases.json and my_agent with your own files)\n"
            "  thadam repeat cases.json --agent my_agent:run --attempts 20\n"
            "  thadam repeat cases.json --agent my_agent:run --report artifacts/repeated.json\n"
            "  thadam repeat cases.json --agent-factory my_agent:create --attempts 20\n\n"
            "--agent reuses one callable across all attempts.\n"
            "--agent-factory calls a zero-argument factory for each case invocation.\n"
            "Next: review a baseline, then use thadam compare-repeated --help.\n"
            "Exit codes: 0 all passed; 1 failed checks/errors; 2 invalid configuration."
        ),
    )
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
        "compare-repeated",
        help="Detect reliability drops between repeated evaluations",
        description=(
            "Compare repeated baseline and candidate evaluations before accepting a change.\n"
            "Check every case and individual check for a lower observed pass rate.\n"
            "This reads saved reports; it does not execute your agent."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (use reports saved by thadam repeat)\n"
            "  thadam compare-repeated baseline.json candidate.json\n"
            "  thadam compare-repeated baseline.json candidate.json --report artifacts/reliability.json\n"
            "  thadam compare-repeated baseline.json candidate.json --max-pass-rate-drop 0.05\n\n"
            "0.05 allows up to five percentage points of decline per case/check.\n"
            "The default is zero: any observed decline blocks. Errors always block.\n"
            "Use equal attempt counts, matching shared/factory modes, and matching tests.\n"
            "Observed rates do not establish statistical significance or causation.\n"
            "Exit codes: 0 within policy/no errors; 1 regression/error; 2 invalid/incompatible."
        ),
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
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show all checks, attempts, and available trace evidence",
        )
        command.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default=argparse.SUPPRESS,
            help="Terminal color policy (default: auto)",
        )
    if not supplied:
        parser.print_help()
        return 0
    arguments = parser.parse_args(supplied)
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
            print(
                formatter(
                    comparison,
                    style=style,
                    width=shutil.get_terminal_size().columns,
                    verbose=arguments.verbose,
                )
            )
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
            print(
                format_repeated(
                    report,
                    style=style,
                    width=shutil.get_terminal_size().columns,
                    verbose=arguments.verbose,
                )
            )
        else:
            print(
                format_summary(
                    report,
                    style=style,
                    width=shutil.get_terminal_size().columns,
                    suite=str(arguments.suite),
                    agent=arguments.agent,
                    verbose=arguments.verbose,
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
