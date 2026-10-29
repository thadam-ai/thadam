# Milestone 2: LangGraph execution evidence and tool assertions

**Status:** implemented in Thadam 0.2.0. Verified with LangGraph 1.2.18, langchain-core 1.7.1, and Python 3.14. Core Thadam remains free of runtime dependencies; this integration uses the optional `langgraph` extra.

## Quick start

From a repository checkout:

```shell
python -m pip install -e '.[dev,langgraph]'
thadam run examples/langgraph_cases.json \
  --agent examples.langgraph_agent:agent \
  --report artifacts/langgraph-report.json
```

The three cases pass using an actual compiled StateGraph, a scripted chat model, and local tool fixtures. With `examples.langgraph_agent:agent_buggy`, the same final outputs fail because the graph skips `get_order`. Model token metadata in this example is synthetic fixture data, not billed usage.

## Connect an existing graph

Wrap a compiled `StateGraph` with the optional adapter. This example defines a wrapper for an existing graph whose state contains a `messages` key:

```python
from thadam.adapters.langgraph import LangGraphAgent


def wrap_graph(compiled_graph):
    return LangGraphAgent(
        compiled_graph,
        input_mapper=lambda request: {
            "messages": [{"role": "user", "content": request["question"]}]
        },
        output_mapper=lambda state: {"answer": state["messages"][-1].content},
        config={"tags": ["thadam-evaluation"]},
    )
```

Export the wrapped object as, for example, `agent` from your own module. Select it through the same CLI `--agent my_module:agent`, or call `run_suite(agent, cases)` in Python. Case inputs must match your input mapper, and assertions must match your selected output. Without an output mapper, the adapter serializes graph state, including supported LangChain message objects, into JSON-compatible values. Unsupported state objects require an explicit output mapper.

Mappers and graph execution are synchronous. Each invocation receives a fresh callback collector and a new `configurable.thread_id`; other configuration, existing callbacks, and tags are preserved without mutating the caller's config. A supplied `thread_id` is replaced for test isolation. Explicit `checkpoint_id` resumption is rejected. Interrupted graphs produce an execution error and no correctness verdict.

Fresh threads avoid sharing checkpoint history between cases. External services, mutable tool state, and stored checkpoints remain the caller's responsibility; the adapter does not reset services or delete checkpoint records.

## Callback coverage

The adapter attaches a handler through `graph.invoke(..., config=...)`. It observes LangChain model and tool lifecycle callbacks. Graph nodes must propagate their runnable configuration when invoking models or tools:

```python
def node(state, config):
    answer = model.invoke(state["messages"], config=config)
    return {"messages": [answer]}
```

This is a pattern for your existing `model`; it is not a standalone example. Plain Python function calls, raw provider HTTP calls, callbacks that are deliberately suppressed, and external work outside that callback scope are not automatically traced. A graph node is not automatically a tool. Assertions describe only the explicitly instrumented scope, not every action an application might perform.

Model and tool records use framework run IDs and parent IDs. A parent may refer to a chain/node callback that is not itself recorded, so the event list is not a complete graph execution tree. No hidden model reasoning is inferred or exposed by Thadam.

## Tool assertions

These work in SDK `TestCase.assertions` and schema-version-1 JSON case files:

| JSON type | SDK type | Meaning |
| --- | --- | --- |
| `tool_called` | `ToolCalled(id, tool)` | At least one observed invocation of the tool |
| `tool_not_called` | `ToolNotCalled(id, tool)` | No observed invocation within the instrumented scope |
| `tool_arguments_match` | `ToolArgumentsMatch(id, tool, expected)` | At least one invocation; every invocation matches the selected top-level arguments |

Example suite:

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "eligible-refund",
      "input": {"order_id": "order-001", "days_since_purchase": 7},
      "assertions": [
        {"id": "lookup-required", "type": "tool_called", "tool": "get_order"},
        {"id": "correct-order", "type": "tool_arguments_match", "tool": "get_order", "expected": {"order_id": "order-001"}},
        {"id": "no-delete", "type": "tool_not_called", "tool": "delete_order"}
      ]
    }
  ]
}
```

An errored tool attempt still counts as a call; a forbidden attempt fails even if the tool throws. A recovered tool error does not independently fail an otherwise satisfied case. Tool success or call ordering is not asserted by these checks.

Argument checks require a non-empty expected object. Extra argument fields are allowed; each selected value uses the same strict JSON comparison as `output_equals`, including boolean/number distinctions. A missing selected field or a mismatched value fails. No call fails the check. Missing structured argument evidence produces an evaluation error instead of guessing.

## Availability and partial traces

- A plain callable returning JSON has unknown tracing: `events: null`, `trace_complete: null`.
- An explicit `AgentResult` supplies an instrumented event sequence. An empty sequence with `trace_complete: true` means no callbacks were observed within that declared scope.
- Unmatched or unfinished callbacks produce `trace_complete: false` and warnings. Tool assertions on unknown or incomplete traces produce an `assertion` error, never a pass.
- If the graph raises, the adapter preserves events in `AgentExecutionError`. The runner records the original exception type and message, keeps partial evidence, and continues to later cases.
- Invalid event records become a `trace` error and are excluded from the report. Invalid final outputs retain valid execution events.

Custom instrumentation can return `AgentResult(output, events, trace_complete, trace_warnings)` using the core `ExecutionEvent`, `EventError`, and `TokenUsage` dataclasses. This is explicit evidence supplied by your integration, not automatic instrumentation of arbitrary Python.

## Version-2 reports

Report schema 2 extends the local runner's records. Input case files remain schema 1. Consumers of report schema 1 should check the version and adopt the fields below.

| Field | Meaning |
| --- | --- |
| `cases[].events` | Ordered event records, or null when instrumentation is unknown |
| `cases[].trace_complete` | Whether observed callback lifecycles were complete; null for unknown instrumentation |
| `cases[].trace_warnings` | Collection gaps or unfinished lifecycle details |
| `cases[].assertions[].event_ids` | Relevant observed events, including all matched tool attempts |

Each event includes `id`, `parent_id`, `kind` (`model` or `tool`), `name`, `status` (`completed`, `error`, or `incomplete`), `started_at_ms`, `duration_ms`, `input`, `input_available`, `output`, `output_available`, `error`, and `usage`. Starts are relative to graph invocation. Unfinished durations are null. `error` contains the observed exception type and message; an errored tool message may also have a captured output.

Model `usage` contains provider-reported `input_tokens`, `output_tokens`, and `total_tokens`. Unavailable usage/counts remain null; explicitly reported zero remains zero. Aggregate provider usage is preferred. Standardized single-message usage is a fallback; ambiguous multi-generation usage is left unavailable rather than double-counted. Usage is not a price estimate.

The CLI expands model/tool evidence beneath failed or errored cases. JSON artifacts retain events for passed cases too. Exit codes and the teal/amber/red presentation follow the existing [local runner contract](01-local-runner.md).

## Validation

Integration tests execute compiled graphs and cover tool arguments/results, model and tool exceptions, parallel-node callback correlation, preservation of existing callbacks, fresh checkpoint threads, graph interrupts, output mapper errors, reported zero versus missing usage, and CLI/SDK agreement. Core tests additionally ensure that unknown/incomplete traces cannot satisfy tool checks and that importing Thadam does not load optional packages.

The tested example uses fixtures. No live provider or paid-model behavior is claimed. Async execution, arbitrary framework auto-instrumentation, tool ordering assertions, and simulation remain future work.

## Upstream interfaces

- [LangGraph graph API and runnable configuration](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [Tool callbacks and structured inputs](https://reference.langchain.com/python/langchain-core/callbacks/manager/CallbackManager/on_tool_start)
- [Chat model callbacks and shared LLM completion handling](https://reference.langchain.com/python/langchain-core/tracers/base/BaseTracer/on_chat_model_start)
