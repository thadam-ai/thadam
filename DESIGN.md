# Thadam design decisions

This document records the agreed stack and visual identity. Update it as decisions evolve, including why we changed direction and what the change affects.

The Python runner, SDK, CLI, optional LangGraph integration, saved-report regression comparison, and repeated-evaluation reliability gates are implemented. The interface, API service, and TypeScript agent support below remain planned.

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

The distribution name is `thadam-ai`; the import package and CLI remain `thadam`. Installation will use `python -m pip install thadam-ai` and optional extras such as `'thadam-ai[langgraph]'`. Distribution and import names are separate Python packaging concepts. Keeping the existing import/command avoids an unnecessary SDK and CLI rename. The PyPI project named `thadam` is unrelated to this repository.

The first upload is pending. The [release workflow](.github/workflows/publish.yml) validates builds on manual runs and publishes only after a matching GitHub release, successful checks, and the configured `pypi` environment approval. Trusted Publishing supplies short-lived credentials; no PyPI API token is stored. See the [publishing guide](docs/publishing.md) for owner setup, candidate-name limitations, and release steps.

## Brand and color theme

Thadam's identity is **teal and blue**, inspired by the supplied Thadam logo. Use this palette across the CLI, future report viewer, dashboard, and other interfaces. These are reusable color roles; the CLI is the first implemented surface.

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
- Keep this table, the CLI's `src/thadam/terminal.py` palette, and future interface tokens aligned when colors change. Record the reason in the decision history.

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
| 2026-10-30 | Prepare `thadam-ai` distribution and OIDC publishing | The PyPI name `thadam` belongs to an unrelated SDK; provide a repeatable release path | Preserve `import thadam` and the `thadam` CLI; validate source/wheel artifacts and isolate publishing permissions; first upload awaits owner account/publisher setup |
| 2026-10-31 | Add complete repeated-evaluation reliability comparison | Review a change using repeated case/check outcomes rather than trusting a single attempt | Preserve schema-3 runs inside distinct repeated-run and reliability-comparison schema-1 envelopes; require equal attempts/modes/contracts, block any errors, and apply an explicit per-case/check drop tolerance |
| 2026-10-31 | Support shared callables and per-invocation agent factories sequentially | Make state ownership explicit without assuming an agent can be copied or reset | Factories construct one agent per case attempt; application resources and verifier state remain caller-owned; no concurrency, retry, or implicit cleanup protocol |
| 2026-11-01 | Unify terminal reports and group repeated evidence | Make verdicts easy to scan while retaining an explicit way to inspect every attempt | Adaptive tables, grouped failures with occurrence numbers and representative traces, and `--verbose` for all commands; serialized reports and gate behavior retain their contracts |
