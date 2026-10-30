"""Real compiled LangGraph runs with controlled models, tools, and checkpoints."""

# Optional integration imports follow the dependency gate below.
# ruff: noqa: E402

import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

pytest.importorskip("langchain_core", minversion="1.0")
pytest.importorskip("langgraph.graph")

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, Generation, LLMResult
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from examples.langgraph_agent import agent, agent_buggy
from thadam import (
    AgentConfigurationError,
    AgentResult,
    OutputEquals,
    ToolCalled,
    ToolNotCalled,
    compare_reports,
    load_report,
    load_suite,
    report_to_dict,
    run_suite,
    write_report,
)
from thadam import TestCase as AgentTestCase
from thadam.adapters.langgraph import LangGraphAgent, _EventCollector

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def disable_external_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


class State(TypedDict):
    value: int


def graph_with(node, *, checkpointer=None):
    graph = StateGraph(State).add_node("work", node)
    graph.add_edge(START, "work")
    graph.add_edge("work", END)
    return graph.compile(checkpointer=checkpointer)


def test_real_graph_captures_model_tools_and_assertion_event_links():
    report = run_suite(agent, load_suite(ROOT / "examples/langgraph_cases.json"))
    assert not report.has_failures
    first = report.cases[0]
    assert first.trace_complete is True
    assert [(event.kind, event.name) for event in first.events] == [
        ("model", "FakeMessagesListChatModel"),
        ("tool", "get_order"),
        ("tool", "issue_refund"),
    ]
    assert all(event.status == "completed" and event.duration_ms >= 0 for event in first.events)
    assert all(event.parent_id for event in first.events)
    assert first.events[1].input == {"order_id": "order-001"}
    assert first.events[1].output == {"order_id": "order-001", "amount_cents": 2500}
    assert first.events[0].usage.input_tokens == 12
    assert first.events[0].usage.output_tokens == 3
    assert first.events[1].usage is None
    assert first.assertions[-1].event_ids == (first.events[-1].id,)
    assert first.events[0].input_available and first.events[0].output_available
    all_ids = [event.id for case in report.cases for event in case.events]
    assert len(set(all_ids)) == len(all_ids)


def test_plausible_output_still_fails_when_agent_skips_required_tool():
    cases = load_suite(ROOT / "examples/langgraph_cases.json")
    correct, buggy = run_suite(agent, cases), run_suite(agent_buggy, cases)
    assert [case.output for case in correct.cases] == [case.output for case in buggy.cases]
    assert [case.status for case in buggy.cases] == ["failed"] * 3
    for case in buggy.cases:
        check = next(item for item in case.assertions if item.id == "lookup-required")
        assert check.passed is False
        assert check.actual == {"calls": 0}
        assert case.trace_complete is True


def test_tool_exception_preserves_events_and_does_not_stop_later_case():
    @tool
    def unreliable(value: int) -> int:
        """Return positive values, simulating a service failure for zero."""
        if value == 0:
            raise TimeoutError("tool service unavailable")
        return value

    def node(state: State, config: RunnableConfig):
        return {"value": unreliable.invoke({"value": state["value"]}, config=config)}

    wrapped = LangGraphAgent(graph_with(node))
    cases = [
        AgentTestCase("broken", {"value": 0}, (ToolCalled("attempt", "unreliable"),)),
        AgentTestCase("next", {"value": 1}, (OutputEquals("out", {"value": 1}),)),
    ]
    report = run_suite(wrapped, cases)
    assert [case.status for case in report.cases] == ["error", "passed"]
    event = report.cases[0].events[0]
    assert event.status == "error"
    assert event.error.type == "TimeoutError"
    assert event.error.message == "tool service unavailable"
    assert event.input == {"value": 0}
    assert report.cases[0].errors[0].type == "TimeoutError"
    assert report.cases[0].trace_complete is True


@pytest.mark.parametrize(
    "counts", [None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}]
)
def test_missing_usage_is_distinct_from_reported_zero(counts):
    model = FakeMessagesListChatModel(responses=[AIMessage(content="ok", usage_metadata=counts)])

    def node(state: State, config: RunnableConfig):
        model.invoke([HumanMessage(content="test")], config=config)
        return state

    result = LangGraphAgent(graph_with(node))({"value": 1})
    assert (
        result.events[0].usage is None
        if counts is None
        else result.events[0].usage.total_tokens == 0
    )


def test_text_model_callbacks_and_unknown_usage_work():
    model = FakeListLLM(responses=["ok"])

    def node(state: State, config: RunnableConfig):
        model.invoke("test prompt", config=config)
        return state

    result = LangGraphAgent(graph_with(node))({"value": 1})
    assert result.events[0].kind == "model"
    assert result.events[0].input == ["test prompt"]
    assert result.events[0].usage is None


def test_model_exception_becomes_errored_event():
    model = FakeMessagesListChatModel(responses=[])

    def node(state: State, config: RunnableConfig):
        model.invoke([HumanMessage(content="test")], config=config)
        return state

    result = run_suite(
        LangGraphAgent(graph_with(node)),
        [AgentTestCase("model-error", {"value": 1}, (OutputEquals("out", None),))],
    ).cases[0]
    assert result.status == "error"
    assert result.events[0].kind == "model"
    assert result.events[0].status == "error"


def test_existing_callbacks_config_and_fresh_checkpoint_threads_are_preserved():
    thread_ids, callbacks = [], []

    class Observer(BaseCallbackHandler):
        def on_chain_start(self, serialized, inputs, **kwargs):
            callbacks.append(kwargs.get("tags", []))

    def node(state: State, config: RunnableConfig):
        thread_ids.append(config["configurable"]["thread_id"])
        assert config["configurable"]["project"] == "test"
        return {"value": state.get("value", 0) + 1}

    observer = Observer()
    config = {
        "callbacks": [observer],
        "tags": ["existing"],
        "configurable": {"thread_id": "original", "project": "test"},
    }
    wrapped = LangGraphAgent(graph_with(node, checkpointer=InMemorySaver()), config=config)
    cases = [
        AgentTestCase(str(i), {"value": 0}, (OutputEquals("out", {"value": 1}),)) for i in range(2)
    ]
    assert not run_suite(wrapped, cases).has_failures
    assert len(set(thread_ids)) == 2
    assert "original" not in thread_ids
    assert config["configurable"]["thread_id"] == "original"
    assert config["callbacks"] == [observer]
    assert any("existing" in tags for tags in callbacks)


def test_parallel_node_events_keep_their_own_arguments_and_outputs():
    barrier = Barrier(2, timeout=5)

    @tool
    def concurrent_tool(value: int) -> int:
        """Wait for both parallel nodes before returning a distinct result."""
        barrier.wait()
        return value * 2

    class ParallelState(TypedDict):
        left: int
        right: int

    def left(state: ParallelState, config: RunnableConfig):
        return {"left": concurrent_tool.invoke({"value": 1}, config=config)}

    def right(state: ParallelState, config: RunnableConfig):
        return {"right": concurrent_tool.invoke({"value": 2}, config=config)}

    builder = StateGraph(ParallelState).add_node("left", left).add_node("right", right)
    builder.add_edge(START, "left").add_edge(START, "right")
    builder.add_edge("left", END).add_edge("right", END)
    result = LangGraphAgent(builder.compile())({"left": 0, "right": 0})
    assert result.output == {"left": 2, "right": 4}
    assert result.trace_complete
    assert len({event.id for event in result.events}) == 2
    assert {(event.input["value"], event.output) for event in result.events} == {(1, 2), (2, 4)}


def test_mapping_error_preserves_the_completed_graph_trace():
    def bad_mapper(_state):
        raise ValueError("cannot select output")

    wrapped = LangGraphAgent(agent.graph, input_mapper=agent.input_mapper, output_mapper=bad_mapper)
    case = load_suite(ROOT / "examples/langgraph_cases.json")[0]
    result = run_suite(wrapped, [case]).cases[0]
    assert result.status == "error"
    assert len(result.events) == 3
    assert result.errors[0].message == "cannot select output"


def test_graph_interrupt_is_not_a_successful_run():
    def node(state: State):
        interrupt("needs approval")
        return state

    wrapped = LangGraphAgent(graph_with(node, checkpointer=InMemorySaver()))
    result = run_suite(
        wrapped, [AgentTestCase("paused", {"value": 1}, (ToolNotCalled("no-tool", "anything"),))]
    ).cases[0]
    assert result.status == "error"
    assert "interrupted before completion" in result.errors[0].message


def test_unfinished_or_unmatched_callbacks_make_trace_incomplete():
    collector = _EventCollector()
    collector.on_tool_start({"name": "get_order"}, "{}", run_id=uuid4(), inputs={})
    collector.on_tool_end("orphan", run_id=uuid4())
    events, complete, warnings = collector.finish()
    assert not complete
    assert events[0].status == "incomplete"
    assert len(warnings) == 2

    def wrapped(_value):
        return AgentResult("ok", events, complete, warnings)

    result = run_suite(
        wrapped, [AgentTestCase("trace", None, (ToolNotCalled("no-tool", "other"),))]
    ).cases[0]
    assert result.status == "error"
    assert result.trace_warnings


def test_tool_error_message_status_is_not_recorded_as_success():
    collector = _EventCollector()
    run_id = uuid4()
    collector.on_tool_start({"name": "tool"}, "{}", run_id=run_id, inputs={})
    collector.on_tool_end(
        ToolMessage(content="handled failure", tool_call_id="call", status="error"), run_id=run_id
    )
    events, complete, _ = collector.finish()
    assert complete
    assert events[0].status == "error"
    assert events[0].error.message == "handled failure"
    assert events[0].output_available
    assert events[0].output["content"] == "handled failure"


def test_tool_run_display_name_does_not_change_assertion_identity():
    @tool
    def named_tool(value: int) -> int:
        """Return a value with a custom display name on the invocation."""
        return value

    def node(state: State, config: RunnableConfig):
        configured = {**config, "run_name": "friendly-display-name"}
        return {"value": named_tool.invoke({"value": state["value"]}, config=configured)}

    case = AgentTestCase("identity", {"value": 1}, (ToolCalled("named", "named_tool"),))
    result = run_suite(LangGraphAgent(graph_with(node)), [case]).cases[0]
    assert result.status == "passed"
    assert result.events[0].name == "named_tool"


def test_aggregate_usage_is_reported_without_guessing_multi_generation_counts():
    collector = _EventCollector()
    run_id = uuid4()
    collector.on_llm_start({"name": "model"}, ["prompt"], run_id=run_id)
    collector.on_llm_end(
        LLMResult(
            generations=[[Generation(text="answer")]],
            llm_output={
                "token_usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}
            },
        ),
        run_id=run_id,
    )
    events, complete, _ = collector.finish()
    assert complete
    assert events[0].usage.input_tokens == 8
    assert events[0].usage.output_tokens == 2
    assert events[0].usage.total_tokens == 10

    collector = _EventCollector()
    collector.on_chat_model_start({"name": "model"}, [], run_id=run_id)
    message = AIMessage(
        content="answer", usage_metadata={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}
    )
    collector.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=message), ChatGeneration(message=message)]]),
        run_id=run_id,
    )
    assert collector.finish()[0][0].usage is None


def test_async_mappers_are_rejected_without_unawaited_coroutines():
    async def asynchronous(value):
        return value

    with pytest.raises(AgentConfigurationError, match="synchronous"):
        LangGraphAgent(agent.graph, input_mapper=asynchronous)
    wrapped = LangGraphAgent(agent.graph, input_mapper=lambda value: asynchronous(value))
    case = load_suite(ROOT / "examples/langgraph_cases.json")[0]
    result = run_suite(wrapped, [case]).cases[0]
    assert result.status == "error"
    assert "synchronous values" in result.errors[0].message


def test_checkpoint_resumption_and_wrong_graph_are_configuration_errors():
    with pytest.raises(AgentConfigurationError, match="compiled StateGraph"):
        LangGraphAgent(object())
    with pytest.raises(AgentConfigurationError, match="resumption"):
        LangGraphAgent(agent.graph, config={"configurable": {"checkpoint_id": "previous"}})


def test_cli_uses_same_traced_graph_outcomes_and_versioned_artifact(tmp_path):
    destination = tmp_path / "graph.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "thadam",
            "run",
            "examples/langgraph_cases.json",
            "--agent",
            "examples.langgraph_agent:agent_buggy",
            "--report",
            str(destination),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 1, process.stderr
    data = json.loads(destination.read_text())
    sdk = report_to_dict(run_suite(agent_buggy, load_suite(ROOT / "examples/langgraph_cases.json")))
    assert data["schema_version"] == 3
    assert data["summary"] == sdk["summary"]
    assert "lookup-required" in process.stdout
    assert "model FakeMessagesListChatModel" in process.stdout
    assert all(case["trace_complete"] for case in data["cases"])
    assert all(event["duration_ms"] >= 0 for case in data["cases"] for event in case["events"])


def test_core_import_does_not_require_or_load_langgraph():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    process = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import thadam, sys; assert not any(n.startswith('langchain') "
            "or n.startswith('langgraph') for n in sys.modules)",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 0, process.stderr


def test_real_graph_reports_compare_tool_regressions_despite_identical_answers(tmp_path):
    cases = load_suite(ROOT / "examples/langgraph_cases.json")
    baseline = run_suite(agent, cases)
    candidate = run_suite(agent_buggy, cases)
    for name, report in (("baseline", baseline), ("candidate", candidate)):
        write_report(report, tmp_path / f"{name}.json")
    result = compare_reports(
        load_report(tmp_path / "baseline.json"), load_report(tmp_path / "candidate.json")
    )
    assert [case.output for case in baseline.cases] == [case.output for case in candidate.cases]
    assert result.exit_code == 1
    assert result.summary.regressions == 3
    first = next(check for check in result.cases[0].checks if check.id == "lookup-required")
    assert first.change == "regression"
    assert first.baseline.event_ids
    assert first.candidate.event_ids == ()
