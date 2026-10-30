# Working in Thadam

## Read these first

1. `README.md` — purpose and current implementation status.
2. `ROADMAP.md` — priorities and completed work.
3. `DESIGN.md` — agreed stack, rationale, and decision history.
4. `docs/architecture.md` — contracts and module boundaries.
5. `docs/milestones/01-local-runner.md` — the implemented first milestone's formats and acceptance criteria; select new work from `ROADMAP.md`.
6. `CONTRIBUTING.md` — setup and shared code conventions.

For instrumentation and tool assertions, also read `docs/milestones/02-langgraph.md`.

This is a Python package for testing and evaluating AI agents. The product is **Thadam (தடம்)**. The distribution/install name is `thadam-ai`; use `thadam` for Python imports, module commands, and the CLI. The separate PyPI project named `thadam` is unrelated. First public publication is pending; do not claim the package is available until a PyPI upload succeeds.

## Current implementation

Milestones 1 and 2 and the first part of milestone 3 are implemented: local execution, optional LangGraph tracing, tool assertions, and saved-report regression comparison. `src/thadam/__init__.py` exports the core SDK; `thadam.adapters.langgraph` is an explicit optional import. Input suites remain schema 1; run reports use schema 3 with declared checks, event links, and availability flags. Comparisons use their own schema 1 and `kind: "comparison"`. `python -m thadam` and the installed command use the same entry point.

For comparison work, read `docs/milestones/03-regression-comparison.md`. Schema-1/2 run reports cannot be compared: generate fresh reports. Custom verifiers require matching explicit revisions. Errors on either side block a clean comparison; changed/missing tests are incompatible. Compare individual checks even when both cases are already failed. Comparison must not execute agents or verifiers.

The engine is sequential and runs trusted code in the current process. LangGraph tracing covers public callbacks in the propagated runnable configuration; ordinary Python functions do not automatically emit events. The adapter uses fresh checkpoint thread IDs. There is no enforced timeout, sandbox, scenario generator, or hidden-reasoning capture. Re-read the code before assuming an API exists.

## Repository map

- `src/thadam/` — core models, validation, assertions, runner, reports, and CLI.
- `src/thadam/events.py` — validation and snapshots of explicit trace evidence.
- `src/thadam/contracts.py` — declared check snapshots and compatibility.
- `src/thadam/report_loading.py` — strict report/evidence parsing.
- `src/thadam/comparison.py` — pure comparison behavior and typed results.
- `src/thadam/comparison_reporting.py` — comparison JSON and terminal presentation.
- `src/thadam/adapters/langgraph.py` — optional graph adapter and callback collector.
- `pyproject.toml` — packaging, Python support, development dependencies, and lint settings.
- `DESIGN.md` — current stack decisions and the reasons behind future changes.
- `docs/architecture.md` — implemented code map, data ownership, and extension boundaries.
- `docs/milestones/` — concrete specifications for individual builds.
- `ROADMAP.md` — canonical feature status and future ideas.
- `CONTRIBUTING.md` — coding conventions shared by human and AI contributors.
- `SECURITY.md` — private vulnerability reporting, supported revisions, and execution/data boundaries.
- `.github/workflows/ci.yml` — repository test, lint, formatting, and package build/install checks.
- `.github/workflows/publish.yml` and `docs/publishing.md` — validated release flow and owner setup; manual workflow runs never publish.
- `scripts/check_installed_package.py` — installed distribution identity, SDK, type marker, and report round-trip checks outside the checkout.
- `examples/` — plain Python and LangGraph refund suites with correct/buggy callables.
- `tests/` — core behavior checks and optional real-graph integration checks.

## How to implement a change

- Pick the smallest complete behavior in the current milestone. Future milestones do not authorize building the whole platform.
- Read existing code and follow its vocabulary before adding another abstraction.
- Use explicit parameters, return types, and small cohesive modules. Prefer plain functions and typed dataclasses when they suffice.
- Keep execution, assertion logic, adapters, reports, and the CLI separate as described in the architecture. The SDK owns behavior; the CLI translates arguments and displays results.
- Add dependencies only for behavior being implemented. Framework and model-provider integrations belong behind optional dependencies.
- Avoid import-time configuration, agent execution, network calls, implicit global state, and hidden provider selection.
- Validate external inputs at the boundary. Distinguish failed assertions, agent execution errors, verifier errors, and invalid suite configuration.
- Preserve stable case IDs and versioned JSON contracts. Document breaking changes to inputs, outputs, or exit codes.
- Unknown tracing is `events=None`, not an observed empty sequence. Tool checks require complete explicit evidence; missing structured arguments produce an error. Preserve partial events when execution raises.
- Keep callback collectors scoped to an invocation and correlate concurrent callbacks by run ID. Never infer token counts or treat unavailable usage as zero.
- Terminal branding and passes use teal; unmet expectations use amber; execution errors use red. Keep labels meaningful without color, honor CLI color policy, and keep ANSI styling out of report artifacts. See `DESIGN.md` for the palette.
- Keep comments focused on intent and non-obvious constraints. Explain a public API's inputs, outputs, and errors in its docstring.
- Update usage documentation and roadmap status with the implementation. Do not describe an unchecked feature as available.

## Validation and handoff

The development extra supplies pytest and Ruff. From the repository root:

```shell
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Use focused tests for real contracts and failure paths. Default tests use controlled agents and tools without a model API key or hosted service. Keep live provider checks explicit and separate. CLI tests import a user's module from a temporary working directory and compare the example's outcomes with the SDK.

Install `'.[dev,langgraph]'` for integration work and run `python -m pytest -q tests/test_langgraph.py`. Without compatible optional packages, that module is skipped. Do not import LangGraph or langchain-core from the core package at module load time.

Repository CI runs core tests on Python 3.10–3.14 and LangGraph tests on Python 3.10 and 3.14. It also builds the distribution and checks a clean wheel installation. Keep its commands and the contributor guide aligned; adding a workflow does not enable required merge checks.

Run `python -m pytest -q examples/regression_test.py` to exercise the consumer pytest example. Validate both workflow files with actionlint when editing `.github/workflows/ci.yml` or `docs/examples/agent-regression.yml`. Baseline updates are explicit reviewable changes; the consumer CI example reads its baseline from the target commit on pull requests.

For packaging work, also validate `.github/workflows/publish.yml`, build source/wheel distributions, run strict metadata checks, and exercise `scripts/check_installed_package.py` with a clean wheel installation outside the checkout. Publishing is a separate release action, not part of CI or a manual validation run. Do not expose OIDC permissions to build/test jobs.

Report what changed, what checks ran, and any remaining limitations. A clean lint result is not evidence that an unimplemented feature works.

## Product constraints

- Task-specific correctness requires a supplied expected outcome, assertion, or verifier.
- AI-generated cases and expectations need review before they serve as trusted release criteria.
- Record observable execution events; do not claim access to hidden model reasoning.
- Agent execution may vary even when assertion logic is deterministic.
- Prefer a useful local workflow and machine-readable artifacts before adding hosted infrastructure.
