# Thadam roadmap

Thadam is an open-source testing, evaluation, and reliability tool for AI agents.

**Current state:** local execution, tracing, regression/reliability gates, suite revisions, baseline review, the operational local dashboard, and reviewable scenario suggestions are implemented.
**Next build:** controlled tool failures and simulated environments (milestone 5).

Milestones below are ordered by dependency and user value, not promised release dates. An unchecked item is planned. Mark an item complete only when implementation, meaningful checks, and usage documentation are present. Keep this file current as work lands.

## Dashboard design refinement

**Status:** implemented. [Design and workflow guide](docs/dashboard-design.md).

**Outcome:** make the functional dashboard feel intentionally designed, minimal,
cohesive, and easy to understand, with a stronger Thadam identity.

- [x] Review the current screens for generic template styling, visual clutter, and unclear hierarchy.
- [x] Refine typography, spacing, alignment, navigation, and table density around the actual testing workflows.
- [x] Keep Thadam's teal/blue palette and clear amber failure/red error meanings consistent across both themes.
- [x] Improve labels, empty states, and progressive disclosure so results and next actions are immediately understandable.
- [x] Preserve every existing dashboard feature, SDK rule, and saved-evidence contract.
- [x] Validate the revised design with real suite-editing, evaluation, comparison, and baseline-review tasks on desktop and narrow screens.

The dashboard follows the user-supplied warm charcoal workspace references: a
slim icon rail, persistent file/detail panes, quiet typography and status dots.
Compact counts, failure-first evidence, focused case editing and progressive
execution settings remain available. Desktop and narrow layouts support
both themes; SDK behavior and saved-artifact contracts remain unchanged.

## Local testing dashboard

**Status:** implemented. [Launch and workflow guide](docs/dashboard.md).

**Outcome:** open one local project, edit suites, run configured agents, investigate
complete evidence, compare evaluations, and explicitly review/approve baselines.

- [x] Discover and strictly validate all saved suite/report/comparison/review/approval kinds without executing application code.
- [x] Show real invocation counts, suite/revision metadata, recorded runtime, searchable artifacts and complete case/check evidence.
- [x] Inspect every repeated attempt, grouped findings, observable traces and reported token usage with explicit unavailable states.
- [x] Edit suites through forms/JSON with validation, revision and stale-write guards.
- [x] Configure shared agents/factories and run evaluations with progress, bounded logs, one active job and explicit interruption.
- [x] Create single/repeated comparisons and full-evidence baseline reviews/approvals using SDK rules.
- [x] Ship a responsive dark/light React/TypeScript interface in Thadam's colors, with no frontend tools required for users.
- [x] Provide controlled examples, API/browser validation, optional-extra CI and clean-wheel checks.

The user expanded the originally read-only viewer to include these explicit local
actions. Default execution remains sequential and trusted; async execution is explicit; the dashboard does not
introduce hosted infrastructure, a sandbox or automatic baseline updates.

## Foundation: a repository humans and AI agents can navigate

- [x] Define the product and first implementation scope.
- [x] Provide a repository guide in `AGENTS.md` and a map in `docs/architecture.md`.
- [x] Establish a Python package scaffold, contributor setup, and code conventions.
- [x] Demonstrate those conventions in the first working feature and its tests.
- [x] Document security maintenance, private vulnerability reporting, and execution/data boundaries in `SECURITY.md`.
- [x] Add repository CI for core and optional LangGraph tests, Ruff checks, and package build/install validation.
- [x] Prepare `thadam-ai` distribution metadata and a validated GitHub-to-PyPI Trusted Publishing workflow.
- [x] Configure the `pypi` release environment with owner approval and version-tag restrictions.
- [ ] Complete owner PyPI 2FA/pending-publisher setup and publish the first `thadam-ai` release.
- [x] Require the repository CI checks before merging to `main`, after their first successful GitHub run.

## 1. Run one agent against saved test cases

**Outcome:** a developer connects a synchronous Python function, runs five cases with one command, and can explain every failure from the report.

Implementation details and acceptance criteria: [local runner specification](docs/milestones/01-local-runner.md).

- [x] Define typed models for test cases, agent results, assertions, and run reports.
- [x] Validate a versioned JSON case file before invoking the agent.
- [x] Connect a custom Python callable through a small adapter contract.
- [x] Run cases sequentially, isolating agent exceptions per case.
- [x] Support deterministic checks: exact output and required top-level output fields.
- [x] Accept a Python verifier for application-specific correctness through the SDK.
- [x] Capture case IDs, actual outputs, assertion evidence, durations, and agent errors.
- [x] Add a Python SDK entry point and a CLI with documented exit codes.
- [x] Show a useful CLI overview without arguments and task-focused help with executable examples for every command.
- [x] Style every help page with Thadam branding and a consistent automatic/explicit color policy across supported Python versions.
- [x] Unify report layouts with verdicts/counts first, adaptive case tables, grouped repeated failures, and verbose evidence across all four commands.
- [x] Produce a terminal summary and a versioned JSON report.
- [x] Include a small agent example, five scenarios, and focused behavior tests that require no model API key.

Completion requires a runnable example showing a passing case, a failed assertion, and an agent error. None may be silently dropped or confused with one another. No model provider, hosted account, or telemetry backend is required for this milestone.

## 2. Inspect LangGraph runs and tool behavior

**Outcome:** a developer tests an existing LangGraph agent and sees evidence about its tools when a case fails.

Implementation, coverage boundaries, and report schema: [LangGraph guide](docs/milestones/02-langgraph.md).

- [x] Add one documented LangGraph integration using an optional dependency.
- [x] Define execution events for observable model and tool calls.
- [x] Support required/forbidden tool checks and selected tool-argument checks.
- [x] Record latency and token usage when the integration exposes them; distinguish unavailable values from zero.
- [x] Link assertion failures to relevant execution events in the report.
- [x] Add a LangGraph example and integration tests using controlled model/tool fixtures.

Instrumentation must use explicit hooks or supported framework interfaces. A custom agent's unreported tool activity is unknown. Internal model reasoning is outside the tracing contract.

## 3. Make suites useful for regression testing

**Outcome:** a team commits test cases to its repository and uses Thadam results to review a change.

- [x] Add a normal pytest integration example and a consumer GitHub Actions example.
- [x] Compare baseline and candidate results by stable case and assertion IDs.
- [x] Report new failures separately from already accepted failures, including inside already-failing cases.
- [x] Record input/check contracts and require explicit revisions for compared custom verifiers.
- [x] Add optional application revision metadata to run reports.
- [x] Support repeated runs and report pass counts, variability, and runtime.
- [x] Compare repeated baseline/candidate case and check pass rates with configurable drop tolerance, strict compatibility, and error-blocking CI gates.
- [x] Define sequential shared-callable and per-invocation factory execution contracts, preserving evidence for every attempt.
- [x] Add explicit suite revisions and a review workflow for intentional contract changes, with exact-evidence acknowledgement and guarded baseline promotion.
- [x] Record missing/changed cases and evaluator errors explicitly rather than counting them as passes.
- [x] Add explicit async SDK/CLI/dashboard execution and bounded per-attempt concurrency, preserving ordered evidence and cancellation cleanup. See [the async contract](docs/milestones/03-async-execution.md); scheduling settings remain caller-owned rather than serialized.

Deterministic assertion logic does not make an LLM's execution deterministic. Reports must retain that distinction.

The [single-run comparison](docs/milestones/03-regression-comparison.md) uses run schema 3 and comparison schema 1. [Repeated evaluation](docs/milestones/03-reliability.md) adds repeated-run schema 1 and reliability-comparison schema 1 with distinct kinds, equal attempt counts, per-case/per-check rate gates, and complete attempt evidence. These compare observed outcomes, not statistical significance or timing/cost budgets. A dedicated pytest plugin remains a possible future integration; the working examples use normal pytest assertions.

[Suite revisions and baseline review](docs/milestones/03-baseline-review.md) add
suite schema 2, identified run schema 4 and single-comparison schema 2, while
preserving legacy formats. Review and approved-baseline artifacts each use schema
1 with distinct kinds. Both single/repeated workflows retain full evidence and
require explicit acknowledgement; ordinary execution/comparison never approves.

## 4. Suggest test scenarios with AI

**Status:** implemented with controlled-provider validation. Live ChatGPT sign-in and model requests still need an explicit manual check with an eligible account. [Guide and contracts](docs/milestones/04-scenario-suggestions.md).

**Outcome:** a developer reviews generated scenarios and saves useful ones into a reusable suite.

- [x] Accept an agent description, tool schemas, behavior contracts, and existing cases.
- [x] Generate candidate normal, boundary, and failure cases through an explicit provider adapter.
- [x] Validate generated structure and retain generation metadata.
- [x] Make generated cases reviewable and editable before inclusion in an approved suite.
- [x] Reuse developer verifiers; require review of generated expected outcomes.
- [x] Keep saved suites runnable without the generation provider.

Generated expectations are proposals. Coverage and correctness still need a developer-defined contract or environment verifier.

## 5. Exercise failures and simulated environments

**Outcome:** a developer checks how an agent recovers from a controlled tool failure.

- [ ] Add tool fixtures for exceptions, invalid responses, and unavailable services.
- [ ] Specify supported timeout and cancellation behavior for each execution mode.
- [ ] Assert bounded retries, recovery behavior, and allowed environment changes.
- [ ] Add stateful test environments with resettable fixtures.
- [ ] Turn discovered failures into saved regression cases.

## 6. Expand interoperability and collaboration

**Outcome:** projects use the same local contracts with more integrations and optional shared services.

- [ ] Add LangChain, CrewAI, and API adapters based on concrete user demand.
- [ ] Export execution evidence through OpenTelemetry where it fits the event model.
- [ ] Add production-trace import compatible with the local dashboard and existing evidence contracts.
- [ ] Design hosted runs, scheduling, result history, and team collaboration around the existing engine.

Keep local execution, the SDK, CLI, and basic evaluations useful as open source. Hosted services should consume the same contracts.

## Ideas to evaluate later

These are possibilities, not committed milestones. Promote an idea when a concrete user need, an owner, and acceptance criteria exist.

- Minimize a failing scenario to a smaller reproducible case.
- Suggest failure clusters from repeated test runs.
- Compare prompts and models using the same reviewed suite.
- Measure scenario coverage against declared behavior contracts.
- Add optional rubric-based model judges with calibration examples and recorded uncertainty.
- Track cost budgets when trustworthy usage and pricing inputs are available.
- Provide editor integrations and machine-readable report inspection for coding agents.
- Support private team deployments and external execution workers.

## Decisions to revisit after milestone 1

- Which real agent workflow should the first LangGraph integration support?
- Which assertion types recur enough to become built-in checks?
- Should pytest become the primary interface or remain an integration alongside the CLI?
- What feedback demonstrates that scenario generation is the next most useful feature?
