"""Suite labels travel with evidence without weakening declared-check compatibility."""

import json
from dataclasses import replace

import pytest

from thadam import (
    OutputEquals,
    ReportValidationError,
    SuiteIdentity,
    SuiteValidationError,
    compare_repeated,
    compare_reports,
    comparison_to_dict,
    load_report,
    load_suite,
    report_to_dict,
    run_repeated,
    run_suite,
    write_report,
)
from thadam import TestCase as Case
from thadam import TestSuite as Suite
from thadam.repetition_loading import repeated_from_dict
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict


def suite(revision="v1", expected=1):
    return Suite(
        SuiteIdentity("refunds", revision), (Case("case", 1, (OutputEquals("answer", expected),)),)
    )


def test_identified_json_and_sdk_survive_round_trip(tmp_path):
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "suite": {"id": "refunds", "revision": "v1"},
                "cases": [
                    {
                        "id": "case",
                        "input": 1,
                        "assertions": [{"id": "answer", "type": "output_equals", "expected": 1}],
                    }
                ],
            }
        )
    )
    loaded = load_suite(path)
    assert loaded == suite()
    assert list(loaded) == list(suite().cases)
    assert loaded[:] == suite().cases
    report = run_suite(lambda x: x, loaded)
    assert report.schema_version == 4
    assert report.suite == SuiteIdentity("refunds", "v1")
    write_report(report, tmp_path / "report.json")
    assert load_report(tmp_path / "report.json") == report
    repeated = run_repeated(lambda x: x, loaded, attempts=2)
    assert all(run.suite == loaded.identity for run in repeated.runs)
    assert repeated_from_dict(repeated_to_dict(repeated)) == repeated


@pytest.mark.parametrize(
    "identity",
    [
        SuiteIdentity("", "v1"),
        SuiteIdentity("refunds", " "),
        SuiteIdentity(1, "v1"),
        SuiteIdentity("a", "\ud800"),
        "v1",
    ],
)
@pytest.mark.parametrize("repeated", [False, True])
def test_invalid_identity_precedes_user_code(identity, repeated):
    calls = []

    def agent(value):
        calls.append(value)
        return value

    with pytest.raises(SuiteValidationError):
        if repeated:
            run_repeated(
                cases=suite().cases,
                suite=identity,
                agent_factory=lambda: calls.append("factory"),
                attempts=2,
            )
        else:
            run_suite(agent, suite().cases, suite=identity)
    assert calls == []


def test_explicit_identity_and_embedded_identity_cannot_conflict():
    with pytest.raises(SuiteValidationError, match="conflicts"):
        run_suite(lambda x: x, suite(), suite=SuiteIdentity("other", "v1"))
    assert run_suite(lambda x: x, suite().cases, suite=suite().identity).suite == suite().identity


@pytest.mark.parametrize(
    "other", [suite("v2"), Suite(SuiteIdentity("other", "v1"), suite().cases), suite().cases]
)
def test_labels_must_match_in_both_comparators(other):
    a = run_suite(lambda x: x, suite())
    b = run_suite(lambda x: x, other)
    result = compare_reports(a, b)
    assert result.exit_code == 2
    assert any("Suite" in issue for case in result.cases for issue in case.issues)
    assert comparison_to_dict(result)["schema_version"] == 2
    assert comparison_to_dict(result)["baseline_suite"] == {"id": "refunds", "revision": "v1"}
    repeated = compare_repeated(
        run_repeated(lambda x: x, suite(), attempts=2), run_repeated(lambda x: x, other, attempts=2)
    )
    assert repeated.exit_code == 2
    assert repeated.issues


def test_matching_label_never_overrides_changed_expectation():
    a = run_suite(lambda x: x, suite())
    b = run_suite(lambda x: x, suite(expected=2))
    assert compare_reports(a, b).exit_code == 2
    assert (
        compare_repeated(
            run_repeated(lambda x: x, suite(), attempts=2),
            run_repeated(lambda x: x, suite(expected=2), attempts=2),
        ).exit_code
        == 2
    )


def test_schema_three_stays_exactly_legacy_and_cannot_smuggle_identity():
    raw = report_to_dict(run_suite(lambda x: x, suite().cases))
    assert raw["schema_version"] == 3 and "suite" not in raw
    assert (
        comparison_to_dict(compare_reports(report_from_dict(raw), report_from_dict(raw)))[
            "schema_version"
        ]
        == 1
    )
    raw["suite"] = {"id": "refunds", "revision": "v1"}
    with pytest.raises(ReportValidationError):
        report_from_dict(raw)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("suite"),
        lambda r: r.update(suite=None),
        lambda r: r["suite"].update(extra="x"),
        lambda r: r["suite"].update(revision=""),
        lambda r: r.update(schema_version=True),
    ],
)
def test_strict_schema_four_identity(mutate):
    raw = report_to_dict(run_suite(lambda x: x, suite()))
    mutate(raw)
    with pytest.raises(ReportValidationError):
        report_from_dict(raw)


def test_attempts_cannot_change_revision():
    report = run_repeated(lambda x: x, suite(), attempts=2)
    altered = replace(
        report, runs=(report.runs[0], replace(report.runs[1], suite=SuiteIdentity("refunds", "v2")))
    )
    with pytest.raises(ReportValidationError, match="Suite"):
        repeated_from_dict(repeated_to_dict(altered))


@pytest.mark.parametrize("identity", [None, "v1"])
def test_sdk_versioned_suite_cannot_silently_drop_invalid_identity(identity):
    with pytest.raises(SuiteValidationError):
        run_suite(lambda x: x, Suite(identity, suite().cases))


@pytest.mark.parametrize(
    "identity", [None, {}, {"id": "s", "revision": ""}, {"id": "s", "revision": "1", "extra": True}]
)
def test_versioned_suite_json_requires_exact_identity(tmp_path, identity):
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "suite": identity,
                "cases": [
                    {
                        "id": "x",
                        "input": 1,
                        "assertions": [{"id": "out", "type": "output_equals", "expected": 1}],
                    }
                ],
            }
        )
    )
    with pytest.raises(SuiteValidationError):
        load_suite(path)
