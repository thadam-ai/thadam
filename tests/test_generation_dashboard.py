"""Authenticated project-confined generation/review APIs and job publication."""

import json
from unittest.mock import Mock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from tests.test_generation import Provider, candidate, context, draft
from thadam.dashboard.server import create_app
from thadam.generation import load_draft, write_draft
from thadam.reporting import write_json_artifact
from thadam.suite_writing import file_fingerprint


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THADAM_CONFIG_DIR", str(tmp_path / ".private-credentials"))
    write_draft(draft(), tmp_path / "draft.json")
    with TestClient(create_app(tmp_path, token="token")) as client:
        client.post("/api/session", headers={"x-thadam-token": "token"})
        yield client


def test_preview_sends_no_context_until_explicit_generation(client, monkeypatch):
    from thadam.providers.openai import OpenAIProvider

    invoke = Mock(side_effect=AssertionError("No network during preview"))
    monkeypatch.setattr(OpenAIProvider, "generate", invoke)
    response = client.post("/api/generate/preview", json=context())
    assert response.status_code == 200
    assert response.json()["request"]["description"] == context()["description"]
    assert "instructions" in response.json()
    invoke.assert_not_called()
    catalog = client.get("/api/workspace").json()
    assert catalog["items"][0]["kind"] == "scenario_draft"
    assert catalog["items"][0]["cases"] == 1
    assert catalog["invalid"] == []


def test_draft_review_preview_and_explicit_suite_write(client, tmp_path):
    artifact = client.get("/api/artifact?path=draft.json").json()
    body = {
        "path": artifact["path"],
        "fingerprint": artifact["fingerprint"],
        "index": 0,
        "decision": "accepted",
        "case": candidate()["case"],
    }
    response = client.post("/api/draft/review", json=body)
    assert response.status_code == 200, response.text
    assert client.post("/api/draft/review", json=body).status_code == 400
    saved = response.json()
    data = {
        "path": "draft.json",
        "fingerprint": saved["fingerprint"],
        "suite_id": "echo",
        "revision": "1",
    }
    preview = client.post("/api/draft/preview", json=data)
    assert preview.status_code == 200
    assert not (tmp_path / "cases.json").exists()
    result = client.post(
        "/api/draft/publish",
        json={**data, "destination": "cases.json", "expected_fingerprint": None},
    )
    assert result.status_code == 200, result.text
    assert result.json()["kind"] == "suite"
    assert client.get("/api/jobs").json() == []
    assert load_draft(tmp_path / "draft.json")["candidates"][0]["decision"] == "accepted"
    assert (
        client.post(
            "/api/draft/publish",
            json={**data, "destination": "cases.json", "expected_fingerprint": None},
        ).status_code
        == 400
    )


def test_acceptance_rejects_incomplete_checks_and_path_escape(client):
    artifact = client.get("/api/artifact?path=draft.json").json()
    incomplete = candidate(assertions=[])["case"]
    body = {
        "path": "draft.json",
        "fingerprint": artifact["fingerprint"],
        "index": 0,
        "decision": "accepted",
        "case": incomplete,
    }
    assert client.post("/api/draft/review", json=body).status_code == 400
    assert (
        client.post("/api/draft/review", json={**body, "path": "../draft.json"}).status_code == 400
    )
    assert client.post("/api/draft/review", json={**body, "decision": "pending"}).status_code == 200
    assert client.get("/api/draft/issues?path=draft.json").json()[0]


def test_connection_endpoints_never_expose_credentials(client, tmp_path, monkeypatch):
    from thadam.providers.credentials import CredentialStore

    store = CredentialStore()
    with store.locked():
        store.write(
            {
                "api_key": "private-key",
                "chatgpt": {
                    "access_token": "private-token",
                    "refresh_token": "refresh-secret",
                    "email": "user@example.com",
                    "scopes": [],
                },
            }
        )
    status = client.get("/api/providers")
    assert status.status_code == 200
    assert status.json()["api_key"] and status.json()["chatgpt"]
    assert "private-" not in status.text and "refresh-secret" not in status.text
    assert "connections.json" not in client.get("/api/workspace").text
    assert client.post("/api/providers/notice", json={}).status_code == 200
    assert client.get("/api/providers").json()["plan_notice_ack"]
    assert (
        client.post("/api/providers/disconnect", json={"connection": "api_key"}).status_code == 200
    )
    assert not client.get("/api/providers").json()["api_key"]
    assert client.get("/api/providers/models?connection=invalid").status_code == 400


def test_source_staleness_blocks_saving_even_to_new_destination(client, tmp_path):
    from thadam.generation import review_candidate

    source = {
        "schema_version": 2,
        "suite": {"id": "echo", "revision": "1"},
        "cases": [candidate("old")["case"]],
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source))
    data = draft(
        source={"path": "source.json", "fingerprint": file_fingerprint(path), "data": source}
    )
    data = review_candidate(data, 0, decision="accepted")
    write_draft(data, tmp_path / "sourced.json")
    artifact = client.get("/api/artifact?path=sourced.json").json()
    path.write_text(json.dumps({**source, "suite": {"id": "echo", "revision": "other"}}))
    response = client.post(
        "/api/draft/publish",
        json={
            "path": "sourced.json",
            "fingerprint": artifact["fingerprint"],
            "suite_id": "echo",
            "revision": "2",
            "destination": "new.json",
            "expected_fingerprint": None,
        },
    )
    assert response.status_code == 400
    assert "Source suite changed" in response.text
    assert not (tmp_path / "new.json").exists()


def test_real_generation_worker_writes_only_a_draft(tmp_path, monkeypatch):
    from thadam.dashboard import worker
    from thadam.providers.openai import OpenAIProvider

    monkeypatch.setattr(
        OpenAIProvider, "generate", lambda self, request: Provider().generate(request)
    )
    write_json_artifact(
        {
            "kind": "generation",
            "connection": "chatgpt",
            "model": "fixture",
            "request": context(),
            "source": None,
        },
        tmp_path / "spec.json",
    )
    monkeypatch.setattr("sys.argv", ["worker", str(tmp_path)])
    assert worker.main() == 0
    assert load_draft(tmp_path / "result.json")["candidates"][0]["decision"] == "pending"
    assert not (tmp_path / "suite.json").exists()


def test_shared_job_controller_rejects_overlap_and_defers_publication(
    client, tmp_path, monkeypatch
):
    jobs = client.app.state.jobs
    spec = {
        "connection": "chatgpt",
        "model": "fixture",
        "request": context(),
        "source": None,
        "report": "generated.json",
    }
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr("thadam.dashboard.jobs.subprocess.Popen", lambda *args, **kw: process)
    monkeypatch.setattr(jobs, "_capture", lambda *args: None)
    started = client.post("/api/generate", json=spec)
    assert started.status_code == 200, started.text
    assert started.json()["total"] == 1  # One request, not fabricated per-case model progress.
    assert not (tmp_path / "generated.json").exists()
    assert client.post("/api/generate", json=spec).status_code == 400
    write_draft(draft(), jobs.directory / "result.json")
    process.poll.return_value = 0
    assert client.get("/api/jobs").json()[0]["state"] == "completed"
    assert load_draft(tmp_path / "generated.json")


def test_interrupted_generation_never_publishes_a_result(client, tmp_path, monkeypatch):
    jobs = client.app.state.jobs
    process = Mock()
    process.poll.return_value = None
    process.pid = 123456
    monkeypatch.setattr("thadam.dashboard.jobs.subprocess.Popen", lambda *args, **kw: process)
    monkeypatch.setattr("thadam.dashboard.jobs.os.killpg", lambda *args: None)
    monkeypatch.setattr(jobs, "_capture", lambda *args: None)
    spec = {
        "connection": "chatgpt",
        "model": "fixture",
        "request": context(),
        "source": None,
        "report": "interrupted.json",
    }
    assert client.post("/api/generate", json=spec).status_code == 200
    write_draft(draft(), jobs.directory / "result.json")
    assert client.post("/api/stop", json={}).json()["state"] == "interrupted"
    assert not (tmp_path / "interrupted.json").exists()


def test_publication_conflict_keeps_existing_file(client, tmp_path, monkeypatch):
    jobs = client.app.state.jobs
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr("thadam.dashboard.jobs.subprocess.Popen", lambda *args, **kw: process)
    monkeypatch.setattr(jobs, "_capture", lambda *args: None)
    spec = {
        "connection": "chatgpt",
        "model": "fixture",
        "request": context(),
        "source": None,
        "report": "conflict.json",
    }
    assert client.post("/api/generate", json=spec).status_code == 200
    write_draft(draft(), jobs.directory / "result.json")
    (tmp_path / "conflict.json").write_text("preserve me")
    process.poll.return_value = 0
    assert client.get("/api/jobs").json()[0]["state"] == "error"
    assert (tmp_path / "conflict.json").read_text() == "preserve me"
