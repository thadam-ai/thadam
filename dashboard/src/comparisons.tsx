import {
    ArrowRight,
    ChevronDown,
    ChevronRight,
    GitCompareArrows,
    Plus,
} from "lucide-react";
import { useState } from "react";
import { api, type Catalog, type Data, type Item } from "./api";
import { Badge, Button, ErrorBox, Field, Json, uid } from "./components";
import { EvaluationView } from "./evaluations";
export function EvaluationSelect({
    label,
    value,
    onChange,
    catalog,
    optional = false,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    catalog: Catalog;
    optional?: boolean;
}) {
    return (
        <Field label={label}>
            <select value={value} onChange={(e) => onChange(e.target.value)}>
                <option value="">
                    {optional
                        ? "None — initial baseline"
                        : "Choose an evaluation"}
                </option>
                {catalog.items
                    .filter((item) =>
                        ["run", "repeated_run", "approved_baseline"].includes(
                            item.kind,
                        ),
                    )
                    .map((item) => (
                        <option key={item.path} value={item.path}>
                            {item.path}
                        </option>
                    ))}
            </select>
        </Field>
    );
}

export function ComparePanel({
    catalog,
    onSaved,
}: {
    catalog: Catalog;
    onSaved: (path: string) => void;
}) {
    const [open, setOpen] = useState(false),
        [baseline, setBaseline] = useState(""),
        [candidate, setCandidate] = useState(""),
        [tolerance, setTolerance] = useState(0),
        [path, setPath] = useState("artifacts/comparison-" + uid() + ".json"),
        [error, setError] = useState(""),
        [busy, setBusy] = useState(false);
    async function compare() {
        setBusy(true);
        setError("");
        try {
            await api("compare", {
                baseline,
                candidate,
                max_pass_rate_drop: tolerance,
                report: path,
            });
            onSaved(path);
            setOpen(false);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    return (
        <section className="action-panel">
            <button
                className="panel-toggle"
                onClick={() => setOpen(!open)}
                aria-expanded={open}
            >
                <span>
                    <GitCompareArrows size={18} />
                    <strong>Compare evaluations</strong>
                    <small>
                        Single-run regressions or repeated reliability
                    </small>
                </span>
                {open ? <ChevronDown size={17} /> : <Plus size={17} />}
            </button>
            {open && (
                <div className="panel-body">
                    {error && <ErrorBox error={error} />}
                    <div className="form-grid">
                        <EvaluationSelect
                            label="Baseline"
                            value={baseline}
                            onChange={setBaseline}
                            catalog={catalog}
                        />
                        <EvaluationSelect
                            label="Candidate"
                            value={candidate}
                            onChange={setCandidate}
                            catalog={catalog}
                        />
                        <Field
                            label="Maximum pass-rate drop"
                            hint="Repeated runs only. 0.05 = five percentage points per case/check."
                        >
                            <input
                                type="number"
                                min={0}
                                max={1}
                                step={0.01}
                                value={tolerance}
                                onChange={(e) =>
                                    setTolerance(Number(e.target.value))
                                }
                            />
                        </Field>
                        <Field label="New comparison file">
                            <input
                                value={path}
                                onChange={(e) => setPath(e.target.value)}
                            />
                        </Field>
                    </div>
                    <div className="form-footer">
                        <p>
                            Comparisons read saved evidence and never execute an
                            agent.
                        </p>
                        <Button
                            primary
                            disabled={busy || !baseline || !candidate || !path}
                            onClick={compare}
                        >
                            {busy ? "Comparing…" : "Compare & save"}
                        </Button>
                    </div>
                </div>
            )}
        </section>
    );
}

export function ComparisonView({
    data,
    catalog,
    onOpen,
}: {
    data: Data;
    catalog: Catalog;
    onOpen: (item: Item) => void;
}) {
    const repeated = data.kind === "reliability_comparison";
    return (
        <>
            <div className="comparison-policy">
                <Badge
                    status={
                        data.exit_code === 2
                            ? "incompatible"
                            : data.exit_code
                              ? "blocked"
                              : "passed"
                    }
                />
                <span>
                    Comparison exit code <strong>{data.exit_code}</strong>
                </span>
                {repeated && (
                    <span>
                        Allowed drop:{" "}
                        <strong>
                            {data.policy.max_pass_rate_drop * 100} percentage
                            points
                        </strong>{" "}
                        per case/check
                    </span>
                )}
            </div>
            {data.issues?.map((issue: string, i: number) => (
                <ErrorBox key={i} error={issue} />
            ))}
            <div className="comparison-sides">
                {["baseline", "candidate"].map((side) => (
                    <div key={side}>
                        <h3>{side}</h3>
                        <p className="mono">
                            {repeated
                                ? data[side].agent_revision ||
                                  data[side].report_id
                                : data[side + "_agent_revision"] ||
                                  data[side + "_run_id"]}
                        </p>
                        {!repeated && (
                            <Button
                                quiet
                                onClick={() => {
                                    const item = catalog.items.find(
                                        (i: Item) =>
                                            (i as any).id ===
                                            data[side + "_run_id"],
                                    );
                                    if (item) onOpen(item);
                                }}
                                disabled={
                                    !catalog.items.some(
                                        (i: Item) =>
                                            (i as any).id ===
                                            data[side + "_run_id"],
                                    )
                                }
                            >
                                Open source run
                                <ArrowRight size={14} />
                            </Button>
                        )}
                    </div>
                ))}
            </div>
            <div className="section-heading">
                <h2>Case and check changes</h2>
                <span>{data.cases.length} cases</span>
            </div>
            {data.cases.map((test: Data) => (
                <details className="case-evidence" key={test.id}>
                    <summary>
                        <ChevronRight size={15} />
                        <strong>{test.id}</strong>
                        <Badge status={test.change.replaceAll("_", " ")} />
                    </summary>
                    <div className="case-body">
                        {test.issues.map((issue: string, i: number) => (
                            <ErrorBox error={issue} key={i} />
                        ))}
                        {test.case_rate && (
                            <RateRow label="Whole case" rate={test.case_rate} />
                        )}{" "}
                        {test.checks.map((check: Data) => (
                            <section
                                className="comparison-check"
                                key={check.id}
                            >
                                <div className="section-heading">
                                    <h3>{check.id}</h3>
                                    <Badge
                                        status={check.change.replaceAll(
                                            "_",
                                            " ",
                                        )}
                                    />
                                </div>
                                {repeated ? (
                                    <RateRow label="Check" rate={check} />
                                ) : (
                                    <div className="evidence-pair">
                                        {["baseline", "candidate"].map(
                                            (side) => (
                                                <div key={side}>
                                                    <h4>{side}</h4>
                                                    {check[side] ? (
                                                        <>
                                                            <p>
                                                                {
                                                                    check[side]
                                                                        .message
                                                                }
                                                            </p>
                                                            <Badge
                                                                status={
                                                                    check[side]
                                                                        .passed
                                                                        ? "passed"
                                                                        : "failed"
                                                                }
                                                            />
                                                            <Json
                                                                label="Expected"
                                                                value={
                                                                    check[side]
                                                                        .expected
                                                                }
                                                            />
                                                            <Json
                                                                label="Actual"
                                                                value={
                                                                    check[side]
                                                                        .actual
                                                                }
                                                            />
                                                            {check[side]
                                                                .event_ids
                                                                .length > 0 && (
                                                                <p className="mono">
                                                                    Events:{" "}
                                                                    {check[
                                                                        side
                                                                    ].event_ids.join(
                                                                        ", ",
                                                                    )}
                                                                </p>
                                                            )}
                                                        </>
                                                    ) : (
                                                        <p className="red">
                                                            No verdict; see
                                                            recorded errors.
                                                        </p>
                                                    )}
                                                </div>
                                            ),
                                        )}
                                    </div>
                                )}
                            </section>
                        ))}
                        {["baseline", "candidate"].map((side) =>
                            (test[side + "_errors"] || []).map(
                                (error: Data, i: number) => (
                                    <ErrorBox
                                        key={side + i}
                                        error={`${side} · ${error.source} · ${error.type}: ${error.message}`}
                                    />
                                ),
                            ),
                        )}
                    </div>
                </details>
            ))}
            {repeated ? (
                <>
                    {["baseline", "candidate"].map((side) => (
                        <details className="full-evaluation" key={side}>
                            <summary>
                                Inspect complete {side} evaluation
                            </summary>
                            <EvaluationView data={data[side]} />
                        </details>
                    ))}
                </>
            ) : (
                <p className="evidence-note">
                    Single-run comparisons preserve check evidence and event
                    links. Full traces remain in the source reports.
                </p>
            )}
        </>
    );
}

export function RateRow({ label, rate }: { label: string; rate: Data }) {
    return (
        <div className="rate-row">
            <span>{label}</span>
            <span>
                {rate.baseline.passed}/{rate.baseline.total} (
                {(rate.baseline.pass_rate * 100).toFixed(1)}%)
            </span>
            <ArrowRight size={14} />
            <span>
                {rate.candidate.passed}/{rate.candidate.total} (
                {(rate.candidate.pass_rate * 100).toFixed(1)}%)
            </span>
            <strong className={rate.pass_rate_delta < 0 ? "amber" : "teal"}>
                {rate.pass_rate_delta > 0 ? "+" : ""}
                {(rate.pass_rate_delta * 100).toFixed(1)} pp
            </strong>
            <small>
                Errors {rate.baseline.errors} → {rate.candidate.errors}
            </small>
        </div>
    );
}
