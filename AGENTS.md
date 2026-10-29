# Working in Thadam

## Read these first

1. `README.md` — purpose and current implementation status.
2. `ROADMAP.md` — priorities and completed work.
3. `docs/architecture.md` — contracts and module boundaries.
4. The relevant milestone document; next is `docs/milestones/01-local-runner.md`.
5. `CONTRIBUTING.md` — setup and shared code conventions.

This is a Python package for testing and evaluating AI agents. The product is **Thadam (தடம்)**. Use `thadam` for Python package and CLI names.

## Current implementation

The package currently contains only `src/thadam/__init__.py` and its version. There is no runner, CLI, agent adapter, scenario generator, or collector yet. Architecture and milestone examples describe planned behavior. Re-read the code before assuming any API exists.

## Repository map

- `src/thadam/` — public Python package; create modules when they have working behavior.
- `pyproject.toml` — packaging, Python support, development dependencies, and lint settings.
- `docs/architecture.md` — planned code map and data ownership.
- `docs/milestones/` — concrete specifications for individual builds.
- `ROADMAP.md` — canonical feature status and future ideas.
- `CONTRIBUTING.md` — coding conventions shared by human and AI contributors.
- `examples/` and `tests/` — planned; add runnable examples and meaningful tests with the features they exercise.

## How to implement a change

- Pick the smallest complete behavior in the current milestone. Future milestones do not authorize building the whole platform.
- Read existing code and follow its vocabulary before adding another abstraction.
- Use explicit parameters, return types, and small cohesive modules. Prefer plain functions and typed dataclasses when they suffice.
- Keep execution, assertion logic, adapters, reports, and the CLI separate as described in the architecture. The SDK owns behavior; the CLI translates arguments and displays results.
- Add dependencies only for behavior being implemented. Framework and model-provider integrations belong behind optional dependencies.
- Avoid import-time configuration, agent execution, network calls, implicit global state, and hidden provider selection.
- Validate external inputs at the boundary. Distinguish failed assertions, agent execution errors, verifier errors, and invalid suite configuration.
- Preserve stable case IDs and versioned JSON contracts. Document breaking changes to inputs, outputs, or exit codes.
- Keep comments focused on intent and non-obvious constraints. Explain a public API's inputs, outputs, and errors in its docstring.
- Update usage documentation and roadmap status with the implementation. Do not describe an unchecked feature as available.

## Validation and handoff

The current development extra supplies Ruff. From the repository root:

```shell
python -m pip install -e '.[dev]'
python -m ruff check .
python -m ruff format --check .
```

No behavior tests exist yet. Add pytest to development dependencies when implementing milestone 1 and use focused tests for real contracts and failure paths. Default test runs should use controlled agents and tools without a model API key or hosted service. Keep live provider checks explicit and separate.

Report what changed, what checks ran, and any remaining limitations. A clean lint result is not evidence that an unimplemented feature works.

## Product constraints

- Task-specific correctness requires a supplied expected outcome, assertion, or verifier.
- AI-generated cases and expectations need review before they serve as trusted release criteria.
- Record observable execution events; do not claim access to hidden model reasoning.
- Agent execution may vary even when assertion logic is deterministic.
- Prefer a useful local workflow and machine-readable artifacts before adding hosted infrastructure.
