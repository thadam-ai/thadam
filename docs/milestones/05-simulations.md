# Conversation and state simulations

**Status:** implemented as the second slice of milestone 5. This extends the
controlled fixture workflow with ordered user turns, per-attempt JSON state, and
checks for turn responses and observed state changes.

## Run the example

```shell
thadam run examples/refund_conversation_cases.json \
  --fixture-factory examples.refund_conversation_agent:create \
  --report artifacts/refund-conversation.json

thadam repeat examples/refund_conversation_cases.json \
  --fixture-factory examples.refund_conversation_agent:create \
  --attempts 5 --report artifacts/refund-conversation-repeated.json
```

The case asks for a $30 refund, corrects it to $25, confirms the action, then
repeats the request. The example retains the correction and writes one refund
into the observable ledger. `create_buggy` ignores the correction and fails the response and state
checks. These controlled callables demonstrate contracts; they do not measure a
live model.

## Conversation contract

Identified simulation suites use **suite schema 4**. Each case contains the
existing `id`, JSON `input`, and `assertions`, plus `tool_fixtures`, an ordered
`conversation` array, and `state_fixture` (an object with `initial`, or null).
The case input supplies shared context. Each turn has a unique stable ID and a
JSON `message`.

The fixture factory is constructed once per case attempt and returns the usual
one-input agent. Thadam calls that same agent once for each turn with:

```json
{
  "case_input": {"order_id": "ord-42"},
  "turn_id": "correction",
  "message": "Correction: refund $25, not $30.",
  "history": [
    {"role": "user", "content": "Please refund $30 for order ord-42."},
    {"role": "assistant", "content": {"amount_cents": 3000}}
  ]
}
```

History includes all completed prior user messages and agent responses in order.
The agent's last response is the case output. `ConversationOutputEquals` (JSON
type `conversation_output_equals`) checks an earlier named turn response. Case
assertions still check the final response and trace.

## Stateful fixture and checks

`StateFixture(initial)` gives the attempt a fresh copy of JSON state. A fixture
factory accesses it through `tools.state.read()` and `tools.state.write(value)`;
reads and writes return/store independent JSON snapshots. Tool scripts and state
are shared across turns in that case attempt, then reset for the next case or
repeated attempt. The application remains trusted Python code, and only state
access through this handle is observable.

`StateEquals` (JSON type `state_equals`) checks the final state. `StateChanges`
(`state_changes`) checks that every changed top-level key belongs to
`allowed_keys`. Use both when a case needs an exact result and a narrow mutation
boundary. Initial and final state snapshots are retained even when an agent
raises; completed turn responses and tool events remain available as partial
evidence.

Simulation suites use schema 4 and runs use **run schema 6**. Fixture-only suites
remain schema 3. The report
retains the full turn script, each available response, the initial state, final
state, assertions, tool scripts and trace. Repeated simulation artifacts use
**repeated-run schema 3** with `execution_mode: "simulations"`; each attempt
contains a schema-6 run. Strict loaders recompute turn/state assertion outcomes,
check response-to-script correspondence, and compare contracts without importing
or executing application code. Conversation scripts and initial state participate
in comparison and baseline review; a changed contract needs an intentional suite
revision and baseline transition.

The SDK, CLI and local dashboard use the existing explicit fixture-factory mode.
The dashboard's JSON suite editor accepts schema 4 and shows transcript and state
evidence in evaluation details. Explicit [execution limits and environment hooks](05-execution-boundaries.md)
add turn caps, per-case spawned deadlines and setup/reset/cleanup. A model-driven
user simulator and hidden reasoning capture are outside this workflow.
