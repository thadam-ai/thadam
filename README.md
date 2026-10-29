# Thadam (தடம்)

### Every agent leaves a trace.

Open-source testing, evaluation, and reliability for AI agents. Thadam helps developers test expected behavior, understand failures, and catch regressions before deployment.

> **Project status: early development.** The first local Python runner, SDK, and CLI work. LangGraph instrumentation, tool tracing, scenario generation, and the dashboard are planned.

## What works today

- A Python SDK and CLI for running agent test scenarios locally
- Developer-defined assertions and verifiers for expected behavior
- Synchronous custom Python agents accepting and returning JSON-compatible values
- Terminal summaries and versioned JSON reports with output, assertion evidence, errors, and duration

Task-specific correctness comes from developer-supplied expectations or verifiers. The runner executes trusted application code in your local Python process. It runs cases sequentially, with no automatic retries, enforced timeouts, or sandbox. Execution evidence currently covers inputs supplied by the suite, returned outputs, checks, errors, and durations; model and tool-call tracing comes later.

## Try it locally

From a checkout of this repository, using Python 3.10 or newer:

```shell
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

thadam run examples/refund_cases.json \
  --agent examples.refund_agent:run \
  --report artifacts/refund-report.json
```

This runs five cases and exits `0` when all pass. The example is a controlled refund-policy function using local fixtures, so it needs no model API key. It validates the engine's behavior; it does not measure an LLM's quality.

To see failure explanations, use the intentionally buggy variant:

```shell
thadam run examples/refund_cases.json \
  --agent examples.refund_agent:run_buggy \
  --report artifacts/buggy-refund-report.json
```

Expected result: **3 passed, 1 failed, 1 error**, with exit code `1`. The failed assertion shows expected and actual values; the errored case records the exception. The final case still runs after the error.

## Connect your agent

Expose a synchronous callable such as `run(input)` in your application. Return a JSON-compatible result; wrap existing framework or client code inside the function if needed. From your application's working directory, run:

```shell
thadam run cases.json --agent my_agent:run --report artifacts/report.json
```

The agent module is imported from your current directory or installed packages. `python -m thadam` is an alternative to the `thadam` console command.

## Python SDK

```python
from examples.refund_agent import run
from thadam import load_suite, run_suite, write_report

cases = load_suite("examples/refund_cases.json")
report = run_suite(agent=run, cases=cases)
write_report(report, "artifacts/sdk-report.json")

print(report.summary)
```

Cases can also be constructed in Python with `TestCase`, `OutputEquals`, `OutputHasKeys`, and custom `Verifier` callbacks. See the [suite and verifier contracts](docs/milestones/01-local-runner.md) for formats, examples, and error semantics.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every case passed |
| `1` | One or more cases failed or errored |
| `2` | Invalid configuration, agent reference, arguments, or report destination |

## Terminal appearance

Thadam uses logo-inspired teal for passes and branding, blue for suite and agent details, amber for failed assertions, and red for execution and configuration errors. Each result also has an explicit status label. Timings align beside cases and failure evidence wraps beneath them.

Color is automatic in interactive terminals and disabled for redirected output, `TERM=dumb`, or a non-empty `NO_COLOR`. Use `--color always` to force color or `--color never` for plain text. An explicit flag takes precedence over `NO_COLOR`. These flags work before or after `run`:

```shell
thadam run examples/refund_cases.json --agent examples.refund_agent:run_buggy --color always
```

Terminals advertising RGB support through `COLORTERM=truecolor` or `24bit` use the brand palette; others use native terminal colors. When `COLORFGBG` advertises a white background, RGB accents use darker shades. Thadam leaves your terminal background and font alone. JSON report artifacts contain data only, without presentation styling.

## Start here

- [Roadmap](ROADMAP.md): ordered milestones, completion criteria, and future ideas
- [Design decisions](DESIGN.md): agreed stack, rationale, and decision history
- [First milestone](docs/milestones/01-local-runner.md): the next implementation and its acceptance criteria
- [Architecture](docs/architecture.md): data flow, contracts, and planned module boundaries
- [Agent guide](AGENTS.md): repository map and working rules for AI coding agents
- [Contributing](CONTRIBUTING.md): development setup and code conventions

## Development

See the contributor guide for development setup. Core checks require no network or model credentials:

```shell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

## Name

**Thadam (தடம்)** is a Tamil word for a trace, track, or footprint.

## License

Thadam is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
