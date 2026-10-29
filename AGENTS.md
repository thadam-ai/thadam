# Working in Thadam

## Read these first

1. `README.md` — purpose and current implementation status.
2. `ROADMAP.md` — priorities and completed work.
3. `DESIGN.md` — agreed stack, rationale, and decision history.
4. `docs/architecture.md` — contracts and module boundaries.
5. `docs/milestones/01-local-runner.md` — the implemented first milestone's formats and acceptance criteria; select new work from `ROADMAP.md`.
6. `CONTRIBUTING.md` — setup and shared code conventions.

This is a Python package for testing and evaluating AI agents. The product is **Thadam (தடம்)**. Use `thadam` for Python package and CLI names.

## Current implementation

Milestone 1 is implemented: typed cases, JSON suite validation, a synchronous Python runner, built-in assertions, SDK verifiers, terminal/JSON reports, and the CLI. `src/thadam/__init__.py` exports the public SDK. `python -m thadam` and the installed `thadam` command use the same entry point. See `docs/architecture.md` for the module map and `tests/` for executable contracts.

The engine is sequential and runs trusted agent code in the current process. It has no enforced timeouts, sandbox, automatic framework instrumentation, tool traces, or scenario generator. Later roadmap items remain planned. Re-read the code before assuming an API exists.

## Repository map

- `src/thadam/` — public SDK, validation, assertions, runner, reports, and CLI.
- `pyproject.toml` — packaging, Python support, development dependencies, and lint settings.
- `DESIGN.md` — current stack decisions and the reasons behind future changes.
- `docs/architecture.md` — implemented code map, data ownership, and extension boundaries.
- `docs/milestones/` — concrete specifications for individual builds.
- `ROADMAP.md` — canonical feature status and future ideas.
- `CONTRIBUTING.md` — coding conventions shared by human and AI contributors.
- `examples/` — five-case refund suite and correct/buggy local policy callables.
- `tests/` — validation, runner, verifier, reporting, and CLI behavior checks.

## How to implement a change

- Pick the smallest complete behavior in the current milestone. Future milestones do not authorize building the whole platform.
- Read existing code and follow its vocabulary before adding another abstraction.
- Use explicit parameters, return types, and small cohesive modules. Prefer plain functions and typed dataclasses when they suffice.
- Keep execution, assertion logic, adapters, reports, and the CLI separate as described in the architecture. The SDK owns behavior; the CLI translates arguments and displays results.
- Add dependencies only for behavior being implemented. Framework and model-provider integrations belong behind optional dependencies.
- Avoid import-time configuration, agent execution, network calls, implicit global state, and hidden provider selection.
- Validate external inputs at the boundary. Distinguish failed assertions, agent execution errors, verifier errors, and invalid suite configuration.
- Preserve stable case IDs and versioned JSON contracts. Document breaking changes to inputs, outputs, or exit codes.
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

Report what changed, what checks ran, and any remaining limitations. A clean lint result is not evidence that an unimplemented feature works.

## Product constraints

- Task-specific correctness requires a supplied expected outcome, assertion, or verifier.
- AI-generated cases and expectations need review before they serve as trusted release criteria.
- Record observable execution events; do not claim access to hidden model reasoning.
- Agent execution may vary even when assertion logic is deterministic.
- Prefer a useful local workflow and machine-readable artifacts before adding hosted infrastructure.
