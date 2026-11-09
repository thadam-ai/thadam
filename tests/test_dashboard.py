"""Complete local dashboard flows, optional API isolation, and execution boundaries."""

import json
import time
from copy import deepcopy

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from thadam import OutputEquals, SuiteIdentity, compare_reports, report_to_dict, run_suite
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


@pytest.mark.parametrize("attempts,async_execution", [(1, False), (2, False), (2, True)])
def test_dashboard_fixture_configuration_execution_and_saved_evidence(
    client, project, attempts, async_execution
):
    data = suite_data()
    data["schema_version"] = 3
    data["cases"][0]["tool_fixtures"] = {
        "lookup": {
            "steps": [
                {"type": "raise", "error": "ConnectionError", "message": "offline"},
                {"type": "return", "value": 1},
            ],
            "repeat_last": False,
        }
    }
    data["cases"][0]["assertions"].append(
        {
            "id": "retry-count",
            "type": "tool_call_count",
            "tool": "lookup",
            "min_calls": 2,
            "max_calls": 2,
        }
    )
    response = client.put(
        "/api/suite", json={"path": "fixtures.json", "data": data, "fingerprint": None}
    )
    assert response.status_code == 200, response.text
    (project / "recovery.py").write_text(
        "def create(tools):\n    def run(value):\n        try:\n            return tools['lookup'](value)\n        except ConnectionError:\n            return tools['lookup'](value)\n    return run\n"
    )
    settings = {
        "suite": "fixtures.json",
        "reference": "recovery:create",
        "attempts": attempts,
        "mode": "shared",
        "agent_revision": "v1",
        "report": "recovery.json",
        "async_execution": async_execution,
        "max_concurrency": 2 if async_execution else 1,
    }
    assert client.post("/api/jobs", json=settings).status_code == 400
    settings["mode"] = "fixtures"
    agent = [{"name": "Recovery", "reference": "recovery:create", "mode": "fixtures"}]
    assert client.put("/api/agents", json=agent).status_code == 200
    assert client.get("/api/agents").json() == agent
    response = client.post("/api/jobs", json=settings)
    assert response.status_code == 200, response.text
    result = completed(client)
    assert result["state"] == "completed" and result["exit_code"] == 0
    saved = client.get("/api/artifact", params={"path": "recovery.json"}).json()["data"]
    assert saved["schema_version"] == (5 if attempts == 1 else 2)
    run = saved if attempts == 1 else saved["runs"][0]
    assert len(run["cases"][0]["events"]) == 2
    assert run["cases"][0]["tool_fixtures"] == data["cases"][0]["tool_fixtures"]


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


def test_guided_fix_verification_saves_candidate_and_comparison_from_approved_baseline(
    client, project
):
    suite = {
        "schema_version": 2,
        "suite": {"id": "refund-fix", "revision": "v1"},
        "cases": [
            {
                "id": "refund",
                "input": {"order": "42"},
                "assertions": [{"id": "amount", "type": "output_equals", "expected": 25}],
            }
        ],
    }
    (project / "reviewed.json").write_text(json.dumps(suite))
    (project / "before.py").write_text("def run(value):\n    return 30\n")
    (project / "after.py").write_text("def run(value):\n    return 25\n")

    def start(reference, report, verification=None):
        settings = {
            "suite": "reviewed.json",
            "reference": reference,
            "mode": "shared",
            "attempts": 1,
            "agent_revision": None,
            "report": report,
        }
        if verification:
            settings["verification"] = verification
        response = client.post(
            "/api/jobs",
            json=settings,
        )
        assert response.status_code == 200, response.text
        return response.json()

    baseline_job = start("before:run", "baseline.json")
    assert completed(client)["id"] == baseline_job["id"]
    review = client.post(
        "/api/review", json={"candidate": "baseline.json", "report": "review.json"}
    ).json()
    approved = client.post(
        "/api/approve",
        json={
            "review": "review.json",
            "baseline": "approved.json",
            "review_digest": review["review_digest"],
            "reviewer": "Maintainer",
            "reason": "Verified baseline",
            "accept_failures": True,
        },
    )
    assert approved.status_code == 200, approved.text
    candidate_job = start(
        "after:run",
        "candidate.json",
        {
            "baseline": "approved.json",
            "baseline_fingerprint": approved.json()["fingerprint"],
            "report": "verification.json",
            "max_pass_rate_drop": 0,
        },
    )
    finished = completed(client)
    assert finished["id"] == candidate_job["id"]
    assert finished["state"] == "completed"
    assert "verification_error" not in finished

    baseline = client.get("/api/artifact", params={"path": "baseline.json"}).json()
    candidate = client.get("/api/artifact", params={"path": "candidate.json"}).json()
    assert baseline["data"]["summary"]["failed"] == 1
    assert candidate["data"]["summary"]["passed"] == 1
    saved = client.get("/api/artifact", params={"path": "verification.json"}).json()
    assert saved["kind"] == "comparison"
    assert saved["data"]["exit_code"] == 0
    assert saved["data"]["cases"][0]["change"] == "fixed"
    assert saved["data"]["cases"][0]["checks"][0]["change"] == "fixed"


def test_guided_verification_keeps_changed_suite_contract_incompatible(client, project):
    original = {
        "schema_version": 2,
        "suite": {"id": "contracts", "revision": "v1"},
        "cases": [
            {
                "id": "first",
                "input": 1,
                "assertions": [{"id": "one", "type": "output_equals", "expected": 1}],
            }
        ],
    }
    (project / "contracts.json").write_text(json.dumps(original))
    (project / "agent.py").write_text("def run(value):\n    return value\n")

    def start(path):
        response = client.post(
            "/api/jobs",
            json={
                "suite": "contracts.json",
                "reference": "agent:run",
                "mode": "shared",
                "attempts": 1,
                "agent_revision": None,
                "report": path,
            },
        )
        assert response.status_code == 200, response.text
        completed(client)

    start("old-contract.json")
    current = client.get("/api/artifact", params={"path": "contracts.json"}).json()
    revised = deepcopy(original)
    revised["suite"]["revision"] = "v2"
    revised["cases"].append(
        {
            "id": "added",
            "input": 2,
            "assertions": [{"id": "two", "type": "output_equals", "expected": 2}],
        }
    )
    saved_suite = client.put(
        "/api/suite",
        json={"path": "contracts.json", "data": revised, "fingerprint": current["fingerprint"]},
    )
    assert saved_suite.status_code == 200, saved_suite.text
    start("new-contract.json")
    comparison = client.post(
        "/api/compare",
        json={
            "baseline": "old-contract.json",
            "candidate": "new-contract.json",
            "report": "incompatible-contract.json",
        },
    )
    assert comparison.status_code == 200, comparison.text
    result = client.get("/api/artifact", params={"path": "incompatible-contract.json"}).json()
    assert result["data"]["exit_code"] == 2
    assert result["data"]["cases"][0]["change"] == "incompatible"
    assert any("revision" in message.lower() for message in result["data"]["cases"][0]["issues"])


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


@pytest.mark.parametrize("attempt", [None, 2])
def test_regression_case_review_and_guarded_append(client, project, attempt):
    from thadam import report_to_dict, run_repeated
    from thadam.repetition_reporting import repeated_to_dict

    cases = [Case("observed", {"value": 1}, (OutputEquals("answer", {"value": 2}),))]
    data = (
        report_to_dict(run_suite(lambda value: value, cases))
        if attempt is None
        else repeated_to_dict(run_repeated(lambda value: value, cases, attempts=2))
    )
    path = project / "observed.json"
    path.write_text(json.dumps(data))
    original = path.read_bytes()
    source = client.get("/api/artifact", params={"path": "observed.json"}).json()
    created = client.post(
        "/api/regression/create",
        json={
            "path": "observed.json",
            "fingerprint": source["fingerprint"],
            "case_id": "observed",
            "attempt": attempt,
        },
    )
    assert created.status_code == 200, created.text
    draft = created.json()
    assert draft["data"]["case"]["assertions"] == []
    assert draft["data"]["source"]["attempt"] == attempt
    assert draft["data"]["source"]["run"]["cases"][0]["output"] == {"value": 1}
    body = {
        "path": draft["path"],
        "fingerprint": draft["fingerprint"],
        "destination": "cases.json",
        "expected_fingerprint": None,
        "suite_id": "echo",
        "revision": "2",
    }
    assert client.post("/api/regression/preview", json=body).status_code == 400
    assert (
        client.post(
            "/api/regression/review",
            json={
                "path": draft["path"],
                "fingerprint": draft["fingerprint"],
                "case": draft["data"]["case"],
                "reviewed": True,
            },
        ).status_code
        == 400
    )
    case = {
        **draft["data"]["case"],
        "assertions": [{"id": "correct", "type": "output_equals", "expected": {"value": 2}}],
    }
    review_body = {
        "path": draft["path"],
        "fingerprint": draft["fingerprint"],
        "case": case,
        "reviewed": True,
    }
    review = client.post("/api/regression/review", json=review_body)
    assert review.status_code == 200, review.text
    draft = review.json()
    assert client.post("/api/regression/review", json=review_body).status_code == 400
    target = client.get("/api/artifact", params={"path": "cases.json"}).json()
    body.update(fingerprint=draft["fingerprint"], expected_fingerprint=target["fingerprint"])
    assert client.post("/api/regression/preview", json={**body, "revision": "1"}).status_code == 400
    preview = client.post("/api/regression/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["cases"]) == 2
    assert (
        client.post("/api/regression/publish", json={**body, "confirmed": False}).status_code == 400
    )
    saved = client.post("/api/regression/publish", json={**body, "confirmed": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"] == preview.json()
    assert (
        client.post("/api/regression/publish", json={**body, "confirmed": True}).status_code == 400
    )
    new_body = {
        **body,
        "destination": "new-suite.json",
        "expected_fingerprint": None,
        "suite_id": "new",
        "revision": "v1",
        "confirmed": True,
    }
    fresh = client.post("/api/regression/publish", json=new_body)
    assert fresh.status_code == 200, fresh.text
    assert client.post("/api/regression/publish", json=new_body).status_code == 400
    protected = {
        **body,
        "destination": "observed.json",
        "expected_fingerprint": source["fingerprint"],
        "confirmed": True,
    }
    assert client.post("/api/regression/publish", json=protected).status_code == 400
    assert path.read_bytes() == original
    assert client.get("/api/artifact", params={"path": draft["path"]}).json()["data"]["reviewed"]


def test_regression_creation_rejects_stale_source_and_bad_attempt(client, project):
    from thadam import report_to_dict

    data = report_to_dict(run_suite(lambda value: value, [Case("a", 1, (OutputEquals("a", 1),))]))
    (project / "run.json").write_text(json.dumps(data))
    source = client.get("/api/artifact", params={"path": "run.json"}).json()
    body = {
        "path": "run.json",
        "fingerprint": source["fingerprint"],
        "case_id": "a",
        "attempt": None,
    }
    for changes in [
        {"fingerprint": "stale"},
        {"attempt": True},
        {"case_id": "absent"},
        {"path": "../run.json"},
    ]:
        assert client.post("/api/regression/create", json={**body, **changes}).status_code == 400
    assert not (project / "regression-drafts").exists()


def test_recorded_example_preview_import_review_and_search(client, project):
    examples = [
        {
            "id": "example-1",
            "input": {"email": "person@example.com"},
            "expected": {"ok": True},
            "context": {"phone": "555-0100"},
            "tags": ["refund", "reviewed-source"],
        },
        {
            "id": "example-2",
            "input": {"email": "missing expectation"},
            "tags": ["needs-check"],
        },
        {
            "id": "example-3",
            "input": {"email": "person@example.com"},
            "expected": {"ok": True},
        },
    ]
    content = "\n".join(json.dumps(item) for item in examples) + "\n"
    (project / "examples.jsonl").write_text(content)
    mapping = {
        "source_id": "id",
        "input": "input",
        "expected": "expected",
        "context": "context",
        "tags": "tags",
    }
    preview_response = client.post(
        "/api/recorded-examples/preview",
        json={
            "path": "examples.jsonl",
            "format": "jsonl",
            "mapping": mapping,
            "mask_fields": ["input.email", "context.phone"],
        },
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["summary"] == {
        "total": 3,
        "valid": 3,
        "invalid": 0,
        "duplicates": 1,
        "already_imported": 0,
    }
    assert "person@example.com" not in preview_response.text
    assert "555-0100" not in preview_response.text
    assert preview["rows"][0]["record"]["context"]["phone"] == "[REDACTED]"
    assert preview["rows"][2]["duplicate_of"] == 1

    duplicate_without_ack = client.post(
        "/api/recorded-examples/import",
        json={
            "path": "examples.jsonl",
            "format": "jsonl",
            "mapping": mapping,
            "mask_fields": ["input.email", "context.phone"],
            "fingerprint": preview["fingerprint"],
            "selected_rows": [3],
            "acknowledged_duplicates": [],
        },
    )
    assert duplicate_without_ack.status_code == 400
    assert "acknowledge duplicate" in duplicate_without_ack.json()["error"]
    assert not (project / "regression-drafts").exists()

    imported_response = client.post(
        "/api/recorded-examples/import",
        json={
            "path": "examples.jsonl",
            "format": "jsonl",
            "mapping": mapping,
            "mask_fields": ["input.email", "context.phone"],
            "fingerprint": preview["fingerprint"],
            "selected_rows": [1, 2, 3],
            "acknowledged_duplicates": [3],
        },
    )
    assert imported_response.status_code == 200, imported_response.text
    drafts = imported_response.json()["drafts"]
    assert len(drafts) == 3
    by_source = {draft["data"]["source"]["source_id"]: draft for draft in drafts}
    reviewed_example = by_source["example-1"]["data"]
    assert reviewed_example["schema_version"] == 2
    assert reviewed_example["source"]["record"]["input"]["email"] == "[REDACTED]"
    assert reviewed_example["source"]["record"]["context"]["phone"] == "[REDACTED]"
    assert reviewed_example["case"]["assertions"] == [
        {"id": "recorded-expected-output", "type": "output_equals", "expected": {"ok": True}}
    ]
    assert reviewed_example["reviewed"] is False
    incomplete = by_source["example-2"]["data"]
    assert incomplete["case"]["assertions"] == []
    assert incomplete["source"]["record"]["tags"] == ["needs-check"]
    assert by_source["example-3"]["data"]["source"]["duplicate_reasons"] == ["input"]
    rejected = client.post(
        "/api/regression/review",
        json={
            "path": by_source["example-2"]["path"],
            "fingerprint": by_source["example-2"]["fingerprint"],
            "case": incomplete["case"],
            "reviewed": True,
        },
    )
    assert rejected.status_code == 400
    assert "at least one check" in rejected.json()["error"]

    catalog = client.get("/api/workspace").json()
    imported_item = next(item for item in catalog["items"] if item["source_id"] == "example-1")
    assert imported_item["review_state"] == "unreviewed"
    assert imported_item["review_tags"] == ["refund", "reviewed-source"]
    assert imported_item["case_id"] == reviewed_example["case"]["id"]

    refreshed = client.post(
        "/api/recorded-examples/preview",
        json={
            "path": "examples.jsonl",
            "format": "jsonl",
            "mapping": mapping,
            "mask_fields": ["input.email", "context.phone"],
        },
    )
    assert [row["already_imported"] for row in refreshed.json()["rows"]] == [True, True, True]
    refused_reimport = client.post(
        "/api/recorded-examples/import",
        json={
            "path": "examples.jsonl",
            "format": "jsonl",
            "mapping": mapping,
            "mask_fields": ["input.email", "context.phone"],
            "fingerprint": refreshed.json()["fingerprint"],
            "selected_rows": [1],
            "acknowledged_duplicates": [],
        },
    )
    assert refused_reimport.status_code == 400
    assert "already imported" in refused_reimport.json()["error"]


def test_recorded_example_import_rejects_stale_source_and_outside_paths(client, project):
    (project / "examples.csv").write_text("id,prompt\na,hello\n")
    body = {
        "path": "examples.csv",
        "format": "csv",
        "mapping": {"source_id": "id", "input": "prompt"},
        "mask_fields": [],
    }
    preview = client.post("/api/recorded-examples/preview", json=body)
    assert preview.status_code == 200, preview.text
    changed = project / "examples.csv"
    changed.write_text("id,prompt\na,changed\n")
    result = client.post(
        "/api/recorded-examples/import",
        json={
            **body,
            "fingerprint": preview.json()["fingerprint"],
            "selected_rows": [2],
            "acknowledged_duplicates": [],
        },
    )
    assert result.status_code == 400
    assert "changed" in result.json()["error"]
    assert not (project / "regression-drafts").exists()
    for path in ("../outside.csv", ".hidden.csv"):
        assert (
            client.post("/api/recorded-examples/preview", json={**body, "path": path}).status_code
            == 400
        )


@pytest.mark.parametrize("attempt", [None, 2])
@pytest.mark.parametrize("append", [False, True])
def test_regression_from_fixture_run_retains_scripts_without_executing_them(
    client, project, attempt, append
):
    from thadam import (
        FixtureAgent,
        ToolCallCount,
        ToolRaise,
        ToolReturn,
        ToolScript,
        load_suite,
        run_repeated,
    )
    from thadam.fixtures import fixtures_to_dict
    from thadam.repetition_reporting import repeated_to_dict

    calls = []
    scripts = {
        "lookup": ToolScript(
            (ToolRaise("ConnectionError", "offline"), ToolReturn(1), ToolReturn(99)),
            repeat_last=True,
        )
    }

    def factory(tools):
        calls.append(True)

        def invoke(value):
            try:
                return tools["lookup"](value)
            except ConnectionError:
                return tools["lookup"](value)

        return invoke

    cases = [
        Case(
            "failure",
            1,
            (OutputEquals("answer", 2), ToolCallCount("attempts", "lookup", 2, 2)),
            tool_fixtures=scripts,
        )
    ]
    data = (
        report_to_dict(run_suite(FixtureAgent(factory), cases))
        if attempt is None
        else repeated_to_dict(run_repeated(FixtureAgent(factory), cases, attempts=2))
    )
    original_calls = len(calls)
    path = project / "fixture-run.json"
    path.write_text(json.dumps(data))
    original_bytes = path.read_bytes()
    source = client.get("/api/artifact", params={"path": path.name}).json()
    created = client.post(
        "/api/regression/create",
        json={
            "path": path.name,
            "fingerprint": source["fingerprint"],
            "case_id": "failure",
            "attempt": attempt,
        },
    )
    assert created.status_code == 200, created.text
    draft = created.json()
    assert draft["data"]["case"]["assertions"] == []
    reviewed_case = {
        **draft["data"]["case"],
        "assertions": [{"id": "reviewed", "type": "output_equals", "expected": 2}],
    }
    response = client.post(
        "/api/regression/review",
        json={
            "path": draft["path"],
            "fingerprint": draft["fingerprint"],
            "case": reviewed_case,
            "reviewed": True,
        },
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    target = suite_data()
    target["schema_version"] = 3
    target["cases"][0]["tool_fixtures"] = fixtures_to_dict(scripts)
    response = client.put(
        "/api/suite", json={"path": "fixture-suite.json", "data": target, "fingerprint": None}
    )
    assert response.status_code == 200
    body = {
        "path": draft["path"],
        "fingerprint": draft["fingerprint"],
        "destination": "fixture-suite.json" if append else "regressions.json",
        "expected_fingerprint": response.json()["fingerprint"] if append else None,
        "suite_id": "echo" if append else "regressions",
        "revision": "2",
    }
    # Appending fixture evidence to an ordinary suite must require explicit migration.
    plain = client.get("/api/artifact", params={"path": "cases.json"}).json()
    refused = client.post(
        "/api/regression/preview",
        json={
            **body,
            "destination": "cases.json",
            "expected_fingerprint": plain["fingerprint"],
            "suite_id": "echo",
        },
    )
    assert refused.status_code == 400 and "fixture suite" in refused.json()["error"]
    preview = client.post("/api/regression/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["schema_version"] == 3
    assert preview.json()["cases"][-1]["tool_fixtures"] == fixtures_to_dict(scripts)
    saved = client.post("/api/regression/publish", json={**body, "confirmed": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"] == preview.json()
    assert path.read_bytes() == original_bytes and len(calls) == original_calls
    report = run_suite(FixtureAgent(factory), load_suite(project / body["destination"]))
    assert report.cases[-1].status == "failed"
    assert [event.status for event in report.cases[-1].events] == ["error", "completed"]


def test_ordinary_regression_can_be_appended_to_fixture_suite(client, project):
    data = report_to_dict(
        run_suite(lambda value: value, [Case("plain", 1, (OutputEquals("out", 1),))])
    )
    (project / "plain.json").write_text(json.dumps(data))
    source = client.get("/api/artifact", params={"path": "plain.json"}).json()
    created = client.post(
        "/api/regression/create",
        json={
            "path": "plain.json",
            "fingerprint": source["fingerprint"],
            "case_id": "plain",
            "attempt": None,
        },
    ).json()
    case = {
        **created["data"]["case"],
        "assertions": [{"id": "reviewed", "type": "output_equals", "expected": 1}],
    }
    reviewed = client.post(
        "/api/regression/review",
        json={
            "path": created["path"],
            "fingerprint": created["fingerprint"],
            "case": case,
            "reviewed": True,
        },
    ).json()
    target = suite_data()
    target["schema_version"] = 3
    target["cases"][0]["tool_fixtures"] = {}
    saved = client.put(
        "/api/suite", json={"path": "fixture-suite.json", "data": target, "fingerprint": None}
    ).json()
    result = client.post(
        "/api/regression/publish",
        json={
            "path": reviewed["path"],
            "fingerprint": reviewed["fingerprint"],
            "destination": "fixture-suite.json",
            "expected_fingerprint": saved["fingerprint"],
            "suite_id": "echo",
            "revision": "2",
            "confirmed": True,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["data"]["cases"][-1]["tool_fixtures"] == {}


def test_regression_from_simulation_preserves_turns_and_state_in_schema_four(client, project):
    from examples.refund_conversation_agent import create
    from thadam import FixtureAgent, load_suite

    cases = load_suite("examples/refund_conversation_cases.json")
    report = run_suite(FixtureAgent(create), cases)
    source_path = project / "simulation.json"
    source_path.write_text(json.dumps(report_to_dict(report)))
    source = client.get("/api/artifact", params={"path": source_path.name}).json()
    created = client.post(
        "/api/regression/create",
        json={
            "path": source_path.name,
            "fingerprint": source["fingerprint"],
            "case_id": report.cases[0].id,
            "attempt": None,
        },
    )
    assert created.status_code == 200, created.text
    draft = created.json()
    draft_case = draft["data"]["case"]
    assert [turn["id"] for turn in draft_case["conversation"]] == [
        "initial-request",
        "correction",
        "confirmation",
        "repeat-request",
    ]
    assert draft_case["state_fixture"] == {"initial": {"refunds": []}}
    assert draft_case["tool_fixtures"] == {}
    draft_case["conversation"][1]["message"] = "Correction: use the reviewed $25 amount."
    draft_case["state_fixture"]["initial"]["reviewed_marker"] = True
    draft_case["assertions"] = [
        {
            "id": "refund-result",
            "type": "output_equals",
            "expected": report.cases[0].output,
        }
    ]
    reviewed = client.post(
        "/api/regression/review",
        json={
            "path": draft["path"],
            "fingerprint": draft["fingerprint"],
            "case": draft_case,
            "reviewed": True,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    draft = reviewed.json()
    body = {
        "path": draft["path"],
        "fingerprint": draft["fingerprint"],
        "destination": "simulation-regressions.json",
        "expected_fingerprint": None,
        "suite_id": "simulation-regressions",
        "revision": "v1",
    }
    preview = client.post("/api/regression/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["schema_version"] == 4
    assert preview.json()["cases"][0]["conversation"] == draft_case["conversation"]
    assert preview.json()["cases"][0]["state_fixture"] == draft_case["state_fixture"]
    published = client.post("/api/regression/publish", json={**body, "confirmed": True})
    assert published.status_code == 200, published.text

    replay = run_suite(FixtureAgent(create), load_suite(project / body["destination"]))
    assert replay.summary.passed == 1
