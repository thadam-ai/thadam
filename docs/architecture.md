# Architecture

**Status:** milestone 1 implemented. Later framework integrations, tracing, and services remain planned.

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
| `src/thadam/assertions.py` | Built-in assertions and Python verifier contract | Return evidence; do not invoke the agent |
| `src/thadam/runner.py` | Execute cases, measure duration, and collect results | No CLI formatting or framework-specific code |
| `src/thadam/reporting.py` | JSON serialization and terminal summaries | Preserve status, IDs, errors, and assertion evidence |
| `src/thadam/terminal.py` | Semantic color roles and terminal capability detection | Styling is optional; do not change execution results or JSON report data |
| `src/thadam/cli.py` | Parse arguments, load the selected agent, invoke SDK, and set exit code | Share engine behavior with Python callers |
| `examples/` | Small runnable agent and suites | Demonstrate actual public APIs |
| `tests/` | Contract and behavior checks | Controlled agent/tool fixtures by default |

Add LangGraph integration, execution-event capture, and provider adapters in their roadmap milestones. Evolve this map when implementation shows a better boundary.

## Contracts

- **Case:** stable ID, JSON input, and explicit expectations. Cases must contain at least one assertion or SDK verifier.
- **Agent:** milestone 1 accepts a synchronous callable with one JSON input and a JSON-compatible output. Each case is an independent invocation.
- **Assertion result:** stable assertion ID, observed value, expected value or contract description, pass/fail, and an explanation. SDK verifiers return a `CheckResult`, which the runner associates with the verifier's ID.
- **Case result:** case ID, status, original input, output when available, assertion results, elapsed time, and structured error details.
- **Run report:** schema version, run ID, case results, and summary counts.

Case states are `passed`, `failed`, and `error`. A failed expectation is `failed`; an agent exception, invalid agent output, or broken verifier is `error` with an explicit source. Invalid suite configuration is rejected before execution. Missing evidence cannot satisfy a check. CLI and SDK use the same rules.

The first milestone specifies [implemented formats, SDK verifiers, and CLI exit codes](milestones/01-local-runner.md). Keep it current when public contracts change. `reporting.report_to_dict` defines the version-1 report shape explicitly.

## Dependencies and extension points

The core has no runtime dependencies. Add dependencies when required by a working feature. Model providers, framework integrations, OpenTelemetry export, and hosted services are optional extensions. Importing Thadam must not select a provider or start a run.

Cases and their JSON data are validated and snapshotted before the first invocation. Each agent receives a copy of its input; each verifier receives its own input/output snapshots. Callback objects retain their identity. This protects recorded evidence from agent/verifier mutations without claiming process isolation or automatically resetting a user's agent state.

Capture only what an integration or explicit agent hook exposes. Later tool assertions must distinguish an observed empty tool list from tool activity that was never instrumented. Usage and cost fields are optional evidence, with unavailable values represented explicitly.

Keep the execution engine usable locally. A future service may schedule runs and store reports while consuming the same execution and reporting contracts.
