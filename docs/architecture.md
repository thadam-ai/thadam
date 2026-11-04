# Architecture

**Status:** milestones 1 and 2, saved-report regression comparison, and repeated-evaluation reliability gates are implemented. Explicit async execution and bounded case concurrency are also implemented; reviewable scenario generation is implemented; hosted services remain planned.

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
| `src/thadam/terminal_reporting.py` | Shared adaptive report layout, grouped findings, and verbose evidence | Pure presentation of recorded data; no artifact writes, agent execution, or evaluation decisions |
| `src/thadam/cli.py` | Parse arguments, load the selected agent, invoke SDK, and set exit code | Share engine behavior with Python callers |
| `src/thadam/cli_help.py` | Help layout styling and early color-policy selection | Apply Thadam's palette after plain-text layout; no application imports or execution |
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

## Suite revisions and baseline review

Identified `TestSuite` sequences carry `SuiteIdentity` through the same runner
and repetition engine. Suite schema 2 produces run schema 4; legacy suite 1 and
run 3 remain unchanged. Comparators require equal labels plus equal actual
contracts. Single-comparison schema 2 carries identity metadata; existing
repeated/reliability envelopes retain schema 1 around schema-3/4 runs.

- `baseline_review.py` owns pure contract diffs, independent full-evidence review
  snapshots, canonical review digests, acknowledgements, and strict review/approval
  reloading. It imports/executes no application code. Stored decisions are recomputed.
- `baseline_reporting.py` renders both sides' outcomes, before/after contracts,
  blockers, and full verbose evidence, and writes review artifacts.
- `baseline_approval.py` owns explicit destination checks, coordination between
  approval writers, stale-baseline detection, and atomic promotion of the complete
  approved-baseline artifact. Ordinary report writers protect approved destinations.
- `baseline_cli.py` translates the two commands' arguments and delegates behavior
  to these SDK modules. `cli.py` protects output paths before application imports.

`load_report`/`load_repeated` recognize approved-baseline wrappers using a local
import at the file-loading boundary, validate the full embedded review and
acknowledgement, then return the approved evaluation. Nested evaluation parsers
accept only raw evaluations, preventing recursive wrapper chains. Approval metadata
is evidence of an explicit local acknowledgement, not authentication or a signature.
See the [complete format and review contract](milestones/03-baseline-review.md).

## Local testing dashboard

`thadam dashboard` lazily imports the optional `dashboard` extra and serves bundled
React/TypeScript assets. `dashboard/src` owns presentation and explicit user actions;
`src/thadam/dashboard` owns project access, authenticated loopback routing and job
lifecycle. The Python SDK still owns execution, assertions, comparison and approval.

- `workspace.py`: project-confined discovery, strict artifact loading, saved agent
  settings, coordinated new-file writes, suite validation/revision/fingerprint guards.
- `jobs.py`: one active managed process, completed-case progress, bounded log capture,
  completed artifact publication, history, explicit interruption and shutdown.
- `worker.py`: validate snapshotted suites, import a deliberately selected agent,
  call the existing SDK and save internal completed evidence. Workers exit if their
  parent server disappears; application code remains trusted; synchronous execution is sequential and async overlap is explicit.
- `server.py`: optional FastAPI app, per-port ephemeral browser session, origin/path
  checks, explicit actions delegating SDK behavior, and packaged static assets.
- `launch.py`: optional dependency handling, local link/browser launch and clean exit.
- `comparison_loading.py`: reload single comparison artifacts, validate recorded
  check/case classifications and summaries; full source contracts/traces remain in
  original run reports. Existing strict loaders own all other report kinds.

`run_suite` and `run_repeated` optionally notify `on_case_complete` with independent
case snapshots; observer exceptions propagate. This allows progress reporting
without changing serialized evidence or assertion outcomes. The dashboard never
publishes an interrupted job as a completed report. Frontend development needs Node;
end users receive bundled assets in the Python wheel and need only the optional
Python server dependencies. See [the operating guide](dashboard.md).

## Explicit async execution

`run_suite_async` and `run_repeated_async` provide cooperative bounded case
overlap; synchronous APIs retain their sequential defaults. Read [the async contract](milestones/03-async-execution.md).
Async runs reuse the runner's validation, evidence and assertion helpers. Attempts
remain ordered; cancellation/observer failure drains workers without a completed
report. CLI `--async --max-concurrency N` and dashboard execution settings select
this path. Existing schemas and shared/factory modes remain unchanged. Scheduling
settings are not serialized or automatically compared; callers must keep baseline
and candidate scheduling consistent. LangGraph exposes an explicit async `ainvoke`.

## Reviewable scenario generation

`generation.py` owns explicit context validation, the `GenerationProvider` protocol,
completed proposals, strict scenario-draft schema 1, exact-case review and suite
composition. `suite_writing.py` shares revision/fingerprint guards across the SDK,
CLI and dashboard. `suites.suite_from_dict` is the pure suite-loading boundary.
`providers/openai.py` optionally handles Responses streaming, explicit API-key or
ChatGPT access, model catalogs and sanitized failures; `chatgpt_auth.py` owns the
loopback OAuth/PKCE listener and verified identity, and `credentials.py` owns private
user-level storage and cross-process refresh serialization. Importing these modules
does not connect or select a provider. The core retains no runtime dependencies.

`generation_cli.py` translates connection, preview, generation, review and save
commands. `dashboard/generation_api.py` exposes the same operations under local
session/origin and project confinement controls. Generation shares the existing
one-active-process job controller and never imports or executes tested application
code. Stopped jobs cannot publish completed drafts. React's `generation.tsx` adds
context preview, connection controls and a focused draft reviewer to Suites.

See [scenario contracts](milestones/04-scenario-suggestions.md). Drafts preserve
selected plaintext context, generation metadata and append-only exact-content
review evidence; credentials remain outside projects. Suite/report/baseline
schemas and evaluation rules are unchanged. A saved suite requires no generation
provider; model-generated correctness remains a human-reviewed proposal.
