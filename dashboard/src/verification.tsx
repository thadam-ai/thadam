import {
    boundaryRequest,
    emptyBoundary,
    ExecutionBoundaryFields,
} from "./execution_limits";
import { Activity, Check, Play, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Catalog, type Data, type Item } from "./api";
import { Button, ErrorBox, Field, uid } from "./components";

export function VerificationPanel({
    catalog,
    active,
    onStarted,
    onOpen,
}: {
    catalog: Catalog;
    active: boolean;
    onStarted: (job: Data) => void;
    onOpen: (path: string) => void;
}) {
    const [boundary, setBoundary] = useState(emptyBoundary);
    const [suite, setSuite] = useState(
        catalog.items.find((item) => item.kind === "suite")?.path || "",
    );
    const [suiteData, setSuiteData] = useState<Data | null>(null);
    const [reference, setReference] = useState("");
    const [mode, setMode] = useState("shared");
    const [attempts, setAttempts] = useState(1);
    const [revision, setRevision] = useState("");
    const [baseline, setBaseline] = useState("");
    const [tolerance, setTolerance] = useState(0);
    const [report, setReport] = useState(
        "artifacts/candidate-" + uid() + ".json",
    );
    const [comparison, setComparison] = useState(
        "artifacts/verification-" + uid() + ".json",
    );
    const [asyncExecution, setAsyncExecution] = useState(false);
    const [concurrency, setConcurrency] = useState(1);
    const [job, setJob] = useState<Data | null>(null);
    const [completedPath, setCompletedPath] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const handledJob = useRef("");
    const onOpenRef = useRef(onOpen);
    onOpenRef.current = onOpen;

    useEffect(() => {
        if (!suite) {
            setSuiteData(null);
            return;
        }
        let alive = true;
        api<Data>("artifact?path=" + encodeURIComponent(suite))
            .then((artifact) => {
                if (alive) setSuiteData(artifact.data);
            })
            .catch((reason) => {
                if (alive) setError((reason as Error).message);
            });
        return () => {
            alive = false;
        };
    }, [suite]);

    const cases: Data[] = suiteData?.cases || [];
    const hasSimulation = cases.some(
        (test) => test.conversation?.length > 0 || test.state_fixture != null,
    );
    const requiresFixtures =
        suiteData?.schema_version === 3 || suiteData?.schema_version === 4;
    const executionMode = requiresFixtures
        ? hasSimulation
            ? "simulations"
            : "fixtures"
        : mode;
    const baselineOptions = matchingVerificationBaselines(
        catalog.items,
        attempts,
        executionMode,
    );

    useEffect(() => {
        if (baseline && !baselineOptions.some((item) => item.path === baseline))
            setBaseline("");
    }, [baselineOptions, baseline]);

    async function start() {
        setBusy(true);
        setError("");
        setCompletedPath("");
        handledJob.current = "";
        try {
            const selectedBaseline = baselineOptions.find(
                (item) => item.path === baseline,
            );
            const started = await api<Data>("jobs", {
                suite,
                reference,
                mode: requiresFixtures ? "fixtures" : mode,
                attempts,
                agent_revision: revision || null,
                report,
                ...boundaryRequest(
                    boundary,
                    requiresFixtures || mode === "fixtures",
                ),
                ...(asyncExecution
                    ? { async_execution: true, max_concurrency: concurrency }
                    : {}),
                ...(selectedBaseline
                    ? {
                          verification: {
                              baseline: selectedBaseline.path,
                              baseline_fingerprint:
                                  selectedBaseline.fingerprint,
                              report: comparison,
                              max_pass_rate_drop: tolerance,
                          },
                      }
                    : {}),
            });
            setJob(started);
            onStarted(started);
        } catch (reason) {
            setError((reason as Error).message);
        } finally {
            setBusy(false);
        }
    }

    useEffect(() => {
        if (!job || job.state !== "running") return;
        let alive = true;
        async function refresh() {
            try {
                const latest = await api<Data>("jobs/" + job!.id);
                if (!alive) return;
                setJob(latest);
                if (
                    latest.state !== "completed" ||
                    handledJob.current === latest.id
                )
                    return;
                handledJob.current = latest.id;
                const verification = latest.settings.verification;
                if (!verification) {
                    setCompletedPath(latest.settings.report);
                    return;
                }
                if (latest.verification_error) {
                    setError(
                        `Candidate saved, but comparison failed: ${latest.verification_error}`,
                    );
                    setCompletedPath(latest.settings.report);
                    return;
                }
                setCompletedPath(verification.report);
                onOpenRef.current(verification.report);
            } catch (reason) {
                if (alive) setError((reason as Error).message);
            }
        }
        const timer = setInterval(() => void refresh(), 750);
        void refresh();
        return () => {
            alive = false;
            clearInterval(timer);
        };
    }, [job?.id, job?.state]);

    return (
        <section className="verification-panel">
            <div className="page-heading">
                <div>
                    <h1>Verify a fix</h1>
                    <p>
                        Run a saved suite against a candidate you choose. Add a
                        matching baseline report to compare checks
                        automatically. Contract changes remain visible as
                        incompatible evidence. Keep async and concurrency
                        settings consistent with the baseline; reports do not
                        record them.
                    </p>
                </div>
            </div>
            {error && <ErrorBox error={error} />}
            <div className="form-grid">
                <Field label="Saved test suite">
                    <select
                        value={suite}
                        onChange={(event) => {
                            setSuiteData(null);
                            setSuite(event.target.value);
                        }}
                    >
                        <option value="">Choose a saved suite</option>
                        {catalog.items
                            .filter((item) => item.kind === "suite")
                            .map((item) => (
                                <option key={item.path} value={item.path}>
                                    {item.path}
                                </option>
                            ))}
                    </select>
                </Field>
                <Field
                    label="Candidate agent"
                    hint="Enter the module:callable for the implementation you want to check. It is imported only when the run starts."
                >
                    <input
                        value={reference}
                        onChange={(event) => setReference(event.target.value)}
                        placeholder="my_agent:run"
                    />
                </Field>
                <Field label="Execution mode">
                    <select
                        value={requiresFixtures ? "fixtures" : mode}
                        disabled={requiresFixtures}
                        onChange={(event) => setMode(event.target.value)}
                    >
                        <option value="shared">Shared callable</option>
                        <option value="fixtures">Tool fixture factory</option>
                        <option value="factory">
                            Fresh factory per invocation
                        </option>
                    </select>
                </Field>
                <Field
                    label="Attempts"
                    hint="Two or more runs a repeated evaluation."
                >
                    <input
                        type="number"
                        min={mode === "factory" && !requiresFixtures ? 2 : 1}
                        value={attempts}
                        onChange={(event) =>
                            setAttempts(Number(event.target.value))
                        }
                    />
                </Field>
                <Field
                    label="Baseline report (optional)"
                    hint={
                        attempts === 1
                            ? "Choose a single run or approved baseline to compare with this candidate."
                            : `Choose a repeated run or approved baseline with ${attempts} attempts in ${executionMode} mode.`
                    }
                >
                    <select
                        value={baseline}
                        onChange={(event) => setBaseline(event.target.value)}
                    >
                        <option value="">
                            No baseline — inspect candidate only
                        </option>
                        {baselineOptions.map((item) => (
                            <option key={item.path} value={item.path}>
                                {verificationBaselineLabel(item)}
                            </option>
                        ))}
                    </select>
                </Field>
                <Field label="Application revision (optional)">
                    <input
                        value={revision}
                        onChange={(event) => setRevision(event.target.value)}
                        placeholder="Commit or application version"
                    />
                </Field>
            </div>
            <details className="advanced-settings">
                <summary>Run and report settings</summary>
                <div className="form-grid">
                    <ExecutionBoundaryFields
                        value={boundary}
                        onChange={setBoundary}
                        fixtures={requiresFixtures || mode === "fixtures"}
                    />
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
                    <Field label="Maximum concurrent cases">
                        <input
                            type="number"
                            min={1}
                            disabled={!asyncExecution}
                            value={asyncExecution ? concurrency : 1}
                            onChange={(event) =>
                                setConcurrency(Number(event.target.value))
                            }
                        />
                    </Field>
                    <Field label="New candidate report path">
                        <input
                            value={report}
                            onChange={(event) => setReport(event.target.value)}
                        />
                    </Field>
                    {baseline && (
                        <>
                            {attempts > 1 && (
                                <Field
                                    label="Maximum pass-rate drop"
                                    hint="Repeated runs only. 0.05 allows a five percentage-point drop per case/check."
                                >
                                    <input
                                        type="number"
                                        min={0}
                                        max={1}
                                        step={0.01}
                                        value={tolerance}
                                        onChange={(event) =>
                                            setTolerance(
                                                Number(event.target.value),
                                            )
                                        }
                                    />
                                </Field>
                            )}
                            <Field label="New comparison report path">
                                <input
                                    value={comparison}
                                    onChange={(event) =>
                                        setComparison(event.target.value)
                                    }
                                />
                            </Field>
                        </>
                    )}
                </div>
            </details>
            {job?.state === "running" && (
                <div className="job">
                    <div className="job-row">
                        <span className="job-state running">
                            <Activity size={17} />
                        </span>
                        <div className="job-title">
                            <strong>Checking {job.settings.reference}</strong>
                            <small>{job.settings.suite}</small>
                        </div>
                        <span className="job-count">
                            {job.completed}/{job.total}
                        </span>
                        <Button
                            onClick={async () => {
                                try {
                                    await api("stop", {});
                                } catch (reason) {
                                    setError((reason as Error).message);
                                }
                            }}
                        >
                            <Square size={13} /> Stop
                        </Button>
                    </div>
                    <progress
                        aria-label="Verification progress"
                        max={job.total}
                        value={job.completed}
                    />
                </div>
            )}
            {job && ["interrupted", "error"].includes(job.state) && (
                <div className="job-error" role="status">
                    Verification {job.state}.{" "}
                    {job.error || "No candidate report was saved."}
                </div>
            )}
            {completedPath && job?.state === "completed" && (
                <div className="evidence-note">
                    <p>
                        {job.settings.verification
                            ? "Candidate evidence and its comparison are saved."
                            : "Candidate evidence is saved. No comparison was made because you did not select a baseline."}
                    </p>
                    <Button onClick={() => onOpen(completedPath)}>
                        <Check size={14} />
                        {job.settings.verification && !job.verification_error
                            ? "Open comparison"
                            : "Open candidate report"}
                    </Button>
                </div>
            )}
            {job?.state !== "running" && (
                <div className="form-footer">
                    <p>
                        {baseline
                            ? "The candidate run and comparison are saved separately. A changed suite contract will be shown as incompatible."
                            : "Without a baseline, the saved candidate report shows current check results but no before/after comparison."}
                    </p>
                    <Button
                        primary
                        disabled={
                            busy ||
                            active ||
                            !suite ||
                            !suiteData ||
                            !reference ||
                            !Number.isInteger(attempts) ||
                            attempts < 1 ||
                            (mode === "factory" &&
                                !requiresFixtures &&
                                attempts < 2) ||
                            (asyncExecution &&
                                (!Number.isInteger(concurrency) ||
                                    concurrency < 1)) ||
                            !report ||
                            (!!baseline && !comparison) ||
                            (!!baseline &&
                                (!Number.isFinite(tolerance) ||
                                    tolerance < 0 ||
                                    tolerance > 1))
                        }
                        onClick={start}
                    >
                        <Play size={14} />
                        {busy ? "Starting…" : "Run candidate"}
                    </Button>
                </div>
            )}
        </section>
    );
}

export function matchingVerificationBaselines(
    items: Item[],
    attempts: number,
    executionMode: string,
): Item[] {
    return items.filter((item) =>
        attempts === 1
            ? item.kind === "run" ||
              (item.kind === "approved_baseline" &&
                  (item.attempts === undefined || item.attempts === null))
            : (item.kind === "repeated_run" ||
                  item.kind === "approved_baseline") &&
              item.attempts === attempts &&
              item.execution_mode === executionMode,
    );
}

export function verificationBaselineLabel(item: Item): string {
    return item.kind === "approved_baseline"
        ? `Approved baseline · ${item.path}`
        : item.path;
}
