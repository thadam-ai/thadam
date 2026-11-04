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
export function ArtifactView({
    artifact,
    catalog,
    onOpen,
    onSaved,
}: {
    artifact: Artifact;
    catalog: Catalog;
    onOpen: (item: Item) => void;
    onSaved: (artifact: Artifact) => void;
}) {
    const data = artifact.data;
    const value = evaluation(data);
    return (
        <>
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
                <EvaluationView data={data} />
            )}
        </>
    );
}
