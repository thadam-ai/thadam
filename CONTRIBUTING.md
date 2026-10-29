# Contributing to Thadam

Thanks for your interest in Thadam. The project is in early development, so discussion about agent testing workflows, assertion contracts, and failure reports is especially useful.

Read the [roadmap](ROADMAP.md), [architecture](docs/architecture.md), and [first milestone](docs/milestones/01-local-runner.md) before starting a feature. [AGENTS.md](AGENTS.md) provides a compact repository map for AI coding agents and human contributors.

## Before you start

- Check existing issues and discussions before starting a large change.
- For a new feature or a substantial design change, open an issue first so the direction can be discussed.
- Keep pull requests focused and explain the user problem they solve.

## Development setup

Thadam targets Python 3.10 and newer. From the repository root, create a virtual environment and install the project in editable mode with its development tools:

```shell
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Run the formatter and linter before opening a pull request:

```shell
python -m ruff format .
python -m ruff check .
```

When behavior is added, include focused tests for it. Add pytest to the development extra with the first runner implementation. Use controlled agents and tools so default tests run without network access, model credentials, or hosted services.

## Code that humans and AI agents can understand

- Use descriptive domain names such as `TestCase`, `AssertionResult`, and `RunReport` consistently across code and documentation.
- Keep functions focused on one responsibility, with explicit inputs and return values. Avoid clever control flow, catch-all utility modules, and speculative plugin systems.
- Type public APIs and shared data contracts. Prefer simple functions and dataclasses before introducing inheritance or a framework.
- Keep the execution engine independent of the CLI, framework integrations, providers, and report presentation.
- Make failures explicit. An assertion failure, an agent exception, and a verifier error carry different evidence and must not be conflated.
- Write docstrings for public contracts and comments for non-obvious decisions. Keep executable examples close to the behavior they explain.
- Give each file a clear purpose and update the architecture map when boundaries change. Create modules when they have behavior to own.
- Keep machine-readable cases and reports versioned, with stable identifiers and documented meanings. These contracts help automation and human reviewers inspect the same evidence.
- Update roadmap status and usage docs in the same change as the feature. Keep planned behavior clearly labeled.

## Pull requests

1. Describe the problem and the approach.
2. Note any compatibility, case/report-schema, or CLI exit-code changes.
3. Include documentation and tests when they apply.
4. Keep commits and file changes focused on the proposed change.

By submitting a contribution, you agree that it is provided under the repository's Apache License 2.0. This project does not currently require a separate contributor license agreement.
