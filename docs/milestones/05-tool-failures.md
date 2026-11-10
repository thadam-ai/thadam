# Controlled tool failures

**Status:** implemented. The first slice adds scripted tool responses and
recovery checks through the SDK, CLI and local dashboard. The second adds scripted
conversations and resettable JSON state; see
[conversation and state simulations](05-simulations.md). External environment
resets and enforced execution timeouts remain planned. Exact call-order checks are
supported by `ToolCallSequence`.

## Run the controlled example

From a checkout with Thadam installed:

```shell
thadam run examples/tool_failure_cases.json \
  --fixture-factory examples.tool_failure_agent:create \
  --report artifacts/tool-recovery.json

thadam repeat examples/tool_failure_cases.json \
  --fixture-factory examples.tool_failure_agent:create \
  --attempts 5 --async --max-concurrency 2 \
  --report artifacts/tool-recovery-repeated.json
```

The three cases cover a temporary outage, a malformed business response, and a
permanent outage with a safe fallback. They require no API key, network service,
or LangGraph installation. `create_buggy` gives up too early and fails all three
cases; `create_excessive` fails the permanent-outage call bound; `create_unhandled`
records service errors with partial tool evidence. These are controlled examples,
not measurements of a live model's recovery ability.

## Explicit integration

Wrap a factory with `FixtureAgent` and pass it to existing runners:

```python
from thadam import (
    FixtureAgent,
    FixtureTools,
    OutputEquals,
    TestCase,
    ToolCallCount,
    ToolCallSequence,
    ToolRaise,
    ToolReturn,
    ToolScript,
    run_suite,
)


def create_agent(tools: FixtureTools):
    lookup = tools["get_order"]

    def agent(request):
        try:
            return lookup.invoke(request)
        except ConnectionError:
            return lookup.invoke(request)

    return agent


case = TestCase(
    "lookup-recovers",
    {"order_id": "one"},
    assertions=(
        OutputEquals("order", {"amount_cents": 2500}),
        ToolCallCount("bounded-retry", "get_order", min_calls=2, max_calls=2),
        ToolCallSequence("recovery-path", ("get_order", "get_order")),
    ),
    tool_fixtures={
        "get_order": ToolScript(
            (
                ToolRaise("ConnectionError", "Order service unavailable"),
                ToolReturn({"amount_cents": 2500}),
            )
        ),
    },
)
report = run_suite(FixtureAgent(create_agent), [case])
assert not report.has_failures
```

The factory takes one positional `FixtureTools` and returns a normal one-input
agent. Thadam constructs it once per case invocation, including every repeated
attempt. Construction is inside the timed/error boundary. `run_suite_async` and
`run_repeated_async` also await async factories and agents; use
`await tools["name"].ainvoke(arguments)` for async tools. Sync tools may be used
inside async agents as well. Independent invocation state supports bounded case
overlap, and attempts remain sequential.

`tools["name"]` obtains a handle; `handle(arguments)` and `handle.invoke(arguments)`
accept one JSON argument value. `ainvoke` consumes the same script and does not
add a delay. Each argument, return value, script and recorded event is snapshotted.
Handles close when the invocation exits or is cancelled and must not be retained
for later work. Resources created by the application remain application-owned.

Only explicitly connected handles are controlled. Thadam does not patch imports,
intercept arbitrary Python or HTTP calls, discover real tools, reset external
services, or prevent application code from performing other work. A fixture handle
never invokes a real-service fallback.

## Script and assertion contracts

- `ToolReturn(value)` returns JSON, including `None`, strings, wrong field types or
  missing fields. A malformed business response remains valid JSON. Arbitrary
  Python objects and non-finite numbers are rejected before execution.
- `ToolRaise(error, message)` selects exactly `TimeoutError`, `ConnectionError` or
  `RuntimeError`. No exception class is imported from suite data. Developer code
  can translate these into a library-specific exception when required.
- Steps are consumed in call order independently per named tool. A script has at
  least one step. `repeat_last=False` is required in JSON and is the SDK default;
  explicit `True` repeats the final return or error until the agent stops.
- Invoking a handle without a script or after exhaustion records
  `FixtureConfigurationError` as a case error with source `fixture`. It remains
  an error if the agent catches it and returns a plausible output. Invalid JSON
  arguments also produce a sticky fixture error. Unknown or closed handles have
  no real-service fallback.
- Unused steps are allowed. Required activity belongs in explicit assertions.
  A handled scripted service error alone does not fail a case. Unhandled errors
  are agent errors, and later cases continue.
- `ToolCallCount(id, tool, min_calls=0, max_calls=None)` counts **every observed
  attempt**, including errors. Bounds are inclusive non-negative integers;
  `max_calls` is null/None or at least `min_calls`. Equal bounds mean exactly N
  calls. Evidence must be complete and explicit, just as for other tool checks.
- Call bounds are assertions evaluated after execution. They do not interrupt an
  infinite loop. A scripted `TimeoutError` does not wait or stop a hung agent.
  Sync execution has no enforced timeout; async cancellation is cooperative and
  drains owned workers. Dashboard Stop retains its existing process controls and
  never publishes an interrupted evaluation as completed.
- `ToolCallSequence(id, tools)` checks the exact start-order sequence of every
  observed tool event. Failed attempts count; extra, missing, or reordered calls
  fail. It requires a complete explicit trace and is evaluated after execution,
  so it does not stop or constrain the agent.

## Saved suites and evidence

Fixture suites use **suite schema 3**, with required identity/revision and a
`tool_fixtures` object on every case (an empty object is allowed):

```json
{
  "schema_version": 3,
  "suite": {"id": "order-recovery", "revision": "v1"},
  "cases": [{
    "id": "temporary-outage",
    "input": {"order_id": "one"},
    "tool_fixtures": {
      "get_order": {
        "steps": [
          {"type": "raise", "error": "ConnectionError", "message": "Offline"},
          {"type": "return", "value": {"amount_cents": 2500}}
        ],
        "repeat_last": false
      }
    },
    "assertions": [
      {"id": "order", "type": "output_equals", "expected": {"amount_cents": 2500}},
      {"id": "attempts", "type": "tool_call_count", "tool": "get_order", "min_calls": 2, "max_calls": 2},
      {"id": "recovery-path", "type": "tool_call_sequence", "tools": ["get_order", "get_order"]}
    ]
  }]
}
```

SDK cases may omit suite identity for local use; reviewed baselines still require
identity. Fixture execution emits **run schema 5**, containing every case's full
script, including unused responses, plus existing check definitions and evidence.
Its `suite` field is an identity or null. Ordinary runs keep schemas 3/4 and old
suites keep schemas 1/2; those suites cannot carry fixture declarations. The new
call-count assertion also works on ordinary explicitly instrumented runs.

Fixture events have IDs prefixed `fixture:`, structured argument availability,
returned values or simulated errors, and timing relative to the invocation.
Factories that return an `AgentResult` retain its model/other tool events, usage,
warnings and completeness; child timestamps are offset from the agent call's
start within the invocation. Invalid child traces produce a trace error while
retaining valid fixture evidence. No hidden reasoning or token usage is inferred.

Repeated fixture runs use **repeated-run schema 2**, `kind: repeated_run`, and
`execution_mode: fixtures`, containing only full schema-5 runs. Ordinary shared
and zero-argument factory workflows retain repeated-run schema 1 and their prior
lifecycle contracts. Repeated counts and pass rates still include every attempt.
Comparison/reliability and baseline-review/approval envelopes keep their existing
schemas, with their strict loaders accepting the new nested evaluations.

Scripts participate in compatibility and baseline review even when never called.
Changing steps, repetition or fixture enablement is a changed contract; identical
suite labels cannot bypass this. Baseline review reports `tool_fixtures_changed`
and requires a revision bump before promotion. Fixture errors block a clean
comparison and cannot be acknowledged away. Loading, comparing and reviewing
never execute agents, factories or tool steps.

## LangGraph integration

Within a factory, use the optional adapter's public helper:

```python
from pydantic import BaseModel
from thadam.adapters.langgraph import fixture_tool


class LookupArguments(BaseModel):
    order_id: str


def connect_lookup(tools):
    return fixture_tool(
        tools["get_order"],
        args_schema=LookupArguments,
        description="Look up an order using this case's controlled responses",
    )
```

Build your graph using that tool and return `LangGraphAgent(graph)` from the
factory (or its `ainvoke` bound method for async execution). Propagate runnable
configuration as usual. The helper supplies sync/async `StructuredTool` wrappers
with explicit fixture metadata; the callback collector leaves those spans to the
fixture runtime, counting each logical invocation once. Model and other tool
callbacks remain available. Manually adding another ordinary callback wrapper
around the same fixture can record a second span; use this helper for integration.
Install the optional `langgraph` extra; core fixtures need no optional packages.

## Dashboard workflow

In **Suites**, choose a case and **Configure tool failures**. This upgrades the
suite to schema 3 and preserves its identity, input, checks and other cases.
Legacy suites gain an editable identity. Add a tool by the exact connected name,
then add returned JSON or simulated error responses. Enable **Repeat final
response** explicitly for a permanent outage. Set `tool_call_count` checks in
Assertions and save with a new revision when modifying an existing contract.
Unfinished JSON remains in the form, survives case selection, and blocks saving.

In **Run evaluation → Execution & save settings**, choose **Tool fixture factory**
and supply your `module:create` reference. One attempt is a single evaluation;
two or more are repeated evaluations. Async and concurrency controls work as
before. Saved agent settings retain the mode. Opening configuration or discovering
a suite never imports application code. Results show full saved scripts, checks,
every fixture event and every attempt; comparison and approval use the SDK rules.

Saved case results also support **Create regression case** through the
[reviewed regression workflow](04-regression-cases.md). Source scripts remain in
the draft's full run snapshot and are included in the explicitly previewed/saved
fixture suite. Source outputs remain evidence, never inferred expectations.

## Validation

Controlled tests cover exceptions, malformed responses, recovery, bounded and
excessive retries, sticky unscripted/exhausted calls, unused steps, repetition,
fresh factories, independent snapshots, async overlap/cancellation, strict saved
evidence, changed unused contracts, revision guards, CLI imports from a temporary
project, dashboard APIs/forms, and real sync/async graph callbacks. Default checks
need no model credentials or hosted service. Milestone 5 does not implement
resettable external systems, real-time delay simulation, or enforced deadlines.
