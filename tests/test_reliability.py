"""Reliability gate contracts, evidence snapshots, and exact tolerance boundaries."""

import json
from dataclasses import replace
from decimal import localcontext

import pytest

from thadam import (
    CheckResult,
    OutputEquals,
    ReportValidationError,
    Verifier,
    compare_repeated,
    load_reliability_comparison,
    reliability_to_dict,
    run_repeated,
    write_reliability_comparison,
)
from thadam import TestCase as AgentCase


def report(values, *, cases=None, revision=None):
    answers = iter(values)

    def agent(_):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return run_repeated(
        agent,
        cases or [AgentCase("case", None, (OutputEquals("answer", 1),))],
        attempts=len(values),
        agent_revision=revision,
    )


@pytest.mark.parametrize(
    "before,after,tolerance,change,code",
    [
        ([1, 1], [1, 1], 0, "unchanged", 0),
        ([1, 0], [1, 0], 0, "unchanged", 0),
        ([0, 0], [1, 1], 0, "improved", 0),
        ([1, 1], [1, 0], 0, "regression", 1),
        ([1] * 10, [1] * 8 + [0] * 2, 0.2, "tolerated_drop", 0),
        ([1] * 10, [1] * 8 + [0] * 2, 0.1999999, "regression", 1),
        ([1, 1], [0, 0], 1, "tolerated_drop", 0),
        ([RuntimeError("old error"), 1], [1, 1], 1, "error", 1),
        ([1, 1], [RuntimeError("new error"), 1], 1, "error", 1),
    ],
)
def test_case_and_check_gate_policy(before, after, tolerance, change, code):
    comparison = compare_repeated(report(before), report(after), max_pass_rate_drop=tolerance)
    assert comparison.cases[0].change == change
    assert comparison.cases[0].checks[0].change == change
    assert comparison.exit_code == code
    assert comparison.compatible


def test_gate_does_not_depend_on_application_decimal_context():
    baseline, candidate = report([1] * 10), report([1] * 8 + [0] * 2)
    with localcontext() as context:
        context.prec = 1
        assert compare_repeated(baseline, candidate, max_pass_rate_drop=0.1999999).exit_code == 1
        assert compare_repeated(baseline, candidate, max_pass_rate_drop=0.2).exit_code == 0


def test_comparison_checks_each_assertion_inside_already_failed_cases():
    cases = [AgentCase("case", None, (OutputEquals("always-failed", 9), OutputEquals("answer", 1)))]
    comparison = compare_repeated(report([1, 1], cases=cases), report([0, 0], cases=cases))
    case = comparison.cases[0]
    assert case.case_rate.baseline.failed == case.case_rate.candidate.failed == 2
    assert case.case_rate.change == "unchanged"
    assert case.checks[1].change == "regression"
    assert comparison.exit_code == 1


def test_improvements_do_not_cancel_regressions():
    cases = [AgentCase("case", None, (OutputEquals("one", 1), OutputEquals("zero", 0)))]
    comparison = compare_repeated(report([1, 1], cases=cases), report([0, 0], cases=cases))
    assert [check.change for check in comparison.cases[0].checks] == ["regression", "improved"]
    assert comparison.exit_code == 1


@pytest.mark.parametrize("value", [True, None, "0.1", -0.1, 1.1, float("nan"), float("inf")])
def test_policy_must_be_explicit_finite_fraction(value):
    saved = report([1, 1])
    with pytest.raises(ReportValidationError, match="max_pass_rate_drop"):
        compare_repeated(saved, saved, max_pass_rate_drop=value)


def test_unequal_attempts_and_execution_modes_are_incompatible():
    baseline = report([1, 1])
    for candidate in (report([1, 1, 1]), replace(baseline, execution_mode="factory")):
        comparison = compare_repeated(baseline, candidate)
        assert not comparison.compatible and comparison.exit_code == 2
        assert comparison.issues and comparison.cases[0].change == "incompatible"


@pytest.mark.parametrize(
    "cases",
    [
        [AgentCase("changed-id", None, (OutputEquals("answer", 1),))],
        [AgentCase("case", {"changed": True}, (OutputEquals("answer", 1),))],
        [AgentCase("case", None, (OutputEquals("changed-check", 1),))],
        [AgentCase("case", None, (OutputEquals("answer", 0),))],
    ],
)
def test_changed_test_contracts_require_reviewed_new_baseline(cases):
    comparison = compare_repeated(report([1, 1]), report([1, 1], cases=cases))
    assert comparison.exit_code == 2
    assert any(case.issues for case in comparison.cases)


@pytest.mark.parametrize("old,new,expected", [(None, None, 2), ("v1", "v2", 2), ("v1", "v1", 0)])
def test_custom_verifiers_require_matching_explicit_revisions(old, new, expected):
    calls = []

    def check(*_):
        calls.append(1)
        return CheckResult(True, "accepted")

    def cases(revision):
        return [AgentCase("case", None, verifiers=(Verifier("custom", check, revision),))]

    comparison = compare_repeated(
        report([1, 1], cases=cases(old)), report([1, 1], cases=cases(new))
    )
    assert comparison.exit_code == expected
    assert len(calls) == 4


def test_attempt_outcomes_are_not_paired_by_position():
    comparison = compare_repeated(report([1, 0, 1, 0]), report([0, 1, 0, 1]))
    assert comparison.exit_code == 0
    assert comparison.cases[0].case_rate.pass_rate_delta == 0


def test_case_and_check_order_do_not_define_identity():
    cases = [
        AgentCase(name, None, (OutputEquals("a", 1), OutputEquals("b", 1))) for name in ("a", "b")
    ]
    baseline = run_repeated(lambda _: 1, cases, attempts=2)
    reordered = [
        replace(case, assertions=tuple(reversed(case.assertions))) for case in reversed(cases)
    ]
    candidate = run_repeated(lambda _: 1, reordered, attempts=2)
    comparison = compare_repeated(baseline, candidate)
    assert comparison.exit_code == 0
    assert [case.id for case in comparison.cases] == ["a", "b"]


def test_standalone_comparison_roundtrip_includes_full_evidence_and_snapshots(tmp_path):
    baseline = report([1, 1], revision="before")
    candidate = report([1, 0], revision="after")
    comparison = compare_repeated(baseline, candidate)
    path = tmp_path / "comparison.json"
    write_reliability_comparison(comparison, path)
    loaded = load_reliability_comparison(path)
    assert reliability_to_dict(loaded) == reliability_to_dict(comparison)
    data = json.loads(path.read_text())
    assert data["candidate"]["runs"][1]["cases"][0]["output"] == 0
    assert data["policy"] == {"max_pass_rate_drop": 0}
    assert comparison.baseline is not baseline
    assert comparison.candidate is not candidate


@pytest.mark.parametrize("condition", ["errors", "attempts", "modes", "contracts"])
def test_blocked_comparisons_also_roundtrip_with_all_issues(tmp_path, condition):
    baseline = report([1, 1])
    candidate = (
        report([RuntimeError("agent unavailable"), 1]) if condition == "errors" else baseline
    )
    if condition == "attempts":
        candidate = report([1, 1, 1])
    elif condition == "modes":
        candidate = replace(baseline, execution_mode="factory")
    elif condition == "contracts":
        candidate = report([1, 1], cases=[AgentCase("case", None, (OutputEquals("answer", 0),))])
    comparison = compare_repeated(baseline, candidate)
    path = tmp_path / "blocked.json"
    write_reliability_comparison(comparison, path)
    loaded = load_reliability_comparison(path)
    assert loaded.exit_code == (1 if condition == "errors" else 2)
    assert reliability_to_dict(loaded) == reliability_to_dict(comparison)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(exit_code=0),
        lambda data: data.update(kind="comparison"),
        lambda data: data.update(schema_version=True),
        lambda data: data.update(compatible=False),
        lambda data: data["policy"].update(unknown=1),
        lambda data: data["summary"].update(regression=0),
        lambda data: data["cases"][0]["checks"][0].update(pass_rate_delta=0),
        lambda data: data["candidate"]["runs"][1]["cases"][0]["assertions"][0].update(passed=True),
    ],
)
def test_comparison_loader_recomputes_and_rejects_altered_verdicts(tmp_path, mutate):
    data = reliability_to_dict(compare_repeated(report([1, 1]), report([1, 0])))
    mutate(data)
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ReportValidationError):
        load_reliability_comparison(path)


def test_optional_langgraph_repeated_evidence_roundtrip_and_comparison(tmp_path):
    pytest.importorskip("langgraph.graph")
    from examples.langgraph_agent import build_agent
    from thadam import load_repeated, load_suite, write_repeated

    cases = load_suite("examples/langgraph_cases.json")
    baseline = run_repeated(cases=cases, agent_factory=build_agent, attempts=2)
    candidate = run_repeated(
        cases=cases, agent_factory=lambda: build_agent("skip_lookup"), attempts=2
    )
    path = tmp_path / "graph.json"
    write_repeated(candidate, path)
    comparison = compare_repeated(baseline, load_repeated(path))
    assert comparison.exit_code == 1
    assert len(comparison.cases) == 3
    assert all(run.cases[0].events for run in comparison.candidate.runs)
    assert all(case.change == "regression" for case in comparison.cases)
