# Terminal report layout

**Status:** implemented for all four commands. Values and timings below are
illustrative. Existing semantic colors apply: teal for brand/success, blue for
context, amber for unmet expectations, red for errors, and muted metadata.

## Shared structure

1. One Thadam heading and command title.
2. Overall result and counts before the case rows.
3. Compact suite/agent or baseline/candidate context.
4. Aligned case rows on wide terminals; stacked rows on narrow terminals.
5. Failure, error, and compatibility details with explicit labels.
6. Artifact location and, when relevant, a hint for verbose evidence.

Use lightweight rules and spacing. Preserve readable labels without color.
Do not print a new Thadam header for every attempt. Formatting uses the existing
color policy, terminal width, and control-character escaping.

## Run

```text
  THADAM  Agent evaluation
  ------------------------------------------------------------------------
  FAILED   3 passed / 1 failed / 1 error

  Suite    examples/refund_cases.json
  Agent    examples.refund_agent:run_buggy

  CASE                       RESULT       DURATION
  eligible-refund            PASSED        0.12 ms
  expired-refund             FAILED        0.08 ms
  refund-window-boundary     PASSED        0.09 ms
  second-order-refund        ERROR         0.04 ms
  unknown-order              PASSED        0.10 ms

  FAILURES
  expired-refund / reject-expired
    Expected  {"approved": false, "amount_cents": 0,
               "reason": "outside_refund_window"}
    Actual    {"approved": true, "amount_cents": 2500,
               "reason": "eligible"}

  ERRORS
  second-order-refund
    Source    agent
    Error     TimeoutError: Order service did not respond

  Report    artifacts/run.json
```

## Single-run comparison

```text
  THADAM  Regression comparison
  ------------------------------------------------------------------------
  BLOCKED   1 regression / 1 error / 3 unchanged

  Baseline   reviewed-baseline
  Candidate  candidate-revision

  CASE                       BASELINE    CANDIDATE   CHANGE
  eligible-refund            PASSED      PASSED      UNCHANGED
  expired-refund             PASSED      FAILED      REGRESSION
  refund-window-boundary     PASSED      PASSED      UNCHANGED
  second-order-refund        PASSED      ERROR       ERROR
  unknown-order              PASSED      PASSED      UNCHANGED

  REGRESSIONS
  expired-refund / reject-expired
    Baseline   passed
    Candidate  failed
    Expected   {"approved": false, "amount_cents": 0,
                "reason": "outside_refund_window"}
    Actual     {"approved": true, "amount_cents": 2500,
                "reason": "eligible"}

  ERRORS
  second-order-refund / candidate
    Error      TimeoutError: Order service did not respond

  Report     artifacts/comparison.json
```

Missing/changed contracts get an INCOMPATIBLE result and actionable reasons.
Existing failures, improvements, tolerated drops, and errors retain meaningful
labels even when other changes determine the overall exit code.

## Repeated evaluation

```text
  THADAM  Repeated evaluation
  ------------------------------------------------------------------------
  FAILED   15 passed / 5 failed / 5 errors

  Attempts  5 per case / 25 invocations / shared agent

  CASE                       PASSED   FAILED   ERRORS   MEDIAN
  eligible-refund               5/5        0        0   0.12 ms
  expired-refund                0/5        5        0   0.08 ms
  refund-window-boundary        5/5        0        0   0.09 ms
  second-order-refund           0/5        0        5   0.04 ms
  unknown-order                 5/5        0        0   0.10 ms

  FAILURES
  expired-refund / reject-expired
    Attempts  1-5 / 5 occurrences
    Expected  {"approved": false, "amount_cents": 0,
               "reason": "outside_refund_window"}
    Actual    {"approved": true, "amount_cents": 2500,
               "reason": "eligible"}

  ERRORS
  second-order-refund
    Attempts  1-5 / 5 occurrences
    Error     TimeoutError: Order service did not respond

  Details   Use --verbose for all attempt and trace evidence.
  Report    artifacts/repeated.json
```

Show variability explicitly for cases whose case/check outcomes change, including
cases that always fail but have individual checks that vary. Keep failed and
errored attempts in the denominator. Default runtime emphasis is median per
case; all existing runtime statistics remain available in verbose output and JSON.

## Repeated comparison

```text
  THADAM  Reliability comparison
  ------------------------------------------------------------------------
  BLOCKED   1 regression / 0 errors

  Baseline   scripted-baseline / 10 attempts / shared agent
  Candidate  scripted-candidate / 10 attempts / shared agent
  Policy     Allow a drop of up to 0 percentage points per case/check

  CASE                  BASELINE       CANDIDATE      CHANGE
  refund-decision       8/10 (80.0%)    6/10 (60.0%)    -20.0 pp

  REGRESSIONS
  refund-decision / approved
    Pass rate   80.0% -> 60.0% / -20.0 percentage points
    Baseline    failed on attempts 5, 10
    Candidate   failed on attempts 4, 5, 9, 10
    Expected    true
    Actual      false

  Observed rates describe these attempts; they do not establish causation.
  Details     Use --verbose for all attempt and trace evidence.
  Report      artifacts/reliability-comparison.json
```

Any case or individual-check drop still appears even when improvements elsewhere
or error precedence affect the case classification. Accepted existing failures
and tolerated drops stay visible. Passing gates use PASSED; incompatible reports
use INCOMPATIBLE; a completed run with failed/errored cases uses FAILED.

## Narrow terminals

Switch to stacked rows when full columns cannot fit, rather than truncating IDs
or hiding results. Wrap long names, paths, expectations, and actual values.

```text
  THADAM  Reliability comparison
  ------------------------------------
  BLOCKED
  1 regression / 0 errors

  refund-decision
    Baseline   8/10 / 80.0%
    Candidate  6/10 / 60.0%
    Change     -20.0 pp
```

## Grouping and verbose evidence

Grouping key: same side, case ID, check ID, failure type,
expected/actual evidence, and error source/type/message. Attempt/run/event IDs
and timing are occurrence metadata and do not split identical failure groups.
For cases with traces, show a clearly labeled representative attempt's trace
and event IDs; verbose output shows each occurrence's complete available trace.
Different expectations, actual values, or error messages remain distinct groups.
Do not merge evidence across baseline and candidate sides.

`--verbose` is available on all four commands. For single runs it expands passing
checks and available traces; for comparisons it expands unchanged checks too.
For repeated reports it expands every attempt with a single shared top-level
heading, one-based attempt labels, original run IDs, and all available evidence.
It does not rerun agents or change artifact contents or exit codes.

## Try it in VS Code

Open Terminal → New Terminal in the repository root. These fixtures use no
model API key. Color is automatic; no explicit color flag is needed.

Run a passing suite (exit 0):

```shell
.venv/bin/python -m thadam run examples/refund_cases.json --agent examples.refund_agent:run
```

Save an intentionally buggy run (exit 1, with 3 passed, 1 failed, 1 error), then
compare it with the reviewed example baseline (comparison also exits 1):

```shell
.venv/bin/python -m thadam run examples/refund_cases.json --agent examples.refund_agent:run_buggy --report artifacts/layout-run.json
.venv/bin/python -m thadam compare examples/baselines/refund-report.json artifacts/layout-run.json
```

See grouped repeated failures and errors (15 passed, 5 failed, 5 errors; exit 1):

```shell
.venv/bin/python -m thadam repeat examples/refund_cases.json --agent examples.refund_agent:run_buggy --attempts 5 --report artifacts/layout-repeated.json
```

Compare repeated evaluations, then expand the same saved evidence without
executing the agent again (both exit 1):

```shell
.venv/bin/python -m thadam compare-repeated examples/baselines/refund-repeated.json artifacts/layout-repeated.json
.venv/bin/python -m thadam compare-repeated examples/baselines/refund-repeated.json artifacts/layout-repeated.json --verbose
```

Drag the terminal pane narrower, or force 40 columns for a stacked preview:

```shell
COLUMNS=40 .venv/bin/python -m thadam compare-repeated examples/baselines/refund-repeated.json artifacts/layout-repeated.json
```

Add `--color never` to inspect plain output, or `--color always` to force the
existing palette. Add `--verbose` to any of the four commands. With run/repeat,
that is a new execution; with comparison commands it only expands saved evidence.
Run these examples as separate commands: an intentional exit 1 still writes its
report and should not prevent inspecting it afterward.

Automated checks:

```shell
.venv/bin/python -m pytest -q tests/test_report_layout.py
.venv/bin/python -m pytest -q tests examples/regression_test.py
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```
