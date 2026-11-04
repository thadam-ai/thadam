"""Complete local dashboard flows, optional API isolation, and execution boundaries."""

import json
import time
from copy import deepcopy

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from thadam import OutputEquals, SuiteIdentity, compare_reports, run_suite
from thadam import TestCase as Case
from thadam import TestSuite as Suite
from thadam.comparison_loading import comparison_from_dict
from thadam.comparison_reporting import comparison_to_dict
from thadam.dashboard.server import create_app
from thadam.dashboard.workspace import Workspace


def suite_data(revision="1", value=1):
    return {
        "schema_version": 2,
        "suite": {"id": "echo", "revision": revision},
        "cases": [
            {
                "id": "echo",
                "input": value,
                "assertions": [{"id": "answer", "type": "output_equals", "expected": value}],
            }
        ],
    }


@pytest.fixture
def project(tmp_path):
    (tmp_path / "cases.json").write_text(json.dumps(suite_data()))
    (tmp_path / "agent.py").write_text(
        "def run(value):\n    print('agent log')\n    return value\ndef factory():\n    return run\ndef broken(value):\n    raise RuntimeError('offline')\ndef slow(value):\n    import time\n    time.sleep(20)\n    return value\n"
    )
    return tmp_path


@pytest.fixture
def client(project):
    with TestClient(create_app(project, token="test-token")) as client:
        assert (
            client.post("/api/session", headers={"x-thadam-token": "test-token"}).status_code == 200
        )
        yield client


def completed(client):
    for _ in range(150):
        jobs = client.get("/api/jobs").json()
        if jobs and jobs[0]["state"] != "running":
            return jobs[0]
        time.sleep(0.03)
    pytest.fail("Evaluation did not complete")


def run(client, reference="agent:run", attempts=1, mode="shared", path="result.json"):
    response = client.post(
        "/api/jobs",
        json={
            "suite": "cases.json",
            "reference": reference,
            "attempts": attempts,
            "mode": mode,
            "agent_revision": "test-change",
            "report": path,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_session_origin_and_path_boundary(project):
    with TestClient(create_app(project, token="secret")) as client:
        assert client.get("/api/workspace").status_code == 401
        assert client.post("/api/session", headers={"x-thadam-token": "wrong"}).status_code == 401
        response = client.post("/api/session", headers={"x-thadam-token": "secret"})
        assert (
            "HttpOnly" in response.headers["set-cookie"]
            and "SameSite=strict" in response.headers["set-cookie"]
        )
        assert (
            client.post("/api/stop", headers={"origin": "https://evil.example"}).status_code == 403
        )
        assert client.get("/api/workspace", headers={"host": "evil.example"}).status_code == 403
        for path in ("../outside.json", "/etc/passwd", ".git/config"):
            assert client.get("/api/artifact", params={"path": path}).status_code == 400
        assert client.get("/").status_code == 200
        assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_discovery_never_imports_agent_and_preserves_invalid_files(client, project):
    (project / "agent.py").write_text("raise RuntimeError('must not import')")
    (project / "broken.json").write_text('{"schema_version":2,"cases":')
    outside = project.parent / "outside.json"
    outside.write_text(json.dumps(suite_data()))
    (project / "link.json").symlink_to(outside)
    ignored = project / "node_modules"
    ignored.mkdir()
    (ignored / "secret.json").write_text(json.dumps(suite_data()))
    data = client.get("/api/workspace").json()
    assert [item["path"] for item in data["items"]] == ["cases.json"]
    assert data["invalid"][0]["path"] == "broken.json"
    assert client.get("/api/artifact", params={"path": "link.json"}).status_code == 400


def test_suite_edit_validation_revision_and_stale_guard(client, project):
    artifact = client.get("/api/artifact", params={"path": "cases.json"}).json()
    modified = suite_data(value=2)
    request = {"path": "cases.json", "data": modified, "fingerprint": artifact["fingerprint"]}
    assert client.put("/api/suite", json=request).status_code == 400
    modified["suite"]["revision"] = "2"
    response = client.put("/api/suite", json=request)
    assert response.status_code == 200, response.text
    assert client.put("/api/suite", json=request).status_code == 400
    request["path"] = "copy.json"
    request["fingerprint"] = None
    assert client.put("/api/suite", json=request).status_code == 200
    request["path"] = "bad.json"
    request["data"]["cases"][0]["assertions"] = []
    assert client.put("/api/suite", json=request).status_code == 400
    assert not (project / "bad.json").exists()


@pytest.mark.parametrize("attempts,mode", [(1, "shared"), (3, "shared"), (2, "factory")])
def test_run_factory_progress_logs_and_saved_sdk_evidence(client, project, attempts, mode):
    job = run(
        client,
        reference="agent:factory" if mode == "factory" else "agent:run",
        attempts=attempts,
        mode=mode,
    )
    finished = completed(client)
    assert finished["state"] == "completed" and finished["exit_code"] == 0
    assert finished["completed"] == finished["total"] == attempts
    artifact = client.get("/api/artifact", params={"path": "result.json"}).json()
    assert artifact["kind"] == ("run" if attempts == 1 else "repeated_run")
    assert "agent log" in client.get("/api/jobs/" + job["id"]).json()["logs"]
    assert (project / "result.json").exists()
    assert client.post("/api/jobs", json=finished["settings"]).status_code == 400


def test_run_error_is_saved_and_other_cases_continue(client, project):
    run(client, reference="agent:broken", attempts=2)
    job = completed(client)
    assert job["state"] == "completed" and job["exit_code"] == 1
    artifact = client.get("/api/artifact", params={"path": "result.json"}).json()
    assert artifact["data"]["summary"]["errors"] == 2


def test_one_job_stop_and_no_fabricated_complete_report(client, project):
    run(client, reference="agent:slow")
    response = client.post(
        "/api/jobs",
        json={
            "suite": "cases.json",
            "reference": "agent:run",
            "attempts": 1,
            "mode": "shared",
            "agent_revision": None,
            "report": "other.json",
        },
    )
    assert response.status_code == 400
    stopped = client.post("/api/stop").json()
    assert stopped["state"] == "interrupted"
    assert not (project / "result.json").exists()
    assert client.get("/api/jobs").json()[0]["state"] == "interrupted"
    run(client, path="next.json")
    assert completed(client)["state"] == "completed"


def test_settings_save_without_import_and_invalid_reference(client):
    agents = [{"name": "Echo", "reference": "does_not_exist:run", "mode": "shared"}]
    assert client.put("/api/agents", json=agents).status_code == 200
    assert client.get("/api/agents").json() == agents
    agents[0]["reference"] = "bad"
    assert client.put("/api/agents", json=agents).status_code == 400
    assert client.get("/api/agents").json()[0]["reference"] == "does_not_exist:run"


def test_compare_review_approve_and_normal_write_protection(client, project):
    run(client, path="old.json")
    completed(client)
    run(client, path="new.json")
    completed(client)
    response = client.post(
        "/api/compare",
        json={"baseline": "old.json", "candidate": "new.json", "report": "comparison.json"},
    )
    assert response.status_code == 200 and response.json()["exit_code"] == 0
    assert client.get("/api/artifact", params={"path": "comparison.json"}).status_code == 200
    review = client.post(
        "/api/review",
        json={"candidate": "new.json", "baseline": "old.json", "report": "review.json"},
    ).json()
    request = {
        "review": "review.json",
        "baseline": "old.json",
        "review_digest": review["review_digest"],
        "reviewer": "Maintainer",
        "reason": "Reviewed",
    }
    assert (
        client.post("/api/approve", json={**request, "review_digest": "stale"}).status_code == 400
    )
    response = client.post("/api/approve", json=request)
    assert response.status_code == 200, response.text
    original = (project / "old.json").read_bytes()
    assert response.json()["kind"] == "approved_baseline"
    assert (
        client.post("/api/review", json={"candidate": "new.json", "report": "old.json"}).status_code
        == 400
    )
    assert (
        client.put(
            "/api/suite",
            json={
                "path": "old.json",
                "data": suite_data(),
                "fingerprint": response.json()["fingerprint"],
            },
        ).status_code
        == 400
    )
    assert (project / "old.json").read_bytes() == original


def test_repeated_compare_and_error_blocked_review(client):
    run(client, attempts=2, path="baseline.json")
    completed(client)
    run(client, attempts=2, path="candidate.json")
    completed(client)
    response = client.post(
        "/api/compare",
        json={
            "baseline": "baseline.json",
            "candidate": "candidate.json",
            "report": "comparison.json",
            "max_pass_rate_drop": 0.05,
        },
    )
    assert response.status_code == 200 and response.json()["kind"] == "reliability_comparison"
    run(client, reference="agent:broken", attempts=2, path="errors.json")
    completed(client)
    response = client.post(
        "/api/review", json={"candidate": "errors.json", "report": "review.json"}
    )
    review = response.json()
    assert review["data"]["blockers"]
    assert (
        client.post(
            "/api/approve",
            json={
                "review": "review.json",
                "baseline": "approved.json",
                "review_digest": review["review_digest"],
                "reviewer": "Me",
                "reason": "Reviewed",
                "accept_failures": True,
            },
        ).status_code
        == 400
    )


def test_job_cannot_overwrite_suite_or_evidence(client, project):
    response = client.post(
        "/api/jobs",
        json={
            "suite": "cases.json",
            "reference": "agent:run",
            "attempts": 1,
            "mode": "shared",
            "agent_revision": None,
            "report": "cases.json",
        },
    )
    assert response.status_code == 400
    assert Workspace(project).read("cases.json")["kind"] == "suite"


def test_progress_callback_snapshots_and_failures():
    cases = Suite(SuiteIdentity("suite", "1"), (Case("case", {}, (OutputEquals("out", {}),)),))

    def callback(result):
        result.input["mutated"] = True

    report = run_suite(lambda _: {}, cases, on_case_complete=callback)
    assert report.cases[0].input == {}

    def broken(_):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        run_suite(lambda _: {}, cases, on_case_complete=broken)


def test_saved_single_comparison_loader_recomputes_classifications():
    report = run_suite(lambda _: 1, [Case("case", None, (OutputEquals("out", 1),))])
    candidate = run_suite(lambda _: 0, [Case("case", None, (OutputEquals("out", 1),))])
    raw = comparison_to_dict(compare_reports(report, candidate))
    assert comparison_from_dict(raw).exit_code == 1
    for mutate in (
        lambda r: r.update(exit_code=0),
        lambda r: r["cases"][0]["checks"][0].update(change="fixed"),
        lambda r: r["summary"].update(regressions=0),
    ):
        altered = deepcopy(raw)
        mutate(altered)
        with pytest.raises(ValueError):
            comparison_from_dict(altered)


def test_publication_continues_without_browser_polling(client, project):
    run(client)
    for _ in range(100):
        if (project / "result.json").exists():
            break
        time.sleep(0.03)
    assert (project / "result.json").exists()


def test_publishing_refuses_a_destination_created_during_execution(client, project):
    (project / "delayed.py").write_text(
        "def run(value):\n    import time\n    time.sleep(.2)\n    return value\n"
    )
    run(client, reference="delayed:run")
    (project / "result.json").write_text("preserve this")
    assert completed(client)["state"] == "error"
    assert (project / "result.json").read_text() == "preserve this"


def test_corrupt_agent_settings_and_invalid_unicode_are_rejected(client, project):
    directory = project / ".thadam/dashboard"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agents.json").write_text('{"agents":[]}')
    assert client.get("/api/agents").status_code == 400
    response = client.put(
        "/api/agents",
        content=json.dumps([{"name": "\ud800", "reference": "x:y", "mode": "shared"}]),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


def test_concurrent_suite_saves_accept_only_one_writer(project):
    from concurrent.futures import ThreadPoolExecutor

    workspace = Workspace(project)
    original = workspace.read("cases.json")

    def save(value):
        try:
            return workspace.save_suite(
                "cases.json", suite_data(revision=str(value), value=value), original["fingerprint"]
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [2, 3]))
    assert sum(result is not None for result in results) == 1


def test_every_assertion_type_round_trips_through_suite_editor_api(client):
    data = suite_data()
    data["cases"][0]["assertions"] += [
        {"id": "keys", "type": "output_has_keys", "keys": ["approved"]},
        {"id": "required", "type": "tool_called", "tool": "lookup"},
        {"id": "forbidden", "type": "tool_not_called", "tool": "delete"},
        {
            "id": "arguments",
            "type": "tool_arguments_match",
            "tool": "lookup",
            "expected": {"id": 1},
        },
    ]
    response = client.put(
        "/api/suite", json={"path": "tools.json", "data": data, "fingerprint": None}
    )
    assert response.status_code == 200
    assert len(response.json()["data"]["cases"][0]["assertions"]) == 5


def test_suite_revision_guard_distinguishes_json_booleans_from_numbers(client):
    created = client.put(
        "/api/suite",
        json={"path": "bool.json", "data": suite_data(value=True), "fingerprint": None},
    ).json()
    changed = client.put(
        "/api/suite",
        json={
            "path": "bool.json",
            "data": suite_data(value=1),
            "fingerprint": created["fingerprint"],
        },
    )
    assert changed.status_code == 400
    assert "revision" in changed.json()["error"]


@pytest.mark.parametrize("attempts,mode", [(1, "shared"), (2, "shared"), (2, "factory")])
def test_async_jobs_save_complete_evidence(client, project, attempts, mode):
    (project / "async_agent.py").write_text(
        "import asyncio\nasync def run(value):\n    await asyncio.sleep(0)\n    return value\nasync def factory():\n    return run\n"
    )
    response = client.post(
        "/api/jobs",
        json={
            "suite": "cases.json",
            "reference": "async_agent:factory" if mode == "factory" else "async_agent:run",
            "attempts": attempts,
            "mode": mode,
            "agent_revision": "async-test",
            "report": "async-result.json",
            "async_execution": True,
            "max_concurrency": 2,
        },
    )
    assert response.status_code == 200, response.text
    job = completed(client)
    assert job["state"] == "completed", job
    assert job["exit_code"] == 0
    assert job["completed"] == job["total"] == attempts
    artifact = client.get("/api/artifact", params={"path": "async-result.json"}).json()
    assert artifact["data"]["summary"]["passed"] == attempts


@pytest.mark.parametrize(
    "extra",
    [
        {"max_concurrency": 2},
        {"async_execution": "yes"},
        {"async_execution": True, "max_concurrency": True},
        {"async_execution": True, "max_concurrency": 0},
    ],
)
def test_async_job_settings_rejected_before_import(client, project, extra):
    (project / "no_import.py").write_text("raise RuntimeError('must not import')")
    response = client.post(
        "/api/jobs",
        json={
            "suite": "cases.json",
            "reference": "no_import:run",
            "attempts": 1,
            "mode": "shared",
            "agent_revision": None,
            "report": "never-written.json",
            **extra,
        },
    )
    assert response.status_code == 400
    assert client.get("/api/jobs").json() == []
    assert not (project / "never-written.json").exists()
