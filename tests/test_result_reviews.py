"""Human review labels remain separate from immutable run outcomes."""

from __future__ import annotations

import json

import pytest

from thadam import OutputEquals, report_to_dict, run_repeated, run_suite
from thadam import TestCase as Case
from thadam.repetition_reporting import repeated_to_dict
from thadam.result_reviews import result_reviews, validate_result_reviews

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from thadam.dashboard.server import create_app


def source_report():
    return report_to_dict(
        run_suite(
            lambda value: value,
            [
                Case("refund", {"order": 1}, (OutputEquals("answer", "ok"),)),
                Case("charge", {"order": 2}, (OutputEquals("answer", "ok"),)),
            ],
        )
    )


@pytest.fixture
def client(tmp_path):
    source = tmp_path / "run.json"
    source.write_text(json.dumps(source_report()))
    with TestClient(create_app(tmp_path, token="labels-token")) as value:
        value.post("/api/session", headers={"x-thadam-token": "labels-token"})
        yield value, source


def test_labels_are_saved_separately_and_searchable(client):
    api, source = client
    original_bytes = source.read_bytes()
    opened = api.get("/api/artifact", params={"path": "run.json"}).json()
    loaded = api.get("/api/result-reviews", params={"path": "run.json"})
    assert loaded.status_code == 200, loaded.text
    draft = loaded.json()
    assert draft["data"]["reviews"] == []

    saved = api.post(
        "/api/result-reviews",
        json={
            "path": "run.json",
            "fingerprint": opened["fingerprint"],
            "review_fingerprint": None,
            "reviews": [
                {
                    "case_id": "refund",
                    "attempt": None,
                    "verdict": "bad",
                    "notes": "Used the wrong policy.",
                    "tags": ["policy-gap"],
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    artifact = saved.json()
    assert artifact["kind"] == "result_reviews"
    assert artifact["data"]["source"]["path"] == "run.json"
    assert source.read_bytes() == original_bytes

    report = api.get("/api/artifact", params={"path": "run.json"}).json()
    assert report["data"]["summary"]["failed"] == opened["data"]["summary"]["failed"]
    catalog = api.get("/api/workspace").json()
    run_item = next(item for item in catalog["items"] if item["path"] == "run.json")
    assert run_item["review_state"] == "in progress"
    assert run_item["review_verdicts"] == ["bad"]
    assert run_item["review_tags"] == ["policy-gap"]
    sidecar = next(item for item in catalog["items"] if item["kind"] == "result_reviews")
    assert sidecar["review_case_ids"] == ["refund"]


def test_result_review_writes_reject_stale_source_or_sidecar(client):
    api, source = client
    opened = api.get("/api/artifact", params={"path": "run.json"}).json()
    body = {
        "path": "run.json",
        "fingerprint": opened["fingerprint"],
        "review_fingerprint": None,
        "reviews": [],
    }
    source.write_text(source.read_text() + "\n")
    assert api.post("/api/result-reviews", json=body).status_code == 400
    assert not (source.parent / "review-labels").exists()

    source.write_text(json.dumps(source_report()))
    refreshed = api.get("/api/artifact", params={"path": "run.json"}).json()
    body["fingerprint"] = refreshed["fingerprint"]
    first = api.post("/api/result-reviews", json=body)
    assert first.status_code == 200, first.text
    body["review_fingerprint"] = "stale"
    assert api.post("/api/result-reviews", json=body).status_code == 400


def test_labels_validate_case_attempt_and_tag_contracts():
    run = {"kind": "run", **source_report()}
    artifact = result_reviews(run, path="run.json", fingerprint="a" * 64)
    with pytest.raises(ValueError, match="absent"):
        validate_result_reviews(
            {
                **artifact,
                "reviews": [
                    {
                        "case_id": "missing",
                        "attempt": None,
                        "verdict": "good",
                        "notes": "",
                        "tags": [],
                    }
                ],
            },
            source=run,
        )
    with pytest.raises(ValueError, match="unique"):
        validate_result_reviews(
            {
                **artifact,
                "reviews": [
                    {
                        "case_id": "refund",
                        "attempt": None,
                        "verdict": "good",
                        "notes": "",
                        "tags": ["duplicate", "duplicate"],
                    }
                ],
            },
            source=run,
        )


def test_repeated_attempts_keep_independent_labels():
    report = repeated_to_dict(
        run_repeated(
            lambda value: value,
            [Case("refund", 1, (OutputEquals("answer", 1),))],
            attempts=2,
        )
    )
    source = {"kind": "repeated_run", **report}
    artifact = result_reviews(
        source,
        path="repeated.json",
        fingerprint="b" * 64,
        reviews=[
            {
                "case_id": "refund",
                "attempt": 1,
                "verdict": "good",
                "notes": "",
                "tags": [],
            },
            {
                "case_id": "refund",
                "attempt": 2,
                "verdict": "bad",
                "notes": "Second attempt diverged.",
                "tags": ["intermittent"],
            },
        ],
    )
    assert validate_result_reviews(artifact, source=source)["reviews"] == artifact["reviews"]
    with pytest.raises(ValueError, match="absent"):
        validate_result_reviews(
            {
                **artifact,
                "reviews": [
                    {
                        "case_id": "refund",
                        "attempt": 3,
                        "verdict": "good",
                        "notes": "",
                        "tags": [],
                    }
                ],
            },
            source=source,
        )
