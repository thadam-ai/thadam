# Architecture

**Status:** milestones 1 and 2 implemented. Regression comparison, scenario generation, and hosted services remain planned.

See [DESIGN.md](../DESIGN.md) for the agreed technology stack, rationale, and decision history.

Thadam executes agent test scenarios and records evidence about whether they satisfy developer-defined expectations. The same engine should be usable from Python, the CLI, and later CI integrations.

## First execution path

```text
JSON case file or Python cases
             |
             v
     validate suite once
             |
             v
     runner -> agent adapter -> developer's agent
             |
             v
      assertion / verifier
             |
             v
        typed report
          /      \
         v        v
   CLI summary   JSON artifact
```

The runner owns the execution lifecycle. An adapter invokes the agent and normalizes its output. Assertions compare observed data with explicit expectations. Reporting serializes those results without deciding whether a case passes.

## Code map

These modules implement the first local execution flow. Add new modules when they have behavior to own.

| Location | Responsibility | Boundary |
| --- | --- | --- |
| `src/thadam/models.py` | Case, assertion, agent result, and report types | No execution, file access, or network calls |
| `src/thadam/suites.py` | Parse and validate JSON suites | Reject invalid cases before agent execution |
| `src/thadam/_json.py` | Shared JSON value validation | Require serializable values at input/output boundaries |
| `src/thadam/errors.py` | Public configuration and report-writing exceptions | Distinguish errors that prevent or interrupt a run from case results |
| `src/thadam/adapters/python.py` | Validate the synchronous Python callable contract | Require one positional input; runner owns invocation |
| `src/thadam/adapters/langgraph.py` | Execute compiled graphs with public model/tool callbacks | Optional imports, per-invocation collectors, JSON state mapping, fresh checkpoint threads |
| `src/thadam/events.py` | Validate and snapshot execution evidence | Reject invalid traces; preserve unknown-versus-empty semantics |
| `src/thadam/assertions.py` | Built-in assertions and Python verifier contract | Return evidence; do not invoke the agent |
| `src/thadam/runner.py` | Execute cases, measure duration, and collect results | No CLI formatting or framework-specific code |
| `src/thadam/reporting.py` | JSON serialization and terminal summaries | Preserve status, IDs, errors, and assertion evidence |
| `src/thadam/terminal.py` | Semantic color roles and terminal capability detection | Styling is optional; do not change execution results or JSON report data |
| `src/thadam/cli.py` | Parse arguments, load the selected agent, invoke SDK, and set exit code | Share engine behavior with Python callers |
| `examples/` | Small runnable agent and suites | Demonstrate actual public APIs |
| `tests/` | Contract and behavior checks | Controlled agent/tool fixtures by default |

Add further framework and provider adapters in their roadmap milestones. Evolve this map when implementation shows a better boundary.

## Contracts

- **Case:** stable ID, JSON input, and explicit expectations. Cases must contain at least one assertion or SDK verifier.
- **Agent:** accepts one JSON input and returns JSON or an explicit `AgentResult`. Each case is an independent invocation. Instrumented exceptions use `AgentExecutionError` to preserve observed events.
- **Assertion result:** stable assertion ID, observed value, expected value or contract description, pass/fail, and an explanation. SDK verifiers return a `CheckResult`, which the runner associates with the verifier's ID.
- **Case result:** case ID, status, input/output, checks, elapsed time, structured errors, optional events, and trace availability.
- **Run report:** schema version, run ID, case results, and summary counts.

Case states are `passed`, `failed`, and `error`. A failed expectation is `failed`; an execution exception, invalid output/trace, unavailable tool evidence, or broken verifier is `error` with an explicit source. Invalid suite configuration is rejected before execution. CLI and SDK use the same rules.

The first milestone specifies [suite formats, SDK verifiers, and CLI exit codes](milestones/01-local-runner.md). The second specifies [LangGraph coverage, tool checks, and execution events](milestones/02-langgraph.md). `reporting.report_to_dict` defines the version-2 report shape. Existing schema-1 case files remain supported.

## Dependencies and extension points

The core has no runtime dependencies. Add dependencies when required by a working feature. Model providers, framework integrations, OpenTelemetry export, and hosted services are optional extensions. Importing Thadam must not select a provider or start a run.

Cases and their JSON data are validated and snapshotted before the first invocation. Each agent receives a copy of its input; each verifier receives its own input/output snapshots. Callback objects retain their identity. This protects recorded evidence from agent/verifier mutations without claiming process isolation or automatically resetting a user's agent state.

Capture only what an integration or explicit agent hook exposes. Raw callable results have unknown events (`None`); an explicit instrumented result may have an empty tuple. Tool assertions require a complete observed callback trace, and argument checks require structured inputs. This completeness flag describes the callback scope, not actions performed outside instrumentation. Missing usage remains `None`.

LangGraph collectors correlate parallel callbacks by framework run ID using a lock, preserving start order, parent IDs, terminal states, and durations. Existing callbacks/config are merged through the public configuration API. Each graph invocation receives a fresh thread ID to separate checkpoint histories; explicit checkpoint resumption is unsupported. The collector records tool/model callbacks, not every chain/node in the graph.

Keep the execution engine usable locally. A future service may schedule runs and store reports while consuming the same execution and reporting contracts.
