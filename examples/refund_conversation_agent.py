"""Controlled example for correction handling and observable refund state."""

from thadam import FixtureTools, JSONValue


def create(tools: FixtureTools):
    state = tools.state

    def agent(request: JSONValue) -> JSONValue:
        if not isinstance(request, dict):
            raise TypeError("Conversation input must be an object")
        turn_id = request["turn_id"]
        case_input = request["case_input"]

        if turn_id == "initial-request":
            return {"amount_cents": 3000, "message": "I can refund $30."}
        if turn_id == "correction":
            return {"amount_cents": 2500, "corrected": True}

        history = request["history"]
        corrected = any(
            item["role"] == "user" and "Correction" in item["content"] for item in history
        )
        if not corrected:
            raise ValueError("The amount correction was not retained")

        current = state.read()
        existing = next(
            (
                refund
                for refund in current["refunds"]
                if refund["order_id"] == case_input["order_id"]
            ),
            None,
        )
        refund = existing or {
            "order_id": case_input["order_id"],
            "amount_cents": 2500,
        }
        if existing is None:
            current["refunds"].append(refund)
            state.write(current)
        return {"refund_id": f"refund-{refund['order_id']}", **refund}

    return agent


def create_buggy(tools: FixtureTools):
    """Demonstrate a bot that uses the original amount and duplicates refunds."""
    state = tools.state

    def agent(request: JSONValue) -> JSONValue:
        if request["turn_id"] != "confirmation":
            return {"amount_cents": 3000}
        current = state.read()
        refund = {"order_id": request["case_input"]["order_id"], "amount_cents": 3000}
        current["refunds"].append(refund)
        state.write(current)
        return {"refund_id": f"refund-{refund['order_id']}", **refund}

    return agent
