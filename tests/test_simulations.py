"""Conversation turns and observable state are retained as strict evidence."""

import asyncio
from pathlib import Path

from thadam import (
    ConversationTurn,
    FixtureAgent,
    OutputEquals,
    StateChanges,
    StateEquals,
    StateFixture,
    load_repeated,
    load_report,
    load_suite,
    report_to_dict,
    run_repeated,
    run_suite,
    run_suite_async,
    write_repeated,
    write_report,
)
from thadam import TestCase as Case
from thadam.repetition_reporting import repeated_to_dict
from thadam.report_loading import report_from_dict

ROOT = Path(__file__).resolve().parents[1]


def test_refund_conversation_reports_each_turn_and_round_trips(tmp_path):
    from examples.refund_conversation_agent import create, create_buggy

    cases = load_suite(ROOT / "examples/refund_conversation_cases.json")
    report = run_suite(FixtureAgent(create), cases)
    result = report.cases[0]

    assert report.schema_version == 6 and report.summary.passed == 1
    assert [turn.id for turn in result.conversation_results] == [
        "initial-request",
        "correction",
        "confirmation",
        "repeat-request",
    ]
    assert result.conversation_results[1].output == {
        "amount_cents": 2500,
        "corrected": True,
    }
    assert result.state_initial == {"refunds": []}
    assert result.state_final == {"refunds": [{"order_id": "ord-42", "amount_cents": 2500}]}

    destination = tmp_path / "run.json"
    write_report(report, destination)
    assert load_report(destination) == report
    assert run_suite(FixtureAgent(create_buggy), cases).summary.failed == 1


def test_repeated_simulations_reset_state_and_preserve_each_attempt(tmp_path):
    from examples.refund_conversation_agent import create

    cases = load_suite(ROOT / "examples/refund_conversation_cases.json")
    repeated = run_repeated(FixtureAgent(create), cases, attempts=3)

    assert repeated.schema_version == 3
    assert repeated.execution_mode == "simulations"
    assert all(run.schema_version == 6 and run.summary.passed == 1 for run in repeated.runs)
    assert all(
        run.cases[0].state_final == repeated.runs[0].cases[0].state_final for run in repeated.runs
    )
    destination = tmp_path / "repeated.json"
    write_repeated(repeated, destination)
    assert repeated_to_dict(load_repeated(destination)) == repeated_to_dict(repeated)


def test_failed_turn_retains_completed_responses_state_and_strict_evidence():
    def create(tools):
        def agent(request):
            if request["turn_id"] == "first":
                tools.state.write({"count": 1})
                return "recorded"
            raise RuntimeError("simulated interruption")

        return agent

    case = Case(
        "partial-conversation",
        {},
        (OutputEquals("final", "unused"), StateEquals("count", {"count": 1})),
        conversation=(ConversationTurn("first", "one"), ConversationTurn("second", "two")),
        state_fixture=StateFixture({"count": 0}),
    )
    report = run_suite(FixtureAgent(create), [case])
    result = report.cases[0]

    assert result.status == "error"
    assert result.errors[0].type == "RuntimeError"
    assert [
        (turn.id, turn.output, turn.output_available) for turn in result.conversation_results
    ] == [("first", "recorded", True)]
    assert result.state_initial == {"count": 0}
    assert result.state_final == {"count": 1}
    assert report_from_dict(report_to_dict(report)) == report


def test_async_simulations_use_same_conversation_and_state_contract():
    async def exercise():
        async def create(tools):
            async def agent(request):
                state = tools.state.read()
                state["count"] += 1
                tools.state.write(state)
                return {"turn": request["turn_id"], "count": state["count"]}

            return agent

        case = Case(
            "async-simulation",
            {"key": "value"},
            (
                OutputEquals("last", {"turn": "two", "count": 2}),
                StateEquals("state", {"count": 2}),
                StateChanges("allowed", ("count",)),
            ),
            conversation=(ConversationTurn("one", "first"), ConversationTurn("two", "second")),
            state_fixture=StateFixture({"count": 0}),
        )
        report = await run_suite_async(FixtureAgent(create), [case])

        assert report.schema_version == 6 and report.summary.passed == 1
        assert [turn.output["count"] for turn in report.cases[0].conversation_results] == [1, 2]

    asyncio.run(exercise())
