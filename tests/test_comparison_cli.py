"""Exercise saved-report comparison through the real command-line boundary."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from thadam import (
    OutputEquals,
    ReportWriteError,
    compare_reports,
    comparison_to_dict,
    run_suite,
    write_comparison,
    write_report,
)
from thadam import TestCase as AgentCase
from thadam.cli import main
from thadam.comparison_reporting import format_comparison
from thadam.terminal import TerminalStyle

ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def reports(tmp_path, *, failed=True):
    cases = [AgentCase("echo", None, (OutputEquals("answer", {"value": 1}),))]
    baseline = run_suite(lambda _: {"value": 1}, cases, agent_revision="before")
    candidate = run_suite(lambda _: {"value": 2 if failed else 1}, cases, agent_revision="after")
    paths = [tmp_path / "baseline.json", tmp_path / "candidate.json"]
    for report, path in zip((baseline, candidate), paths):
        write_report(report, path)
    return paths, compare_reports(baseline, candidate)


def test_cli_from_another_directory_agrees_with_sdk(tmp_path):
    paths, expected = reports(tmp_path)
    destination = tmp_path / "artifacts" / "comparison.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    process = subprocess.run(
        [sys.executable, "-m", "thadam", "compare", *map(str, paths), "--report", str(destination)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 1, process.stderr
    assert json.loads(destination.read_text()) == comparison_to_dict(expected)
    assert "REGRESSION: echo" in process.stdout
    assert "1 regression\n" in process.stdout
    assert "expected:" in process.stdout and "actual:" in process.stdout
    assert "before" in process.stdout and "after" in process.stdout
    assert "\x1b[" not in process.stdout


def test_incompatible_reports_write_actionable_artifact(tmp_path, capsys):
    paths, _ = reports(tmp_path)
    different = run_suite(lambda _: 1, [AgentCase("echo", None, (OutputEquals("answer", 1),))])
    write_report(different, paths[1])
    destination = tmp_path / "comparison.json"
    assert main(["compare", *map(str, paths), "--report", str(destination)]) == 2
    assert "definition" in capsys.readouterr().out
    assert json.loads(destination.read_text())["summary"]["incompatible"] == 1


@pytest.mark.parametrize("placement", ["before", "after"])
def test_color_policy_applies_to_compare_without_styling_json(tmp_path, capsys, placement):
    paths, _ = reports(tmp_path)
    destination = tmp_path / "comparison.json"
    arguments = ["compare", *map(str, paths), "--report", str(destination)]
    arguments = (
        ["--color", "always", *arguments]
        if placement == "before"
        else [*arguments, "--color", "always"]
    )
    assert main(arguments) == 1
    assert "\x1b[33mREGRESSION" in capsys.readouterr().out
    assert "\x1b[" not in destination.read_text()


@pytest.mark.parametrize("source_index", [0, 1])
@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_output_cannot_overwrite_either_input_or_file_alias(tmp_path, source_index, alias, capsys):
    paths, _ = reports(tmp_path)
    source = paths[source_index]
    original = source.read_bytes()
    destination = tmp_path / "alias.json"
    if alias == "same":
        destination = source
    elif alias == "symlink":
        destination.symlink_to(source)
    else:
        destination.hardlink_to(source)
    assert main(["compare", *map(str, paths), "--report", str(destination)]) == 2
    assert "must differ" in capsys.readouterr().err
    assert source.read_bytes() == original


def test_atomic_comparison_failure_preserves_existing_file(tmp_path, monkeypatch):
    _, comparison = reports(tmp_path)
    destination = tmp_path / "comparison.json"
    destination.write_text("previous artifact")

    def blocked(_source, _destination):
        raise PermissionError("blocked")

    monkeypatch.setattr(Path, "replace", blocked)
    with pytest.raises(ReportWriteError):
        write_comparison(comparison, destination)
    assert destination.read_text() == "previous artifact"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "baseline.json",
        "candidate.json",
        "comparison.json",
    ]


def test_invalid_reports_and_write_errors_have_useful_exit_codes(tmp_path, capsys):
    paths, _ = reports(tmp_path)
    directory = tmp_path / "directory"
    directory.mkdir()
    assert main(["compare", *map(str, paths), "--report", str(directory)]) == 2
    assert "Cannot write report" in capsys.readouterr().err
    paths[0].write_text('{"schema_version": 2}')
    assert main(["compare", *map(str, paths)]) == 2
    captured = capsys.readouterr()
    assert "generate fresh" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("width", [20, 40, 80, 120])
def test_comparison_output_wraps_and_colors_preserve_plain_meaning(tmp_path, width):
    _, comparison = reports(tmp_path)
    plain = format_comparison(comparison, width=width)
    styled = format_comparison(
        comparison, width=width, style=TerminalStyle(enabled=True, truecolor=True)
    )
    assert ANSI.sub("", styled) == plain
    assert all(len(line) <= min(width, 96) for line in plain.splitlines())
    assert "\x1b[38;2;251;191;36mREGRESSION" in styled or width == 20


def test_terminal_control_characters_in_metadata_and_ids_are_inert():
    cases = [AgentCase("case\x1b[31m\nspoof", None, (OutputEquals("answer", 1),))]
    baseline = run_suite(lambda _: 1, cases, agent_revision="rev\x1b[31m")
    candidate = run_suite(lambda _: 0, cases)
    output = format_comparison(compare_reports(baseline, candidate))
    assert "\x1b" not in output
    assert "\\x1b[31m" in output


def test_cli_success_and_explicit_revision_metadata(tmp_path, capsys):
    paths, _ = reports(tmp_path, failed=False)
    assert main(["compare", *map(str, paths), "--color", "never"]) == 0
    assert "\x1b[" not in capsys.readouterr().out
    report_path = tmp_path / "revision.json"
    assert (
        main(
            [
                "run",
                str(ROOT / "examples/refund_cases.json"),
                "--agent",
                "examples.refund_agent:run",
                "--agent-revision",
                "abc123",
                "--report",
                str(report_path),
            ]
        )
        == 0
    )
    assert json.loads(report_path.read_text())["agent_revision"] == "abc123"
