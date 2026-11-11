"""Public execution-policy contracts across runners and saved evidence."""

import asyncio
from copy import deepcopy

import pytest

from thadam import (
    ConversationTurn,
    ExecutionLimits,
    FixtureAgent,
    OutputEquals,
    StateFixture,
    SuiteIdentity,
    run_repeated,
    run_repeated_async,
    run_suite,
    run_suite_async,
)
from thadam import (
    TestCase as Case,
)
from thadam.baseline_review import review_baseline
from thadam.comparison import compare_reports
from thadam.errors import ReportValidationError, SuiteValidationError
from thadam.repetition_loading import repeated_from_dict
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict
from thadam.reporting import report_to_dict


def identity(value):
    return value


def factory():
    return identity


async def async_factory():
    return identity


def conversation_factory(tools):
    return identity


def make_case():
    return Case("one", "ok", assertions=(OutputEquals("expected", "ok"),))


@pytest.mark.parametrize("async_mode", [False, True])
def test_suite_deadline_public_api_roundtrip(async_mode):
    limits = ExecutionLimits(timeout_seconds=5, cleanup_timeout_seconds=0.2)
    report = (
        asyncio.run(run_suite_async(identity, [make_case()], limits=limits))
        if async_mode
        else run_suite(identity, [make_case()], limits=limits)
    )
    assert report.summary.passed == 1
    assert report.schema_version == 7
    assert report.cases[0].execution_limits == limits
    raw = report_to_dict(report)
    assert report_to_dict(report_from_dict(raw)) == raw
    broken = deepcopy(raw)
    broken["cases"][0]["execution_limits"]["unexpected"] = True
    with pytest.raises(ReportValidationError):
        report_from_dict(broken)


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("factory_mode", [False, True])
def test_repeated_limits_keep_every_attempt_and_factory_mode(async_mode, factory_mode):
    limits = ExecutionLimits(timeout_seconds=5, cleanup_timeout_seconds=0.1)
    kwargs = (
        {"agent_factory": async_factory if async_mode else factory}
        if factory_mode
        else {"agent": identity}
    )
    if async_mode:
        report = asyncio.run(
            run_repeated_async(cases=[make_case()], attempts=2, limits=limits, **kwargs)
        )
    else:
        report = run_repeated(cases=[make_case()], attempts=2, limits=limits, **kwargs)
    assert report.schema_version == 4
    assert report.execution_mode == ("factory" if factory_mode else "shared")
    assert len(report.runs) == 2
    assert all(run.summary.passed == 1 and run.schema_version == 7 for run in report.runs)
    raw = repeated_to_dict(report)
    assert repeated_to_dict(repeated_from_dict(raw)) == raw


def test_changed_limits_incompatible_and_require_revision_review():
    suite = SuiteIdentity("policy", "v1")
    baseline = run_suite(identity, [make_case()], suite=suite, limits=ExecutionLimits(max_turns=1))
    candidate = run_suite(identity, [make_case()], suite=suite, limits=ExecutionLimits(max_turns=2))
    assert not compare_reports(baseline, candidate).compatible
    review = review_baseline(candidate, baseline)
    assert any(change.scope == "execution_limits_changed" for change in review.changes)
    assert review.blockers


@pytest.mark.parametrize("async_mode", [False, True])
def test_turn_limit_retains_prior_turn_and_strict_roundtrip(async_mode):
    configured = Case(
        "turns",
        None,
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={},
        conversation=(ConversationTurn("first", "hello"), ConversationTurn("second", "later")),
    )
    kwargs = {"limits": ExecutionLimits(max_turns=1)}
    report = (
        asyncio.run(run_suite_async(FixtureAgent(conversation_factory), [configured], **kwargs))
        if async_mode
        else run_suite(FixtureAgent(conversation_factory), [configured], **kwargs)
    )
    result = report.cases[0]
    assert result.status == "error"
    assert result.errors[0].type == "TurnLimitExceeded"
    assert [turn.id for turn in result.conversation_results] == ["first"]
    raw = report_to_dict(report)
    assert report_to_dict(report_from_dict(raw)) == raw


def test_startup_timeout_with_state_roundtrips_unknown_final():
    configured = Case(
        "state",
        None,
        assertions=(OutputEquals("expected", None),),
        tool_fixtures={},
        state_fixture=StateFixture({"ready": False}),
    )
    report = run_suite(
        FixtureAgent(conversation_factory),
        [configured],
        limits=ExecutionLimits(timeout_seconds=0.00001, cleanup_timeout_seconds=0.1),
    )
    assert report.cases[0].errors[0].type == "TimeoutError"
    assert report.cases[0].state_initial == {"ready": False}
    assert report.cases[0].state_final is None
    raw = report_to_dict(report)
    assert report_to_dict(report_from_dict(raw)) == raw


@pytest.mark.parametrize(
    "limits",
    [
        ExecutionLimits(),
        ExecutionLimits(max_turns=True),
        ExecutionLimits(max_turns=0),
        ExecutionLimits(timeout_seconds=float("nan")),
        ExecutionLimits(timeout_seconds=1, cleanup_timeout_seconds=-1),
    ],
)
@pytest.mark.parametrize("async_mode", [False, True])
def test_invalid_policy_never_executes_application(limits, async_mode):
    called = []

    def agent(value):
        called.append(value)
        return value

    with pytest.raises(SuiteValidationError):
        if async_mode:
            asyncio.run(run_suite_async(agent, [make_case()], limits=limits))
        else:
            run_suite(agent, [make_case()], limits=limits)
    assert not called


@pytest.mark.parametrize("async_mode", [False, True])
def test_invalid_repeated_policy_does_not_construct_factory(async_mode):
    called = []

    def forbidden_factory():
        called.append(True)
        return identity

    with pytest.raises(SuiteValidationError):
        if async_mode:
            asyncio.run(
                run_repeated_async(
                    cases=[make_case()],
                    agent_factory=forbidden_factory,
                    attempts=2,
                    limits=ExecutionLimits(timeout_seconds=0),
                )
            )
        else:
            run_repeated(
                cases=[make_case()],
                agent_factory=forbidden_factory,
                attempts=2,
                limits=ExecutionLimits(timeout_seconds=0),
            )
    assert not called


def test_repeated_loader_rejects_changed_policy_between_attempts():
    report = run_repeated(identity, [make_case()], attempts=2, limits=ExecutionLimits(max_turns=1))
    raw = repeated_to_dict(report)
    raw["runs"][1]["cases"][0]["execution_limits"]["max_turns"] = 2
    with pytest.raises(ReportValidationError, match="limits differ"):
        repeated_from_dict(raw)


def test_loader_rejects_observed_turns_exceeding_saved_policy():
    configured = Case(
        "turns",
        None,
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={},
        conversation=(ConversationTurn("first", "hello"), ConversationTurn("second", "later")),
    )
    report = run_suite(
        FixtureAgent(conversation_factory), [configured], limits=ExecutionLimits(max_turns=2)
    )
    raw = report_to_dict(report)
    raw["cases"][0]["execution_limits"]["max_turns"] = 1
    with pytest.raises(ReportValidationError):
        report_from_dict(raw)


def test_limited_plain_regression_draft_retains_source_policy_only():
    from thadam.regression import regression_draft

    report = run_suite(identity, [make_case()], limits=ExecutionLimits(max_turns=1))
    raw = report_to_dict(report)
    draft = regression_draft(raw, path="run.json", fingerprint="0" * 64, case_id="one")
    assert draft["source"]["run"] == raw
    assert draft["source"]["run"]["cases"][0]["execution_limits"]["max_turns"] == 1
    assert draft["case"] == {"id": "one-regression", "input": "ok", "assertions": []}


def test_limited_simulation_regression_draft_preserves_declared_setup():
    from thadam.models import ToolReturn, ToolScript
    from thadam.regression import regression_draft

    configured = Case(
        "simulation",
        {"context": True},
        assertions=(OutputEquals("expected", "ok"),),
        tool_fixtures={"unused": ToolScript((ToolReturn({"value": 1}),))},
        conversation=(ConversationTurn("first", "hello"),),
        state_fixture=StateFixture({"initial": True}),
    )
    raw = report_to_dict(
        run_suite(
            FixtureAgent(conversation_factory), [configured], limits=ExecutionLimits(max_turns=1)
        )
    )
    draft = regression_draft(raw, path="run.json", fingerprint="0" * 64, case_id="simulation")
    assert draft["source"]["run"] == raw
    source = raw["cases"][0]
    for field in ("input", "tool_fixtures", "conversation", "state_fixture"):
        assert draft["case"][field] == source[field]
    assert draft["case"]["assertions"] == []
    assert "execution_limits" not in draft["case"]
