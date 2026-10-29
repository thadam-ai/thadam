# Milestone 1: local Python test runner

**Status:** implemented. Commands below run from a repository checkout after editable installation. [Milestone 2](02-langgraph.md) adds optional LangGraph instrumentation. Enforced timeouts and hosted services remain future work.

## User outcome

A developer connects a Python agent, runs five saved scenarios, and gets a readable result for each case plus a JSON report. The example works without a hosted account or model API key.

## Supported agent

The agent is a synchronous Python callable accepting one positional JSON input and returning one JSON-compatible value. A callable may wrap an existing agent. Milestone 2 additionally accepts explicit `AgentResult` evidence and provides a LangGraph adapter; plain Python callables remain uninstrumented unless they supply events.

The example uses a local refund-policy function with order fixtures. `examples.refund_agent:run` passes all five cases; `run_buggy` yields three passes, one failed assertion, and one agent error. It demonstrates the runner without claiming to evaluate an actual LLM. CLI integration tests also load an independently defined user module from a temporary working directory.

## Suite format

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "eligible-refund",
      "input": {"order_id": "order-001", "days_since_purchase": 7},
      "assertions": [
        {
          "id": "refund-decision",
          "type": "output_equals",
          "expected": {"approved": true, "amount_cents": 2500, "reason": "eligible"}
        }
      ]
    }
  ]
}
```

Initial built-in assertions:

- `output_equals`: exact JSON equality, ignoring object key order and preserving array order. JSON numbers compare by numeric value, so `1` equals `1.0`; booleans remain distinct, so `true` does not equal `1`. Object outputs must have the same keys as the expected value.
- `output_has_keys`: require a non-empty `keys` array of unique strings naming top-level object keys. Additional output keys are allowed. A non-object output fails the assertion.

Inputs, expected values, and outputs use null, booleans, finite numbers, valid Unicode strings, arrays, and string-keyed objects. Python tuples, sets, non-finite numbers, cyclic containers, and containers nested beyond 100 levels are rejected. Very large integers must fit the interpreter's JSON serialization limits.

## Python SDK and verifiers

`load_suite(path)` reads and validates a suite. `run_suite(agent, cases)` also accepts a sequence of Python `TestCase` objects and returns a `RunReport`. `write_report(report, path)` writes JSON; `report_to_dict(report)` returns a JSON-compatible dictionary.

Verifiers are SDK-only callbacks; JSON suites do not execute verifier code. Each callback accepts input and output snapshots and returns `CheckResult(passed, message, expected, actual)`. The runner attaches the stable ID from `Verifier`. A raised exception, wrong return type, non-boolean decision, empty message, or invalid evidence produces a verifier error. A case may have assertions, verifiers, or both, but must have at least one check.

```python
from thadam import CheckResult, OutputHasKeys, TestCase, Verifier, run_suite


def respects_limit(case_input, output):
    amount = output["amount_cents"]
    limit = case_input["limit_cents"]
    return CheckResult(
        passed=amount <= limit,
        message="Refund must stay within the approved limit",
        expected={"maximum_cents": limit},
        actual=amount,
    )


case = TestCase(
    id="refund-limit",
    input={"limit_cents": 2500},
    assertions=(OutputHasKeys("fields", ("amount_cents",)),),
    verifiers=(Verifier("within-limit", respects_limit),),
)
report = run_suite(agent=lambda _: {"amount_cents": 3000}, cases=[case])
assert report.cases[0].status == "failed"
```

Unsupported schema versions, duplicate IDs, duplicate JSON object keys, unknown fields, unknown assertion types, invalid parameters, empty suites, and cases with no check are rejected before invoking any agent. Case IDs must be unique across the suite; assertion/verifier IDs must be unique within each case. SDK-created cases undergo the same validation.

## CLI

The CLI loads an agent explicitly from a Python module and callable name:

```shell
thadam run examples/refund_cases.json \
  --agent examples.refund_agent:run \
  --report artifacts/refund-report.json
```

The suite is validated before the agent module is imported. Agent imports and execution are trusted Python code; their standard output is redirected to standard error to keep the CLI summary readable. `--report` is optional, creates missing parent directories, and writes the artifact atomically. It cannot target the suite file. An existing report is replaced only after a new report is successfully written.

`--color auto|always|never` controls terminal styling and can appear before or after `run`. Auto mode detects TTYs, respects a non-empty `NO_COLOR` and `TERM=dumb`, and leaves redirected output plain. Explicit modes override that detection. The summary includes a compact heading, suite/agent context, case statuses, durations, and wrapped failure evidence. Teal indicates passes, amber failed expectations, and red errors. JSON artifacts and exit codes use the same contracts in every color mode.

CLI exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Every case passed |
| `1` | Execution completed with one or more failed or errored cases |
| `2` | Invalid arguments, suite, agent reference, or report-write failure |

## Report requirements

Current reports use schema version 2 and contain `schema_version`, `run_id`, `summary`, and an ordered `cases` array. Summary fields are `total`, `passed`, `failed`, and `errors`. Cases contain `id`, `status`, `duration_ms`, `input`, `output`, `output_available`, `assertions`, `errors`, `events`, `trace_complete`, and `trace_warnings`. Plain Python runs have null events/completeness and an empty warning list. Input is the original case snapshot, even if the agent mutates its argument. A returned JSON null has `output_available: true`; an agent error has `output_available: false`.

Assertions contain `id`, `passed`, `message`, `expected`, `actual`, and `event_ids`. Output checks and SDK verifiers have empty event links. Errors contain `source` (`agent`, `output`, `verifier`, `assertion`, or `trace`), `type`, `message`, and an optional `assertion_id`. Invalid output becomes an `output` error and is omitted from JSON evidence; valid trace events are retained. Errors take precedence over failed expectations. Later cases continue. `KeyboardInterrupt` propagates; `SystemExit`, including exit code zero, from tested code becomes a case error. An agent import that raises `SystemExit` is a configuration error. See milestone 2 for event validation and trace availability semantics.

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
