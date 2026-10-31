"""Exercise the real CLI in a user's working directory and compare SDK results."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from examples.refund_agent import run, run_buggy
from thadam import ReportWriteError, load_suite, report_to_dict, run_suite, write_report

ROOT = Path(__file__).resolve().parents[1]


def invoke(*arguments, cwd=ROOT):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "thadam", *map(str, arguments)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.parametrize(
    ("agent", "function", "code"), [("run", run, 0), ("run_buggy", run_buggy, 1)]
)
def test_five_case_cli_example_agrees_with_sdk(tmp_path, agent, function, code):
    path = tmp_path / "nested" / "report.json"
    command = invoke(
        "run",
        "examples/refund_cases.json",
        "--agent",
        f"examples.refund_agent:{agent}",
        "--report",
        path,
    )
    assert command.returncode == code, command.stderr
    artifact = json.loads(path.read_text())
    sdk = report_to_dict(run_suite(function, load_suite(ROOT / "examples/refund_cases.json")))
    assert artifact["schema_version"] == 3
    assert artifact["run_id"]
    assert artifact["summary"] == sdk["summary"]
    assert artifact["summary"]["total"] == 5
    for actual, expected in zip(artifact["cases"], sdk["cases"]):
        assert actual.pop("duration_ms") >= 0
        expected.pop("duration_ms")
        assert actual == expected
    if code == 1:
        assert artifact["summary"] == {"total": 5, "passed": 3, "failed": 1, "errors": 1}
        assert "reject-expired" in command.stdout
        assert "expected:" in command.stdout
        assert "Order service did not respond" in command.stdout


def test_existing_user_module_loads_from_current_directory_and_logs_go_to_stderr(tmp_path):
    (tmp_path / "my_agent.py").write_text(
        'print("import log")\ndef run(value):\n    print("agent log")\n    return value\n'
    )
    (tmp_path / "cases.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "user-agent",
                        "input": {"message": "தடம்"},
                        "assertions": [
                            {"id": "echo", "type": "output_equals", "expected": {"message": "தடம்"}}
                        ],
                    }
                ],
            }
        )
    )
    command = invoke(
        "run", "cases.json", "--agent", "my_agent:run", "--report", "out/report.json", cwd=tmp_path
    )
    assert command.returncode == 0, command.stderr
    assert "user-agent" in command.stdout
    assert "import log" not in command.stdout
    assert "import log" in command.stderr
    assert "agent log" in command.stderr
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["cases"][0]["output"] == {"message": "தடம்"}


@pytest.mark.parametrize(
    "reference",
    [
        "missing",
        "absent_agent_module:run",
        "examples.refund_agent:missing",
        "examples.refund_agent:ORDERS",
    ],
)
def test_bad_agent_references_return_configuration_error(reference):
    command = invoke("run", "examples/refund_cases.json", "--agent", reference)
    assert command.returncode == 2
    assert "thadam:" in command.stderr
    assert "Traceback" not in command.stderr


def test_invalid_suite_is_rejected_before_agent_import(tmp_path):
    marker = tmp_path / "imported"
    (tmp_path / "agent.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef run(value): return value\n"
    )
    (tmp_path / "bad.json").write_text('{"schema_version": 1, "cases": []}')
    command = invoke("run", "bad.json", "--agent", "agent:run", cwd=tmp_path)
    assert command.returncode == 2
    assert not marker.exists()


def test_cli_rejects_report_overwriting_suite_and_handles_write_errors(tmp_path):
    suite = ROOT / "examples/refund_cases.json"
    original = suite.read_bytes()
    command = invoke("run", suite, "--agent", "examples.refund_agent:run", "--report", suite)
    assert command.returncode == 2
    assert suite.read_bytes() == original
    destination = tmp_path / "directory"
    destination.mkdir()
    command = invoke("run", suite, "--agent", "examples.refund_agent:run", "--report", destination)
    assert command.returncode == 2
    assert "Cannot write report" in command.stderr
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_report_failure_preserves_previous_artifact(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text("previous report")
    report = run_suite(run, load_suite(ROOT / "examples/refund_cases.json"))

    def cannot_replace(_source, _target):
        raise PermissionError("blocked destination")

    monkeypatch.setattr(Path, "replace", cannot_replace)
    with pytest.raises(ReportWriteError, match="blocked destination"):
        write_report(report, path)
    assert path.read_text() == "previous report"
    assert list(tmp_path.iterdir()) == [path]


def test_cli_help_and_argument_errors():
    assert invoke("--help").returncode == 0
    assert "0.3.0" in invoke("--version").stdout
    assert invoke("run", "examples/refund_cases.json").returncode == 2


def test_bare_command_shows_overview_without_configuration_or_execution(tmp_path):
    overview = invoke(cwd=tmp_path)
    explicit = invoke("--help", cwd=tmp_path)
    assert overview.returncode == explicit.returncode == 0
    assert overview.stdout == explicit.stdout
    assert overview.stderr == ""
    assert "Getting started" in overview.stdout
    assert "expected outcomes" in overview.stdout
    assert "python -m thadam" in overview.stdout
    assert "compare-repeated --help" in overview.stdout
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command", ["run", "compare", "repeat", "compare-repeated"])
def test_command_help_has_executable_application_examples(tmp_path, command):
    from thadam import run_repeated, write_repeated

    (tmp_path / "my_agent.py").write_text(
        "def run(value):\n    return value\ndef create():\n    return run\n"
    )
    suite = {
        "schema_version": 1,
        "cases": [
            {
                "id": "echo",
                "input": 1,
                "assertions": [{"id": "answer", "type": "output_equals", "expected": 1}],
            }
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(suite))
    cases = load_suite(path)
    if command == "compare":
        saved = run_suite(lambda value: value, cases)
        for side in ("baseline", "candidate"):
            write_report(saved, tmp_path / f"{side}.json")
    elif command == "compare-repeated":
        saved = run_repeated(lambda value: value, cases, attempts=2)
        for side in ("baseline", "candidate"):
            write_repeated(saved, tmp_path / f"{side}.json")
    help_output = invoke(command, "--help", cwd=tmp_path)
    assert help_output.returncode == 0 and help_output.stderr == ""
    assert "Examples" in help_output.stdout and "Exit codes:" in help_output.stdout
    examples = [
        line.strip().split()[1:]
        for line in help_output.stdout.splitlines()
        if line.strip().startswith(f"thadam {command} ") and "examples/" not in line
    ]
    assert len(examples) >= 2
    for arguments in examples:
        result = invoke(*arguments, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
    incomplete = invoke(command, cwd=tmp_path)
    assert incomplete.returncode == 2
    assert "required" in incomplete.stderr


def test_agent_import_cannot_exit_zero_and_report_a_successful_run(tmp_path):
    (tmp_path / "exiting.py").write_text("raise SystemExit(0)\n")
    command = invoke(
        "run", ROOT / "examples/refund_cases.json", "--agent", "exiting:run", cwd=tmp_path
    )
    assert command.returncode == 2
    assert "Cannot load agent" in command.stderr
