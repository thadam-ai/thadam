# Execution limits and external environments

**Status:** implemented as the final slice of milestone 5 in the source checkout.
Defaults retain sequential synchronous or cooperative asynchronous execution.
Explicit turn caps, process deadlines and external hooks use the same SDK,
CLI and dashboard execution paths. No milestone 6 evaluators are introduced.

## Select a policy

```python
from thadam import ExecutionLimits, run_suite

# Use an importable module-level agent and an if __name__ == "__main__" guard
# when calling this from a script: deadline workers use multiprocessing spawn.
limits = ExecutionLimits(max_turns=4, timeout_seconds=10, cleanup_timeout_seconds=1)
report = run_suite(agent, cases, limits=limits)
```

`run_suite`, `run_suite_async`, `run_repeated` and `run_repeated_async` accept
`limits=ExecutionLimits(...)`. Positive integer `max_turns` caps each scripted
conversation; the runner stops **before** invoking the next excess turn and
records `TurnLimitExceeded`. Prior turn responses and state remain available.
A case with no conversation has one invocation. A cap does not truncate a suite
or silently count an unfinished conversation as successful.

`timeout_seconds` must be positive and finite. Setting it opts into a **fresh
spawned process per case attempt**, including for synchronous agents. Its wall
clock starts before worker startup and covers environment setup/reset, factory
construction, every conversation turn, cleanup, output validation and verifiers.
The deadline is per case, not per turn or per repeated suite. Async mode retains
bounded case overlap; attempts stay ordered and do not overlap.

Each process receives a serialized copy of the configured callable and case.
Shared callable mutations are not retained across cases in deadline mode. Factory
construction stays inside the worker; factory-produced agents and external handles
need not be picklable. The supplied callable/factory, hook callbacks and verifiers
must be importable and picklable. Nested functions, lambdas, interactive definitions
and existing unpicklable connections cannot be passed as worker configuration.
Configuration is checked before any case runs. Construct connections in setup or
the factory inside the worker. No third-party serialization package is required.

Expiry always yields an error with type `TimeoutError`, unavailable case output
and no passing assertion results. The parent first requests cooperative async
cancellation, allows part of `cleanup_timeout_seconds` for settling, then uses
the remaining grace to terminate/kill and reap the worker. This grace must be
finite and non-negative; zero requests immediate termination. A worker crash or
exit without a result, even exit code zero, becomes `WorkerProcessError`.
Agent `SystemExit` remains an error. Caller cancellation/observer failure stops
owned workers and propagates without publishing a completed evaluation.

A forced kill cannot run Python finally blocks. Cleanup is attempted when control
can reach it; successful external rollback is never inferred from termination.
Owned workers monitor parent death so stopping a dashboard job cannot leave a
case worker running. Deadlines terminate the owned worker, not arbitrary detached
subprocesses or remote service requests. This process boundary is not a sandbox.

## External environment lifecycle

```python
from thadam import EnvironmentHooks, FixtureAgent

# These functions live at module scope in your application.
environment = EnvironmentHooks(setup=create_database, reset=seed_database,
                               cleanup=dispose_database)
agent = FixtureAgent(create_agent, environment=environment)
```

`setup()` returns an opaque trusted handle, exposed to `create_agent(tools)` as
`tools.environment`. `reset(handle)` runs before the agent factory. The same
handle, controlled tool scripts and JSON state span every turn in that attempt.
`cleanup(handle)` runs after execution, including reset, factory and agent
failures. Each case/repeated attempt calls setup and reset afresh. There is no
implicit shared environment, service discovery or real-service fallback.

Reset and cleanup are optional; setup is required. Setup must release resources
it partially allocates if it fails or is cancelled before returning a handle.
After setup successfully returns (including a None handle), cleanup is attempted
once. Async runners await hooks; synchronous runners reject declared async hooks
before execution. Async cleanup is shielded/drained on caller cancellation;
without a process deadline a cancellation-resistant hook can delay shutdown.
Hooks must themselves coordinate shared external systems when cases overlap.
Fresh handles do not make a shared database automatically isolated.

Setup/reset/cleanup failures are explicit `EnvironmentLifecycleError` case errors
with the failing phase and original exception type/message. If execution and
cleanup both fail, the original execution error is preserved and cleanup failure
is retained as an evidence warning. A successful agent followed by failed cleanup
cannot pass. Handles and credentials are never serialized. Hook definitions are
application code: use explicit `agent_revision` and keep environment configuration
consistent when comparing evaluations.

## Evidence, versions and comparison

Runs using limits use **run schema 7**. Every case retains `execution_limits` as
`{max_turns, timeout_seconds, cleanup_timeout_seconds}` (or null for a case with
no policy), plus existing script, transcript, tool and state evidence. Schema 7
allows null `tool_fixtures` for ordinary agents. Repeated evaluations containing
these runs use **repeated-run schema 4** with the existing shared/factory/fixtures/
simulations modes. Existing runs without limits keep their prior versions;
suite formats, comparison formats and exit codes are unchanged.

Controlled fixtures publish snapshots on state/tool/turn/lifecycle progress.
A deadline retains the last received snapshot, marks the trace incomplete and
never invents events from arbitrary Python work. Plain callable activity remains
unknown. If startup expires before any snapshot, events/completeness are null,
initial state retains its declared value, and final state is unavailable (null,
with an explicit error message). Otherwise final state is the last observed
snapshot, not proof that a remote service stopped changing afterward.

Strict loading validates policies and turn caps, and rejects contradictory
completed transcripts. Repetition requires matching policies on every attempt.
Changed limits are incompatible in single/reliability comparisons, and intentional
baseline review requires the usual suite revision change. Comparison and review
never execute agents, verifiers or hooks. Regression drafts retain the complete
source run including policy; reusable suites retain their existing schemas, so
select the execution policy explicitly when running a saved regression suite.

## CLI and dashboard

```shell
thadam repeat examples/environment_cases.json \
  --fixture-factory examples.environment_agent:create \
  --environment examples.environment_agent:environment \
  --attempts 3 --max-turns 2 --case-timeout 10 --cleanup-timeout 1 \
  --report artifacts/environment-repeated.json

python -m examples.environment_agent --attempts 3 --timeout-seconds 10
```

The controlled example uses a real temporary SQLite file. Setup creates a dirty
row, reset clears it before each attempt, two turns use the same connection, and
cleanup closes/removes the database. No hosted service or model key is needed.

Both `run` and `repeat` support these options; `--environment` requires
`--fixture-factory` and names an exported `EnvironmentHooks` instance. Imports
remain explicit trusted application execution. The dashboard exposes the same
settings under execution settings in Run and Verify a fix, validates them before
starting a job, and displays saved policy beside case evidence. Use a matching
policy for the selected baseline. Saving agents retains its existing reference/
mode contract; boundary settings are chosen explicitly for each job.

## Validation

Controlled checks cover sync/async success, blocking calls, uncooperative
cancellation, hung verifiers/cleanup, process crashes, startup expiry, parent death,
turn caps, partial transcripts/state, reset failures, cleanup after failure,
repeated isolation, factory pickling, pre-execution configuration rejection,
report/repetition round trips, changed-policy comparison/review, regression drafts,
CLI imports and dashboard request guards. Live external-service resets remain
application-specific; the SQLite example establishes the local hook contract.
