import { ChevronDown, Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api, type Artifact, type Catalog, type Data, type Item } from "./api";
import { EvaluationSelect } from "./comparisons";
import { Button, Copy, ErrorBox, Field, Json, uid } from "./components";
import { EvaluationView } from "./evaluations";
export function ReviewPanel({
    catalog,
    onSaved,
    initiallyOpen = false,
}: {
    catalog: Catalog;
    initiallyOpen?: boolean;
    onSaved: (artifact: Artifact) => void;
}) {
    const [open, setOpen] = useState(initiallyOpen),
        [baseline, setBaseline] = useState(""),
        [candidate, setCandidate] = useState(""),
        [path, setPath] = useState("artifacts/review-" + uid() + ".json"),
        [error, setError] = useState(""),
        [busy, setBusy] = useState(false);
    async function review() {
        setBusy(true);
        setError("");
        try {
            onSaved(
                await api<Artifact>("review", {
                    baseline,
                    candidate,
                    report: path,
                }),
            );
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
                    <ShieldCheck size={18} />
                    <strong>Review a baseline update</strong>
                    <small>Inspect changes before accepting evidence</small>
                </span>
                {open ? <ChevronDown size={17} /> : <Plus size={17} />}
            </button>
            {open && (
                <div className="panel-body">
                    {error && <ErrorBox error={error} />}
                    <div className="form-grid">
                        <EvaluationSelect
                            label="Current baseline (optional)"
                            optional
                            value={baseline}
                            onChange={setBaseline}
                            catalog={catalog}
                        />
                        <EvaluationSelect
                            label="Proposed evaluation"
                            value={candidate}
                            onChange={setCandidate}
                            catalog={catalog}
                        />
                        <Field label="New review file">
                            <input
                                value={path}
                                onChange={(e) => setPath(e.target.value)}
                            />
                        </Field>
                    </div>
                    <div className="form-footer">
                        <p>
                            Every attempt and available trace is preserved in
                            the review.
                        </p>
                        <Button
                            primary
                            disabled={busy || !candidate || !path}
                            onClick={review}
                        >
                            {busy ? "Reviewing…" : "Create review"}
                        </Button>
                    </div>
                </div>
            )}
        </section>
    );
}

export function BaselineView({
    artifact,
    catalog,
    onSaved,
}: {
    artifact: Artifact;
    catalog: Catalog;
    onSaved: (artifact: Artifact) => void;
}) {
    const approved = artifact.kind === "approved_baseline",
        review = approved ? artifact.data.review : artifact.data;
    const baselineId = review.baseline?.report_id || review.baseline?.run_id;
    const [destination, setDestination] = useState(
        catalog.items.find((item: Item) => (item as any).id === baselineId)
            ?.path || "baselines/approved-" + uid() + ".json",
    );
    const [reviewer, setReviewer] = useState(""),
        [reason, setReason] = useState(""),
        [accepted, setAccepted] = useState(false),
        [reviewed, setReviewed] = useState(false),
        [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    async function approve() {
        setBusy(true);
        setError("");
        try {
            onSaved(
                await api<Artifact>("approve", {
                    review: artifact.path,
                    baseline: destination,
                    review_digest: artifact.review_digest,
                    reviewer,
                    reason,
                    accept_failures: accepted,
                }),
            );
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    return (
        <>
            {approved && (
                <div className="approval-receipt">
                    <ShieldCheck size={22} />
                    <div>
                        <h2>Reviewed and approved</h2>
                        <p>
                            {artifact.data.reviewer} · {artifact.data.reason}
                        </p>
                        <small>
                            {artifact.data.accepted_failures
                                ? "Failed expectations were explicitly acknowledged."
                                : "No failure acknowledgement was required."}
                        </small>
                    </div>
                </div>
            )}
            <dl className="metadata">
                <div>
                    <dt>Review digest (SHA-256)</dt>
                    <dd className="mono hash">
                        {artifact.review_digest}
                        <Copy value={artifact.review_digest || ""} />
                    </dd>
                </div>
                <div>
                    <dt>Transition</dt>
                    <dd>
                        {review.baseline
                            ? "Baseline replacement"
                            : "Initial baseline"}
                    </dd>
                </div>
            </dl>
            {review.blockers.map((blocker: string, i: number) => (
                <ErrorBox key={i} error={blocker} />
            ))}
            <div className="section-heading">
                <h2>What changed</h2>
                <span>{review.changes.length} contract / settings changes</span>
            </div>
            {review.changes.map((change: Data, i: number) => (
                <section className="contract-change" key={i}>
                    <h3>
                        {change.scope.replaceAll("_", " ")}
                        {change.case_id ? " · " + change.case_id : ""}
                        {change.check_id ? " / " + change.check_id : ""}
                    </h3>
                    <div className="evidence-pair">
                        <Json label="Before" value={change.before} />
                        <Json label="After" value={change.after} />
                    </div>
                </section>
            ))}
            {!review.changes.length && (
                <p className="evidence-note">
                    No declared contract changes. Inspect the new outcomes
                    before accepting them.
                </p>
            )}
            {["baseline", "candidate"].map(
                (side) =>
                    review[side] && (
                        <details
                            className="full-evaluation"
                            key={side}
                            open={side === "candidate"}
                        >
                            <summary>
                                Inspect {side} evaluation and evidence
                            </summary>
                            <EvaluationView data={review[side]} />
                        </details>
                    ),
            )}
            {!approved && (
                <section className="approval-form">
                    <h2>Approve this reviewed evidence</h2>
                    <p>
                        The saved baseline will contain this complete review and
                        your acknowledgement.
                    </p>
                    {error && <ErrorBox error={error} />}
                    <div className="form-grid">
                        <Field
                            label="Baseline destination"
                            hint={
                                review.baseline
                                    ? "Choose the existing baseline included in this review. Changed evidence will be refused."
                                    : "Choose a new file for the initial baseline."
                            }
                        >
                            <input
                                value={destination}
                                onChange={(e) => setDestination(e.target.value)}
                            />
                        </Field>
                        <Field label="Reviewer">
                            <input
                                value={reviewer}
                                onChange={(e) => setReviewer(e.target.value)}
                                placeholder="Your name"
                            />
                        </Field>
                        <Field label="Reason">
                            <input
                                value={reason}
                                onChange={(e) => setReason(e.target.value)}
                                placeholder="Why is this baseline being accepted?"
                            />
                        </Field>
                    </div>
                    {review.has_failures && (
                        <label className="checkbox warning">
                            <input
                                type="checkbox"
                                checked={accepted}
                                onChange={(e) => setAccepted(e.target.checked)}
                            />
                            I inspected and accept the failed expectations. They
                            will remain visible.
                        </label>
                    )}
                    <label className="checkbox">
                        <input
                            type="checkbox"
                            checked={reviewed}
                            onChange={(e) => setReviewed(e.target.checked)}
                        />
                        I reviewed the changes and evaluation evidence above.
                    </label>
                    <div className="form-footer">
                        <p>
                            {review.blockers.length
                                ? "Resolve all blockers before approval."
                                : "Approval saves locally. Commit the baseline through your normal pull request."}
                        </p>
                        <Button
                            primary
                            disabled={
                                busy ||
                                !reviewed ||
                                !reviewer.trim() ||
                                !reason.trim() ||
                                !!review.blockers.length ||
                                (review.has_failures && !accepted)
                            }
                            onClick={approve}
                        >
                            <ShieldCheck size={15} />
                            {busy ? "Approving…" : "Approve baseline"}
                        </Button>
                    </div>
                </section>
            )}
        </>
    );
}
