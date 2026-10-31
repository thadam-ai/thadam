# Thadam (தடம்)

### Every agent leaves a trace.

Open-source testing, evaluation, and reliability for AI agents. Thadam helps developers test expected behavior, understand failures, and catch regressions before deployment.

> **Project status: early development.** The local runner, SDK, CLI, optional LangGraph integration, tool assertions, saved-report regression comparison, and repeated-evaluation reliability gates work. Scenario generation and the dashboard are planned.

## What works today

- A Python SDK and CLI for running agent test scenarios locally
- Developer-defined assertions and verifiers for expected behavior
- Synchronous custom Python agents accepting and returning JSON-compatible values
- An optional LangGraph adapter capturing supported model/tool callbacks and reported token usage
- Assertions for required/forbidden tool calls and selected arguments, linked to execution events
- Terminal summaries and versioned JSON reports with output, assertion evidence, errors, and duration
- Compare reviewed baselines with candidate reports, detecting newly failing checks and incompatible tests
- Repeat evaluations, inspect case/check pass rates and runtime, and gate changes on observed reliability drops

Task-specific correctness comes from developer-supplied expectations or verifiers. The runner executes trusted application code in your local Python process. It runs cases sequentially, with no automatic retries, enforced timeouts, or sandbox. Plain Python functions provide input/output evidence; the optional LangGraph adapter additionally records instrumented model and tool calls. Tool assertions require explicit tracing evidence.

## Explore the CLI

Run `thadam` without arguments for an overview, a getting-started guide, and the
available workflows. It exits successfully without loading or executing an agent.
`thadam --help` shows the same overview. Each command has its own explanation,
copyable application examples, and exit-code guidance:

```shell
thadam
thadam run --help
thadam compare --help
thadam repeat --help
thadam compare-repeated --help
```

Replace `cases.json` and `my_agent:run` in the help examples with your application's
suite and callable. The refund example labeled as a repository example requires
a checkout. In VS Code, open **Terminal → New Terminal** in the repository root
and use `.venv/bin/python -m thadam` or
`.venv/bin/python -m thadam repeat --help` with the development environment.

Help uses Thadam's teal branding and blue section headings automatically in an
interactive terminal. `--color never` disables styling and `--color always`
forces it, including when passed alongside `--help`. Redirected output,
`NO_COLOR`, and `TERM=dumb` follow the same policy as execution summaries.

## Package installation

The first PyPI release is being prepared. Once it is published, install the **`thadam-ai`** distribution with Python 3.10 or newer:

```shell
python -m pip install thadam-ai
thadam --help
```

For LangGraph support, install `python -m pip install 'thadam-ai[langgraph]'`. The Python import remains `thadam`, and the command remains `thadam`. The separate PyPI package named `thadam` is unrelated to this project.

The installed SDK works with your own agents without checking out this repository:

```python
from thadam import OutputEquals, TestCase, run_suite

cases = [
    TestCase("echo", {"message": "hello"}, (OutputEquals("answer", {"message": "hello"}),)),
]
report = run_suite(agent=lambda request: request, cases=cases)
print(report.summary)
```

See the [publishing guide](https://github.com/thadam-ai/thadam/blob/main/docs/publishing.md) for release setup and status. The following example suites and agent modules live in the repository checkout; they are not installed by pip.

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

Cases can also be constructed in Python with `TestCase`, `OutputEquals`, `OutputHasKeys`, and custom `Verifier` callbacks. See the [suite and verifier contracts](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/01-local-runner.md) for formats, examples, and error semantics.

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

Wrap your own compiled graph with `LangGraphAgent` from `thadam.adapters.langgraph`, optionally supplying input/output mappers and graph config. See the [LangGraph guide](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/02-langgraph.md) for integration code, tool assertion formats, coverage limits, and checkpoint isolation.

Reports now use **schema version 3**. They retain execution events and availability fields from schema 2 and add declared check definitions, an evaluation version, and optional application revision metadata. Uninstrumented Python runs have `events: null`, not an observed empty trace. Existing case files still use schema version 1 and continue to work. Comparing older reports requires fresh runs because those reports lack declared check contracts.

## Catch regressions after a change

Generate a candidate report and compare it with the committed example baseline:

```shell
thadam run examples/refund_cases.json --agent examples.refund_agent:run \
  --agent-revision my-change --report artifacts/candidate.json
thadam compare examples/baselines/refund-report.json artifacts/candidate.json \
  --report artifacts/comparison.json
```

This comparison exits `0`. The saved baseline uses local refund fixtures; its revision label and zero timings are fixture data, not a performance measurement. With your own agent, explicitly generate and review a baseline before committing it. Baselines are never selected or updated automatically.

Try `examples.refund_agent:run_buggy` to see a new failed check and an agent error. `run` exits `1` but still writes its report; run `compare` afterward to inspect the differences. A newly failing check is caught even if its case was already failing another check.

Comparison matches case/check IDs and verifies that inputs and declared expectations agree. Changed or missing cases/checks, changed expectations, and unversioned/changed custom verifiers are incompatible. Existing assertion failures stay visible and may be acknowledged through a reviewed baseline; errors on either side always block a clean gate.

SDK usage:

```python
from thadam import compare_reports, load_report, write_comparison

comparison = compare_reports(
    load_report("examples/baselines/refund-report.json"),
    load_report("artifacts/candidate.json"),
)
write_comparison(comparison, "artifacts/comparison.json")
print(comparison.summary)
```

The [comparison guide](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/03-regression-comparison.md) documents contracts, verifier revisions, classifications, and limitations. Run the [pytest example](https://github.com/thadam-ai/thadam/blob/main/examples/regression_test.py) with `python -m pytest -q examples/regression_test.py`. The [consumer GitHub Actions example](https://github.com/thadam-ai/thadam/blob/main/docs/examples/agent-regression.yml) reads the reviewed baseline from the PR's target commit and gates on the comparison result. Adapt its paths and application installation before copying it into your own workflow.

## Compare agent reliability across repeated attempts

Evaluate the candidate five times against the reviewed local fixture baseline:

```shell
thadam repeat examples/refund_cases.json --agent examples.refund_agent:run \
  --attempts 5 --agent-revision my-change --report artifacts/repeated-candidate.json
thadam compare-repeated examples/baselines/refund-repeated.json \
  artifacts/repeated-candidate.json --report artifacts/reliability-comparison.json
```

Both commands exit `0`. The baseline contains five attempts using the controlled
refund fixture; its zero timings and revision labels are fixture data, not LLM
performance measurements. Try `examples.refund_agent:run_buggy` to see failures
and errors. `repeat` still saves all attempts when it exits `1`; comparison must
run afterward and its exit code decides the regression gate.

Each case and check shows pass/fail/error counts and observed pass rates. Reports
also retain runtime summaries and every attempt's outputs, errors, checks, and
available traces. A comparison artifact includes both full evaluations, so the
failed attempts remain inspectable without the original files. For scripted
variation from 80% to 60%, run `python -m examples.reliability_demo` (expected exit
`1`); it writes all three artifacts under `artifacts/reliability-demo/`.

Comparison requires equal attempt counts, execution modes, and input/check
contracts. It checks each case and each individual assertion, including inside
already-failing cases. By default any observed pass-rate decrease blocks.
`--max-pass-rate-drop 0.05` allows a drop of up to **five percentage points** per
case/check; equality is allowed. Errors on either side always block, regardless
of tolerance. Existing failures and tolerated drops stay visible. These are
observed rates, not significance tests or proof that a change caused a difference.

Python SDK:

```python
from examples.refund_agent import run
from thadam import compare_repeated, load_repeated, load_suite, run_repeated, write_repeated

baseline = load_repeated("examples/baselines/refund-repeated.json")
candidate = run_repeated(
    agent=run,
    cases=load_suite("examples/refund_cases.json"),
    attempts=baseline.attempts,
    agent_revision="my-change",
)
write_repeated(candidate, "artifacts/repeated-candidate.json")
comparison = compare_repeated(baseline, candidate, max_pass_rate_drop=0.0)
print(comparison.exit_code, comparison.summary)
```

`--agent` reuses one callable for all case invocations. For stateful agents, use
`--agent-factory my_agent:create` instead: a synchronous zero-argument factory
must construct an agent for each case invocation. The SDK equivalent is
`run_repeated(cases=cases, agent_factory=create, attempts=20)`. Reports record
`shared` or `factory` mode, and comparison rejects a mode change. Factories do
not reset external services, globals, or verifier state; developers own that
isolation and resource lifecycle. Execution remains sequential with no retries
or enforced timeouts.

`write_reliability_comparison` saves a standalone comparison, and
`load_reliability_comparison` validates and recomputes its gate without executing
application code. See the [full execution/report contract](docs/milestones/03-reliability.md),
[pytest gates](examples/regression_test.py), and
[consumer CI example](docs/examples/agent-regression.yml). For your own agent,
explicitly generate, inspect, and review a baseline before committing it. Candidate
jobs never update it; pull requests read the baseline from the target commit.

## Exit codes

| Code | `run` | `compare` |
| --- | --- | --- |
| `0` | Every case passed | Compatible reports, no regressions or errors |
| `1` | One or more cases failed or errored | A newly failing check or an error on either side |
| `2` | Invalid configuration, agent reference, arguments, or report destination | Invalid/incompatible reports or artifact write failure |

`repeat` uses the `run` exit-code meanings for all invocations.
`compare-repeated` uses the `compare` meanings, with the configured pass-rate policy.

## Terminal appearance

Thadam uses logo-inspired teal for passes and branding, blue for suite and agent details, amber for failed assertions, and red for execution and configuration errors. Each result also has an explicit status label. Timings align beside cases and failure evidence wraps beneath them.

Color is automatic in interactive terminals and disabled for redirected output, `TERM=dumb`, or a non-empty `NO_COLOR`. Use `--color always` to force color or `--color never` for plain text. An explicit flag takes precedence over `NO_COLOR`. These flags work before or after `run`:

```shell
thadam run examples/refund_cases.json --agent examples.refund_agent:run_buggy --color always
```

Terminals advertising RGB support through `COLORTERM=truecolor` or `24bit` use the brand palette; others use native terminal colors. When `COLORFGBG` advertises a white background, RGB accents use darker shades. Thadam leaves your terminal background and font alone. JSON report artifacts contain data only, without presentation styling.

## Start here

- [Roadmap](https://github.com/thadam-ai/thadam/blob/main/ROADMAP.md): ordered milestones, completion criteria, and future ideas
- [Design decisions](https://github.com/thadam-ai/thadam/blob/main/DESIGN.md): agreed stack, rationale, and decision history
- [Local runner](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/01-local-runner.md): SDK, suite format, and report contracts
- [LangGraph integration](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/02-langgraph.md): callbacks, tool assertions, and execution evidence
- [Regression comparison](https://github.com/thadam-ai/thadam/blob/main/docs/milestones/03-regression-comparison.md): reviewed baselines, report compatibility, and CI gates
- [Repeated reliability](docs/milestones/03-reliability.md): attempt evidence, agent lifecycle, pass-rate comparisons, and CI policy
- [Architecture](https://github.com/thadam-ai/thadam/blob/main/docs/architecture.md): data flow, contracts, and module boundaries
- [Agent guide](https://github.com/thadam-ai/thadam/blob/main/AGENTS.md): repository map and working rules for AI coding agents
- [Contributing](https://github.com/thadam-ai/thadam/blob/main/CONTRIBUTING.md): development setup and code conventions
- [Security policy](https://github.com/thadam-ai/thadam/blob/main/SECURITY.md): supported versions, private reporting, and execution boundaries

## Development

See the contributor guide for development setup. Core checks require no network or model credentials:

```shell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Install `'.[dev,langgraph]'` to include the real-graph integration tests. They also use controlled fixtures and need no model credentials. Without the extra, those tests are skipped.

The [CI workflow](https://github.com/thadam-ai/thadam/blob/main/.github/workflows/ci.yml) runs on pull requests and pushes to `main`. It checks Ruff lint and formatting, core tests on Python 3.10–3.14, LangGraph tests on Python 3.10 and 3.14, and package build and installation. See [the contributor guide](https://github.com/thadam-ai/thadam/blob/main/CONTRIBUTING.md#automated-checks) for local equivalents and merge-check guidance.

## Name

**Thadam (தடம்)** is a Tamil word for a trace, track, or footprint.

## License

Thadam is licensed under the Apache License 2.0. See [LICENSE](https://github.com/thadam-ai/thadam/blob/main/LICENSE).
