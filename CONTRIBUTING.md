# Contributing to Thadam

Thanks for your interest in Thadam. The project is in early development, so discussion about agent testing workflows, assertion contracts, and failure reports is especially useful.

Read the [roadmap](ROADMAP.md), [architecture](docs/architecture.md), and [first milestone](docs/milestones/01-local-runner.md) before starting a feature. [AGENTS.md](AGENTS.md) provides a compact repository map for AI coding agents and human contributors.

## Before you start

- Check existing issues and discussions before starting a large change.
- For a new feature or a substantial design change, open an issue first so the direction can be discussed.
- Keep pull requests focused and explain the user problem they solve.
- Report suspected vulnerabilities through the [security policy's private reporting route](SECURITY.md#report-a-vulnerability-privately), rather than a public issue.

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
python -m pytest -q
```

When behavior is added, include focused tests for it. Use controlled agents and tools so default tests run without network access, model credentials, or hosted services. The current suite covers input validation, error handling, verifier contracts, report artifacts, and CLI/SDK agreement. Live model checks should be separate and explicitly configured.

For LangGraph development, install `python -m pip install -e '.[dev,langgraph]'` before running tests. `tests/test_langgraph.py` runs actual compiled graphs with scripted models and local tools; it is skipped when compatible optional dependencies are absent. Run that module when changing callback handling and the full suite when changing shared models, assertions, or reports. Check dependency resolution in a clean environment with `python -m pip check`.

## Automated checks

The [CI workflow](.github/workflows/ci.yml) runs for every pull request and push to `main`, and can also be started manually from GitHub Actions. Its jobs are:

| Check | What it verifies |
| --- | --- |
| `Lint` | Ruff lint and formatting on Python 3.14 |
| `Core tests (Python 3.10)` through `Core tests (Python 3.14)` | Editable installation, dependency consistency, and pytest without optional integrations on each minor version |
| `LangGraph tests (Python 3.10)` and `LangGraph tests (Python 3.14)` | Optional imports, dependency consistency, and the full test suite (including the LangGraph module) with that extra installed |
| `Package` | Isolated source/wheel build, strict metadata checks, clean wheel installation, and installed SDK/CLI checks outside the checkout |

Tests use controlled fixtures and require no model credentials. The workflow has read-only repository permissions, does not persist checkout credentials, and pins actions to full commit hashes. Review upstream changes when updating those pins. The workflow does not publish packages or upload execution reports.

Run lint and formatting checks locally with `python -m ruff check .` and `python -m ruff format --check .`. To reproduce the optional integration checks:

```shell
python -m pip install -e '.[dev,langgraph]'
python -m pip check
python -m pytest -q tests/test_langgraph.py
python -m pytest -q
```

To check packaging locally, first remove stale build output if present, then run:

```shell
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

The workflow creates a fresh virtual environment to install the resulting wheel and check its CLI and type marker. An editable source installation alone does not verify that the distribution includes the required files.

### Maintainer merge settings

After the workflow has run successfully on GitHub, maintainers should configure a rule for `main` requiring all checks listed above before merging. Workflow files do not enable branch protection by themselves. Select the exact check names from a completed run, keep the names unique, and update the rule when changing the Python matrix. See GitHub's [required status checks guidance](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging).

Keep repository CI separate from consumer workflows that test a user's agent. The saved-report comparison and [consumer CI example](docs/examples/agent-regression.yml) are implemented; repeated runs and a dedicated pytest plugin remain planned. See the [comparison contract](docs/milestones/03-regression-comparison.md). Run the consumer pytest example with `python -m pytest -q examples/regression_test.py`.

When changing report formats, preserve declared checks and distinguish run schema 3 from comparison schema 1. Compared custom verifiers need explicit revisions. Test new failures inside already-failing cases, changed/missing contracts, invalid saved evidence, and errors on both sides. Review baseline changes as changes to accepted behavior; never regenerate a baseline automatically in a candidate job.

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
