"""CLI and optional dashboard boundaries for explicit execution policies."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from thadam import load_report
from thadam.repetition_loading import load_repeated

ROOT = Path(__file__).resolve().parents[1]
MODULE = """from pathlib import Path
from thadam import EnvironmentHooks
MARKER = Path(__file__).with_name("lifecycle.txt")
def record(value):
    with MARKER.open("a") as stream:
        stream.write(value + "\\n")
def setup():
    record("setup")
    return ["dirty"]
def reset(handle):
    record("reset")
    handle.clear()
def cleanup(handle):
    record("cleanup")
environment = EnvironmentHooks(setup, reset, cleanup)
def create(tools):
    def agent(request):
        if request["turn_id"] == "inspect":
            return list(tools.environment)
        tools.environment.append("done")
        return list(tools.environment)
    return agent
"""


@pytest.fixture
def boundary_project(tmp_path):
    (tmp_path / "boundary_agent.py").write_text(MODULE)
    data = {
        "schema_version": 4,
        "suite": {"id": "boundaries", "revision": "v1"},
        "cases": [
            {
                "id": "conversation",
                "input": None,
                "tool_fixtures": {},
                "state_fixture": None,
                "conversation": [
                    {"id": "inspect", "message": "inspect"},
                    {"id": "change", "message": "change"},
                ],
                "assertions": [
                    {
                        "id": "reset",
                        "type": "conversation_output_equals",
                        "turn_id": "inspect",
                        "expected": [],
                    },
                    {"id": "done", "type": "output_equals", "expected": ["done"]},
                ],
            }
        ],
    }
    (tmp_path / "cases.json").write_text(json.dumps(data))
    return tmp_path


def cli(project, *arguments):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "thadam", *arguments],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.parametrize("repeated", [False, True])
def test_cli_deadline_environment_reference_and_report_roundtrip(boundary_project, repeated):
    arguments = [
        "repeat" if repeated else "run",
        "cases.json",
        "--fixture-factory",
        "boundary_agent:create",
        "--environment",
        "boundary_agent:environment",
        "--max-turns",
        "2",
        "--case-timeout",
        "5",
        "--cleanup-timeout",
        "0.5",
        "--report",
        "report.json",
    ]
    if repeated:
        arguments.extend(["--attempts", "2"])
    result = cli(boundary_project, *arguments)
    assert result.returncode == 0, result.stderr
    report = (load_repeated if repeated else load_report)(boundary_project / "report.json")
    assert not report.has_failures
    assert (boundary_project / "lifecycle.txt").read_text().splitlines() == [
        "setup",
        "reset",
        "cleanup",
    ] * (2 if repeated else 1)


def test_cli_turn_bound_retains_prior_response_and_cleans_up(boundary_project):
    result = cli(
        boundary_project,
        "run",
        "cases.json",
        "--fixture-factory",
        "boundary_agent:create",
        "--environment",
        "boundary_agent:environment",
        "--max-turns",
        "1",
        "--report",
        "report.json",
    )
    assert result.returncode == 1, result.stderr
    report = load_report(boundary_project / "report.json")
    assert report.summary.errors == 1
    assert len(report.cases[0].conversation_results) == 1
    assert report.cases[0].conversation_results[0].output == []
    assert (boundary_project / "lifecycle.txt").read_text().splitlines()[-1] == "cleanup"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--case-timeout", "0"],
        ["--max-turns", "-1"],
        ["--cleanup-timeout", "0.2"],
        ["--environment", "boundary_agent:environment"],
    ],
)
def test_cli_invalid_settings_reject_before_import_or_hook(boundary_project, arguments):
    (boundary_project / "never.py").write_text('raise RuntimeError("must not import")')
    result = cli(boundary_project, "run", "cases.json", "--agent", "never:run", *arguments)
    assert result.returncode == 2, result.stderr
    assert "must not import" not in result.stderr
    assert not (boundary_project / "lifecycle.txt").exists()


@pytest.fixture
def dashboard_client(boundary_project):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from thadam.dashboard.server import create_app

    with TestClient(create_app(boundary_project, token="test-token")) as client:
        assert (
            client.post("/api/session", headers={"x-thadam-token": "test-token"}).status_code == 200
        )
        yield client


def specification(**extra):
    return {
        "suite": "cases.json",
        "reference": "boundary_agent:create",
        "mode": "fixtures",
        "attempts": 1,
        "agent_revision": "test",
        "report": "report.json",
        **extra,
    }


def completed(client):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()
        if jobs and jobs[0]["state"] != "running":
            return jobs[0]
        time.sleep(0.03)
    pytest.fail("Dashboard evaluation did not finish")


def test_dashboard_deadline_environment_settings_reach_worker(dashboard_client, boundary_project):
    settings = specification(
        environment="boundary_agent:environment",
        execution_limits={"max_turns": 2, "timeout_seconds": 5, "cleanup_timeout_seconds": 0.5},
    )
    response = dashboard_client.post("/api/jobs", json=settings)
    assert response.status_code == 200, response.text
    job = completed(dashboard_client)
    assert job["state"] == "completed" and job["exit_code"] == 0, job
    assert job["settings"]["environment"] == settings["environment"]
    assert job["settings"]["execution_limits"] == settings["execution_limits"]
    assert not load_report(boundary_project / "report.json").has_failures
    assert (boundary_project / "lifecycle.txt").read_text().splitlines() == [
        "setup",
        "reset",
        "cleanup",
    ]


@pytest.mark.parametrize(
    "extra",
    [
        {
            "execution_limits": {
                "max_turns": True,
                "timeout_seconds": None,
                "cleanup_timeout_seconds": 1,
            }
        },
        {"execution_limits": {"max_turns": 1}},
        {
            "execution_limits": {
                "max_turns": None,
                "timeout_seconds": 0,
                "cleanup_timeout_seconds": 1,
            }
        },
        {
            "execution_limits": {
                "max_turns": 1,
                "timeout_seconds": None,
                "cleanup_timeout_seconds": 1,
                "unknown": 2,
            }
        },
        {"environment": "boundary_agent:environment", "mode": "shared"},
        {"environment": "boundary_agent"},
        {"environment": 42},
    ],
)
def test_dashboard_invalid_settings_reject_before_import_or_hooks(
    dashboard_client, boundary_project, extra
):
    (boundary_project / "never.py").write_text('raise RuntimeError("must not import")')
    response = dashboard_client.post(
        "/api/jobs", json=specification(reference="never:create", **extra)
    )
    assert response.status_code == 400, response.text
    assert dashboard_client.get("/api/jobs").json() == []
    assert not (boundary_project / "lifecycle.txt").exists()
    assert not (boundary_project / "report.json").exists()
