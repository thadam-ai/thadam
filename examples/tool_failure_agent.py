"""Controlled refund recovery; these fixtures never contact a service or move money."""

from thadam import FixtureTools, JSONValue


def _build(tools: FixtureTools, attempts: int, *, recover: bool = True):
    def run(value: JSONValue) -> JSONValue:
        for _ in range(attempts):
            try:
                order = tools["get_order"].invoke({"order_id": value["order_id"]})
            except (ConnectionError, TimeoutError):
                if not recover:
                    raise
                continue
            if isinstance(order, dict) and type(order.get("amount_cents")) is int:
                return {
                    "approved": True,
                    "amount_cents": order["amount_cents"],
                    "reason": "eligible",
                }
        return {"approved": False, "amount_cents": 0, "reason": "service_unavailable"}

    return run


def create(tools: FixtureTools):
    """Try twice, validating each response; return an explicit outage fallback."""
    return _build(tools, 2)


def create_buggy(tools: FixtureTools):
    """Give up after one attempt; transient failure cases and retry checks fail."""
    return _build(tools, 1)


def create_excessive(tools: FixtureTools):
    """Retry four times; the permanent outage case violates the call bound."""
    return _build(tools, 4)


def create_unhandled(tools: FixtureTools):
    """Let the first service error escape; partial tool evidence remains available."""
    return _build(tools, 1, recover=False)
