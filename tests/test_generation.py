"""Generation proposals, exact review, contract validation and guarded saving."""

import json
from copy import deepcopy

import pytest

from thadam import CheckResult, GenerationResult, Verifier, run_suite
from thadam.cli import main
from thadam.generation import (
    candidate_issues,
    draft_issues,
    load_draft,
    publish_draft,
    review_candidate,
    reviewed_cases,
    selected_suite,
    suggest_cases,
    validate_draft,
    validate_request,
    write_draft,
)
from thadam.suite_writing import file_fingerprint
from thadam.suites import suite_from_dict


def context():
    return {
        "description": "Echo JSON",
        "behavior": "Return input unchanged",
        "examples": [{"input": 1, "output": 1}],
        "count": 1,
    }


def candidate(identifier="echo", assertions=None):
    return {
        "case": {
            "id": identifier,
            "input": 1,
            "assertions": [{"id": "answer", "type": "output_equals", "expected": 1}]
            if assertions is None
            else assertions,
        },
        "category": "normal",
        "rationale": "Echo contract",
        "uncertainty": "",
    }


class Provider:
    def __init__(self, candidates=None):
        self.candidates = [candidate()] if candidates is None else candidates
        self.calls = []

    def generate(self, request):
        self.calls.append(deepcopy(request))
        request["description"] = "provider mutation"
        return GenerationResult(self.candidates, "controlled", "fixture", usage=None)


def draft(candidates=None, source=None):
    return suggest_cases(Provider(candidates), context(), source=source)


def test_generation_is_proposed_and_snapshots_provider_boundary():
    provider = Provider()
    data = suggest_cases(provider, context())
    assert data["request"]["description"] == "Echo JSON"
    assert data["generation"]["usage"] is None
    assert data["candidates"][0]["decision"] == "pending"
    with pytest.raises(ValueError, match="Accept at least"):
        selected_suite(data, suite_id="echo", revision="1")
    assert provider.calls[0]["count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"count": True},
        {"count": 0},
        {"count": 21},
        {"behavior": ""},
        {"examples": []},
        {"examples": [{"input": 1}]},
        {"tool_schemas": "wrong"},
        {"unknown": 1},
        {"schemas": []},
    ],
)
def test_invalid_context_rejected_before_provider(change):
    provider = Provider()
    with pytest.raises(ValueError):
        suggest_cases(provider, {**context(), **change})
    assert not provider.calls


def test_schemas_or_explicit_existing_cases_can_supply_input_contract():
    assert validate_request({**context(), "examples": [], "schemas": {"input": {"type": "number"}}})
    assert validate_request({**context(), "examples": [], "existing_cases": [candidate()["case"]]})
    assert candidate_issues({"id": "x", "input": None, "assertions": []})


def test_duplicate_and_unsupported_cases_remain_editable_drafts():
    data = draft(
        [
            candidate(),
            candidate(),
            candidate("unsupported", [{"id": "x", "type": "python", "code": "raise Exception"}]),
        ]
    )
    assert "Duplicate" in draft_issues(data, 0)[0]
    assert "unknown assertion" in draft_issues(data, 2)[0]
    with pytest.raises(ValueError, match="Cannot accept"):
        review_candidate(data, 0, decision="accepted")
    data = review_candidate(data, 1, decision="discarded")
    data = review_candidate(data, 0, decision="accepted")
    fixed = candidate("fixed")["case"]
    data = review_candidate(data, 2, decision="accepted", case=fixed)
    suite = selected_suite(data, suite_id="suite", revision="v1")
    assert [c["id"] for c in suite["cases"]] == ["echo", "fixed"]


def test_expected_outcomes_cannot_change_after_acceptance():
    data = review_candidate(draft(), 0, decision="accepted")
    data["candidates"][0]["case"]["assertions"][0]["expected"] = 2
    with pytest.raises(ValueError, match="reviewed content|after review"):
        validate_draft(data)


def test_incomplete_draft_can_be_completed_with_explicit_sdk_verifier():
    data = draft([candidate(assertions=[])])
    with pytest.raises(ValueError, match="at least one check"):
        review_candidate(data, 0, decision="accepted")
    calls = []

    def verify(value, output):
        calls.append(True)
        return CheckResult(output == value, "Echo contract")

    cases = reviewed_cases(data, verifiers={"echo": (Verifier("echo", verify, revision="v1"),)})
    assert calls == []
    assert run_suite(lambda x: x, cases).summary.passed == 1
    assert calls == [True]
    assert data["candidates"][0]["decision"] == "pending"


def test_draft_roundtrip_keeps_originals_and_append_only_reviews(tmp_path):
    path = tmp_path / "draft.json"
    data = draft()
    write_draft(data, path)
    before = file_fingerprint(path)
    accepted = review_candidate(data, 0, decision="accepted")
    write_draft(accepted, path, expected_fingerprint=before)
    assert load_draft(path) == accepted
    with pytest.raises(ValueError, match="changed"):
        write_draft(data, path, expected_fingerprint=before)
    changed = deepcopy(accepted)
    changed["candidates"][0]["original"]["rationale"] = "erase evidence"
    with pytest.raises(ValueError, match="retained"):
        write_draft(changed, path, expected_fingerprint=file_fingerprint(path))
    reset = review_candidate(accepted, 0, decision="pending", case=candidate("renamed")["case"])
    assert reset["candidates"][0]["reviewed_digest"] is None
    assert len(reset["candidates"][0]["reviews"]) == 2


def test_suite_append_preserves_identity_and_requires_revision_and_fingerprint(tmp_path):
    source_path = tmp_path / "cases.json"
    source_data = {
        "schema_version": 2,
        "suite": {"id": "echo", "revision": "1"},
        "cases": [candidate("old")["case"]],
    }
    source_path.write_text(json.dumps(source_data))
    before = file_fingerprint(source_path)
    source = {"path": str(source_path), "fingerprint": before, "data": source_data}
    data = review_candidate(draft(source=source), 0, decision="accepted")
    with pytest.raises(ValueError, match="new suite revision"):
        selected_suite(data, revision="1")
    with pytest.raises(ValueError, match="fingerprint"):
        publish_draft(data, source_path, revision="2")
    suite = publish_draft(data, source_path, revision="2", expected_fingerprint=before)
    assert suite["suite"] == {"id": "echo", "revision": "2"}
    assert len(suite_from_dict(suite)) == 2
    with pytest.raises(ValueError, match="changed"):
        publish_draft(data, source_path, revision="3", expected_fingerprint=before)


def test_no_draft_or_suite_can_overwrite_a_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"kind": "approved_baseline"}')
    data = review_candidate(draft(), 0, decision="accepted")
    with pytest.raises(ValueError):
        publish_draft(
            data, path, suite_id="x", revision="1", expected_fingerprint=file_fingerprint(path)
        )
    with pytest.raises(ValueError):
        write_draft(data, path, expected_fingerprint=file_fingerprint(path))
    assert json.loads(path.read_text()) == {"kind": "approved_baseline"}


def test_cli_preview_review_save_and_plain_agent_execution(tmp_path, capsys):
    request = tmp_path / "context.json"
    request.write_text(json.dumps(context()))
    assert main(["suggest", str(request)]) == 0
    assert '"context"' in capsys.readouterr().out
    path, suite = tmp_path / "draft.json", tmp_path / "cases.json"
    write_draft(draft(), path)
    assert main(["review-draft", str(path), "--case", "1", "--decision", "accepted"]) == 0
    args = [
        "save-draft",
        str(path),
        "--destination",
        str(suite),
        "--suite-id",
        "echo",
        "--revision",
        "1",
    ]
    assert main(args) == 0
    assert not suite.exists()
    assert main([*args, "--write"]) == 0
    assert main(["run", str(suite), "--agent", "examples.refund_agent:run"]) == 1
    assert main(["review-draft", str(path), "--case", "0", "--decision", "accepted"]) == 2


def test_cli_generation_selects_explicit_connection_and_never_overwrites(tmp_path, monkeypatch):
    from thadam.providers.openai import OpenAIProvider

    calls = []

    def generate(self, request):
        calls.append((self.connection, self.model))
        return Provider().generate(request)

    monkeypatch.setattr(OpenAIProvider, "generate", generate)
    request, target = tmp_path / "context.json", tmp_path / "draft.json"
    request.write_text(json.dumps(context()))
    assert main(["suggest", str(request), "--send"]) == 2
    args = [
        "suggest",
        str(request),
        "--send",
        "--connection",
        "chatgpt",
        "--model",
        "selected",
        "--draft",
        str(target),
    ]
    assert main(args) == 0
    assert calls == [("chatgpt", "selected")]
    assert main(args) == 2
    assert len(calls) == 1


def test_draft_loader_rejects_missing_normalized_context():
    data = draft()
    del data["request"]["existing_cases"]
    with pytest.raises(ValueError, match="normalized context"):
        validate_draft(data)


def test_controlled_generation_demo_requires_no_model_and_refuses_replacement(tmp_path):
    from examples.generation_demo import create_demo

    destination = tmp_path / "demo"
    create_demo(destination)
    data = load_draft(destination / "suggestions.json")
    assert data["generation"]["provider"] == "controlled_demo"
    assert len(data["candidates"]) == 3
    assert all(x["decision"] == "pending" for x in data["candidates"])
    with pytest.raises(FileExistsError):
        create_demo(destination)
