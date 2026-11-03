"""Intentional baseline changes require exact review and guarded explicit promotion."""

import json
from dataclasses import replace

import pytest

from thadam import (
    CheckResult,
    OutputEquals,
    OutputHasKeys,
    ReportValidationError,
    ReportWriteError,
    SuiteIdentity,
    Verifier,
    approve_review,
    approved_from_dict,
    approved_to_dict,
    compare_repeated,
    compare_reports,
    load_baseline_review,
    load_evaluation,
    load_repeated,
    load_report,
    review_baseline,
    review_from_dict,
    review_to_dict,
    run_repeated,
    run_suite,
    write_approved_baseline,
    write_baseline_review,
    write_report,
)
from thadam import TestCase as Case
from thadam import TestSuite as Suite
from thadam.baseline_reporting import format_baseline_review
from thadam.terminal import TerminalStyle


def cases(revision="v1", expected=1):
    return Suite(
        SuiteIdentity("refund", revision), (Case("a", None, (OutputEquals("out", expected),)),)
    )


def report(revision="v1", expected=1, output=1, repeated=False):
    if repeated:
        return run_repeated(lambda _: output, cases(revision, expected), attempts=2)
    return run_suite(lambda _: output, cases(revision, expected))


def approval(review, **kwargs):
    return approve_review(
        review,
        review_digest=review.digest,
        reviewer="Maintainer",
        reason="Reviewed policy change",
        **kwargs,
    )


@pytest.mark.parametrize("repeated", [False, True])
def test_complete_initial_and_update_workflow(tmp_path, repeated):
    first = report(repeated=repeated)
    review = review_baseline(first)
    assert not review.blockers and review.exit_code == 0
    path = tmp_path / "review.json"
    write_baseline_review(review, path)
    assert load_baseline_review(path) == review
    destination = tmp_path / "baseline.json"
    write_approved_baseline(approval(review), destination)
    loader = load_repeated if repeated else load_report
    assert loader(destination) == first
    # Every approval retains the inspected evidence and explicit acknowledgement.
    stored = json.loads(destination.read_text())
    assert stored["kind"] == "approved_baseline"
    assert stored["review_digest"] == review.digest
    assert approved_from_dict(stored) == approval(review)
    second = report("v2", expected=2, output=2, repeated=repeated)
    updated = review_baseline(second, loader(destination))
    assert not updated.blockers
    assert {change.scope for change in updated.changes} == {"suite", "check_changed"}
    write_approved_baseline(approval(updated), destination)
    assert loader(destination) == second
    comparator = compare_repeated if repeated else compare_reports
    assert comparator(loader(destination), second).exit_code == 0
    assert comparator(first, second).exit_code == 2
    assert load_evaluation(destination) == second
    assert approved_from_dict(json.loads(destination.read_text())).review.baseline == first
    # Wrappers do not accumulate approvals recursively.
    assert "approved_baseline" not in json.dumps(json.loads(destination.read_text())["review"])


def test_contract_diff_preserves_full_before_after_and_all_changed_scopes():
    old = run_suite(
        lambda _: {"v": 1},
        Suite(
            SuiteIdentity("s", "v1"),
            (
                Case("removed", 0, (OutputEquals("out", {"v": 1}),)),
                Case(
                    "edited",
                    {"x": 1},
                    (OutputEquals("out", {"v": 1}), OutputHasKeys("removed-check", ("v",))),
                ),
            ),
        ),
    )
    new = run_suite(
        lambda _: {"v": 2},
        Suite(
            SuiteIdentity("s", "v2"),
            (
                Case(
                    "edited",
                    {"x": 2},
                    (OutputEquals("out", {"v": 2}), OutputHasKeys("added-check", ("v",))),
                ),
                Case("added", 1, (OutputEquals("out", {"v": 2}),)),
            ),
        ),
    )
    review = review_baseline(new, old)
    assert {change.scope for change in review.changes} == {
        "suite",
        "case_added",
        "case_removed",
        "input_changed",
        "check_added",
        "check_removed",
        "check_changed",
    }
    changed = next(change for change in review.changes if change.scope == "check_changed")
    assert changed.before["parameters"]["expected"] == {"v": 1}
    assert changed.after["parameters"]["expected"] == {"v": 2}
    assert not review.blockers
    # Snapshot mutable evidence independently of callers.
    new.cases[0].input["x"] = 999
    assert review.candidate.cases[0].input == {"x": 2}


def test_changed_contract_requires_new_revision_but_reordered_keys_do_not():
    review = review_baseline(report(expected=2, output=2), report())
    assert any("without a new suite revision" in blocker for blocker in review.blockers)
    with pytest.raises(ReportValidationError, match="blocked"):
        approval(review)
    a = run_suite(
        lambda _: {"a": 1, "b": 2},
        Suite(SuiteIdentity("s", "1"), (Case("x", {}, (OutputHasKeys("keys", ("a", "b")),)),)),
    )
    b = run_suite(
        lambda _: {"a": 1, "b": 2},
        Suite(SuiteIdentity("s", "1"), (Case("x", {}, (OutputHasKeys("keys", ("b", "a")),)),)),
    )
    assert not review_baseline(b, a).changes
    assert not review_baseline(b, a).blockers


def test_revision_only_and_legacy_adoption_are_explicit_changes():
    review = review_baseline(report("v2"), report())
    assert [change.scope for change in review.changes] == ["suite"]
    assert not review.blockers
    legacy = run_suite(lambda _: 1, cases().cases)
    adopted = review_baseline(report(), legacy)
    assert not adopted.blockers
    assert adopted.changes[0].before is None
    assert review_baseline(legacy).blockers


def test_different_suite_and_evaluation_kind_cannot_overwrite_workflow():
    candidate = replace(report(), suite=SuiteIdentity("other", "v1"))
    assert any(
        "Suite ID changed" in issue for issue in review_baseline(candidate, report()).blockers
    )
    assert any(
        "Evaluation kind" in issue
        for issue in review_baseline(report(repeated=True), report()).blockers
    )


@pytest.mark.parametrize("repeated", [False, True])
def test_failed_expectations_require_acknowledgement_and_stay_failed(tmp_path, repeated):
    candidate = report(output=0, repeated=repeated)
    review = review_baseline(candidate)
    assert review.has_failures and not review.blockers
    with pytest.raises(ReportValidationError, match="explicitly accept"):
        approval(review)
    accepted = approval(review, accept_failures=True)
    write_approved_baseline(accepted, tmp_path / "baseline.json")
    loaded = load_evaluation(tmp_path / "baseline.json")
    assert loaded.has_failures
    comparator = compare_repeated if repeated else compare_reports
    assert comparator(loaded, candidate).exit_code == 0
    assert accepted.accepted_failures is True


def test_candidate_errors_never_approvable_but_old_errors_can_be_replaced():
    def broken(_):
        raise RuntimeError("offline")

    errored = run_suite(broken, cases())
    review = review_baseline(errored)
    assert any("errors" in issue for issue in review.blockers)
    with pytest.raises(ReportValidationError, match="blocked"):
        approval(review, accept_failures=True)
    assert not review_baseline(report(), errored).blockers


def test_verifier_revisions_are_diffed_without_executing_verifier():
    calls = []

    def verifier(_i, _o):
        calls.append(1)
        return CheckResult(True, "ok")

    def evaluated(revision, verifier_revision):
        return run_suite(
            lambda _: None,
            Suite(
                SuiteIdentity("s", revision),
                (Case("x", None, verifiers=(Verifier("policy", verifier, verifier_revision),)),),
            ),
        )

    old, candidate = evaluated("1", "1"), evaluated("2", "2")
    calls.clear()
    review = review_baseline(candidate, old)
    approved_from_dict(approved_to_dict(approval(review)))
    assert calls == []
    assert any(change.scope == "check_changed" for change in review.changes)
    assert review_baseline(evaluated("3", None), old).blockers


def test_attempt_and_mode_changes_are_reviewed_as_settings():
    old = report(repeated=True)
    new = run_repeated(cases=cases(), agent_factory=lambda: lambda _: 1, attempts=3)
    review = review_baseline(new, old)
    assert {change.scope for change in review.changes} == {"attempts", "execution_mode"}
    assert not review.blockers


@pytest.mark.parametrize(
    "metadata",
    [
        dict(reviewer=""),
        dict(reason=" "),
        dict(reason="\ud800"),
        dict(accept_failures=1),
        dict(review_digest="0" * 64),
    ],
)
def test_invalid_acknowledgements_or_stale_review_rejected(metadata):
    review = review_baseline(report())
    kwargs = dict(reviewer="Maintainer", reason="Reviewed", review_digest=review.digest)
    kwargs.update(metadata)
    with pytest.raises(ReportValidationError):
        approve_review(review, **kwargs)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(extra=1),
        lambda r: r.update(schema_version=True),
        lambda r: r.update(kind="other"),
        lambda r: r.update(blockers=["fake"]),
        lambda r: r.update(changes=[]),
        lambda r: r.update(has_failures=True),
        lambda r: r.update(exit_code=1),
        lambda r: r["candidate"]["summary"].update(passed=0),
    ],
)
def test_strict_review_recomputes_decisions(mutate):
    raw = review_to_dict(review_baseline(report()))
    mutate(raw)
    with pytest.raises(ReportValidationError):
        review_from_dict(raw)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(extra=1),
        lambda r: r.update(schema_version=True),
        lambda r: r.update(kind="other"),
        lambda r: r.update(review_digest="bad"),
        lambda r: r.update(reviewer=""),
        lambda r: r.update(accepted_failures=1),
        lambda r: r["review"].update(candidate=r),
    ],
)
def test_strict_approval_rejects_corruption_or_nested_wrappers(mutate):
    raw = approved_to_dict(approval(review_baseline(report())))
    mutate(raw)
    with pytest.raises(ReportValidationError):
        approved_from_dict(raw)


def test_complete_evidence_changes_digest_and_old_digest_cannot_approve():
    candidate = report()
    review = review_baseline(candidate)
    changed = replace(candidate, run_id="different-run")
    other = review_baseline(changed)
    assert review.digest != other.digest
    with pytest.raises(ReportValidationError, match="digest"):
        approve_review(other, review_digest=review.digest, reviewer="Me", reason="Reviewed")
    assert (
        review_from_dict(json.loads(json.dumps(review_to_dict(review), sort_keys=True))).digest
        == review.digest
    )


def test_destination_guard_preserves_new_or_changed_baseline(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text("important")
    with pytest.raises(ReportValidationError, match="cannot overwrite"):
        write_approved_baseline(approval(review_baseline(report())), path)
    assert path.read_text() == "important"
    old, candidate = report(), report("v2")
    review = review_baseline(candidate, old)
    changed = report("v3")
    write_report(changed, path)
    original = path.read_bytes()
    with pytest.raises(ReportValidationError, match="changed since review"):
        write_approved_baseline(approval(review), path)
    assert path.read_bytes() == original
    assert not path.with_name(path.name + ".thadam-approval.lock").exists()
    path.unlink()
    with pytest.raises(ReportValidationError, match="missing"):
        write_approved_baseline(approval(review), path)


def test_symlink_and_competing_approval_guard(tmp_path):
    path = tmp_path / "baseline.json"
    target = tmp_path / "target.json"
    target.write_text("untouched")
    path.symlink_to(target)
    with pytest.raises(ReportValidationError, match="symbolic"):
        write_approved_baseline(approval(review_baseline(report())), path)
    assert target.read_text() == "untouched"
    path.unlink()
    lock = tmp_path / "baseline.json.thadam-approval.lock"
    lock.touch()
    with pytest.raises(ReportWriteError):
        write_approved_baseline(approval(review_baseline(report())), path)
    assert lock.exists() and not path.exists()


def test_failed_atomic_write_preserves_current_baseline(tmp_path, monkeypatch):
    old = report()
    path = tmp_path / "baseline.json"
    write_report(old, path)
    original = path.read_bytes()

    def fail(_data, _path):
        raise ReportWriteError("disk full")

    monkeypatch.setattr("thadam.baseline_approval._replace_json_artifact", fail)
    with pytest.raises(ReportWriteError, match="disk full"):
        write_approved_baseline(approval(review_baseline(report("v2"), old)), path)
    assert path.read_bytes() == original
    assert not (tmp_path / "baseline.json.thadam-approval.lock").exists()


def test_wrong_workflow_loader_rejects_approval_kind(tmp_path):
    path = tmp_path / "baseline.json"
    write_approved_baseline(approval(review_baseline(report(repeated=True))), path)
    with pytest.raises(ReportValidationError, match="single-run"):
        load_report(path)
    path.unlink()
    write_approved_baseline(approval(review_baseline(report())), path)
    with pytest.raises(ReportValidationError, match="repeated-run"):
        load_repeated(path)


def test_review_depth_budget_includes_deep_payloads(tmp_path):
    value = 0
    for _ in range(100):
        value = [value]
    candidate = run_repeated(
        lambda x: x,
        Suite(SuiteIdentity("deep", "1"), (Case("x", value, (OutputEquals("out", value),)),)),
        attempts=2,
    )
    review = review_baseline(candidate)
    path = tmp_path / "review.json"
    write_baseline_review(review, path)
    loaded = load_baseline_review(path)
    assert loaded == review
    write_approved_baseline(approval(loaded), tmp_path / "baseline.json")
    assert load_repeated(tmp_path / "baseline.json") == candidate


@pytest.mark.parametrize("width", [20, 40, 96])
def test_review_terminal_keeps_failures_values_digest_and_theme(width):
    review = review_baseline(report("v2", expected=2, output=0), report())
    plain = format_baseline_review(review, width=width)
    assert "THADAM" in plain and "CANDIDATE" in plain.upper()
    assert "--accept-failures" in plain or width == 20
    assert "\x1b" not in plain
    colored = format_baseline_review(review, style=TerminalStyle(enabled=True), width=width)
    assert "\x1b[" in colored
    assert review == review_from_dict(review_to_dict(review))


def test_error_in_a_later_attempt_blocks_approval_without_inventing_failed_expectations():
    calls = 0

    def agent(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("later attempt failed")
        return 1

    repeated = run_repeated(agent, cases(), attempts=3)
    review = review_baseline(repeated)
    assert review.blockers and not review.has_failures
    with pytest.raises(ReportValidationError, match="blocked"):
        approval(review, accept_failures=True)


def test_review_approval_keeps_instrumented_evidence_and_output_availability(tmp_path):
    from thadam import AgentResult, ExecutionEvent, ToolCalled

    event = ExecutionEvent(
        "tool-id",
        "tool",
        "lookup",
        "completed",
        0,
        duration_ms=1,
        input={"id": 1},
        input_available=True,
        output=None,
        output_available=True,
    )
    candidate = run_suite(
        lambda _: AgentResult(None, (event,)),
        Suite(
            SuiteIdentity("tools", "1"), (Case("case", None, (ToolCalled("required", "lookup"),)),)
        ),
    )
    review = review_baseline(candidate)
    path = tmp_path / "approved.json"
    write_approved_baseline(approval(review), path)
    loaded = load_report(path)
    assert loaded == candidate
    assert loaded.cases[0].assertions[0].event_ids == ("tool-id",)
    assert loaded.cases[0].events[0].output_available
    assert "tool-id" in format_baseline_review(review, verbose=True)
    # Changing an observable event also changes what was inspected.
    changed = replace(candidate, cases=(replace(candidate.cases[0], duration_ms=999),))
    assert review_baseline(changed).digest != review.digest
