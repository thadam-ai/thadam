"""Argument translation for explicit baseline review and approval commands."""

import argparse
import shutil
from collections.abc import Callable
from pathlib import Path

from thadam._json import read_json
from thadam.baseline_approval import write_approved_baseline
from thadam.baseline_reporting import format_baseline_review, write_baseline_review
from thadam.baseline_review import (
    approve_review,
    load_baseline_review,
    load_evaluation,
    review_baseline,
    review_from_dict,
)
from thadam.errors import ReportValidationError
from thadam.reporting import format_report_path
from thadam.terminal import TerminalStyle
from thadam.terminal_reporting import ReportView


def add_baseline_commands(
    commands: argparse._SubParsersAction,
) -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """Register review/approval help and explicit acknowledgement arguments."""
    review = commands.add_parser(
        "review-baseline",
        help="Review test changes and proposed baseline evidence",
        description="Inspect a candidate and optional old baseline before approving an intentional update.\nAlso reopen a saved review without running your agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples (use a schema-2 suite to generate candidate.json)\n"
        "  thadam review-baseline candidate.json --report review.json\n"
        "  thadam review-baseline candidate.json --baseline baseline.json --report review.json\n"
        "  thadam review-baseline review.json --verbose\n\n"
        "Review every changed input/check and the new outcomes.\n"
        "Exit codes: 0 ready for human review; 1 approval blockers; 2 invalid input/write failure.",
    )
    review.add_argument("evidence", type=Path, help="Candidate evaluation or saved review")
    review.add_argument(
        "--baseline", type=Path, help="Current baseline being intentionally replaced"
    )
    review.add_argument(
        "--report", type=Path, help="Save a standalone review for explicit approval"
    )
    approve = commands.add_parser(
        "approve-baseline",
        help="Approve exact reviewed evidence as a baseline",
        description="Save an approved baseline with its complete review and acknowledgement.\nRefuse blockers, a stale review digest, or a destination changed since review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples (copy the SHA-256 shown by review-baseline)\n"
        "  thadam approve-baseline review.json --baseline baseline.json --review-digest SHA256 --reviewer YourName --reason 'Reviewed policy update'\n\n"
        "Use --accept-failures only after inspecting failed expectations. Errors cannot be accepted.\n"
        "This writes a local file. Commit it through your normal pull-request review.\n"
        "Exit codes: 0 baseline written; 2 invalid, stale, blocked, or write failure.",
    )
    approve.add_argument("review", type=Path, help="Saved review to approve")
    approve.add_argument(
        "--baseline", type=Path, required=True, help="Approved baseline destination"
    )
    approve.add_argument(
        "--review-digest", required=True, help="Exact SHA-256 of the inspected review"
    )
    approve.add_argument("--reviewer", required=True, help="Reviewer name recorded with approval")
    approve.add_argument("--reason", required=True, help="Why this baseline is being accepted")
    approve.add_argument(
        "--accept-failures", action="store_true", help="Explicitly acknowledge failed expectations"
    )
    return review, approve


def handle_baseline_command(
    arguments: argparse.Namespace, *, style: TerminalStyle, same_file: Callable[[Path, Path], bool]
) -> int:
    """Load evidence, delegate SDK review/approval, and render using the shared theme."""
    width = shutil.get_terminal_size().columns
    if arguments.command == "review-baseline":
        sources = [arguments.evidence] + ([arguments.baseline] if arguments.baseline else [])
        if arguments.report and any(same_file(arguments.report, path) for path in sources):
            raise ReportValidationError(
                "Review destination must differ from its evidence and baseline"
            )
        try:
            data = read_json(arguments.evidence, max_depth=125)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ReportValidationError(str(error)) from error
        if isinstance(data, dict) and data.get("kind") == "baseline_review":
            if arguments.baseline:
                raise ReportValidationError(
                    "A saved review already includes its baseline; omit --baseline"
                )
            review = review_from_dict(data)
        else:
            review = review_baseline(
                load_evaluation(arguments.evidence),
                load_evaluation(arguments.baseline) if arguments.baseline else None,
            )
        print(format_baseline_review(review, style=style, width=width, verbose=arguments.verbose))
        if arguments.report:
            write_baseline_review(review, arguments.report)
            print("\n" + format_report_path(str(arguments.report), style=style, width=width))
        return review.exit_code
    if same_file(arguments.baseline, arguments.review):
        raise ReportValidationError("Baseline destination must differ from the review file")
    approval = approve_review(
        load_baseline_review(arguments.review),
        review_digest=arguments.review_digest,
        reviewer=arguments.reviewer,
        reason=arguments.reason,
        accept_failures=arguments.accept_failures,
    )
    write_approved_baseline(approval, arguments.baseline)
    view = ReportView(style, width)
    view.header("Baseline approval")
    view.summary("APPROVED", "brand", [])
    view.field("Baseline", str(arguments.baseline))
    view.field("Reviewer", approval.reviewer)
    view.field("Reason", approval.reason)
    view.field("Review SHA-256", approval.review_digest)
    view.add("Commit this baseline through your normal pull-request review.")
    print(view.finish())
    return 0
