import { useState } from "react";
import { api } from "./api";
import { ErrorBox } from "./components";
import { RegressionDraft } from "./regression";
import {
    evaluation,
    kindName,
    outcome,
    type Artifact,
    type Catalog,
    type Item,
} from "./api";
import { BaselineView } from "./baselines";
import { ComparisonView } from "./comparisons";
import { Badge, titlePath } from "./components";
import { EvaluationView } from "./evaluations";
import { ResultReviewEditor, ResultReviewsArtifact } from "./result_reviews";
export function ArtifactView({
    artifact,
    catalog,
    onOpen,
    onSaved,
    onDirty = () => {},
}: {
    artifact: Artifact;
    catalog: Catalog;
    onOpen: (item: Item) => void;
    onSaved: (artifact: Artifact) => void;
    onDirty?: (dirty: boolean) => void;
}) {
    const [error, setError] = useState("");
    const [creating, setCreating] = useState(false);
    async function create(id: string, attempt: number | null) {
        if (creating) return;
        setCreating(true);
        setError("");
        try {
            onSaved(
                await api<Artifact>("regression/create", {
                    path: artifact.path,
                    fingerprint: artifact.fingerprint,
                    case_id: id,
                    attempt,
                }),
            );
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setCreating(false);
        }
    }
    if (artifact.kind === "regression_draft")
        return (
            <RegressionDraft
                artifact={artifact}
                catalog={catalog}
                onSaved={onSaved}
                onDirty={onDirty}
            />
        );
    if (artifact.kind === "result_reviews")
        return (
            <ResultReviewsArtifact
                artifact={artifact}
                catalog={catalog}
                onOpen={onOpen}
            />
        );
    const data = artifact.data;
    const value = evaluation(data);
    return (
        <>
            {error && <ErrorBox error={error} />}
            {creating && <p role="status">Creating regression draft…</p>}
            <div className="page-heading">
                <div>
                    <div className="title-with-badge">
                        <h1>
                            {value.suite?.id ||
                                value.runs?.[0]?.suite?.id ||
                                titlePath(artifact.path)}
                        </h1>
                        {artifact.kind.includes("baseline") && (
                            <Badge
                                status={outcome({
                                    ...artifact,
                                    summary: value.summary,
                                    exit_code: data.exit_code,
                                })}
                            />
                        )}
                    </div>
                    <p className="artifact-path">
                        <span>
                            {kindName[artifact.kind] || "Saved evidence"}
                        </span>
                        <span className="mono">{artifact.path}</span>
                    </p>
                </div>
            </div>
            {["baseline_review", "approved_baseline"].includes(
                artifact.kind,
            ) ? (
                <BaselineView
                    artifact={artifact}
                    catalog={catalog}
                    onSaved={onSaved}
                />
            ) : artifact.kind.includes("comparison") ? (
                <ComparisonView data={data} catalog={catalog} onOpen={onOpen} />
            ) : (
                <>
                    {["run", "repeated_run"].includes(artifact.kind) && (
                        <ResultReviewEditor
                            artifact={artifact}
                            onSaved={() => onSaved(artifact)}
                            onDirty={onDirty}
                        />
                    )}
                    <EvaluationView
                        data={data}
                        onRegression={
                            ["run", "repeated_run"].includes(artifact.kind)
                                ? create
                                : undefined
                        }
                    />
                </>
            )}
        </>
    );
}
