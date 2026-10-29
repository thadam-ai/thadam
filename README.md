# Thadam (தடம்)

### Every agent leaves a trace.

Open-source testing, evaluation, and reliability for AI agents. Thadam helps developers test expected behavior, understand failures, and catch regressions before deployment.

> **Project status: pre-MVP.** This repository contains project guidance and a Python package scaffold. The test runner, SDK, and CLI are planned and are not implemented yet.

## What Thadam is building

- A Python SDK and CLI for running agent test scenarios locally
- Developer-defined assertions and verifiers for expected behavior
- Custom Python agent support, followed by a LangGraph integration
- Failure reports with execution evidence and tool-call records
- Reusable regression suites, followed by reviewed AI-generated scenario suggestions

The first build is a local testing engine: connect a Python agent, run saved cases, check expectations, and write a useful report. Task-specific correctness comes from developer-supplied expectations or verifiers. Tracing helps explain the results.

## Start here

- [Roadmap](ROADMAP.md): ordered milestones, completion criteria, and future ideas
- [First milestone](docs/milestones/01-local-runner.md): the next implementation and its acceptance criteria
- [Architecture](docs/architecture.md): data flow, contracts, and planned module boundaries
- [Agent guide](AGENTS.md): repository map and working rules for AI coding agents
- [Contributing](CONTRIBUTING.md): development setup and code conventions

## Development

The package scaffold targets Python 3.10 and newer. See the contributor guide for editable installation and lint commands. SDK and CLI examples in milestone documents describe proposed behavior.

## Name

**Thadam (தடம்)** is a Tamil word for a trace, track, or footprint.

## License

Thadam is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
