# Milestone 1: local Python test runner

**Status:** planned; the commands and formats below are proposed, not implemented.

## User outcome

A developer connects a Python agent, runs five saved scenarios, and gets a readable result for each case plus a JSON report. The example works without a hosted account or model API key.

## Supported agent

Start with a synchronous Python callable that accepts one JSON value and returns one JSON-compatible value. A callable may wrap an existing agent. Milestone 1 evaluates its returned output; automatic framework or tool discovery follows later.

Keep the example small: a refund-policy agent backed by local fixtures. It should make policy mistakes observable without a model dependency. Include one intentionally buggy variant to demonstrate useful failures.

## Proposed suite format

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "eligible-refund",
      "input": {"order_id": "order-123", "days_since_purchase": 7},
      "assertions": [
        {
          "id": "refund-decision",
          "type": "output_equals",
          "expected": {"approved": true, "amount": 25}
        }
      ]
    }
  ]
}
```

Initial built-in assertions:

- `output_equals`: exact JSON equality, ignoring object key order. Compare JSON types strictly, so boolean `true` cannot satisfy numeric `1`; decide and document number semantics in implementation.
- `output_has_keys`: require specified top-level keys in an object output; report a failed assertion if the output is not an object.

The Python SDK also accepts an explicit verifier callable for domain rules. Define its typed input and assertion-result output as part of implementation. A verifier exception is an evaluation error, not a passed or failed expectation.

Reject unsupported schema versions, duplicate IDs, unknown assertion types, invalid parameters, empty suites, and cases with no check before invoking any agent. SDK-created cases undergo the same validation.

## Proposed interfaces

The CLI loads an agent explicitly from a Python module and callable name:

```shell
thadam run examples/refund_cases.json \
  --agent examples.refund_agent:run \
  --report artifacts/refund-report.json
```

The Python SDK should expose a small `run_suite` entry point using the same runner and returning a typed report. Keep file parsing and report writing explicit. Finalize parameter names in working code rather than publishing speculative callable examples here.

CLI exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Every case passed |
| `1` | Execution completed with one or more failed or errored cases |
| `2` | Invalid arguments, suite, agent reference, or report-write failure |

## Report requirements

Include schema version, run ID, stable case IDs, summary counts, per-case duration, actual output when available, and assertion evidence. Record error type, source, and message for agent or verifier exceptions. Terminal output should identify failed cases and explain which expectation was violated. A supported JSON report must remain parseable even when a case produces an error.

Do not imply the runner can reproduce a probabilistic agent exactly. Milestone 1 runs sequentially, without automatic retries, enforced execution timeouts, or concurrent state management. These behaviors need explicit contracts in later milestones.

## Implementation order

1. Define typed models and validation rules with meaningful contract tests.
2. Add built-in assertions and verifier handling.
3. Add the Python adapter and sequential runner.
4. Add reporting, SDK exports, and the CLI.
5. Add the example, five scenarios, and a documented end-to-end invocation.

Each step should have readable code and the checks needed to establish its behavior. Add new modules only as these steps need them.

## Acceptance criteria

- The five-case example runs through both the CLI and Python SDK.
- Passing, assertion failure, agent exception, and verifier exception paths are exercised explicitly.
- One case error does not prevent later cases from running.
- All input cases appear exactly once in a completed run report, with correct summary counts.
- Invalid suites are rejected before the first agent invocation.
- SDK and CLI agree about case results and statuses.
- JSON output can be parsed independently; exit codes match the documented result.
- Module-loading failures and report-writing failures produce useful messages.
- Core behavior tests run without network access or model credentials.
- README examples show implemented behavior and the roadmap reflects completed work.
