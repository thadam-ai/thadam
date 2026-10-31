# Repeated evaluation and reliability comparison

**Status:** implemented. The SDK, CLI, strict artifacts, examples, and CI gates
are available from this checkout; package publication remains a separate action.

## Agreed outcome

Evaluate a baseline and candidate repeatedly, retain every attempt, compare case
and individual-check pass rates, and use the comparison as a reviewable CI gate.
This is a complete local SDK/CLI workflow. Existing single-run APIs and schemas
remain supported unchanged.

## Execution contract

`run_repeated(agent, cases, attempts=10, agent_revision=None)` runs complete suites
sequentially in attempt order. Attempts must be an integer of at least two. Use
`agent_factory=` instead of `agent=` to construct a fresh synchronous agent for
each case invocation. Exactly one must be supplied. Shared callable mode retains
the same callable across all invocations. Factory creation/invocation errors are
recorded as agent errors and later cases/attempts continue. Invalid factory
signatures, suites, counts, and revisions are rejected before execution.

Snapshot all case contracts before execution. Each invocation and verifier gets
independent JSON snapshots through the existing runner. A factory does not reset
external services, module globals, verifier state, or shared resources and does
not imply sandboxing. No implicit retries, concurrency, timeouts, resource
cleanup protocol, or checkpoint resumption is introduced. KeyboardInterrupt
propagates and an interrupted evaluation does not write a completed report.

## Evidence and summaries

Repeated-run schema 1 has `kind: repeated_run`, an ID, an execution mode
(`shared` or `factory`), and an ordered array of full schema-3 run reports.
The array's one-based positions identify attempts; each run has a unique run ID.
All attempts have the same case/input/check contracts and application revision.
Reports include validated, recomputed per-case/per-check counts, pass rates,
outcome variability, and case runtime totals, minimum, maximum, mean, and median.

Every check's denominator is all attempts. A missing verdict due to a recorded
error is an error, never a pass or a dropped observation. Available independent
check verdicts remain visible even when another check errors. Case success
requires all checks and no errors. Variability means observed pass/fail/error
outcomes vary, including individual checks within always-failing cases; it does
not mean arbitrary output differences. Runtime includes evaluation, and factory
mode includes construction; runtime summaries are descriptive, not CI budgets.

Strict loaders reject unsupported versions, unknown fields, duplicate IDs/keys,
inconsistent summaries, altered contracts, invalid evidence, and missing attempts.
Loading/comparison never executes agent factories, agents, or custom verifiers.

## Comparison contract

`compare_repeated(baseline, candidate, max_pass_rate_drop=0.0)` requires equal
attempt counts, equal execution modes, and the existing strict input/check
compatibility rules, including matching explicit custom-verifier revisions.
Case/check ordering may differ. Added/missing/changed tests are incompatible;
intentional changes require review and a new explicitly selected baseline.

Compare every case's pass rate and every individual check's pass rate. Block if
any observed decrease is strictly greater than the allowed drop. Tolerance is a
finite fraction from 0 to 1 (0.05 means five percentage points), applied to each
case/check independently; equality is allowed. Any recorded error on either side
always blocks, regardless of tolerance. Existing failures and tolerated drops
remain visible. Improvement elsewhere cannot cancel a regression. Attempt
numbers identify evidence, not statistically paired trials.

Comparison schema 1 has `kind: reliability_comparison`, the explicit policy,
baseline/candidate IDs and revisions, compatibility issues, case/check counts,
rate differences, classifications, summary, and exit code. It embeds both full
repeated reports so all evidence remains available in a standalone artifact.
Rates are observed estimates, not statistical significance or causal claims.

## CLI and review workflow

```
thadam repeat cases.json --agent-factory my_agent:create --attempts 20 \
  --agent-revision baseline-sha --report baseline.json
thadam repeat cases.json --agent-factory my_agent:create --attempts 20 \
  --agent-revision candidate-sha --report candidate.json
thadam compare-repeated baseline.json candidate.json \
  --max-pass-rate-drop 0 --report comparison.json
```

`repeat`: 0 for every invocation passing; 1 for any failed/errored invocation;
2 for configuration or artifact failures. A run with failures still writes its
report. `compare-repeated`: 0 for compatible evidence within policy and no errors;
1 for a regression or error; 2 for incompatible/invalid evidence or write failure.
Both commands honor the existing color policy and atomic/path protection rules.
Terminal evidence identifies side, one-based attempt, run ID, case/check, errors,
and available event IDs. No report is styled with ANSI escapes.

Consumer examples must read the reviewed baseline from the PR target commit,
continue comparison after candidate exit 1, and never promote baselines
automatically. Users review generation settings, state/reset behavior, evidence,
and accepted failure rates before committing a baseline. Publishing the package
remains a separate release action.

## Acceptance criteria

- Demonstrate passing, failing, varying, and errored attempts without model keys.
- SDK/CLI agree, and both report kinds survive strict JSON round trips.
- Detect per-check drops even when all cases fail on both sides.
- Test tolerance boundaries, error precedence, altered contracts, mismatched
  attempts/modes, partial traces, and factory failures with continuation.
- Test invalid configuration before side effects, immutable snapshots, terminal
  control escaping/color, atomic writes, and source aliases.
- Provide runnable pytest and consumer CI examples with a reviewed fixture
  baseline, and verify the installed package outside the checkout.
