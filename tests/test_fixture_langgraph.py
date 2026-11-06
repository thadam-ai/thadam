"""Real graph integration of scripted tools, including async callback evidence."""

# ruff: noqa: E402
import asyncio

import pytest

pytest.importorskip("langchain_core", minversion="1.0")
pytest.importorskip("langgraph.graph")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

from thadam import (
    FixtureAgent,
    OutputEquals,
    ToolCallCount,
    ToolRaise,
    ToolReturn,
    ToolScript,
    run_suite,
    run_suite_async,
)
from thadam import TestCase as Case
from thadam.adapters.langgraph import LangGraphAgent, fixture_tool
from thadam.report_loading import validate_report


class Arguments(BaseModel):
    value: int


class State(TypedDict):
    value: int


@pytest.mark.parametrize("async_execution", [False, True])
def test_fixture_tool_counted_once_while_model_events_and_usage_retained(
    monkeypatch, async_execution
):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    def factory(tools):
        lookup = fixture_tool(
            tools["lookup"], args_schema=Arguments, description="Controlled lookup"
        )
        model = FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="lookup",
                    usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                )
            ]
        )

        def sync_node(state, config):
            model.invoke("look up", config=config)
            try:
                result = lookup.invoke(state, config=config)
            except ConnectionError:
                result = lookup.invoke(state, config=config)
            return {"value": result}

        async def async_node(state, config):
            await model.ainvoke("look up", config=config)
            try:
                result = await lookup.ainvoke(state, config=config)
            except ConnectionError:
                result = await lookup.ainvoke(state, config=config)
            return {"value": result}

        graph = StateGraph(State).add_node("work", async_node if async_execution else sync_node)
        graph.add_edge(START, "work").add_edge("work", END)
        wrapped = LangGraphAgent(graph.compile())
        return wrapped.ainvoke if async_execution else wrapped

    case = Case(
        "recover",
        {"value": 1},
        (OutputEquals("out", {"value": 25}), ToolCallCount("count", "lookup", 2, 2)),
        tool_fixtures={
            "lookup": ToolScript((ToolRaise("ConnectionError", "offline"), ToolReturn(25)))
        },
    )
    report = (
        asyncio.run(run_suite_async(FixtureAgent(factory), [case]))
        if async_execution
        else run_suite(FixtureAgent(factory), [case])
    )
    result = validate_report(report).cases[0]
    assert result.status == "passed", result.errors
    assert result.trace_complete and not result.trace_warnings
    assert len(result.events) == 3
    assert len({event.id for event in result.events}) == 3
    models = [event for event in result.events if event.kind == "model"]
    assert len(models) == 1 and models[0].usage.total_tokens == 3
    assert [event.status for event in result.events if event.kind == "tool"] == [
        "error",
        "completed",
    ]
