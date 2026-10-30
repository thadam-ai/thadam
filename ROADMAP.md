# Thadam roadmap

Thadam is an open-source testing, evaluation, and reliability tool for AI agents.

**Current state:** milestones 1 and 2 implemented; local runner, optional LangGraph integration, tool assertions, and execution reports.
**Next build:** milestone 3, regression comparison and CI integration.

Milestones below are ordered by dependency and user value, not promised release dates. An unchecked item is planned. Mark an item complete only when implementation, meaningful checks, and usage documentation are present. Keep this file current as work lands.

## Foundation: a repository humans and AI agents can navigate

- [x] Define the product and first implementation scope.
- [x] Provide a repository guide in `AGENTS.md` and a map in `docs/architecture.md`.
- [x] Establish a Python package scaffold, contributor setup, and code conventions.
- [x] Demonstrate those conventions in the first working feature and its tests.
- [x] Document security maintenance, private vulnerability reporting, and execution/data boundaries in `SECURITY.md`.
- [x] Add repository CI for core and optional LangGraph tests, Ruff checks, and package build/install validation.
- [ ] Require the repository CI checks before merging to `main`, after their first successful GitHub run.

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

- [ ] Add pytest integration and a GitHub Actions example.
- [ ] Compare baseline and candidate results by stable case and assertion IDs.
- [ ] Report new failures separately from already accepted failures.
- [ ] Support repeated runs and report pass counts, variability, and runtime.
- [ ] Version cases and record agent/application revision metadata for comparisons.
- [ ] Record missing cases and evaluator errors explicitly rather than counting them as passes.
- [ ] Add async execution and bounded concurrency when the adapter and report contracts can support them.

Deterministic assertion logic does not make an LLM's execution deterministic. Reports must retain that distinction.

## 4. Suggest test scenarios with AI

**Outcome:** a developer reviews generated scenarios and saves useful ones into a reusable suite.

- [ ] Accept an agent description, tool schemas, behavior contracts, and existing cases.
- [ ] Generate candidate normal, boundary, and failure cases through an explicit provider adapter.
- [ ] Validate generated structure and retain generation metadata.
- [ ] Make generated cases reviewable and editable before inclusion in an approved suite.
- [ ] Reuse developer verifiers; require review of generated expected outcomes.
- [ ] Keep saved suites runnable without the generation provider.

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
- [ ] Add an optional local report viewer and production-trace import.
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
