# Local testing dashboard

**Status:** implemented in the checkout. Publishing remains a separate release action.

The dashboard opens one project folder in your browser. It uses the existing Python
SDK to edit saved suites, run evaluations, inspect evidence, compare results, and
explicitly review and approve baselines. The CLI remains available for scripting
and CI. The interface is React/TypeScript, bundled with the Python package.
End users do not need Node.js, a hosted account, or a model provider to view reports.

See the [visual dashboard tour](dashboard-tour.md) for failure inspection, suite
editing, regression comparison, and scenario review in both themes.

## Launch from VS Code

Open **Terminal → New Terminal** in this repository:

```shell
.venv/bin/python -m pip install -e '.[dev,dashboard]'
.venv/bin/python -m examples.dashboard_demo
.venv/bin/python -m thadam dashboard artifacts/dashboard-demo
```

The controlled demo needs no model API key. It contains saved suites, passing and
failing single/repeated runs, both comparison kinds, instrumented tool evidence,
a review, and a clearly labeled illustrative approved baseline. It creates a
workspace only in an empty folder; use `--output artifacts/dashboard-demo-2` to
preserve an existing demo.

The command opens the browser and prints a local session link. Keep that terminal
open. **Ctrl+C** closes the server and interrupts an active evaluation. To use your
own project, pass its directory instead:

```shell
thadam dashboard /path/to/your/project
thadam dashboard . --port 8766 --no-browser
```

The dashboard was added after the published `thadam-ai` v0.3.0 release; install it
from this checkout with `'.[dashboard]'`. A future release containing the dashboard
will expose `thadam-ai[dashboard]`. Add `[langgraph]` separately when your agent uses
that optional adapter. Agents
use the same Python environment as the server; install application dependencies
there. Only the selected project is the worker's working directory.

## Workspace layout

The icon rail switches between Overview, Suites, Evaluations, Comparisons and
Baselines; hover or focus an icon to see its label. The file list and selected
report/editor stay side by side on desktop and scroll independently. Search and
result filters stay with the list. Use **Hide file list** for a wider inspector.
On narrow screens, select a file to open its detail, then **Back to files** to
return. The rail stays available. File modification dates appear in the inspector
footer; these are filesystem dates, not execution timestamps.

**Run evaluation** opens configuration in the inspector. **Compare** in the
Comparisons library and **Review** in Baselines open the corresponding forms.
Opening any of these forms never runs an agent or writes evidence. Saving a suite
refreshes its displayed evidence and stale-write fingerprint; navigation protects
unsaved changes.

## Navigation

- **Overview:** saved evaluation files, aggregate invocation counts, recent saved
  artifacts, search and result filters. Counts describe these files, not unique
  production sessions or historical trends. Filenames lead the evidence list, with suite/revision or artifact kind as
  secondary context. The selected detail retains its full project-relative path. Dates are filesystem modification times.
- **Suites:** discover schema-1/2 suites; create or edit cases, JSON inputs, expected
  outputs, required output keys, and required/forbidden/tool-argument assertions.
  Select a case from the case list to edit it; unfinished JSON remains intact when
  selecting another case, and invalid fields keep Save blocked. Fix invalid fields
  before switching to full JSON view. Expand **Suite settings** for file location,
  identity and revision. Change an identified suite's revision when its
  cases, inputs or checks change. Save validates the complete suite. Stale edits
  are refused; choose a new file path for Save as. Unsaved changes are guarded
  when navigating away or closing the browser.
- **Evaluations:** configure a named `module:callable` agent without importing it;
  choose a suite, shared or factory mode, attempts, explicit application revision,
  and a new report path. Execution mode, application revision, report destination
  and saved-agent naming are under **Execution & save settings**. **Run evaluation** is the only action that imports or
  executes application code. One attempt with a shared callable is a single run;
  two or more attempts produce a repeated evaluation. Factory mode requires at
  least two attempts, matching the repeated-run SDK/CLI workflow. Use **Review
  labels** on a saved result to add per-case (and per-attempt) good, bad, or
  needs-review verdicts, notes, and failure tags. The dashboard stores these in
  a separate `review-labels/` artifact and leaves run evidence unchanged.
- **Comparisons:** choose baseline and candidate evidence and save a single-run
  regression or repeated reliability comparison. Equal attempts, lifecycle modes,
  suite labels and actual contracts still apply. A drop tolerance of `0.05` means
  five percentage points per case/check. Errors always block. Comparison never
  imports agents or verifiers.
- **Baselines:** save a full-evidence review, inspect exact contract changes and
  both evaluations, and explicitly approve the reviewed candidate. Provide a
  reviewer, reason, destination, and acknowledgement of inspected evidence.
  Failed expectations require their own checkbox; candidate errors cannot be
  accepted. The browser submits the exact displayed review digest; the SDK
  revalidates it and rejects stale reviews or baseline destinations.

For the demo, configure `agent:run` in shared mode, `agent:run_buggy` to see failed
expectations, or `agent:create` in factory mode. Save an agent name to reuse it.
Python agent implementations and custom verifier code stay in your editor;
reports containing SDK verifier outcomes remain fully inspectable.

For controlled failures, use **Configure tool failures** in a case editor. Add
named scripts with JSON returns or simulated errors, optionally repeat the final
response, and add `tool_call_count` checks for inclusive attempt bounds or
`tool_call_sequence` checks for exact tool start order. Scripts
are saved case contracts and require a suite revision change when edited.
Choose **Tool fixture factory** in execution settings and supply a factory that
accepts `FixtureTools`; one attempt is supported. Scripts reset per invocation,
including repeated/async runs. Results include **Configured tool fixtures** and
the observed calls. See [the integration and controlled demo](milestones/05-tool-failures.md).
Call bounds and scripted timeout errors do not impose execution deadlines.

## Evidence and job lifecycle

Opening an artifact is read-only. Supported files are suites, schema-3/4 runs,
comparison schemas 1/2, repeated/reliability schema-1 reports, baseline reviews,
and approved baselines. The existing strict SDK loaders validate recorded evidence.
Single comparisons validate their stored check decisions and summaries; their
source runs are required to independently establish original contract compatibility.

Large integer IDs retain their exact JSON digits through viewing, editing and
download; they are not rounded to browser floating-point values.

Evaluation details lead with a readable outcome and counts. Run metadata expands
under **Run details**. Cases are presented with errors/failures first; the first
problem and its unsuccessful checks open immediately. **Invocation input and output**
expands separately. Comparisons summarize regressed cases and cases with errors,
including a newly failing check inside an already-errored case; the saved SDK gate
result, every case classification and all evidence remain available.

Case details include inputs, output availability, check declarations and outcomes,
expected/actual values, event links, errors, and observable tool/model events.
Each event retains input/output availability, parent IDs, timing, terminal state,
errors, and provider-reported usage. Zero usage remains zero; unavailable usage
is labeled unavailable. No hidden model reasoning is claimed.

Repeated evaluations include case/check counts and rates, all runtime statistics,
variability, grouped identical findings with occurrence attempt numbers and a
clearly labeled representative case, plus every individual attempt and run ID.
Reliability comparisons and reviews retain both full evaluations. Single-run
comparison artifacts retain assertion event links; full traces are in the source
run reports, which can be opened when present in the project.

For async agents, select **Async** in **Execution & save settings** and choose
**Maximum concurrent cases**. Attempts remain sequential, but async cases within
an attempt may overlap. See the [async contract](milestones/03-async-execution.md)
for shared state, cancellation and comparison-setting limits.

Evaluation jobs use a separate process and remain visible across browser reloads.
Progress is emitted after each case invocation. Logs retain the most recent
64 KiB. Completed evaluations are published even when the browser is closed;
failed expectations or recorded agent errors still save complete reports.

**Stop** terminates the active worker process group on POSIX (the worker on
Windows) and marks the job interrupted. It does not publish a completed report.
Stopping cannot undo external side effects already performed by trusted agent
code. If evaluation configuration/import fails, the job is an error with logs.
If a destination appears while a job runs, publication fails without replacing
that file; the internal result remains in the private job directory for recovery.

Settings, job state and bounded logs live in `.thadam/dashboard/`. The repository
ignores that directory. A server session ending normally stops its worker. On a
hard server exit, the worker's parent watcher exits; recovered running job records
are displayed as interrupted on the next launch. This is a local process manager,
not a sandbox or distributed execution service. Explicit per-case deadlines use fresh spawned workers.

## Files and local access

Discovery recursively examines project JSON files, skipping hidden directories,
virtual environments, build output and `node_modules`. It does not follow symbolic
links. Invalid recognizable artifacts are listed separately without hiding valid
reports. Search/filtering uses the discovered catalog; Refresh rereads the files.
Large case lists paginate. Individual JSON artifacts are limited to 32 MiB in the
browser workflow; larger artifacts remain usable through the SDK. No synthetic
statistics fill empty states.

Search in Overview and Evaluations also matches labeled case IDs and failure
tags. **Filter by review label** finds unlabeled results or results with a good,
bad, or needs-review label. Review labels are local annotations, not authenticated
approvals; saved run outcomes remain authoritative for comparisons.

New report/review destinations must be absent, preserving existing evidence.
Suite saves use a fingerprint to reject stale browser edits. Baseline approval
uses the existing exact-evidence and stale-baseline guards. Browser writes within
one server are coordinated; unrelated external writers still require normal Git
review and are not covered by a filesystem transaction.

The server binds only to `127.0.0.1`. Its printed link establishes an ephemeral
browser session, with the token removed from the address after connection. API
requests require that session; cross-origin write requests are rejected. Browser
file access is confined to the selected project, with hidden/parent/absolute paths
and symbolic links refused. Report text is rendered as text, never executable HTML.
No report or agent output is sent to a hosted service.

Dark mode is the default; the light toggle persists in that browser. Both themes
use the documented Thadam semantic colors and status labels. The layout supports
keyboard navigation, visible focus, reduced motion, and narrow screens.

## Frontend development and validation

Node is for maintainers building the interface, not for dashboard users. From the
repository root:

```shell
python -m pip install -e '.[dev,dashboard]' httpx
python -m pytest -q tests examples/regression_test.py
python -m ruff check .
python -m ruff format --check .
```

From `dashboard/` with Node 22:

```shell
npm ci
npm test
npm run format:check
npm run build
```

The build writes production assets and third-party notices to
`src/thadam/dashboard/static/`. Commit the source, lockfile and rebuilt assets
together. CI rebuilds and checks those assets, exercises dashboard workflows on
Python 3.10 and 3.14, and keeps the core-only dependency checks separate. Reproduce
workflow validation with actionlint after editing CI.

## Suggest and review test cases

Install the optional `ai` extra and open **Suites → Suggest** to use ChatGPT plan
sign-in or your OpenAI API key. Models and billing paths are chosen explicitly.
Preview selected outgoing context before generating. Drafts appear beside suites;
review/edit and accept individual cases, then preview and explicitly save a suite.
No agent is executed and no baseline is approved by generation or saving.
See [scenario suggestions](milestones/04-scenario-suggestions.md) for connection,
privacy, interruption, artifact and revision contracts, CLI/SDK examples, and a
controlled demo requiring no subscription or network.

## Create a regression case

Open a saved run case, or select an individual repeated attempt, and choose
**Create regression case**. Review the original evidence, supply explicit checks,
save the reviewed draft, and preview a new or existing suite before saving.
See the [workflow and draft contract](milestones/04-regression-cases.md).

## Import recorded examples

Open **Suites → Import examples** to preview and import a project-local JSONL or
CSV file as regression drafts. Map source columns/paths and configure masking
before preview; duplicate rows require an explicit acknowledgement. Imported
examples remain unreviewed, and supplied expected answers are only proposed
checks until a developer reviews them. See the [workflow guide](milestones/04-regression-cases.md)
for format details and redaction limits.

## Verify a fix

Open **Suites → Verify fix**, choose a saved suite and enter the candidate
`module:callable`. Optionally choose a compatible baseline to save and open a
before/after comparison when the candidate run completes. Changed contracts are
reported as incompatible; without a baseline, the candidate report is available
on its own. See the [workflow guide](milestones/04-regression-cases.md) for
baseline requirements, revision handling, and exports.

## Run a conversation simulation

Open a suite schema 4 artifact in **Suites** and edit its JSON to define ordered
conversation turns, a fresh JSON state fixture and response/state assertions.
Run it in **Evaluations** with **Tool fixture factory** selected. Each case attempt
starts with the declared initial state and reuses the same factory agent across
turns. Evaluation details show every completed user/agent exchange, initial and
final state, configured tool scripts, checks and trace evidence. The dashboard
uses the existing project, revision, one-active-job and interruption guards.
See [conversation and state simulations](milestones/05-simulations.md).

### Execution limits and environment hooks

Run and Verify a fix expose optional turn limits, case deadline seconds, cleanup
grace and a fixture environment reference under execution settings. A deadline
uses a fresh process per case; importable agent/factory/verifier definitions are
required and shared callable state is not retained. Environment references name
exported EnvironmentHooks instances and require fixtures mode. Saved reports show
the selected policy, errors and partial evidence; changed policy is incompatible
with an existing baseline. [Boundary guide](milestones/05-execution-boundaries.md).
