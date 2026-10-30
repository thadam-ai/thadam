"""Regression gates depend on compatible contracts and each individual verdict."""

from dataclasses import replace

import pytest

from thadam import (
    AgentResult,
    CheckResult,
    OutputEquals,
    OutputHasKeys,
    ReportValidationError,
    SuiteValidationError,
    ToolCalled,
    Verifier,
    compare_reports,
    comparison_to_dict,
    load_report,
    run_suite,
    write_comparison,
    write_report,
)
from thadam import TestCase as AgentCase


def echo_case(case_id="echo", value=1, expected=1):
    return AgentCase(case_id, value, (OutputEquals("answer", expected),))


@pytest.mark.parametrize(
    ("old", "new", "change", "code"),
    [
        (1, 1, "unchanged_pass", 0),
        (1, 0, "regression", 1),
        (0, 1, "fixed", 0),
        (0, 0, "existing_failure", 0),
    ],
)
def test_each_verdict_transition(old, new, change, code):
    baseline = run_suite(lambda _: old, [echo_case()], agent_revision="before")
    candidate = run_suite(lambda _: new, [echo_case()], agent_revision="after")
    report = compare_reports(baseline, candidate)
    assert report.exit_code == code
    assert report.compatible
    assert report.cases[0].change == change
    assert report.cases[0].checks[0].change == change
    assert sum(vars(report.summary).values()) == 2  # One total and one classified case.
    assert report.baseline_agent_revision == "before"
    assert report.candidate_agent_revision == "after"


def test_failed_to_failed_case_can_contain_a_new_regression():
    case = AgentCase(
        "two-checks",
        None,
        (
            OutputEquals("exact", {"answer": 1}),
            OutputHasKeys("required", ("answer",)),
        ),
    )
    baseline = run_suite(lambda _: {"answer": 2}, [case])
    candidate = run_suite(lambda _: {}, [case])
    assert baseline.cases[0].status == candidate.cases[0].status == "failed"
    result = compare_reports(baseline, candidate)
    assert result.exit_code == 1
    assert result.cases[0].change == "regression"
    assert [item.change for item in result.cases[0].checks] == ["existing_failure", "regression"]


def test_case_order_check_order_and_object_key_order_are_not_identity():
    first = AgentCase(
        "first",
        {"a": 1, "b": 2},
        (
            OutputHasKeys("keys", ("a", "b")),
            OutputEquals("exact", {"a": 1, "b": 2}),
        ),
    )
    second = echo_case("second")
    reordered = replace(
        first,
        input={"b": 2, "a": 1},
        assertions=(
            OutputEquals("exact", {"b": 2, "a": 1}),
            OutputHasKeys("keys", ("b", "a")),
        ),
    )
    result = compare_reports(
        run_suite(lambda value: value, [first, second]),
        run_suite(lambda value: value, [second, reordered]),
    )
    assert result.exit_code == 0
    assert [case.id for case in result.cases] == ["first", "second"]
    assert [check.id for check in result.cases[0].checks] == ["keys", "exact"]


@pytest.mark.parametrize(
    "candidate_case",
    [
        echo_case(value=2),
        echo_case(expected=2),
        AgentCase("echo", 1, (OutputHasKeys("answer", ("value",)),)),
        AgentCase("echo", 1, (OutputEquals("renamed", 1),)),
        AgentCase("echo", 1, (OutputEquals("answer", 1), OutputEquals("added", 1))),
    ],
)
def test_changed_contracts_are_incompatible(candidate_case):
    result = compare_reports(
        run_suite(lambda value: value, [echo_case()]),
        run_suite(lambda value: value, [candidate_case]),
    )
    assert result.exit_code == 2
    assert not result.compatible
    assert result.cases[0].change == "incompatible"
    assert result.cases[0].issues


def test_added_and_missing_cases_are_visible():
    result = compare_reports(
        run_suite(lambda value: value, [echo_case("missing")]),
        run_suite(lambda value: value, [echo_case("added")]),
    )
    assert result.exit_code == 2
    assert [case.id for case in result.cases] == ["missing", "added"]
    assert result.summary.incompatible == 2


def test_numbers_and_booleans_follow_existing_json_semantics():
    baseline = run_suite(lambda value: value, [echo_case()])
    same_number = run_suite(lambda value: value, [echo_case(value=1.0, expected=1.0)])
    boolean = run_suite(lambda value: value, [echo_case(value=True, expected=True)])
    assert compare_reports(baseline, same_number).exit_code == 0
    assert compare_reports(baseline, boolean).exit_code == 2


@pytest.mark.parametrize(
    ("before", "after", "code"),
    [(None, None, 2), ("v1", "v2", 2), ("v1", None, 2), ("v1", "v1", 0)],
)
def test_verifiers_require_matching_explicit_revisions(before, after, code):
    calls = []

    def verifier(_input, _output):
        calls.append(1)
        return CheckResult(True, "valid", expected=1, actual=1)

    baseline = run_suite(
        lambda value: value,
        [
            AgentCase(
                "custom",
                None,
                verifiers=(Verifier("policy", verifier, revision=before),),
            )
        ],
    )
    candidate = run_suite(
        lambda value: value,
        [
            AgentCase(
                "custom",
                None,
                verifiers=(Verifier("policy", verifier, revision=after),),
            )
        ],
    )
    assert len(calls) == 2
    assert compare_reports(baseline, candidate).exit_code == code
    assert len(calls) == 2  # Loading/comparison never re-executes custom code.


def test_errors_on_either_side_block_a_clean_gate_and_keep_all_cases():
    def broken(_):
        raise TimeoutError("service unavailable")

    cases = [echo_case("first"), echo_case("later")]
    good = run_suite(lambda value: value, cases)
    bad = run_suite(broken, cases)
    for baseline, candidate in ((good, bad), (bad, good), (bad, bad)):
        report = compare_reports(baseline, candidate)
        assert report.exit_code == 1
        assert report.summary.errors == 2
        assert all(case.change == "error" for case in report.cases)
        assert report.cases[0].baseline_errors or report.cases[0].candidate_errors


def test_unknown_tool_evidence_cannot_become_a_pass_or_a_baseline_allowance():
    case = AgentCase("tools", None, (ToolCalled("lookup", "get_order"),))
    unknown = run_suite(lambda _: None, [case])
    observed_empty = run_suite(lambda _: AgentResult(None), [case])
    result = compare_reports(observed_empty, unknown)
    assert result.exit_code == 1
    assert result.cases[0].candidate_errors[0].source == "assertion"


def test_report_round_trip_and_comparison_evidence_are_independent(tmp_path):
    baseline = run_suite(lambda _: {"value": [1]}, [echo_case(expected={"value": [1]})])
    candidate = run_suite(lambda _: {"value": [2]}, [echo_case(expected={"value": [1]})])
    path = tmp_path / "run.json"
    write_report(candidate, path)
    loaded = load_report(path)
    assert loaded == candidate
    result = compare_reports(baseline, loaded)
    candidate.cases[0].output["value"].append(3)
    loaded.cases[0].assertions[0].actual["value"].append(4)
    assert result.cases[0].checks[0].candidate.actual == {"value": [2]}
    comparison_path = tmp_path / "comparison.json"
    write_comparison(result, comparison_path)
    import json

    artifact = json.loads(comparison_path.read_text())
    assert artifact == comparison_to_dict(result)
    assert artifact["kind"] == "comparison"
    assert artifact["schema_version"] == 1
    assert artifact["exit_code"] == 1
    assert artifact["cases"][0]["checks"][0]["candidate"]["actual"] == {"value": [2]}


def test_invalid_sdk_reports_use_the_same_validation_as_files():
    report = run_suite(lambda value: value, [echo_case()])
    invalid = replace(report, cases=(replace(report.cases[0], assertions=()),))
    with pytest.raises(ReportValidationError, match="Every declared check"):
        compare_reports(report, invalid)
    with pytest.raises(ReportValidationError):
        compare_reports(report, object())


@pytest.mark.parametrize("revision", ["", " ", 1, True, "\ud800"])
def test_bad_revisions_are_rejected_before_agent_execution(revision):
    def agent(_):
        pytest.fail("Agent must not run")

    with pytest.raises(SuiteValidationError):
        run_suite(agent, [echo_case()], agent_revision=revision)
    with pytest.raises(SuiteValidationError):
        run_suite(
            agent,
            [
                AgentCase(
                    "custom",
                    None,
                    verifiers=(
                        Verifier("policy", lambda _i, _o: CheckResult(True, "valid"), revision),
                    ),
                )
            ],
        )
