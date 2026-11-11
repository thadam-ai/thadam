# Thadam design decisions

This document records the agreed stack and visual identity. Update it as decisions evolve, including why we changed direction and what the change affects.

The Python runner, SDK, CLI, optional LangGraph integration, saved-report regression comparison, repeated-evaluation reliability gates, suite revisions, and explicit baseline review are implemented. The local React dashboard and optional FastAPI service are also implemented. TypeScript agent support remains planned.

## Stack

| Component | Recommended stack | When |
| --- | --- | --- |
| Testing engine, SDK, CLI | Python | First milestone |
| Report viewer and dashboard | React + TypeScript | After useful reports exist |
| API for running tests and accessing results | Python + FastAPI | When the dashboard needs live data |
| Support for agents written in TypeScript | TypeScript adapter or SDK | Based on user demand |

## Why these choices

- **Python engine:** connect directly to Python agents and developer-written verifiers, starting with a local SDK and CLI.
- **React + TypeScript interface:** build an interactive report viewer and dashboard around the engine's versioned report contracts.
- **FastAPI service:** expose the existing Python engine when live execution and result access need an API. Keep execution and evaluation rules in the engine so SDK, CLI, and API agree.
- **TypeScript agent support:** add an adapter or SDK when real use cases establish how JavaScript and TypeScript agents should connect.

## Package and release names

The distribution name is `thadam-ai`; the import package and CLI remain `thadam`. Installation uses `python -m pip install thadam-ai` and optional extras such as `'thadam-ai[langgraph]'`. Distribution and import names are separate Python packaging concepts. Keeping the existing import/command avoids an unnecessary SDK and CLI rename. The PyPI project named `thadam` is unrelated to this repository.

The first release, [v0.3.0](https://pypi.org/project/thadam-ai/0.3.0/), was published on 2026-10-30. Features added after that tag currently require a source checkout. The [release workflow](.github/workflows/publish.yml) validates builds on manual runs and publishes only after a matching GitHub release, successful checks, and the configured `pypi` environment approval. Trusted Publishing supplies short-lived credentials; no PyPI API token is stored. See the [publishing guide](docs/publishing.md) for release scope, owner setup, and release steps.

## Brand and color theme

Thadam's identity is **teal and blue**, inspired by the supplied Thadam logo. Use this palette across the CLI, dashboard, and other interfaces. The table below defines the CLI palette; the dashboard uses the quieter surface-specific tokens described below while retaining the same semantic roles.

| Role | Dark surfaces | Light surfaces | Use |
| --- | --- | --- | --- |
| Teal: brand / success | `#2DD4BF` | `#00706B` | Branding, primary actions, passed cases, success totals |
| Blue: information | `#38BDF8` | `#0369A1` | Informational context, links, suite, agent, and report location |
| Muted | `#94A3B8` | `#475569` | Rules, labels, durations, expected values, zero counts |
| Failed assertion | `#FBBF24` | `#92400E` | Unmet expectations and actual values |
| Error | `#F87171` | `#B91C1C` | Execution, verifier, output, and configuration errors |

### Rules for future interfaces

- Teal and blue establish the brand. Keep body text neutral and use accents for meaningful actions, status, and navigation.
- **Blue and teal never encode an error.** Failed expectations use amber; execution and system errors use red.
- Always pair status colors with meaningful labels or another non-color cue.
- Use the appropriate dark or light palette and verify contrast against the actual background. The current reference canvases are dark `#070D13` and light `#FFFFFF`.
- Define shared semantic tokens when building the frontend: `--color-brand`, `--color-info`, `--color-muted`, `--color-warning`, and `--color-error`, mapped to this table. Reuse them across components.
- Preserve semantic meanings across the CLI and dashboard. Record surface-specific palette changes and their reasons in the decision history.

## Terminal presentation

The CLI is a task-focused interface. Use compact branding, aligned results and timings, and indented evidence. Preserve explicit status labels in every mode so color is supplemental.

The implementation lives in `src/thadam/terminal.py`; presentation stays separate from execution and JSON report contracts. Native ANSI colors provide the fallback when RGB support is unknown. Auto mode respects TTY detection, `NO_COLOR`, and `TERM=dumb`; explicit `--color` flags override automatic decisions.

Invoking `thadam` without arguments displays the overview and returns 0. It is a
discovery action, equivalent to `--help`. Incomplete execution/comparison commands
still return 2. Command help explains the user task, gives copyable application
examples, and describes exit codes; repository-only examples are labeled.

Help pages begin with the teal product heading, use blue section/option labels,
and teal command examples. Styling is applied after argparse lays out plain
text, preserving alignment. Python's native help colors are disabled where
available so the same Thadam palette and color policy apply on Python 3.10–3.14.

Execution/comparison reports share a verdict-first layout and adaptive case
tables, switching to stacked rows below 60 columns or when full columns cannot
fit. Repeated failures are grouped by side, case/check, and matching evidence;
attempt/run/event IDs and timing do not split identical findings. Representative
traces are labeled. `--verbose` expands every attempt and available evidence
under one top-level heading. Formatting remains independent of JSON contracts,
evaluation rules, and gate exit codes.

## Updating this document

When a decision changes, update the stack and rationale above, then add a dated entry below describing the change, the reason, and its impact. Keep planned choices distinct from implemented components. Update the [architecture](docs/architecture.md) and [roadmap](ROADMAP.md) when a decision changes module boundaries or delivery order.

## Decision history

| Date | Decision | Why | Impact |
| --- | --- | --- | --- |
| 2026-10-29 | Adopt the stack above | Start with direct Python agent testing while supporting a future web interface and additional agent runtimes | Build the Python runner first; introduce the other components when their stated needs arise |
| 2026-10-29 | Implement the local runner using Python's standard library | Validate the test execution and reporting contracts without requiring model services | The core has no runtime dependencies; pytest and Ruff are development tools |
| 2026-10-29 | Add logo-inspired terminal presentation | Give passes and context a teal/blue identity while retaining conventional failure and error colors | Optional styling, explicit statuses, wrapped evidence, and plain redirected output; report data and exit codes retain their contracts |
| 2026-10-29 | Adopt teal/blue as the shared interface theme | Preserve the logo's identity across future product surfaces | Reuse the palette and semantic roles in the CLI, report viewer, and dashboard; keep amber/red failure and error meanings |
| 2026-10-29 | Add LangGraph through public callbacks and an optional extra | Observe real tool/model execution while keeping the core dependency-free | Per-invocation collectors, fresh checkpoint threads, and explicit event availability; no inferred hidden reasoning |
| 2026-10-29 | Version execution reports as schema 2 | Make event records, availability flags, and assertion-event links explicit for consumers | Report readers must support the new version; existing schema-1 case files and CLI exit codes remain valid |
| 2026-10-30 | Add deterministic saved-report comparison and run schema 3 | Prevent changed expectations or missing evidence from masquerading as improvements | Snapshot declared checks before execution; require explicit verifier revisions; compare schema-3 reports and emit comparison schema 1 without rerunning agents |
| 2026-10-30 | Gate on individual checks and errors on either side | Case totals can hide a newly failing check, and errored baselines do not establish usable verdicts | Explicitly selected baselines can acknowledge existing assertion failures; regressions/errors return 1 and incompatible contracts return 2 |
| 2026-10-30 | Prepare `thadam-ai` distribution and OIDC publishing | The PyPI name `thadam` belongs to an unrelated SDK; provide a repeatable release path | Preserve `import thadam` and the `thadam` CLI; validate source/wheel artifacts and isolate publishing permissions; owner account/publisher setup required before the first upload |
| 2026-10-30 | Publish `thadam-ai` v0.3.0 to PyPI | Make the local runner, LangGraph tracing, tool assertions, and saved-report comparison installable | First public release is available; later features on `main` require a subsequent release |
| 2026-10-31 | Add complete repeated-evaluation reliability comparison | Review a change using repeated case/check outcomes rather than trusting a single attempt | Preserve schema-3 runs inside distinct repeated-run and reliability-comparison schema-1 envelopes; require equal attempts/modes/contracts, block any errors, and apply an explicit per-case/check drop tolerance |
| 2026-10-31 | Support shared callables and per-invocation agent factories sequentially | Make state ownership explicit without assuming an agent can be copied or reset | Factories construct one agent per case attempt; application resources and verifier state remain caller-owned; no concurrency, retry, or implicit cleanup protocol |
| 2026-11-01 | Unify terminal reports and group repeated evidence | Make verdicts easy to scan while retaining an explicit way to inspect every attempt | Adaptive tables, grouped failures with occurrence numbers and representative traces, and `--verbose` for all commands; serialized reports and gate behavior retain their contracts |
| 2026-11-03 | Add explicit suite revisions and reviewed baseline promotion | Make intentional test changes reviewable without allowing revision labels to bypass contract checks | Preserve legacy formats; add suite schema 2, run schema 4, single-comparison schema 2, full-evidence review/approval artifacts, exact digest acknowledgement, and stale-destination protection |
| 2026-11-03 | Refine the operational dashboard around evidence and focused editing | Make saved results easier to scan and failures faster to investigate | Compact counts, neutral surfaces, readable result summaries, failure-first investigation and a case navigator that preserves unfinished drafts; SDK and artifact rules remain unchanged |
| 2026-11-03 | Adopt the user's supplied quiet workspace references | Replace the generic broad-sidebar dashboard with the requested neat, elegant composition | Warm charcoal frame, slim icon rail, persistent independently scrolling file/detail panes, container-responsive evidence, regular-weight type and desaturated semantic colors; SDK contracts unchanged |

## Local dashboard

The user approved an operational local testing workspace extending the original
read-only viewer. React + TypeScript with self-hosted Inter ships as bundled assets
in the Python package; FastAPI/Uvicorn are behind the `dashboard` extra. The core
retains no runtime dependencies. See [the confirmed surface brief](docs/dashboard-design.md).

Navigation is Overview, Suites, Evaluations, Comparisons and Baselines in a slim
icon rail. A compact header names the scope and project. Saved files remain beside
the inspector, each with its own scroll area, and the library can be hidden for
more editing room. Narrow screens switch between list and detail with an explicit
Back to files action. Container queries adapt forms/evidence to inspector width.

The user's reference screenshots pin the visual world: warm neutral charcoal,
thin dividers, regular-weight headings and restrained color. The outer canvas is
`#171816`, content `#1F201E`, rail/library `#1B1C1A`, text `#D6D8D2`, and secondary
text `#A5A89F`. Dashboard semantic accents are teal `#70C5B5`, blue `#82B4D6`, amber
`#E4BB86`, and red `#E29B97`. The primary action uses a muted teal fill `#24545B`
with light text `#D7EDEB`. Light mode uses warm off-white surfaces with dark semantic
accents. Teal identifies active navigation and primary actions; blue identifies selected
evidence, links and keyboard focus. Accents were strengthened slightly at the
user's request while retaining the neutral surfaces. The CLI palette above remains
unchanged. Status dots always carry words.

Compact counts support the file list; readable outcomes lead details. The first
problem and unsuccessful checks open into expected/actual evidence; metadata and
raw input/output expand separately. Suite editing preserves drafts and refreshes
fingerprints after saves. Explicit Run/Save/Compare/Review/Approve actions continue
to use SDK rules. See the surface brief for layout, type scale and state coverage.

The server uses a project-confined authenticated loopback session. Evaluation jobs
run sequential SDK evaluations in managed subprocesses, with completed-case progress
and explicit interruption. These are local process controls, not sandboxing or
new timeout guarantees. Report and approval schemas retain their contracts.

## Async execution

Explicit async APIs and CLI/dashboard settings use a bounded cooperative worker
pool. Synchronous APIs remain sequential; no thread-pool parallelism is implied.
Reports retain their existing schemas and ordered evidence. Scheduling settings
are caller-owned and not automatically checked by comparison; see the
[async contract](docs/milestones/03-async-execution.md).

## Scenario suggestion extension

The existing Operate workspace extends Suites with a compact Suggest action,
connection controls, explicit outgoing-context preview, and a list/detail draft
reviewer. It retains Inter, warm neutral surfaces, shared spacing, semantic colors
and narrow-screen pane behavior. No new visual world or decorative AI surface is
introduced. Subscription use, API billing, unreviewed expectations and explicit
suite saving have separate labels and actions.

The provider-independent core owns drafts/review; optional HTTPX and PyJWT support
OpenAI API-key and direct ChatGPT-plan access. Authentication is user-level local
state, distinct from project evidence. Existing case/report schemas remain unchanged.
Generated cases never become trusted checks without explicit review, and saved
suites run without the generation provider. See the scenario guide for limitations.

## Explicit case boundaries

ExecutionLimits keeps in-process defaults and opts into standard-library spawn
workers for per-case deadlines. This bounds blocking sync agents without adding
a serialization dependency or implying a sandbox. EnvironmentHooks explicitly
owns external setup/reset/cleanup per attempt. Deadline grace bounds shutdown;
forced termination may skip cleanup. Policies are recorded and compared using
run schema 7 and repeated schema 4; existing suite contracts stay unchanged.
See [execution boundaries](docs/milestones/05-execution-boundaries.md).
