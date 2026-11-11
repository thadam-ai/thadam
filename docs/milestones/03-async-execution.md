# Async agents and bounded concurrency

**Status:** implemented. Synchronous SDK/CLI defaults are unchanged.

## Start here

Expose a synchronous or async callable accepting one JSON input. Async execution
awaits awaitable results; it does not put synchronous callables in threads.

```python
import asyncio
from thadam import OutputEquals, TestCase, run_suite_async


async def echo(value):
    await asyncio.sleep(0)
    return value


cases = [TestCase("echo", {"message": "hello"}, (OutputEquals("answer", {"message": "hello"}),))]
report = asyncio.run(run_suite_async(echo, cases, max_concurrency=4))
assert not report.has_failures
```

Inside an existing event loop use `await run_suite_async(...)` directly.

```shell
thadam run cases.json --agent my_agent:run --async --max-concurrency 4 --report run.json
thadam repeat cases.json --agent my_agent:run --attempts 5 --async --max-concurrency 4 --report repeated.json
thadam repeat cases.json --agent-factory my_agent:create --attempts 5 --async --max-concurrency 4
```

`--max-concurrency` defaults to 1 and must be a positive integer. Limits above 1
require `--async`. Invalid limits are rejected before importing the agent.
The async SDK names are `run_suite_async` and `run_repeated_async`; their sync
counterparts continue to reject coroutine functions. The CLI exit codes and report
writers are unchanged. An errored evaluation still saves complete case evidence.

In the dashboard expand **Execution & save settings**, choose **Async** under
**Execution engine**, and set **Maximum concurrent cases**. Opening configuration
does not import agents. One managed evaluation process remains active at a time;
case overlap is internal to that process, not multiple dashboard jobs. Progress
is emitted in completion order and interruption never publishes a completed report.

## Lifecycle and evidence contract

- Validate/snapshot the entire suite before any agent or factory invocation.
- Use a bounded worker pool: at most the selected number of invocations are active.
- Preserve suite order in saved results, even when completion order differs.
- Progress observers remain synchronous and receive independent completed-case
  snapshots in completion order. Their errors propagate, not as agent errors.
- Repeat complete suite attempts in order, waiting for all cases in one attempt
  before starting the next. Retain every attempt and individual check outcome.
- Shared mode retains one callable. Factory mode constructs one fresh agent for
  each invocation, awaiting a zero-argument async factory when needed. Factory
  construction and invocation errors remain agent errors and later cases continue.
- Assertions and verifiers retain existing semantics. Verifiers remain synchronous.
  Missing tracing stays unknown; instrumented results/errors retain complete or
  partial explicit evidence. Usage is never inferred.
- Cancellation or observer failure cancels and awaits all owned worker tasks, then
  propagates without returning a completed report. Tested `SystemExit`, even 0,
  remains a per-case error. `KeyboardInterrupt` propagates.

Concurrency is cooperative. Blocking sync code blocks the event loop. An agent
that suppresses cancellation can delay shutdown. Defaults introduce no enforced
timeout, sandbox, automatic retries, provider selection or implicit resource
cleanup.
Callers own external side effects, shared-agent reentrancy, resource limits,
verifier state and cleanup. A factory does not reset global/external resources.

## Reports and comparisons

Existing run schemas 3/4 and repeated schema 1 remain unchanged, as do the
shared/factory mode names and all baseline/approval contracts. Runtime is measured
per invocation; sums of overlapping durations are not wall-clock elapsed time.

Scheduling settings (sync/async and concurrency limit) are **not encoded in these
report schemas**, so comparisons cannot automatically reject a scheduling change.
Use identical scheduling settings for reviewed baselines and candidates, and record
that configuration alongside the suite/application revision. No claim of isolation
or reproducibility follows from equal execution modes. Comparison still never
executes agents or verifiers. A future versioned scheduling contract can make
these settings machine-comparable without changing legacy artifacts silently.

## LangGraph

Use `LangGraphAgent(graph).ainvoke` as the async agent reference (or wrap it in your
own async callable). It awaits the compiled graph's public `ainvoke`, keeps the
existing callback collector scoped to one invocation, and uses a fresh checkpoint
thread ID for each case. Mappers remain synchronous. See the [tracing guide](02-langgraph.md)
for coverage, event availability and partial error evidence.

## Validation

Controlled tests cover overlap bounds, ordering, immutable evidence, report
round trips, factory construction, continuation after errors, cancellation and
observer cleanup, invalid settings before imports, CLI execution and dashboard
jobs. All examples can run without model keys or external services.

Optional `limits=ExecutionLimits(...)` selects turn caps or fresh spawned case
processes for deadlines; `EnvironmentHooks` supplies explicit cleanup. These are
documented in [execution boundaries](05-execution-boundaries.md). Legacy default
execution and concurrency semantics above remain in effect without a deadline.
