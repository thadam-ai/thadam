"""Exercise consumer CLI execution, comparison, safety boundaries, and presentation."""

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
    compare_repeated,
    load_reliability_comparison,
    load_repeated,
    reliability_to_dict,
    run_repeated,
    write_reliability_comparison,
    write_repeated,
)
from thadam import TestCase as AgentCase
from thadam.cli import main
from thadam.reliability_reporting import format_reliability_comparison
from thadam.repetition_reporting import format_repeated
from thadam.terminal import TerminalStyle

ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def reports(tmp_path):
    cases = [AgentCase("echo", {"value": 1}, (OutputEquals("answer", {"value": 1}),))]
    baseline = run_repeated(lambda value: value, cases, attempts=2, agent_revision="before")
    candidate = run_repeated(lambda _: {"value": 0}, cases, attempts=2, agent_revision="after")
    paths = [tmp_path / "baseline.json", tmp_path / "candidate.json"]
    for report, path in zip((baseline, candidate), paths):
        write_repeated(report, path)
    return paths, compare_repeated(baseline, candidate)


@pytest.mark.parametrize("selection", ["--agent", "--agent-factory"])
def test_real_cli_imports_consumer_module_and_preserves_evidence(tmp_path, selection):
    (tmp_path / "consumer.py").write_text(
        'def run(value):\n    print("agent log")\n    return value\n'
        'def create():\n    print("factory log")\n    return run\n'
    )
    suite = tmp_path / "cases.json"
    suite.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "echo",
                        "input": {"value": 1},
                        "assertions": [
                            {"id": "answer", "type": "output_equals", "expected": {"value": 1}}
                        ],
                    }
                ],
            }
        )
    )
    destination = tmp_path / "artifacts" / "repeated.json"
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "thadam",
            "repeat",
            str(suite),
            selection,
            "consumer:create" if selection == "--agent-factory" else "consumer:run",
            "--attempts",
            "3",
            "--agent-revision",
            "consumer-sha",
            "--report",
            str(destination),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    saved = load_repeated(destination)
    assert saved.attempts == 3 and saved.agent_revision == "consumer-sha"
    assert saved.cases[0].counts.passed == 3
    assert saved.execution_mode == ("factory" if selection == "--agent-factory" else "shared")
    assert "agent log" in process.stderr and "agent log" not in process.stdout
    assert "3/3 (100.0%)" in process.stdout and "MEDIAN" in process.stdout


def test_comparison_cli_matches_sdk_with_standalone_artifact(tmp_path, capsys):
    paths, expected = reports(tmp_path)
    destination = tmp_path / "comparison.json"
    assert main(["compare-repeated", *map(str, paths), "--report", str(destination)]) == 1
    assert json.loads(destination.read_text()) == reliability_to_dict(expected)
    assert load_reliability_comparison(destination).exit_code == 1
    output = capsys.readouterr().out
    assert "REGRESSION: echo" in output
    assert "Candidate attempt 1" in output and "expected:" in output and "actual:" in output
    assert "before" in output and "after" in output
    assert main(["compare-repeated", *map(str, paths), "--max-pass-rate-drop", "1"]) == 0
    assert "TOLERATED DROP" in capsys.readouterr().out


@pytest.mark.parametrize("placement", ["before", "after"])
def test_color_policy_has_no_effect_on_artifact(tmp_path, capsys, placement):
    paths, _ = reports(tmp_path)
    destination = tmp_path / "comparison.json"
    args = ["compare-repeated", *map(str, paths), "--report", str(destination)]
    args = ["--color", "always", *args] if placement == "before" else [*args, "--color", "always"]
    assert main(args) == 1
    assert "\x1b[" in capsys.readouterr().out
    assert "\x1b[" not in destination.read_text()


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_comparison_output_cannot_replace_either_source(tmp_path, index, alias, capsys):
    paths, _ = reports(tmp_path)
    source = paths[index]
    previous = source.read_bytes()
    output = tmp_path / "alias.json"
    if alias == "same":
        output = source
    elif alias == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    assert main(["compare-repeated", *map(str, paths), "--report", str(output)]) == 2
    assert "must differ" in capsys.readouterr().err
    assert source.read_bytes() == previous


def test_repeat_failed_cases_write_report_and_later_attempts_run(tmp_path, capsys):
    path = tmp_path / "candidate.json"
    assert (
        main(
            [
                "repeat",
                str(ROOT / "examples/refund_cases.json"),
                "--agent",
                "examples.refund_agent:run_buggy",
                "--attempts",
                "2",
                "--report",
                str(path),
            ]
        )
        == 1
    )
    saved = load_repeated(path)
    assert all(run.summary.errors == 1 and run.summary.failed == 1 for run in saved.runs)
    assert len(saved.runs) == 2
    output = capsys.readouterr().out
    assert "attempts 1-2 / 2 occurrences" in output
    assert output.count("THADAM") == 1


def test_repeat_protects_suite_path_and_invalid_count_prevents_import(tmp_path, capsys):
    suite = ROOT / "examples/refund_cases.json"
    assert main(["repeat", str(suite), "--agent", "nonexistent:run", "--report", str(suite)]) == 2
    assert "must differ" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        main(["repeat", str(suite), "--agent", "nonexistent:run", "--attempts", "1"])
    assert error.value.code == 2
    assert "Cannot load" not in capsys.readouterr().err


def test_interrupted_evaluation_never_replaces_completed_evidence(tmp_path, monkeypatch):
    destination = tmp_path / "report.json"
    destination.write_text("previous completed evidence")

    def factory():
        raise KeyboardInterrupt

    monkeypatch.setattr("thadam.cli._load_reference", lambda _: factory)
    with pytest.raises(KeyboardInterrupt):
        main(
            [
                "repeat",
                str(ROOT / "examples/refund_cases.json"),
                "--agent-factory",
                "consumer:create",
                "--report",
                str(destination),
            ]
        )
    assert destination.read_text() == "previous completed evidence"


@pytest.mark.parametrize("writer", [write_repeated, write_reliability_comparison])
def test_atomic_failure_preserves_existing_artifact(tmp_path, monkeypatch, writer):
    _, comparison = reports(tmp_path)
    path = tmp_path / "report.json"
    path.write_text("previous")

    def blocked(*_):
        raise PermissionError("blocked")

    monkeypatch.setattr(Path, "replace", blocked)
    with pytest.raises(ReportWriteError):
        writer(comparison.baseline if writer is write_repeated else comparison, path)
    assert path.read_text() == "previous"
    assert len(list(tmp_path.iterdir())) == 3


def test_invalid_policy_and_legacy_reports_produce_configuration_errors(tmp_path, capsys):
    paths, _ = reports(tmp_path)
    assert main(["compare-repeated", *map(str, paths), "--max-pass-rate-drop", "nan"]) == 2
    assert "finite number" in capsys.readouterr().err
    paths[0].write_text('{"schema_version": 3}')
    assert main(["compare-repeated", *map(str, paths)]) == 2
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("width", [20, 40, 80, 120])
def test_terminal_wraps_escapes_controls_and_preserves_colorless_meaning(tmp_path, width):
    _, comparison = reports(tmp_path)
    for formatter, value in (
        (format_repeated, comparison.candidate),
        (format_reliability_comparison, comparison),
    ):
        plain = formatter(value, width=width)
        styled = formatter(value, width=width, style=TerminalStyle(enabled=True, truecolor=True))
        assert ANSI.sub("", styled) == plain
        assert all(len(line) <= min(width, 96) for line in plain.splitlines())
    cases = [AgentCase("case\x1b[31m\nspoof", None, (OutputEquals("answer", 1),))]
    saved = run_repeated(lambda _: 0, cases, attempts=2, agent_revision="rev\x1b[31m")
    assert "\x1b" not in format_repeated(saved)
    assert "\\x1b[31m" in format_repeated(saved)
