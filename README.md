# Thadam (தடம்)

### Every agent leaves a trace.

Open-source testing, evaluation, and reliability for AI agents. Thadam helps developers test expected behavior, understand failures, and catch regressions before deployment.

> **Project status: early development.** The local runner, SDK, CLI, optional LangGraph integration, and tool assertions work. Scenario generation, regression comparison, and the dashboard are planned.

## What works today

- A Python SDK and CLI for running agent test scenarios locally
- Developer-defined assertions and verifiers for expected behavior
- Synchronous custom Python agents accepting and returning JSON-compatible values
- An optional LangGraph adapter capturing supported model/tool callbacks and reported token usage
- Assertions for required/forbidden tool calls and selected arguments, linked to execution events
- Terminal summaries and versioned JSON reports with output, assertion evidence, errors, and duration

Task-specific correctness comes from developer-supplied expectations or verifiers. The runner executes trusted application code in your local Python process. It runs cases sequentially, with no automatic retries, enforced timeouts, or sandbox. Plain Python functions provide input/output evidence; the optional LangGraph adapter additionally records instrumented model and tool calls. Tool assertions require explicit tracing evidence.

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

## Test a LangGraph agent

Install the optional integration from this checkout and run the controlled example:

```shell
python -m pip install -e '.[langgraph]'
thadam run examples/langgraph_cases.json \
  --agent examples.langgraph_agent:agent \
  --report artifacts/langgraph-report.json
```

All three cases pass. The example uses a real compiled LangGraph, a scripted model, and local tools. Its token counts are fixture metadata; no paid model is called.

The buggy variant returns the same final answers but skips the required order lookup:

```shell
thadam run examples/langgraph_cases.json \
  --agent examples.langgraph_agent:agent_buggy \
  --report artifacts/langgraph-buggy-report.json
```

All three cases fail their tool checks. Failure reports show observed model/tool events and their IDs. JSON reports retain arguments, results, errors, durations, and reported usage, including partial events when graph execution raises an exception.

Wrap your own compiled graph with `LangGraphAgent` from `thadam.adapters.langgraph`, optionally supplying input/output mappers and graph config. See the [LangGraph guide](docs/milestones/02-langgraph.md) for integration code, tool assertion formats, coverage limits, and checkpoint isolation.

Reports now use **schema version 2**: case records add `events`, `trace_complete`, and `trace_warnings`; assertions add `event_ids`. Uninstrumented Python runs have `events: null`, not an observed empty trace. Existing case files still use schema version 1 and continue to work.

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
- [Local runner](docs/milestones/01-local-runner.md): SDK, suite format, and report contracts
- [LangGraph integration](docs/milestones/02-langgraph.md): callbacks, tool assertions, and execution evidence
- [Architecture](docs/architecture.md): data flow, contracts, and module boundaries
- [Agent guide](AGENTS.md): repository map and working rules for AI coding agents
- [Contributing](CONTRIBUTING.md): development setup and code conventions

## Development

See the contributor guide for development setup. Core checks require no network or model credentials:

```shell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Install `'.[dev,langgraph]'` to include the real-graph integration tests. They also use controlled fixtures and need no model credentials. Without the extra, those tests are skipped.

## Name

**Thadam (தடம்)** is a Tamil word for a trace, track, or footprint.

## License

Thadam is licensed under the Apache License 2.0. See [LICENSE](LICENSE).
