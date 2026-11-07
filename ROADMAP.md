# Thadam roadmap

Thadam is an open-source testing, evaluation, and reliability tool for AI agents.

**Current state:** local execution, tracing, regression/reliability gates, suite revisions, baseline review, the operational local dashboard, reviewable scenario suggestions, reviewed regression cases, and controlled tool-failure testing are implemented.
**Next build:** review labels and recorded-example imports (milestone 4.5, workflow 2). Creating reviewed regression cases from saved results is implemented; guided fix verification and the remaining milestone 5 workflows are planned.

**Published release:** [`thadam-ai` v0.3.0](https://pypi.org/project/thadam-ai/0.3.0/),
released on 2026-10-30. Completed features below describe `main`; reliability
gates, baseline review, the dashboard, async execution, and scenario suggestions
were added after that release and currently require a source checkout.

Milestones below are ordered by dependency and user value, not promised release dates. An unchecked item is planned. Mark an item complete only when implementation, meaningful checks, and usage documentation are present. Keep this file current as work lands.

## Product direction and build order

Thadam helps developers turn observed agent behavior into reviewed test cases,
explainable evaluations, and repeatable release checks. Keep the local SDK, CLI,
suites, and basic evaluations useful without a hosted service or model provider.
Optional integrations and shared services should consume those same contracts.

The 2026-11-04 priority review draws on Raindrop's
[local debugger and replay](https://www.raindrop.ai/docs/workshop/overview/) and
[curated datasets](https://www.raindrop.ai/docs/platform/datasets/), alongside
Latitude's [trace-derived datasets](https://docs.latitude.so/datasets/overview),
[evaluation alignment](https://docs.latitude.so/evaluations/alignment), and
[local simulations](https://docs.latitude.so/test-and-fix/simulations).
These workflows inform our priorities; the milestones below define Thadam's scope.

| Priority | Milestones | User benefit |
| --- | --- | --- |
| Next | 4.5 | Turn an observed failure into a reviewed test and verify a fix |
| Core testing expansion | 5–7 | Test conversations and recovery, evaluate semantic behavior, and compare configurations |
| Connect and investigate | 8–9 | Reuse existing telemetry and coding tools, and track recurring failures |
| Longer term, after user validation | 10–11 | Delegate reliability work to an always-on AI teammate and collaborate through optional shared services |

Start each milestone with the smallest complete workflow and a concrete user
example. Specify any new artifact formats, migration rules, and execution/data
boundaries before implementation. Validate later priorities with real projects
before taking on continuous ingestion or shared infrastructure.

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
- [x] Publish the first `thadam-ai` release through Trusted Publishing: [v0.3.0](https://github.com/thadam-ai/thadam/releases/tag/v0.3.0), available on PyPI since 2026-10-30.
- [ ] Publish a follow-up release containing the newer features implemented on `main`.
- [ ] Complete and record the explicit live-provider check for scenario suggestions, including sign-in, model access, and an actual generation request.
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

## 4.5. Turn real failures into reviewed regression tests

**Status:** in progress. Workflow 1 is implemented in the checkout; workflows 2 and 3 remain planned. [Workflow and draft contract](docs/milestones/04-regression-cases.md).

**Outcome:** a developer starts with an observed failure, saves an independently
reviewed regression case, and sees whether a candidate fix meets the same checks.

### 1. Create a regression case from an existing result

- [x] Add an explicit dashboard action to create a draft case from a saved case result, including a selected repeated attempt.
- [x] Retain the source artifact, case/attempt identity, original input/output, and relevant observable evidence as provenance.
- [x] Let the developer edit the input and supply expected behavior through supported JSON assertions before accepting the case.
- [x] Preview the resulting suite and save selected reviewed cases using existing suite identity, revision, and stale-write guards.

### 2. Review and import recorded examples

- [ ] Attach good, bad, or needs-review verdicts, notes, and failure tags to saved results without modifying the original execution evidence or gate outcome.
- [ ] Import recorded examples through a documented JSONL/CSV format with explicit field mapping, structural validation, and duplicate review.
- [ ] Preserve source IDs and supplied context; examples lacking trusted expectations remain reviewable drafts and cannot count as passing tests.
- [ ] Provide configurable field masking and a data preview before importing, exporting, or sending selected examples to a provider; document redaction limits.
- [ ] Search and filter drafts and reviewed examples by case, review state, and failure tags.

### 3. Make verifying the fix easier

- [ ] Run the saved reviewed suite against a deliberately selected candidate using the existing runner and progress/interruption behavior.
- [ ] Show original and candidate evidence together, with per-check changes and existing single/repeated comparison decisions when contracts are compatible.
- [ ] Make changed contracts or missing comparable baseline evidence explicit; require a fresh reviewed baseline when necessary.
- [ ] Export the reviewed suite and resulting reports for the existing pytest/CI workflow; keep baseline approval a separate explicit action.

The observed answer is evidence, not an automatically correct expectation. Human
labels do not overwrite recorded assertion results. Importing or reviewing an
example does not execute agents or verifiers. Imported partial traces retain
unavailable evidence explicitly. Saving a case, running a candidate, comparing
reports, and approving a baseline remain distinct actions.

Completion requires a controlled end-to-end example: inspect a bad result, review
the expected behavior, save the case, reproduce the failure, and verify a fix.
Include an import with incomplete evidence and an incompatible comparison path.

## 5. Exercise failures and conversation simulations

**Status:** partially implemented. Controlled tool failures and retry-count checks are available; conversation simulation and stateful environments remain planned.

**Outcome:** a developer checks whether an agent completes a conversation and
recovers from controlled failures while preserving the expected state.

- [x] Add tool fixtures for exceptions, invalid responses, and unavailable services through the SDK, CLI and dashboard. See [controlled tool failures](docs/milestones/05-tool-failures.md).
- [ ] Define a conversation scenario with ordered user/agent turns, per-turn checks, final outcome checks, and explicit state lifecycle/reset rules.
- [ ] Support scripted follow-up turns and session evidence for context retention, repeated questions, and behavior after a correction.
- [x] Assert inclusive tool-call/retry bounds and recovery through explicit output/tool checks.
- [ ] Assert allowed observable state changes.
- [x] Specify scripted timeout errors, cooperative async cancellation and existing dashboard interruption for current execution modes; no enforced execution deadline.
- [ ] Specify conversation turn limits, enforced deadlines and additional cleanup behavior before offering enforcement guarantees.
- [ ] Add resettable stateful fixtures and retain partial conversation/tool evidence on failure or interruption.
- [x] Save discovered single/repeated case failures through milestone 4.5's reviewed regression workflow, retaining controlled fixture scripts.

Fixture suites use schema 3, fixture runs schema 5 and repeated fixture runs schema
2 with mode `fixtures`. Existing suite/run/repeated formats retain their contracts.
Factories receive controlled tools afresh for every case attempt. Scripts are
reviewed case contracts, including unused steps; changed scripts are incompatible
without an intentional baseline transition. Call bounds evaluate completed
evidence and do not stop execution. Stateful environments, call-order checks and
enforced deadlines remain outside the implemented slice.

Begin with scripted conversations and controlled tools. Any later model-driven
user simulator needs explicit budgets, stopping rules, recorded configuration,
and a supplied success criterion. Observable state changes require instrumentation;
scenario execution does not imply sandboxing or hidden-reasoning access.

## 6. Evaluate behavior with reviewed rubrics

**Status:** planned. Builds on existing assertion/verifier contracts and milestone 4.5's reviewed examples.

**Outcome:** a developer evaluates useful behavior even when a correct response
can have several wordings, and can inspect why the evaluator reached its verdict.

- [ ] Add recurring deterministic checks such as JSON schema, text/regex, and numeric constraints where real suites establish the need.
- [ ] Add optional rubric-based model evaluators for supplied criteria such as task completion, relevance, and policy adherence, with references/context when needed.
- [ ] Version evaluator definitions and retain rubric, provider/model, configuration, verdict, explanation, and reported usage in comparable evidence.
- [ ] Compare evaluator verdicts against a separate set of human-reviewed examples; expose disagreement and false-positive/negative examples before enabling a gate.
- [ ] Keep evaluator failures, unavailable evidence, and uncertain decisions explicit; never silently count them as passes.
- [ ] Provide explicit request/cost budgets and optional provider adapters; retain deterministic checks and user-supplied Python verifiers without model dependencies.

Generated cases and generated evaluators need independent review. An LLM verdict
is a recorded judgment against a supplied rubric, not proof of factual correctness.
Changing a rubric/model must follow declared comparison compatibility rules;
evaluation or calibration never silently revises release criteria or baselines.

## 7. Compare configurations, quality, latency, and cost

**Status:** planned. Builds on current regression/reliability comparisons; uses milestone 6 for rubric-based metrics.

**Outcome:** a developer can compare prompt/model/agent configurations on the same
reviewed suite and understand the quality, speed, and usage tradeoffs.

- [ ] Define named experiment configurations and run the same suite with explicit attempt counts, lifecycle modes, and scheduling settings.
- [ ] Retain available code/prompt/model revisions, provider settings, suite/evaluator revisions, and scheduling configuration so differences remain inspectable.
- [ ] Show side-by-side outputs, per-check outcomes, pass-rate changes, recorded latency, and reported token usage for each configuration.
- [ ] Add versioned provider pricing inputs or provider-reported costs, with visible pricing coverage and unavailable values rather than zero-cost assumptions.
- [ ] Support explicit quality, latency, token, and cost policies with documented sample requirements and full gate evidence.
- [ ] Keep statistical uncertainty separate from configured pass-rate tolerances; distinguish inconclusive evidence from a demonstrated improvement.
- [ ] Save/export experiment definitions and results for local use and CI while preserving existing report readers and pure comparison behavior.

Use observed data and declared configurations. Replaying an input does not
reproduce an external service's past state. Report comparisons continue to execute
no agents or verifiers; an explicit experiment runner owns new execution.

## 8. Connect existing agents, telemetry, and coding assistants

**Status:** planned. Select integrations from concrete user projects; implement them incrementally.

**Outcome:** a developer connects an existing agent with little setup, brings its
recorded failures into Thadam, and uses the same evidence from a coding assistant.

- [ ] Provide guided project setup and diagnostics that validate a connection and explain missing tracing before a first evaluation.
- [ ] Add an explicit HTTP agent adapter and define a TypeScript execution contract that reuses suite/check semantics, based on user demand.
- [ ] Add selected framework/provider tracing integrations beyond LangGraph with clear capture boundaries and optional dependencies.
- [ ] Import/export supported OpenTelemetry traces with documented field mapping, source provenance, and honest completeness/usage flags.
- [ ] Add a documented bridge for externally curated datasets or exported traces, beginning with one real workflow such as Latitude datasets or Raindrop evidence.
- [ ] Expose project-confined report inspection, comparison, and draft proposal tools through an optional MCP server and a documented setup/investigation skill.
- [ ] Use explicit project-scoped actions for agent execution, provider requests, and artifact writes; preserve review and baseline approval guards.

The generic JSONL/CSV importer in milestone 4.5 remains usable independently.
Imported telemetry never invents expectations, complete traces, or passing checks.
MCP access follows the same SDK, confinement, credential, and review rules as the
CLI/dashboard. Viewing an external trace or importing examples does not replay it.

## 9. Track recurring failures and investigate evidence

**Status:** planned, after evidence capture/review and stable configuration metadata.

**Outcome:** a developer sees which failure patterns recur, which revisions first
showed them, and whether a verified fix continues to hold across evaluations.

- [ ] Build a local history index over saved reports, annotations, suite revisions, and experiment/configuration metadata, with rebuildable source links.
- [ ] Group known failures by reviewed tags/check identities first; offer optional semantic grouping with inspectable supporting examples.
- [ ] Track occurrence counts, affected cases/sessions, first/last seen, and open, resolved, ignored, or regressed status.
- [ ] Add content and metadata search, saved filters, and an optional semantic search path with clear coverage/ranking limits.
- [ ] Link each tracked problem to reviewed regression cases, fixes, and the evaluations that verified them; detect observed recurrences.
- [ ] Offer optional evidence-linked investigation summaries and a focused export for a coding assistant or GitHub issue, with explicit user-directed sharing.

Keep generated clusters and root-cause explanations reviewable. Similar symptoms
do not establish a shared cause. This milestone starts with local saved evidence;
continuous production discovery belongs to milestone 10.

## 10. Add an always-on AI teammate for incident response

**Status:** longer-term, subject to demand and operational validation. Requires reviewed evaluation methods, telemetry mappings, and failure history from earlier milestones.

**Outcome:** a team gives an AI teammate an ongoing responsibility such as
"watch our refund agent, investigate new failures, and bring us a tested fix."
The teammate works between conversations, carries project context forward, and
returns with evidence, completed work, and decisions that need the team's review.

- [ ] Add opt-in continuous trace/event ingestion with bounded processing, explicit retention, deletion, and configurable capture/redaction policies.
- [ ] Associate events with supplied session/user, environment, and deployment metadata; keep evaluation/simulation traffic separate from production.
- [ ] Run explicitly enabled conditions or reviewed evaluators on scoped/sampled traffic and surface processing cost, coverage, and failures.
- [ ] Track named behavior signals and emerging failure patterns using recorded evidence and human feedback.
- [ ] Add threshold/recurrence monitors that open incidents when explicitly configured conditions are met.
- [ ] Compare deployment cohorts on observed quality and available latency/usage/cost, explaining population, sampling, and attribution limits.
- [ ] Connect an alert to a reviewed local regression case, candidate verification, and a post-deploy check using the same behavior definition.

### Persistent, conversational AI teammate

The product shape is inspired by [Grok Bot's operational teammates](https://x.ai/news/incident-sweep)
and [OpenAI dots](https://openai.com/index/introducing-dots/): give a bot an ongoing
job, talk to it where the team works, and let it carry the work through to an outcome.
Thadam's teammate specializes in agent reliability and incident investigation.

- [ ] Provide a dedicated bot that teammates can message or mention in Thadam, Slack, or Teams to ask questions, assign work, give feedback, and follow an investigation in the same conversation.
- [ ] Accept standing goals in natural language, with an explicit project scope, connected tools, usage budgets, and pause/stop controls; continue assigned work between messages.
- [ ] Retain project context across sessions: agent architecture, repositories, suites, known failures, runbooks, prior investigations, and reviewed team feedback, with inspectable memory and project isolation.
- [ ] Connect to deliberately selected repositories, CI results, traces/logs, metrics, issues, and support feedback; use these tools to investigate when a relevant event arrives or a configured routine wakes the bot.
- [ ] Independently gather evidence, correlate recent changes, reproduce a failure through Thadam, and prepare a regression-case draft and tested candidate fix or draft pull request for review. Generated expectations still require independent review.
- [ ] Return useful findings, progress, blockers, and concrete approval requests to the conversation; accept corrections and carry that context into subsequent work.
- [ ] After an approved fix, verify recovery against the same behavior checks, watch for recurrence, and prepare an incident summary with evidence and regression-test follow-ups.
- [ ] Support a persistent worker environment and resumable background jobs, with visible activity, bounded retries, explicit action permissions, and recorded outcomes; keep the local SDK/CLI useful independently.

Start with a controlled end-to-end example: a teammate assigns "watch this agent"
in chat, a new failure triggers an investigation, and the bot returns in that
conversation with a reproduced failure, regression draft, and tested fix to review.
Demonstrate follow-up feedback, continuation after a worker restart, and recovery
verification after the team approves the fix.

Specify data handling and deployment boundaries before ingesting customer traffic.
Redaction is best effort, and a quiet monitor does not prove there are no failures.
Evidence may support a proposed fix; automatic code changes, merges, deployments,
and baseline promotion require separate explicitly designed workflows.

## 11. Collaborate through optional shared services

**Status:** longer-term, after validation of the local workflow and production needs.

**Outcome:** a team shares reviewed suites, findings, and evaluation history while
controlling who can view data, execute agents, and approve release criteria.

- [ ] Add shared project history, durable review queues, reviewer attribution, comments, and explicit approval/audit records.
- [ ] Define authentication, project isolation, roles, and permissions for viewing evidence, editing suites, running jobs, and approving baselines.
- [ ] Support private deployments and an optional hosted service using the same SDK and versioned artifacts.
- [ ] Add explicit scheduled runs and external workers with documented resource, interruption, and execution-isolation boundaries.
- [ ] Provide retention/deletion, backup/export, credential storage, and operational diagnostics suitable for the selected deployment model.
- [ ] Preserve a useful open-source local path for suites, execution, deterministic evaluation, comparison, and reviewed artifact export.

Local approval artifacts currently record acknowledgement, not authenticated
identity. Shared services must add the relevant identity and access controls
explicitly, without reinterpreting old artifacts as authenticated approvals.

## Ideas to evaluate later

These are possibilities, not committed milestones. Promote an idea when a concrete user need, an owner, and acceptance criteria exist.

- Minimize a failing scenario to a smaller reproducible case.
- Measure scenario coverage against declared behavior contracts.
- Add retrieval-specific evaluation when projects supply source documents, expected evidence, and concrete quality criteria.
- Add model-driven user simulators after scripted conversation scenarios establish reliable stopping and success rules.

## Decisions to revisit with users

- Which real failure takes too much work to turn into a trusted regression case today?
- Which repeated custom verifiers justify a built-in deterministic check or optional rubric evaluator?
- Which integration, external dataset source, or runtime is blocking adoption in a real project?
- Do users get more value from the CLI/pytest workflow, dashboard review, or coding-agent tools?
- What usage and operational evidence justifies continuous monitoring or shared infrastructure?
