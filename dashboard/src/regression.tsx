import { useEffect, useState } from "react";
import {
    api,
    json,
    parseJSON,
    type Artifact,
    type Catalog,
    type Data,
} from "./api";
import { Button, ErrorBox, Field, Json } from "./components";

export function RegressionDraft({
    artifact,
    catalog,
    onSaved,
    onDirty,
}: {
    artifact: Artifact;
    catalog: Catalog;
    onSaved: (artifact: Artifact) => void;
    onDirty: (dirty: boolean) => void;
}) {
    const [draft, setDraft] = useState(artifact);
    const [text, setText] = useState(json(artifact.data.case));
    const [target, setTarget] = useState<Artifact | null>(null);
    const [destination, setDestination] = useState("suites/regressions.json");
    const [suiteId, setSuiteId] = useState("regressions");
    const [revision, setRevision] = useState("v1");
    const [reviewed, setReviewed] = useState(artifact.data.reviewed);
    const [preview, setPreview] = useState<Data | null>(null);
    const [confirmed, setConfirmed] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const edited =
        text !== json(draft.data.case) || reviewed !== draft.data.reviewed;
    useEffect(() => {
        onDirty(edited);
        return () => onDirty(false);
    }, [edited]);
    useEffect(() => {
        setPreview(null);
        setConfirmed(false);
    }, [text, destination, suiteId, revision, draft]);
    async function perform(action: () => Promise<void>) {
        setBusy(true);
        setError("");
        try {
            await action();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    const source = draft.data.source;
    const original = source.run.cases.find(
        (test: Data) => test.id === source.case_id,
    );
    const body = {
        path: draft.path,
        fingerprint: draft.fingerprint,
        destination,
        expected_fingerprint: target?.fingerprint ?? null,
        suite_id: suiteId,
        revision,
    };
    return (
        <section className="regression-editor">
            <div className="page-heading">
                <div>
                    <h1>Create regression case</h1>
                    <p>
                        {source.path} · {source.case_id}
                        {source.attempt ? ` · attempt ${source.attempt}` : ""}
                    </p>
                </div>
            </div>
            <p>
                Define what the agent should do. The recorded answer is
                reference evidence; expectations start empty.
            </p>
            {error && <ErrorBox error={error} />}
            <details>
                <summary>Original failure evidence</summary>
                <Json value={original} />
            </details>
            <Field
                label="Regression case JSON"
                hint={
                    'Edit the input and add supported assertions, for example: {"id":"answer","type":"output_equals","expected":{"approved":true}}.'
                }
            >
                <textarea
                    className="code-input draft-case-json"
                    value={text}
                    spellCheck={false}
                    onChange={(e) => {
                        setText(e.target.value);
                        setReviewed(false);
                    }}
                />
            </Field>
            <label className="check">
                <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                />
                I reviewed the input and supplied the correct expectations.
            </label>
            <div className="generation-row">
                <Button
                    disabled={busy}
                    onClick={() =>
                        perform(async () => {
                            const result = await api<Artifact>(
                                "regression/review",
                                {
                                    path: draft.path,
                                    fingerprint: draft.fingerprint,
                                    case: parseJSON(text),
                                    reviewed,
                                },
                            );
                            setDraft(result);
                            setText(json(result.data.case));
                            onDirty(false);
                        })
                    }
                >
                    {reviewed ? "Save reviewed case" : "Save draft edits"}
                </Button>
            </div>
            <section className="generation-save">
                <h2>Save to a suite</h2>
                <Field label="Append to an existing suite">
                    <select
                        disabled={busy}
                        value={target?.path ?? ""}
                        onChange={(e) => {
                            const path = e.target.value;
                            if (!path) {
                                setTarget(null);
                                setDestination("suites/regressions.json");
                                setSuiteId("regressions");
                                setRevision("v1");
                                return;
                            }
                            perform(async () => {
                                const next = await api<Artifact>(
                                    "artifact?path=" + encodeURIComponent(path),
                                );
                                setTarget(next);
                                setDestination(path);
                                setSuiteId(next.data.suite?.id ?? "");
                                setRevision("");
                            });
                        }}
                    >
                        <option value="">Create a new suite</option>
                        {catalog.items
                            .filter((item) => item.kind === "suite")
                            .map((item) => (
                                <option key={item.path} value={item.path}>
                                    {item.path}
                                </option>
                            ))}
                    </select>
                </Field>
                <div className="generation-row">
                    <Field label="Suite destination">
                        <input
                            disabled={!!target}
                            value={destination}
                            onChange={(e) => setDestination(e.target.value)}
                        />
                    </Field>
                    {(!target || target.data.suite) && (
                        <>
                            <Field label="Suite ID">
                                <input
                                    disabled={!!target}
                                    value={suiteId}
                                    onChange={(e) => setSuiteId(e.target.value)}
                                />
                            </Field>
                            <Field
                                label="Suite revision"
                                hint={
                                    target
                                        ? `Use a revision different from ${target.data.suite.revision}`
                                        : "For example: v1"
                                }
                            >
                                <input
                                    value={revision}
                                    onChange={(e) =>
                                        setRevision(e.target.value)
                                    }
                                />
                            </Field>
                        </>
                    )}
                </div>
                <Button
                    disabled={busy || edited || !draft.data.reviewed}
                    onClick={() =>
                        perform(async () =>
                            setPreview(
                                await api<Data>("regression/preview", body),
                            ),
                        )
                    }
                >
                    Preview suite changes
                </Button>
                {preview && (
                    <>
                        <Json label="Resulting suite" value={preview} />
                        <label className="check">
                            <input
                                type="checkbox"
                                checked={confirmed}
                                onChange={(e) => setConfirmed(e.target.checked)}
                            />
                            I reviewed the resulting suite and destination.
                        </label>
                        <Button
                            primary
                            disabled={busy || !confirmed || edited}
                            onClick={() =>
                                perform(async () => {
                                    const saved = await api<Artifact>(
                                        "regression/publish",
                                        { ...body, confirmed: true },
                                    );
                                    onDirty(false);
                                    onSaved(saved);
                                })
                            }
                        >
                            Save reviewed suite
                        </Button>
                    </>
                )}
            </section>
            <p className="evidence-note">
                The draft retains the original run and review separately. Saving
                a suite does not run an agent or approve a baseline.
            </p>
        </section>
    );
}
