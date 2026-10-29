"""A controlled agent-shaped fixture for demonstrating the testing engine.

This is a local policy function, not an LLM agent. Wrap your existing agent with
the same one-input/one-output contract to test it without changing the runner.
"""

from thadam import JSONValue

ORDERS = {"order-001": 2500, "order-002": 6000}


def run(request: JSONValue) -> JSONValue:
    """Apply a 30-day refund policy to local order fixtures, using integer cents."""
    if not isinstance(request, dict):
        raise ValueError("Refund requests must be objects")
    order_id = request["order_id"]
    days = request["days_since_purchase"]
    if not isinstance(order_id, str) or type(days) is not int or days < 0:
        raise ValueError("Provide an order ID and a non-negative integer purchase age")
    if order_id not in ORDERS:
        return {"approved": False, "amount_cents": 0, "reason": "order_not_found"}
    if days > 30:
        return {"approved": False, "amount_cents": 0, "reason": "outside_refund_window"}
    return {"approved": True, "amount_cents": ORDERS[order_id], "reason": "eligible"}


def run_buggy(request: JSONValue) -> JSONValue:
    """Intentionally demonstrate one policy failure and one service exception."""
    if isinstance(request, dict):
        if request.get("order_id") == "order-002":
            raise TimeoutError("Order service did not respond")
        if request.get("order_id") == "order-001" and request["days_since_purchase"] > 30:
            return {"approved": True, "amount_cents": ORDERS["order-001"], "reason": "eligible"}
    return run(request)
