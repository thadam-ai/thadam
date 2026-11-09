# Create regression cases from saved results

**Status:** workflows 1–3, including saved-result review labels, are
implemented in the checkout.

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

`kind: "regression_draft"` schema 1 records source runs. Schema 2 records
imported examples. Both use these top-level fields:

- `id`: independent draft identifier.
- `source`: schema 1 records the source run path/fingerprint, case ID, optional
  attempt, and full validated run snapshot. Schema 2 records the examples file
  path/fingerprint, format, row, source ID, mapping, applied masks, duplicate
  decision, and masked mapped fields.
- `case`: editable ID, JSON input, and supported assertions.
- `reviewed`: explicit acknowledgement of the current case's input/expectations.

`thadam.regression.regression_draft` and `validate_regression_draft` create and
validate independent snapshots without executing application code. Draft review
stores the latest case and acknowledgement, not an authenticated reviewer identity
or a complete review history. Source evidence and suite/report schemas stay intact.

The source fingerprint is checked when creating or importing the draft. Later
source changes or deletion do not invalidate the retained snapshot. Keep the
draft alongside the saved suite to preserve provenance; the suite itself does
not embed the snapshot. Saved-run drafts may include sensitive evidence from
other cases in the selected run. Imported records retain only mapped fields and
apply the selected masks; masking is not automatic and does not find unselected
sensitive data. Review all retained evidence before sharing it.

Creating/reviewing a draft and saving a suite make no provider requests, run no
agents or verifiers, and never approve baselines. A saved suite is a future test;
its expected behavior is not evidence that the original run satisfied that check.

## Review labels on saved results

Open a single or repeated run and expand **Review labels**. Each single-run case,
or each case in each repeated attempt, can receive a **good**, **bad**, or
**needs review** verdict, notes, and comma-separated failure tags. Save the labels
to a separate `kind: "result_reviews"`, schema-1 artifact under
`review-labels/`. The artifact links the source path, source ID, and exact-byte
fingerprint. Each review identifies a case and optional one-based attempt, then
stores its verdict, notes, and tags. Editing labels never rewrites a run, changes
a check result, or changes a comparison/reliability gate.

Repeated attempts are labeled independently. Dashboard search matches case IDs
and failure tags; the review filter finds unlabeled results and results with a
selected verdict. The artifact is local review evidence, not an authenticated
reviewer identity or proof that the label is correct. If the source file changes,
reload before saving labels against the new result.

## Import recorded examples

Open **Suites → Import examples** and choose a project-relative `.jsonl` or
`.csv` file. Imports are local and read-only until you select rows and import
them. Preview validates each row, identifies duplicates by source ID or exact
mapped input, and lets you acknowledge duplicates before selecting them. The
import is limited to 8 MiB and 500 rows per preview.

JSONL contains one JSON object per non-empty line. Map each logical field to a
source path; JSONL paths use dot notation and numeric list indexes. CSV mapping
uses exact header names, and CSV cells stay strings. The `input` mapping is
required. `source_id`, `actual`, `expected`, `context`, `events`, and `tags` are
optional. A missing source ID gets a row-based fallback; missing mapped
optional values stay absent. Tags may be a comma-separated string or an array
of strings. See [`examples/recorded_examples.jsonl`](../../examples/recorded_examples.jsonl)
for an example file.

The preview contains only mapped fields. Add comma-separated masks using paths
in that mapped projection, such as `input.customer.email` or `context.*`.
Masks are applied before values reach the browser and before drafts are saved.
Source IDs stay visible so imported evidence can be identified. Redaction only
covers selected paths; it does not discover sensitive values, mask source IDs,
or alter the original file. A mask that does not match a present mapped field
makes that row invalid, so fix the mapping or mask and preview it again. Review
the preview and select only examples that are appropriate to retain.

Each selected row becomes an independent schema-2 `regression_draft` under
`regression-drafts/`. The artifact retains the source path, exact-byte
fingerprint, row, source ID, mapping, duplicate decision, and masked mapped
record. If an expected field is mapped, it seeds a proposed output-equality
assertion; that answer is untrusted evidence and the draft remains unreviewed.
Without a mapped expected value, the draft has no checks and cannot be reviewed
or published until a developer supplies one. Import never runs an agent or
verifier. Re-importing the same file, mapping, masks, and row is detected and
cannot overwrite the existing draft.

The Suites search includes draft case IDs, source IDs, and failure tags. The
review filter can show unreviewed or reviewed drafts. Search is local to the
saved artifact catalog; imported records are not sent to providers.

## Verify a fix

After saving a reviewed regression suite, open **Suites → Verify fix**. Choose
the saved suite and enter a candidate `module:callable`; the candidate is
imported only when the run starts. The workflow uses the existing dashboard job
runner, progress, stop behavior, and report writing. Async execution, attempts,
fixture mode, and application revision are available under run settings.

Optionally choose a single baseline report for a single candidate run, or a
repeated report with the same attempt count and execution mode for repeated
verification. When the candidate finishes, Thadam saves a separate comparison
and opens its existing per-case and per-check before/after view. A changed suite
contract or otherwise incompatible report remains visible as incompatible; run
the intended baseline implementation against the exact reviewed suite to create
fresh comparable evidence. A baseline is optional; without one, the saved
candidate report shows the current check outcomes but no before/after decision.

Suite, candidate report, and comparison JSON can be downloaded from their saved
artifact views for the existing CLI/pytest/CI workflow. Comparison does not run
agents or verifiers, and approval of a baseline remains a separate explicit
action. Repeated comparisons apply the existing per-case/check pass-rate drop
policy, defaulting to zero unless you choose another tolerance.
Keep async and concurrency settings consistent across baseline and candidate
runs; those scheduling settings are not recorded in reports.
