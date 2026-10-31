# Milestone 3: compare saved agent runs

**Status:** implemented in Thadam 0.3.0. This document specifies single-run comparison. [Repeated evaluation and reliability comparison](03-reliability.md) are also implemented with separate artifact kinds and commands; a pytest plugin and async execution remain planned.

## Outcome

A developer explicitly selects a reviewed baseline, runs the candidate against the same cases, and compares the saved reports through the SDK or CLI:

```shell
thadam compare baseline.json candidate.json --report comparison.json
```

Comparison reads evidence and applies deterministic rules. It neither executes agents nor imports their modules. A difference between two model runs is an observed regression, not proof that a code change caused it. Repeated-run statistics are outside this build.

## Report version 3

Input suites remain schema 1. Run reports become schema 3, adding:

- `evaluation_version: 1`: the built-in evaluation semantics understood by this comparator.
- `agent_revision`: optional, explicitly supplied application revision metadata; never discovered through Git or environment variables implicitly.
- `cases[].check_definitions`: ordered records with `id`, `type`, and `parameters`, captured before execution, including on errored cases.

Built-in parameters contain their declared expected JSON, required keys, or tool name and arguments. SDK `Verifier` gains an optional `revision` string. Its definition records that revision; comparison requires it to be non-empty and equal on both sides. The developer must change it when verifier behavior or external criteria change. Function names, source inspection, and returned explanations cannot establish equivalent verifier behavior.

Schema-1/2 reports lack sufficient contract data and are rejected with instructions to generate a fresh baseline and candidate. Existing run exit codes and suite files retain their meaning. This is an explicit report-format change in Thadam 0.3.0.

## Validation and compatibility

`load_report(path)` returns a validated `RunReport`. Reject unknown fields/versions, duplicate JSON keys or IDs, invalid JSON values/timings/flags, inconsistent counts or statuses, orphaned event links, and missing or contradictory check outcomes. Validate instrumented evidence with the existing trace contract. Built-in outcomes must agree with their recorded definitions, output, and events; verifier decisions remain supplied evidence.

`compare_reports(baseline, candidate)` validates SDK reports through the same boundary and returns independent snapshots. Match cases and checks by ID, preserving baseline order and appending candidate-only cases. Reordering cases/checks or object keys does not change their identity. JSON values follow the engine's number/boolean semantics; required output-key sets ignore ordering.

Different case sets, inputs, check sets, assertion types/parameters, evaluator versions, or absent/changed verifier revisions produce explicit incompatibilities. No missing check is counted as a pass. There is no automatic baseline update or expectation override.

## Classification and exit codes

Compare each check, not only case totals: a new failing check inside an already-failing case is still a regression.

| Baseline check → candidate check | Classification |
| --- | --- |
| Pass → fail | `regression` |
| Fail → pass | `fixed` |
| Fail → fail | `existing_failure` |
| Pass → pass | `unchanged_pass` |
| Missing verdict because of a recorded error | `error` |

Case classification precedence is `incompatible`, `error`, `regression`, `existing_failure`, `fixed`, `unchanged_pass`. A case with errors on either side remains an `error`, even if the candidate recovers; replace an errored baseline with reviewed usable evidence. Existing assertion failures may be accepted only by explicitly selecting that reviewed baseline. They remain visible. Case summary counts are mutually exclusive; check changes remain individually visible.

| Compare exit code | Meaning |
| --- | --- |
| `0` | Compatible reports, no new failing checks, and no errors on either side |
| `1` | A regression or recorded execution/evaluation error |
| `2` | Invalid reports, incompatible tests, or comparison artifact write failure |

Comparison JSON has its own schema 1 and `kind: "comparison"`, baseline/candidate run IDs and revision metadata, case and check changes with both assertion verdicts/evidence/event links, original case errors, compatibility messages, summary counts, and the exit code. Original run reports retain full traces. Terminal output uses the existing color policy, meaningful labels, escaped control characters, wrapped details, and no ANSI styling in JSON. Output must not replace either input report, including through symlinks/hard links. Writes are atomic.

## Consumer integration

The [pytest example](../../examples/regression_test.py) is a normal test using the SDK, not a plugin. Run it with `python -m pytest -q examples/regression_test.py`.

The [GitHub Actions example](../examples/agent-regression.yml) now uses repeated reliability evaluation: it installs the application, runs a candidate five times, and compares against a committed repeated baseline. For a single-run gate, substitute `run`/`compare` and the single-run baseline. Commit and review the initial baseline on the target branch before enabling this workflow. On pull requests a second checkout reads that target commit's baseline independently of candidate changes. Candidate run exit 1 still permits comparison, so existing acknowledged assertion failures can be distinguished from regressions; configuration errors stop immediately. The comparison result decides the final job status.

Adapt the installation command, suite path, agent reference, and baseline path for your application. Intentional test/expectation changes fail this strict gate until a maintainer explicitly reviews and promotes a matching baseline. Automated baseline promotion is outside this build. Do not enable `pull_request_target` to run untrusted candidate code or give test jobs production credentials. The example does not upload potentially sensitive execution artifacts.

## Implementation boundaries

- `models.py`: stored check definitions and run report metadata.
- `contracts.py`: snapshot and validate declared check definitions.
- `report_loading.py`: strict run-report parsing and evidence consistency.
- `comparison.py`: typed comparison results and pure classification.
- `comparison_reporting.py`: comparison JSON and terminal output.
- `reporting.py`: run serialization and shared atomic artifact writing.
- `cli.py`: argument translation, file loading, presentation, and exit codes.

Keep the core free of runtime dependencies. Export the useful SDK contracts from `thadam`; optional LangGraph imports stay explicit.

## Acceptance checks

- Compare SDK-generated and reloaded reports with identical outcomes, regressions, fixes, existing failures, and errors.
- Detect newly failing assertions when both case statuses are already failed.
- Refuse changed expectations, inputs, test sets, evaluator versions, and unversioned/changed custom verifiers.
- Exercise malformed/forged report boundaries and partial/unknown tracing without accepting missing evidence.
- Preserve all results, stable IDs, evidence links, and snapshots through JSON round trips.
- Match CLI exit codes and JSON with SDK results, including color policy and protected/atomic output paths.
- Run real compiled LangGraph reports through comparison using controlled local models/tools.
- Provide an executable pytest example and a GitHub Actions example using a reviewed baseline, explicit application revision, and a candidate run; baseline files are never silently regenerated.
