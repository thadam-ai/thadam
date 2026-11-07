import {
    Activity,
    ArrowRight,
    Check,
    ChevronDown,
    ChevronRight,
    CircleAlert,
    Play,
    Plus,
    Save,
    Search,
    Square,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, counts, json, type Catalog, type Data } from "./api";
import { Badge, Button, ErrorBox, Field, Json, uid } from "./components";
export function RunPanel({
    open,
    onToggle,
    catalog,
    active,
    onStarted,
}: {
    open: boolean;
    onToggle: () => void;
    catalog: Catalog;
    active: boolean;
    onStarted: (job: Data) => void;
}) {
    const [agents, setAgents] = useState<Data[]>([]),
        [name, setName] = useState("My agent"),
        [reference, setReference] = useState(""),
        [mode, setMode] = useState("shared"),
        [asyncExecution, setAsyncExecution] = useState(false),
        [concurrency, setConcurrency] = useState(1);
    const [suite, setSuite] = useState(
            catalog.items.find((item) => item.kind === "suite")?.path || "",
        ),
        [attempts, setAttempts] = useState(1),
        [revision, setRevision] = useState(""),
        [report, setReport] = useState(
            "artifacts/evaluation-" + uid() + ".json",
        );
    const [error, setError] = useState(""),
        [busy, setBusy] = useState(false),
        [saved, setSaved] = useState(false);
    useEffect(() => {
        api<Data[]>("agents")
            .then(setAgents)
            .catch((e) => setError(e.message));
    }, []);
    async function start() {
        setBusy(true);
        setError("");
        try {
            onStarted(
                await api("jobs", {
                    suite,
                    reference,
                    mode,
                    attempts,
                    agent_revision: revision || null,
                    report,
                    ...(asyncExecution
                        ? {
                              async_execution: true,
                              max_concurrency: concurrency,
                          }
                        : {}),
                }),
            );
            setReport("artifacts/evaluation-" + uid() + ".json");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    async function saveAgent() {
        setError("");
        try {
            const item = { name, reference, mode };
            const list = [
                ...agents.filter((agent) => agent.name !== name),
                item,
            ];
            await api("agents", list, "PUT");
            setAgents(list);
            setSaved(true);
            setTimeout(() => setSaved(false), 1800);
        } catch (e) {
            setError((e as Error).message);
        }
    }
    return (
        <section className={"action-panel " + (open ? "expanded" : "")}>
            <button
                className="panel-toggle"
                onClick={onToggle}
                aria-expanded={open}
            >
                <span>
                    <Play size={17} />
                    <strong>Run an evaluation</strong>
                    <small>Choose your agent and test suite</small>
                </span>
                {open ? <ChevronDown size={18} /> : <Plus size={18} />}
            </button>
            {open && (
                <div className="panel-body">
                    {error && <ErrorBox error={error} />}
                    <div className="form-grid">
                        <Field label="Test suite">
                            <select
                                value={suite}
                                onChange={(e) => setSuite(e.target.value)}
                            >
                                <option value="">Choose a suite</option>
                                {catalog.items
                                    .filter((i) => i.kind === "suite")
                                    .map((i) => (
                                        <option key={i.path} value={i.path}>
                                            {i.path}
                                        </option>
                                    ))}
                            </select>
                        </Field>
                        <Field label="Saved agent">
                            <select
                                defaultValue=""
                                onChange={(e) => {
                                    const agent = agents.find(
                                        (a) => a.name === e.target.value,
                                    );
                                    if (agent) {
                                        setName(agent.name);
                                        setReference(agent.reference);
                                        setMode(agent.mode);
                                    }
                                }}
                            >
                                <option value="">
                                    Configure an agent below
                                </option>
                                {agents.map((a) => (
                                    <option key={a.name}>{a.name}</option>
                                ))}
                            </select>
                        </Field>
                        <Field
                            label="Agent reference"
                            hint={
                                mode === "fixtures"
                                    ? "Factory accepting FixtureTools and returning a fresh agent for each case. Imported only when you run."
                                    : "Your Python module:callable, imported only when you run."
                            }
                        >
                            <input
                                value={reference}
                                onChange={(e) => setReference(e.target.value)}
                                placeholder="my_agent:run"
                            />
                        </Field>
                        <Field
                            label="Attempts"
                            hint="1 = single run; 2 or more = repeated evaluation."
                        >
                            <input
                                type="number"
                                min={mode === "factory" ? 2 : 1}
                                value={attempts}
                                onChange={(e) =>
                                    setAttempts(Number(e.target.value))
                                }
                            />
                        </Field>
                    </div>
                    <details className="advanced-settings">
                        <summary>
                            Execution & save settings <ChevronRight size={14} />
                        </summary>
                        <div className="form-grid">
                            <Field label="Execution engine">
                                <select
                                    value={asyncExecution ? "async" : "sync"}
                                    onChange={(event) =>
                                        setAsyncExecution(
                                            event.target.value === "async",
                                        )
                                    }
                                >
                                    <option value="sync">Synchronous</option>
                                    <option value="async">Async</option>
                                </select>
                            </Field>
                            <Field
                                label="Maximum concurrent cases"
                                hint="Async only. Your shared agent and resources must support overlapping calls."
                            >
                                <input
                                    type="number"
                                    min={1}
                                    step={1}
                                    disabled={!asyncExecution}
                                    value={asyncExecution ? concurrency : 1}
                                    onChange={(event) =>
                                        setConcurrency(
                                            Number(event.target.value),
                                        )
                                    }
                                />
                            </Field>
                            <Field label="Execution mode">
                                <select
                                    value={mode}
                                    onChange={(e) => {
                                        setMode(e.target.value);
                                        if (
                                            e.target.value === "factory" &&
                                            attempts < 2
                                        )
                                            setAttempts(5);
                                    }}
                                >
                                    <option value="shared">
                                        Shared callable
                                    </option>
                                    <option value="fixtures">
                                        Tool fixture factory
                                    </option>
                                    <option value="factory">
                                        Fresh factory per invocation
                                    </option>
                                </select>
                            </Field>
                            <Field label="Application revision (optional)">
                                <input
                                    value={revision}
                                    onChange={(e) =>
                                        setRevision(e.target.value)
                                    }
                                    placeholder="Commit or application version"
                                />
                            </Field>
                            <Field label="New report path">
                                <input
                                    value={report}
                                    onChange={(e) => setReport(e.target.value)}
                                />
                            </Field>
                            <Field label="Agent name">
                                <div className="inline-field">
                                    <input
                                        value={name}
                                        onChange={(e) =>
                                            setName(e.target.value)
                                        }
                                    />
                                    <Button onClick={saveAgent}>
                                        {saved ? (
                                            <Check size={15} />
                                        ) : (
                                            <Save size={15} />
                                        )}
                                        Save agent
                                    </Button>
                                </div>
                            </Field>
                        </div>
                    </details>
                    <div className="form-footer">
                        <p>
                            Runs trusted Python code from this project.
                            {asyncExecution
                                ? "Async case overlap is bounded by your limit; attempts remain sequential."
                                : "Evaluation is sequential."}
                        </p>
                        <Button
                            primary
                            disabled={busy || active || !suite || !reference}
                            onClick={start}
                        >
                            <Play size={15} />
                            {busy ? "Starting…" : "Run evaluation"}
                        </Button>
                    </div>
                </div>
            )}
        </section>
    );
}

export function JobList({
    jobs,
    onRefresh,
    onOpen,
}: {
    jobs: Data[];
    onRefresh: () => void;
    onOpen: (path: string) => void;
}) {
    const [expanded, setExpanded] = useState<string | null>(null),
        [detail, setDetail] = useState<Data | null>(null),
        [error, setError] = useState("");
    useEffect(() => {
        if (!expanded) return;
        let alive = true;
        const load = () =>
            api<Data>("jobs/" + expanded)
                .then((data) => {
                    if (alive) setDetail(data);
                })
                .catch((e) => {
                    if (alive) setError(e.message);
                });
        load();
        const timer = setInterval(load, 1000);
        return () => {
            alive = false;
            clearInterval(timer);
        };
    }, [expanded]);
    return (
        <div className="job-list">
            {error && <ErrorBox error={error} />}
            <div className="section-heading">
                <h2>Local jobs</h2>
                <small>
                    Progress and logs stay available across browser reloads
                </small>
            </div>
            {jobs.slice(0, 10).map((job) => (
                <div className="job" key={job.id}>
                    <div className="job-row">
                        <span className={"job-state " + job.state}>
                            {job.state === "running" ? (
                                <Activity size={17} />
                            ) : job.state === "completed" ? (
                                <Check size={17} />
                            ) : (
                                <CircleAlert size={17} />
                            )}
                        </span>
                        <div className="job-title">
                            <strong>
                                {job.settings.kind === "generation"
                                    ? "Scenario suggestions"
                                    : job.settings.suite}
                            </strong>
                            <small>
                                {job.settings.kind === "generation"
                                    ? `${job.settings.model} · ${job.settings.request.count} suggestions requested`
                                    : `${job.settings.reference} · ${job.settings.attempts} ${job.settings.attempts === 1 ? "attempt" : "attempts"}`}
                            </small>
                        </div>
                        <span className="job-count">
                            {job.completed}/{job.total}
                        </span>
                        <Badge status={job.state} />
                        <Button
                            quiet
                            onClick={() => {
                                setExpanded(
                                    expanded === job.id ? null : job.id,
                                );
                                setDetail(null);
                            }}
                        >
                            Logs
                        </Button>
                        {job.state === "running" ? (
                            <Button
                                onClick={async () => {
                                    try {
                                        await api("stop", {});
                                        onRefresh();
                                    } catch (e) {
                                        setError((e as Error).message);
                                    }
                                }}
                            >
                                <Square size={13} />
                                Stop
                            </Button>
                        ) : job.state === "completed" ? (
                            <Button onClick={() => onOpen(job.settings.report)}>
                                Open result
                                <ArrowRight size={13} />
                            </Button>
                        ) : null}
                    </div>
                    {job.state === "running" && (
                        <progress
                            aria-label={
                                job.settings.kind === "generation"
                                    ? "Generation request progress"
                                    : "Evaluation progress"
                            }
                            max={job.total}
                            value={job.completed}
                        />
                    )}{" "}
                    {job.error && <p className="job-error">{job.error}</p>}
                    {expanded === job.id && (
                        <pre className="logs">
                            {detail?.logs || "No log output yet."}
                        </pre>
                    )}
                </div>
            ))}
        </div>
    );
}

export function EvaluationView({
    data,
    onRegression,
}: {
    data: Data;
    onRegression?: (id: string, attempt: number | null) => void;
}) {
    const c = counts(data),
        repeated = data.kind === "repeated_run";
    return (
        <>
            <section className="run-outcome" aria-label="Evaluation result">
                <h2 className={c.errors ? "red" : c.failed ? "amber" : "teal"}>
                    {c.errors
                        ? `${c.errors} ${repeated ? (c.errors === 1 ? "invocation" : "invocations") : c.errors === 1 ? "case" : "cases"} with errors`
                        : c.failed
                          ? `${c.failed} of ${c.total} ${repeated ? "invocations" : "cases"} failed`
                          : `All ${c.total} ${repeated ? "invocations" : "cases"} passed`}
                </h2>
                <div className="outcome-counts">
                    <span>
                        <b>{c.passed}</b> passed
                    </span>
                    <span className={c.failed ? "amber" : ""}>
                        <b>{c.failed}</b> failed
                    </span>
                    <span className={c.errors ? "red" : ""}>
                        <b>{c.errors}</b> errors
                    </span>
                </div>
            </section>
            <details className="run-metadata">
                <summary>
                    Run details <ChevronRight size={14} />
                </summary>
                <dl className="metadata">
                    <div>
                        <dt>Suite</dt>
                        <dd>
                            {(data.suite || data.runs?.[0]?.suite)?.id ||
                                "Not recorded"}
                            {(data.suite || data.runs?.[0]?.suite)?.revision
                                ? " · " +
                                  (data.suite || data.runs?.[0]?.suite).revision
                                : ""}
                        </dd>
                    </div>
                    <div>
                        <dt>Application revision</dt>
                        <dd>{data.agent_revision || "Not recorded"}</dd>
                    </div>
                    <div>
                        <dt>{repeated ? "Evaluation ID" : "Run ID"}</dt>
                        <dd className="mono">
                            {data.report_id || data.run_id}
                        </dd>
                    </div>
                    {repeated && (
                        <div>
                            <dt>Execution</dt>
                            <dd>
                                {data.attempts} attempts · {data.execution_mode}
                            </dd>
                        </div>
                    )}
                </dl>
            </details>
            {repeated ? (
                <RepeatedView data={data} onRegression={onRegression} />
            ) : (
                <CaseList
                    cases={data.cases || []}
                    onRegression={
                        onRegression
                            ? (id) => onRegression(id, null)
                            : undefined
                    }
                />
            )}
        </>
    );
}

export function CaseList({
    cases,
    onRegression,
}: {
    cases: Data[];
    onRegression?: (id: string) => void;
}) {
    const [search, setSearch] = useState(""),
        [status, setStatus] = useState("all"),
        [page, setPage] = useState(0);
    const filtered = cases
        .filter(
            (test) =>
                test.id.toLowerCase().includes(search.toLowerCase()) &&
                (status === "all" || test.status === status),
        )
        .sort((a, b) => {
            const priority = (status: string) =>
                status === "error" ? 0 : status === "failed" ? 1 : 2;
            return priority(a.status) - priority(b.status);
        });
    const firstProblem = filtered.find((test) => test.status !== "passed");
    return (
        <>
            <div className="section-heading">
                <h2>Cases</h2>
                <span>
                    {cases.length} cases
                    {firstProblem ? " · failures first" : ""}
                </span>
            </div>
            <div className="library-controls">
                <div className="search">
                    <Search size={15} />
                    <input
                        aria-label="Search cases"
                        placeholder="Find a case…"
                        value={search}
                        onChange={(e) => {
                            setSearch(e.target.value);
                            setPage(0);
                        }}
                    />
                </div>
                <select
                    aria-label="Filter cases"
                    value={status}
                    onChange={(e) => {
                        setStatus(e.target.value);
                        setPage(0);
                    }}
                >
                    {["all", "passed", "failed", "error"].map((s) => (
                        <option key={s} value={s}>
                            {s === "all" ? "All cases" : s}
                        </option>
                    ))}
                </select>
            </div>
            {filtered.slice(page * 50, (page + 1) * 50).map((test) => (
                <details
                    className="case-evidence"
                    key={test.id}
                    open={test.id === firstProblem?.id}
                >
                    <summary>
                        <ChevronRight size={16} />
                        <strong>{test.id}</strong>
                        <Badge status={test.status} />
                        <span className="duration">
                            {Number(String(test.duration_ms)).toFixed(2)} ms
                        </span>
                    </summary>
                    {onRegression && (
                        <Button onClick={() => onRegression(test.id)}>
                            Create regression case
                        </Button>
                    )}
                    <CaseEvidence test={test} />
                </details>
            ))}
            {!filtered.length && <p className="muted">No matching cases.</p>}
            {filtered.length > 50 && (
                <div className="pagination">
                    <Button disabled={!page} onClick={() => setPage(page - 1)}>
                        Previous
                    </Button>
                    <span>
                        {page * 50 + 1}–
                        {Math.min((page + 1) * 50, filtered.length)} of{" "}
                        {filtered.length}
                    </span>
                    <Button
                        disabled={(page + 1) * 50 >= filtered.length}
                        onClick={() => setPage(page + 1)}
                    >
                        Next
                    </Button>
                </div>
            )}
        </>
    );
}

export function CaseEvidence({ test }: { test: Data }) {
    return (
        <div className="case-body">
            {(test.errors || []).map((error: Data, i: number) => (
                <ErrorBox
                    key={i}
                    error={`${error.source}${error.assertion_id ? " / " + error.assertion_id : ""} · ${error.type}: ${error.message}`}
                />
            ))}
            <h3>Checks</h3>
            {(test.check_definitions || []).map((definition: Data) => {
                const result = (test.assertions || []).find(
                    (check: Data) => check.id === definition.id,
                );
                return (
                    <details
                        className={
                            "check-evidence " +
                            (result && !result.passed ? "unmet" : "")
                        }
                        key={definition.id}
                        open={!result?.passed}
                    >
                        <summary>
                            <ChevronRight size={14} />
                            <strong>{definition.id}</strong>
                            <span className="type-label">
                                {definition.type}
                            </span>
                            <Badge
                                status={
                                    result
                                        ? result.passed
                                            ? "passed"
                                            : "failed"
                                        : "error"
                                }
                            />
                        </summary>
                        <div className="check-body">
                            {result ? (
                                <>
                                    <p>{result.message}</p>
                                    <div className="evidence-pair">
                                        <Json
                                            label="Expected"
                                            value={result.expected}
                                        />
                                        <Json
                                            label="Actual"
                                            value={result.actual}
                                        />
                                    </div>
                                    {result.event_ids.length > 0 && (
                                        <p className="event-links">
                                            Linked events:{" "}
                                            {result.event_ids.join(", ")}
                                        </p>
                                    )}
                                </>
                            ) : (
                                <p className="red">
                                    No verdict available. The recorded error is
                                    not a pass.
                                </p>
                            )}
                            <details className="raw-detail">
                                <summary>Declared check</summary>
                                <Json value={definition} />
                            </details>
                        </div>
                    </details>
                );
            })}
            <details className="raw-detail invocation-io">
                <summary>Invocation input and output</summary>
                <div className="evidence-pair">
                    <Json label="Input" value={test.input} />
                    {test.output_available ? (
                        <Json label="Observed output" value={test.output} />
                    ) : (
                        <div className="unavailable">
                            Output unavailable. See recorded errors.
                        </div>
                    )}
                </div>
            </details>
            {test.conversation?.length > 0 && (
                <details className="raw-detail conversation-evidence" open>
                    <summary>
                        Conversation · {test.conversation_results?.length || 0}/
                        {test.conversation.length} responses
                    </summary>
                    {(test.conversation || []).map(
                        (turn: Data, index: number) => {
                            const result = (
                                test.conversation_results || []
                            ).find((item: Data) => item.id === turn.id);
                            return (
                                <section
                                    key={turn.id}
                                    className="conversation-turn"
                                >
                                    <h4>
                                        Turn {index + 1} · {turn.id}
                                    </h4>
                                    <div className="evidence-pair">
                                        <Json
                                            label="User message"
                                            value={turn.message}
                                        />
                                        {result?.output_available ? (
                                            <Json
                                                label="Agent response"
                                                value={result.output}
                                            />
                                        ) : (
                                            <div className="unavailable">
                                                Response unavailable. See
                                                recorded errors.
                                            </div>
                                        )}
                                    </div>
                                </section>
                            );
                        },
                    )}
                </details>
            )}
            {test.state_fixture !== undefined &&
                test.state_fixture !== null && (
                    <details className="raw-detail state-evidence" open>
                        <summary>Observable state</summary>
                        <div className="evidence-pair">
                            <Json
                                label="Initial state"
                                value={test.state_initial}
                            />
                            <Json
                                label="Final state"
                                value={test.state_final}
                            />
                        </div>
                    </details>
                )}
            {test.tool_fixtures !== undefined && (
                <details className="raw-detail">
                    <summary>Configured tool fixtures</summary>
                    <p className="muted">
                        Saved responses include unused steps. Each invocation
                        starts with a fresh script.
                    </p>
                    <Json value={test.tool_fixtures} />
                </details>
            )}
            <TraceView test={test} />
        </div>
    );
}

export function TraceView({ test }: { test: Data }) {
    const events = test.events;
    return (
        <section className="trace-section">
            <div className="section-heading">
                <h3>Execution trace</h3>
                <span>
                    {events === null
                        ? "Unavailable"
                        : `${events.length} observed events`}
                </span>
            </div>
            {events === null ? (
                <p className="muted">
                    Tracing was not available for this invocation. Plain Python
                    callables do not emit events automatically.
                </p>
            ) : (
                <>
                    <p className="muted">
                        {test.trace_complete
                            ? "Complete within the recorded instrumentation scope."
                            : "Partial trace — some execution evidence may be missing."}
                    </p>
                    {(test.trace_warnings || []).map(
                        (warning: string, i: number) => (
                            <p className="amber" key={i}>
                                {warning}
                            </p>
                        ),
                    )}
                    {events.length === 0 && (
                        <p className="muted">
                            Tracing was observed, with no recorded tool or model
                            events.
                        </p>
                    )}
                    {events.map((event: Data) => (
                        <details className="trace-event" key={event.id}>
                            <summary>
                                <span className="event-kind">{event.kind}</span>
                                <strong>{event.name}</strong>
                                <Badge status={event.status} />
                                <span className="duration">
                                    {event.duration_ms === null
                                        ? "Duration unavailable"
                                        : Number(
                                              String(event.duration_ms),
                                          ).toFixed(2) + " ms"}
                                </span>
                            </summary>
                            <div className="check-body">
                                <dl className="metadata">
                                    <div>
                                        <dt>Event ID</dt>
                                        <dd className="mono">{event.id}</dd>
                                    </div>
                                    <div>
                                        <dt>Parent ID</dt>
                                        <dd className="mono">
                                            {event.parent_id ?? "None recorded"}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt>Started</dt>
                                        <dd>
                                            {String(event.started_at_ms)} ms
                                            from invocation
                                        </dd>
                                    </div>
                                </dl>
                                <div className="evidence-pair">
                                    {event.input_available ? (
                                        <Json
                                            label="Event input"
                                            value={event.input}
                                        />
                                    ) : (
                                        <p className="unavailable">
                                            Input unavailable
                                        </p>
                                    )}
                                    {event.output_available ? (
                                        <Json
                                            label="Event output"
                                            value={event.output}
                                        />
                                    ) : (
                                        <p className="unavailable">
                                            Output unavailable
                                        </p>
                                    )}
                                </div>
                                {event.error && (
                                    <ErrorBox
                                        error={
                                            event.error.type +
                                            ": " +
                                            event.error.message
                                        }
                                    />
                                )}
                                <div className="token-usage">
                                    <strong>Reported token usage</strong>
                                    {[
                                        "input_tokens",
                                        "output_tokens",
                                        "total_tokens",
                                    ].map((key) => (
                                        <span key={key}>
                                            {key.replace("_tokens", "")}:{" "}
                                            <b>
                                                {event.usage?.[key] ??
                                                    "Unavailable"}
                                            </b>
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </details>
                    ))}
                </>
            )}
        </section>
    );
}

export function RepeatedView({
    data,
    onRegression,
}: {
    data: Data;
    onRegression?: (id: string, attempt: number | null) => void;
}) {
    const [attempt, setAttempt] = useState(0),
        [caseSearch, setCaseSearch] = useState("");
    const groups = new Map<
        string,
        {
            caseId: string;
            check: string;
            message: string;
            attempts: number[];
            test: Data;
        }
    >();
    data.runs.forEach((run: Data, index: number) =>
        run.cases.forEach((test: Data) => {
            for (const check of test.assertions.filter(
                (c: Data) => !c.passed,
            )) {
                const key = json([
                    test.id,
                    check.id,
                    check.message,
                    check.expected,
                    check.actual,
                ]);
                const group = groups.get(key);
                if (group) group.attempts.push(index + 1);
                else
                    groups.set(key, {
                        caseId: test.id,
                        check: check.id,
                        message: check.message,
                        attempts: [index + 1],
                        test,
                    });
            }
            for (const error of test.errors) {
                const key = json([test.id, error]);
                const group = groups.get(key);
                if (group) group.attempts.push(index + 1);
                else
                    groups.set(key, {
                        caseId: test.id,
                        check: error.assertion_id || error.source,
                        message: error.type + ": " + error.message,
                        attempts: [index + 1],
                        test,
                    });
            }
        }),
    );
    return (
        <>
            <div className="section-heading">
                <h2>Reliability by case</h2>
                <span>Every attempt counts</span>
            </div>
            <div className="search standalone">
                <Search size={15} />
                <input
                    aria-label="Find reliability case"
                    placeholder="Find a case…"
                    value={caseSearch}
                    onChange={(e) => setCaseSearch(e.target.value)}
                />
            </div>
            {data.cases
                .filter((test: Data) =>
                    test.id.toLowerCase().includes(caseSearch.toLowerCase()),
                )
                .map((test: Data) => (
                    <details className="case-evidence" key={test.id}>
                        <summary>
                            <ChevronRight size={15} />
                            <strong>{test.id}</strong>
                            {test.variable && <Badge status="variable" />}
                            <span className="rate">
                                {test.counts.passed}/{test.counts.total} passed{" "}
                                <b>
                                    {(test.counts.pass_rate * 100).toFixed(1)}%
                                </b>
                            </span>
                            <span className="duration">
                                {test.runtime.median_ms.toFixed(2)} ms median
                            </span>
                        </summary>
                        <div className="case-body">
                            <div className="table-scroll">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Check</th>
                                            <th>Passed</th>
                                            <th>Failed</th>
                                            <th>Errors</th>
                                            <th>Pass rate</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {test.checks.map((check: Data) => (
                                            <tr key={check.id}>
                                                <td>{check.id}</td>
                                                <td>
                                                    {check.counts.passed}/
                                                    {check.counts.total}
                                                </td>
                                                <td
                                                    className={
                                                        check.counts.failed
                                                            ? "amber"
                                                            : ""
                                                    }
                                                >
                                                    {check.counts.failed}
                                                </td>
                                                <td
                                                    className={
                                                        check.counts.errors
                                                            ? "red"
                                                            : ""
                                                    }
                                                >
                                                    {check.counts.errors}
                                                </td>
                                                <td>
                                                    {(
                                                        check.counts.pass_rate *
                                                        100
                                                    ).toFixed(1)}
                                                    %
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            <dl className="metadata">
                                {Object.entries(test.runtime).map(
                                    ([key, value]) => (
                                        <div key={key}>
                                            <dt>
                                                {key
                                                    .replace("_ms", "")
                                                    .replace("_", " ")}
                                            </dt>
                                            <dd>
                                                {Number(value).toFixed(2)} ms
                                            </dd>
                                        </div>
                                    ),
                                )}
                            </dl>
                        </div>
                    </details>
                ))}
            <p className="evidence-note">
                Observed rates describe these attempts. They do not establish
                statistical significance or causation.
            </p>
            {groups.size > 0 && (
                <>
                    <div className="section-heading">
                        <h2>Recurring findings</h2>
                        <span>Grouped by identical evidence</span>
                    </div>
                    {[...groups.values()].map((group, i) => (
                        <details className="case-evidence" key={i}>
                            <summary>
                                <ChevronRight size={15} />
                                <strong>
                                    {group.caseId} / {group.check}
                                </strong>
                                <span className="amber">
                                    {group.attempts.length} occurrences
                                </span>
                            </summary>
                            <div className="case-body">
                                <p>{group.message}</p>
                                <p>Attempts: {group.attempts.join(", ")}</p>
                                <p className="evidence-note">
                                    Representative evidence from attempt{" "}
                                    {group.attempts[0]}. Select any individual
                                    attempt below for its complete evidence.
                                </p>
                                <CaseEvidence test={group.test} />
                            </div>
                        </details>
                    ))}
                </>
            )}
            <div className="section-heading">
                <h2>Individual attempts</h2>
                <select
                    aria-label="Choose attempt"
                    value={attempt}
                    onChange={(e) => setAttempt(Number(e.target.value))}
                >
                    {data.runs.map((_: Data, index: number) => (
                        <option key={index} value={index}>
                            Attempt {index + 1}
                        </option>
                    ))}
                </select>
            </div>
            <div className="attempt-id">
                Run ID <code>{data.runs[attempt].run_id}</code>
            </div>
            <CaseList
                key={attempt}
                cases={data.runs[attempt].cases}
                onRegression={
                    onRegression
                        ? (id) => onRegression(id, attempt + 1)
                        : undefined
                }
            />
        </>
    );
}
