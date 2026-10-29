"""Actual LangGraph execution with a scripted model and local tools; no provider key.

The model's usage metadata is a fixture, not measured or billable token usage.
Its response chooses the plan. The buggy plan approves without looking up an
order, demonstrating why a plausible final answer can still fail a tool check.
"""

import json
from typing import Literal

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from examples.refund_agent import ORDERS
from thadam import JSONValue
from thadam.adapters.langgraph import LangGraphAgent


class RefundState(TypedDict):
    request: dict[str, JSONValue]
    result: JSONValue


@tool
def get_order(order_id: str) -> dict:
    """Look up the order amount in cents using local order fixtures."""
    return {"order_id": order_id, "amount_cents": ORDERS.get(order_id)}


@tool
def issue_refund(order_id: str, amount_cents: int) -> dict:
    """Issue a simulated refund; this fixture never moves money."""
    return {"approved": True, "amount_cents": amount_cents, "reason": "eligible"}


def build_agent(plan: Literal["lookup_order", "skip_lookup"] = "lookup_order") -> LangGraphAgent:
    """Create a graph that explicitly propagates callbacks to model/tool invocations."""
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=plan,
                usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
            )
        ]
    )

    def decide(state: RefundState, config: RunnableConfig) -> dict:
        request = state["request"]
        order_id, days = request["order_id"], request["days_since_purchase"]
        response = model.invoke([HumanMessage(content=json.dumps(request))], config=config)
        if response.content == "skip_lookup":
            amount = ORDERS.get(order_id)
        else:
            order = get_order.invoke({"order_id": order_id}, config=config)
            amount = order["amount_cents"]
        if amount is None:
            result = {"approved": False, "amount_cents": 0, "reason": "order_not_found"}
        elif days > 30:
            result = {"approved": False, "amount_cents": 0, "reason": "outside_refund_window"}
        else:
            result = issue_refund.invoke(
                {"order_id": order_id, "amount_cents": amount}, config=config
            )
        return {"result": result}

    graph = StateGraph(RefundState).add_node("decide", decide)
    graph.add_edge(START, "decide")
    graph.add_edge("decide", END)
    return LangGraphAgent(
        graph.compile(),
        input_mapper=lambda value: {"request": value},
        output_mapper=lambda state: state["result"],
    )


agent = build_agent()
agent_buggy = build_agent("skip_lookup")
