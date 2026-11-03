# Suite revisions and intentional baseline review

**Status:** implemented in the checkout. Package publication is a separate action.

## Outcome

A developer changes an expected policy, reviews every changed test and the new
execution evidence, then explicitly approves a matching baseline. A revision label
never overrides actual contract checks. Neither runs nor comparison gates approve
baselines automatically.

For example, changing refunds from 30 days to 14 days changes an expectation.
The old and new reports remain incompatible. Review the policy change, generate
usable evidence for the new policy, and approve that evidence as the next baseline
through your normal pull-request process.

## Identified suites

Existing schema-1 suites and schema-3 run reports retain their exact formats and
remain usable with one another. Schema-2 suites add required identity metadata:

```json
{
  "schema_version": 2,
  "suite": {"id": "refund-policy", "revision": "policy-14-days"},
  "cases": [
    {
      "id": "expired",
      "input": {"days": 20},
      "assertions": [
        {"id": "decision", "type": "output_equals", "expected": {"approved": false}}
      ]
    }
  ]
}
```

IDs and revisions are explicit non-empty strings, not inferred filenames, Git
commits, or automatic counters. Bump the revision when inputs, case/check sets,
expectations, assertion types, or verifier criteria change. Stable case/check IDs
identify the same scenarios and checks across revisions. Custom verifiers still
need their own explicit revisions whenever their behavior changes.

`load_suite` returns a tuple for schema 1 and a `TestSuite` sequence for schema 2.
Pass either directly to `run_suite` or `run_repeated`. Slicing a `TestSuite` returns
cases without identity; construct a new `TestSuite` when selecting a versioned
subset, with a revision appropriate to the changed contracts.

```python
from thadam import OutputEquals, SuiteIdentity, TestCase, TestSuite, run_suite

suite = TestSuite(
    SuiteIdentity("refund-policy", "policy-14-days"),
    (TestCase("expired", {"days": 20}, (OutputEquals("decision", {"approved": False}),)),),
)
report = run_suite(lambda value: {"approved": value["days"] <= 14}, suite)
```

SDK callers with an existing case sequence may supply `suite=SuiteIdentity(...)`
to either execution function. Conflicting embedded/explicit identities and invalid
metadata fail before user code. Every repeated attempt retains the same identity.

Identified runs use **run schema 4**, which adds `suite: {id, revision}` to schema
3. Single-run comparisons involving identified runs use **comparison schema 2**,
adding `baseline_suite` and `candidate_suite` (either may be null during migration).
Legacy-only comparisons remain schema 1 with their existing fields. Repeated-run
and reliability-comparison wrappers remain schema 1; their nested runs support
schemas 3 and 4. Earlier Thadam builds cannot read these new identified artifacts.

Comparisons require matching suite identities/revisions, or two unidentified
legacy suites, as well as the existing matching input/check contracts. Equal
labels cannot conceal changed expectations. Adding identity to a legacy workflow
requires review and a matching identified baseline.

## Review before approval

First generate candidate evidence using `run` or `repeat`, then review it:

```shell
thadam review-baseline candidate.json --baseline baselines/refund.json --report artifacts/review.json
thadam review-baseline artifacts/review.json --verbose
```

For the initial baseline, omit `--baseline`. Review reads saved evidence and never
imports or executes agents, factories, or verifiers. The saved artifact embeds both
complete evaluations, every repeated attempt, and all available trace evidence.
It is self-contained even if the original candidate is moved or changed.

Terminal output shows old and new suite revisions, application revisions,
execution settings, added/removed cases and checks, changed inputs, exact before
and after check definitions, both sides' per-check outcomes, failure/error evidence,
and blockers. `--verbose` expands every attempt, output, and available trace using
the existing terminal theme. Changed contracts do not produce a valid regression
gate; the review explains the intentional transition.

Review schema 1 has `kind: baseline_review`, `baseline` (null initially),
`candidate`, `changes`, `blockers`, `has_failures`, and `exit_code`. Change records
contain `scope`, `case_id`, `check_id`, `before`, and `after`. Strict loading
validates embedded evaluations and recomputes changes and decisions. Unknown or
contradictory fields, duplicate JSON keys, and invalid evidence are rejected.

Approval blockers are:

- Missing candidate suite ID/revision.
- Changed case/input/check contracts without a changed suite revision.
- Candidate execution/evaluation errors, including any repeated attempt.
- Candidate custom verifiers without explicit revisions.
- A different suite ID or switching single/repeated evaluation kind. Use a separate
  baseline for a different suite or evaluation workflow.

An old errored baseline may be replaced by usable evidence. Changing attempt counts
or shared/factory execution mode is shown explicitly as a settings change; after
approval, future comparisons require those matching settings. Revisions need not
be numbers or be ordered.

Review exit codes: **0** ready for human inspection (possibly with failed
expectations); **1** approval blockers; **2** invalid input or write failure.
`--report` is optional for inspection, but approval requires a saved review.

## Explicit approval

Copy the full SHA-256 displayed by review, then supply it with a reviewer, reason,
and destination:

```shell
thadam approve-baseline artifacts/review.json \
  --baseline baselines/refund.json \
  --review-digest COPY_THE_FULL_REVIEW_SHA256 \
  --reviewer YourName --reason 'Reviewed the 14-day refund policy'
```

The digest covers canonical JSON for the entire review, including outputs,
durations, IDs, trace evidence, and every attempt. It binds approval to the exact
inspected evidence; JSON whitespace/key ordering do not affect it. If the review
changes, inspect it and copy its new digest. The digest is not a signature and
does not establish reviewer identity or authorize a GitHub merge.

Failed expectations require `--accept-failures` after inspection. They remain
failed in the approved evidence and visible in future comparisons. There is no
flag accepting candidate errors. Reviewer and reason are explicit supplied
metadata. Approval neither executes code nor pushes files to GitHub.

The destination is an **approved-baseline schema 1** artifact with
`kind: approved_baseline`, the complete `review`, `review_digest`, `reviewer`,
`reason`, and `accepted_failures`. This makes evidence and acknowledgement one
atomic file write. `load_report`, `load_repeated`, and the existing comparison
commands validate this wrapper and use its candidate evaluation. Original raw
baseline reports remain supported. Later review embeds the previous evaluation,
not a recursive chain of approval wrappers; Git retains approval history.

Promotion safeguards:

- Initial approval requires a destination that does not exist.
- Replacement requires the destination to contain the exact old evaluation in the
  review, including its IDs, timings, and evidence. Missing or changed evidence
  requires a new review. Whitespace differences and approval metadata on the old
  wrapper do not change the underlying evaluation.
- Symlink destinations are refused. A per-destination exclusive lock coordinates
  concurrent Thadam approvals. Filesystem failures preserve the existing baseline.
- Ordinary report/review writers refuse to overwrite approved baselines, including
  through symlinks or hard links. CLI output paths are checked before importing an
  agent. Review output must differ from both source files; approval cannot overwrite
  its review file.

These are local workflow safeguards, not filesystem permissions or a transaction
with unrelated external file writers. Keep baselines in Git and review them through
protected pull requests. A crash can leave a `.thadam-approval.lock` file: confirm
no approval process is running before removing that lock manually.

Approval exit codes: **0** baseline written; **2** invalid, stale, blocked,
unacknowledged failures, or write failure. No PyPI release or automatic CI baseline
update is involved.

## SDK workflow

```python
from thadam import (
    approve_review,
    load_baseline_review,
    load_evaluation,
    review_baseline,
    write_approved_baseline,
    write_baseline_review,
)

review = review_baseline(
    load_evaluation("candidate.json"),
    load_evaluation("baselines/refund.json"),
)
write_baseline_review(review, "artifacts/review.json")
print(review.digest, review.blockers)

# After independently inspecting the review, copy its displayed digest here.
review = load_baseline_review("artifacts/review.json")
approval = approve_review(
    review,
    review_digest="COPY_THE_INSPECTED_SHA256",
    reviewer="YourName",
    reason="Reviewed policy change",
)
write_approved_baseline(approval, "baselines/refund.json")
```

SDK approval uses `accept_failures=True` for explicitly reviewed failures. Invalid
or stale evidence raises `ReportValidationError`; filesystem failures raise
`ReportWriteError`. Approval writes nothing until `write_approved_baseline` is
called. No public API discovers baselines or revisions automatically.

## Test in VS Code

Open **Terminal → New Terminal** at the repository root:

```shell
.venv/bin/python -m examples.baseline_review_demo
```

This controlled demo changes the refund policy from 30 to 14 days, creates both
single and repeated old/candidate reports and reviews under
`artifacts/baseline-review-demo`, and prints two complete approval commands with
their actual digests. It does not approve them. It needs no model API key. To run
it again without changing prior evidence, use `--output artifacts/review-demo-2`.

Inspect the saved review:

```shell
.venv/bin/python -m thadam review-baseline artifacts/baseline-review-demo/repeated-review.json --verbose
```

Before approval, this intentionally returns **2** because the policy changed:

```shell
.venv/bin/python -m thadam compare-repeated \
  artifacts/baseline-review-demo/repeated-baseline.json \
  artifacts/baseline-review-demo/repeated-candidate.json
```

Run the printed approval command after inspection, using `.venv/bin/python`
instead of `python` if the environment is not activated. Run the comparison again:
it now returns **0** against the approved 14-day baseline. Trying an old digest,
rerunning the same initial approval, or pointing an ordinary `run --report` at
that approved baseline must fail without replacing it.

Automated checks:

```shell
.venv/bin/python -m pytest -q tests/test_suite_revisions.py tests/test_baseline_review.py tests/test_baseline_cli.py tests/test_baseline_review_demo.py
.venv/bin/python -m pytest -q tests examples/regression_test.py
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Consumer CI should keep reading the baseline from its PR target commit, as in the
existing example. Intentional test revisions remain incompatible in that gate
until the reviewed baseline transition lands; this feature does not bypass the
branch's review policy or select an initial baseline from candidate code.
