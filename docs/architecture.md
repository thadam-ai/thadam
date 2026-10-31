# Architecture

**Status:** milestones 1 and 2, saved-report regression comparison, and repeated-evaluation reliability gates are implemented. Scenario generation, async execution, and hosted services remain planned.

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
| `src/thadam/contracts.py` | Snapshot and compare declared check definitions | Keep declared expectations separate from observed results |
| `src/thadam/report_loading.py` | Strict run-report parsing and evidence validation | Reject missing, inconsistent, or unsupported data without importing agent code |
| `src/thadam/comparison.py` | Typed comparison results, compatibility checks, and regression classification | Pure SDK behavior; validate/snapshot both reports, with no agent execution |
| `src/thadam/comparison_reporting.py` | Comparison JSON and terminal formatting | Preserve evidence and gate result; reuse atomic artifact writes and color roles |
| `src/thadam/repetition.py` | Repeated evaluation, lifecycle validation, and typed outcome/runtime summaries | Sequential attempts, shared callable or per-case agent factory; reuse the single-run engine |
| `src/thadam/repetition_loading.py` | Strict repeated-run parsing and snapshots | Validate all nested runs, identical contracts across attempts, and recomputed summaries |
| `src/thadam/repetition_reporting.py` | Repeated-run JSON and terminal evidence | Preserve complete schema-3 attempts inside repeated-run schema 1 |
| `src/thadam/reliability.py` | Pure per-case/check reliability comparison and CI policy | Require equal attempts/modes/contracts; errors always block; tolerance never hides individual drops |
| `src/thadam/reliability_reporting.py` | Standalone reliability comparison and terminal evidence | Embed both full repeated reports; display rates and unsuccessful attempt evidence |
| `src/thadam/reliability_loading.py` | Reload and recompute saved reliability comparisons | Reject altered counts, decisions, policy fields, and evidence without executing application code |
| `src/thadam/runner.py` | Execute cases, measure duration, and collect results | No CLI formatting or framework-specific code |
| `src/thadam/reporting.py` | JSON serialization and terminal summaries | Preserve status, IDs, errors, and assertion evidence |
| `src/thadam/terminal.py` | Semantic color roles and terminal capability detection | Styling is optional; do not change execution results or JSON report data |
| `src/thadam/cli.py` | Parse arguments, load the selected agent, invoke SDK, and set exit code | Share engine behavior with Python callers |
| `examples/` | Small runnable agent and suites | Demonstrate actual public APIs |
| `tests/` | Contract and behavior checks | Controlled agent/tool fixtures by default |
| `scripts/check_installed_package.py` | Validate an installed distribution outside the checkout | Check distribution name/version, packaged types, and a real SDK/report round trip |
| `.github/workflows/publish.yml` | Build, validate, and publish reviewed release distributions | Separate upload job with OIDC; manual runs validate without publishing |

Add further framework and provider adapters in their roadmap milestones. Evolve this map when implementation shows a better boundary.

## Contracts

- **Case:** stable ID, JSON input, and explicit expectations. Cases must contain at least one assertion or SDK verifier.
- **Agent:** accepts one JSON input and returns JSON or an explicit `AgentResult`. Each case is an independent invocation. Instrumented exceptions use `AgentExecutionError` to preserve observed events.
- **Assertion result:** stable assertion ID, observed value, expected value or contract description, pass/fail, and an explanation. SDK verifiers return a `CheckResult`, which the runner associates with the verifier's ID.
- **Case result:** case ID, status, input/output, checks, elapsed time, structured errors, optional events, and trace availability.
- **Run report:** schema version, run ID, case results, and summary counts.

Case states are `passed`, `failed`, and `error`. A failed expectation is `failed`; an execution exception, invalid output/trace, unavailable tool evidence, or broken verifier is `error` with an explicit source. Invalid suite configuration is rejected before execution. CLI and SDK use the same rules.

The first milestone specifies [suite formats, SDK verifiers, and CLI exit codes](milestones/01-local-runner.md). The second specifies [LangGraph coverage, tool checks, and execution events](milestones/02-langgraph.md). The third specifies [report compatibility, verifier revisions, comparison classifications, and CI gates](milestones/03-regression-comparison.md). `reporting.report_to_dict` defines the version-3 run report; `comparison_reporting.comparison_to_dict` defines comparison schema 1. Existing schema-1 case files remain supported.

Saved report comparison follows `load_report -> validate evidence -> match case/check contracts -> classify each check -> summarize cases -> terminal/JSON`. Schema 3 snapshots declared checks before execution, including for errored cases. Built-in results are checked against their recorded output and events; custom verifiers require developer-supplied revisions for compatibility and are never executed while loading or comparing. Report validation establishes internal consistency, not authenticity: selecting and reviewing trusted baselines remains the caller's responsibility.

[Repeated evaluation](milestones/03-reliability.md) snapshots the suite before user code,
then runs complete suites in attempt order through the existing engine. It either
reuses one callable or invokes a factory inside every case's timed/error boundary.
Summaries use every attempt as the denominator; unavailable check verdicts count
as errors. Repeated-run schema 1 (`kind: repeated_run`) wraps full schema-3 runs.
Reliability comparison validates both inputs, checks matching attempt counts,
lifecycle mode and contracts, and evaluates each case/check independently under
an explicit fractional drop policy. Its schema 1 (`kind: reliability_comparison`)
embeds both reports and the gate decision; its loader recomputes that decision.
All existing single-run contracts remain unchanged. Factory state/resource
isolation is caller-owned, and observed-rate gates make no significance claim.

## Dependencies and extension points

The core has no runtime dependencies. Add dependencies when required by a working feature. Model providers, framework integrations, OpenTelemetry export, and hosted services are optional extensions. Importing Thadam must not select a provider or start a run.

The distribution name `thadam-ai` is separate from the import/CLI name `thadam`. Build and publishing tools remain CI/development dependencies; they are not imported by the installed SDK. The [publishing guide](publishing.md) records the first-release prerequisites and the environment-gated release boundary.

Cases and their JSON data are validated and snapshotted before the first invocation. Each agent receives a copy of its input; each verifier receives its own input/output snapshots. Callback objects retain their identity. This protects recorded evidence from agent/verifier mutations without claiming process isolation or automatically resetting a user's agent state.

Capture only what an integration or explicit agent hook exposes. Raw callable results have unknown events (`None`); an explicit instrumented result may have an empty tuple. Tool assertions require a complete observed callback trace, and argument checks require structured inputs. This completeness flag describes the callback scope, not actions performed outside instrumentation. Missing usage remains `None`.

LangGraph collectors correlate parallel callbacks by framework run ID using a lock, preserving start order, parent IDs, terminal states, and durations. Existing callbacks/config are merged through the public configuration API. Each graph invocation receives a fresh thread ID to separate checkpoint histories; explicit checkpoint resumption is unsupported. The collector records tool/model callbacks, not every chain/node in the graph.

Keep the execution engine usable locally. A future service may schedule runs and store reports while consuming the same execution and reporting contracts.
