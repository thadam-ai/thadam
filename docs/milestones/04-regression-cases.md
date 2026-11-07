# Create regression cases from saved results

**Status:** the first workflow of milestone 4.5 is implemented in the checkout.
Review labels/imports and guided before/after verification remain planned.

Open a saved single run, or choose an individual attempt in a repeated run. Expand
its case and select **Create regression case**. Thadam saves a new draft under
`regression-drafts/` and opens it in the same inspector. Passing and errored cases
can also become regression cases. Comparison and baseline artifacts do not offer
this action; open the original run instead.

The draft starts with the original input, a proposed case ID, and an empty
assertions array. Open **Original failure evidence** to inspect the source output,
checks, errors, and available tool/model events. Supply the intended input and
supported assertions in **Regression case JSON**. The example beside the editor
shows the assertion shape, not an inferred correct answer.

Select the input/expectation review checkbox and **Save reviewed case**. You may
also save incomplete work through **Save draft edits**. Editing a case clears the
local review acknowledgement; unreviewed or unsaved cases cannot preview a suite.
SDK-only Python verifiers must be attached by application code; this form accepts
the existing JSON assertion types and never imports verifier code.

Choose a new suite destination, ID, and revision, or select an existing suite to
append to. Identified suites keep their ID and require a new revision. Legacy
suites keep their format. Duplicate case IDs and invalid checks are rejected.
Select **Preview suite changes**, inspect the entire resulting suite, acknowledge
the preview/destination, and select **Save reviewed suite**. A changed draft or
existing destination requires reloading; new destinations never overwrite files.
The saved suite uses the existing suite format and can run through the CLI/SDK.

For a source case from a controlled fixture evaluation, the preview and saved
suite retain the source case's complete tool scripts, including unused responses
and explicit repetition. New destinations use identified fixture suite schema 3.
Existing destinations must already be fixture suites; enable tool fixtures in the
suite editor first when needed. An ordinary regression case appended to a fixture
suite starts with an explicit empty script object. Inspect these scripts in the
suite preview, then configure any additional responses in the saved suite editor.
Run fixture suites through an explicit tool fixture factory as described in the
[tool-failure guide](05-tool-failures.md). Saving still executes no agents or tools.

For a source case from a schema-6 conversation/state simulation, the draft also
retains its ordered conversation, initial state, and tool scripts. New destinations
use identified suite schema 4, and simulation cases can only be appended to schema-4
suites. Plain or fixture-only cases appended to schema 4 receive empty conversation
and null state fields. Review the complete setup in the preview before publishing.

## Draft evidence and boundaries

`kind: "regression_draft"`, `schema_version: 1` has these fields:

- `id`: independent draft identifier.
- `source`: source artifact path and exact-byte fingerprint, case ID, optional
  one-based attempt number, and a complete validated snapshot of the selected run.
- `case`: editable ID, JSON input, and supported assertions.
- `reviewed`: explicit acknowledgement of the current case's input/expectations.

`thadam.regression.regression_draft` and `validate_regression_draft` create and
validate independent snapshots without executing application code. Draft review
stores the latest case and acknowledgement, not an authenticated reviewer identity
or a complete review history. Source evidence and suite/report schemas stay intact.

The source fingerprint is checked when creating the draft. Later source changes
or deletion do not invalidate the retained snapshot. Keep the draft alongside the
saved suite to preserve provenance; the suite itself does not embed the snapshot.
Drafts contain original input/output and may include sensitive evidence from other
cases in the selected run. Automatic masking is not implemented in this first
workflow; review the draft before sharing it.

Creating/reviewing a draft and saving a suite make no provider requests, run no
agents or verifiers, and never approve baselines. A saved suite is a future test;
its expected behavior is not evidence that the original run satisfied that check.
