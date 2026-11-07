import { useEffect, useMemo, useState } from "react";
import { api, type Artifact, type Catalog, type Data, type Item } from "./api";
import { Badge, Button, ErrorBox, Field } from "./components";

type ReviewLabel = {
    case_id: string;
    attempt: number | null;
    verdict: string;
    notes: string;
    tags: string[];
};

function key(caseId: string, attempt: number | null) {
    return JSON.stringify([caseId, attempt]);
}

function parseTags(value: string): string[] {
    return value
        .split(",")
        .map((tag) => tag.trim())
        .filter((tag, index, all) => !!tag && all.indexOf(tag) === index);
}

function tagTextFor(reviews: ReviewLabel[]): Record<string, string> {
    return Object.fromEntries(
        reviews.map((review) => [
            key(review.case_id, review.attempt),
            review.tags.join(", "),
        ]),
    );
}

function sourceCases(
    artifact: Artifact,
): { id: string; attempt: number | null }[] {
    if (artifact.kind === "repeated_run")
        return artifact.data.runs.flatMap((run: Data, index: number) =>
            run.cases.map((test: Data) => ({
                id: test.id,
                attempt: index + 1,
            })),
        );
    return artifact.data.cases.map((test: Data) => ({
        id: test.id,
        attempt: null,
    }));
}

export function ResultReviewEditor({
    artifact,
    onSaved,
    onDirty = () => {},
}: {
    artifact: Artifact;
    onSaved: (artifact: Artifact) => void;
    onDirty?: (dirty: boolean) => void;
}) {
    const entries = useMemo(() => sourceCases(artifact), [artifact]);
    const [reviewPath, setReviewPath] = useState("");
    const [reviewFingerprint, setReviewFingerprint] = useState<string | null>(
        null,
    );
    const [labels, setLabels] = useState<Record<string, ReviewLabel>>({});
    const [tagText, setTagText] = useState<Record<string, string>>({});
    const [savedReviews, setSavedReviews] = useState<ReviewLabel[]>([]);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [loaded, setLoaded] = useState(false);
    const reviews = Object.values(labels)
        .filter((item) => item.verdict)
        .map((item) => ({
            ...item,
            tags: parseTags(
                tagText[key(item.case_id, item.attempt)] ??
                    item.tags.join(", "),
            ),
        }));
    const edited = JSON.stringify(reviews) !== JSON.stringify(savedReviews);
    useEffect(() => {
        onDirty(edited);
        return () => onDirty(false);
    }, [edited]);
    useEffect(() => {
        let alive = true;
        setLoaded(false);
        api<Data>("result-reviews?path=" + encodeURIComponent(artifact.path))
            .then((result) => {
                if (!alive) return;
                setReviewPath(result.path);
                setReviewFingerprint(result.fingerprint);
                setLabels(
                    Object.fromEntries(
                        result.data.reviews.map((review: ReviewLabel) => [
                            key(review.case_id, review.attempt),
                            review,
                        ]),
                    ),
                );
                setTagText(tagTextFor(result.data.reviews));
                setSavedReviews(result.data.reviews);
                setError("");
            })
            .catch((e) => alive && setError(e.message))
            .finally(() => alive && setLoaded(true));
        return () => {
            alive = false;
        };
    }, [artifact.path, artifact.fingerprint]);

    function update(
        caseId: string,
        attempt: number | null,
        patch: Partial<ReviewLabel>,
    ) {
        const id = key(caseId, attempt);
        setLabels((current) => ({
            ...current,
            [id]: {
                ...(current[id] || {
                    case_id: caseId,
                    attempt,
                    verdict: "",
                    notes: "",
                    tags: [],
                }),
                ...patch,
            },
        }));
    }

    async function save() {
        setBusy(true);
        setError("");
        try {
            const result = await api<Artifact>("result-reviews", {
                path: artifact.path,
                fingerprint: artifact.fingerprint,
                review_path: reviewPath,
                review_fingerprint: reviewFingerprint,
                reviews,
            });
            setLabels(
                Object.fromEntries(
                    result.data.reviews.map((review: ReviewLabel) => [
                        key(review.case_id, review.attempt),
                        review,
                    ]),
                ),
            );
            setTagText(tagTextFor(result.data.reviews));
            setSavedReviews(result.data.reviews);
            setReviewPath(result.path);
            setReviewFingerprint(result.fingerprint);
            onSaved(artifact);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <section className="result-review-editor" aria-label="Review labels">
            <div className="section-heading">
                <div>
                    <h2>Review labels</h2>
                    <p>
                        Labels and notes are saved separately from the run and
                        never change its checks or gate result.
                    </p>
                </div>
                <Badge status={reviewFingerprint ? "reviewed" : "unreviewed"} />
            </div>
            {error && <ErrorBox error={error} />}
            {!loaded ? (
                <p role="status">Loading review labels…</p>
            ) : (
                <>
                    <div className="result-review-list">
                        {entries.map((entry) => {
                            const id = key(entry.id, entry.attempt);
                            const value = labels[id] || {
                                case_id: entry.id,
                                attempt: entry.attempt,
                                verdict: "",
                                notes: "",
                                tags: [],
                            };
                            const heading = entry.attempt
                                ? `${entry.id} · attempt ${entry.attempt}`
                                : entry.id;
                            return (
                                <details className="result-review-row" key={id}>
                                    <summary>
                                        <strong>{heading}</strong>
                                        {value.verdict ? (
                                            <Badge status={value.verdict} />
                                        ) : (
                                            <span className="muted">
                                                Not labeled
                                            </span>
                                        )}
                                    </summary>
                                    <div className="result-review-fields">
                                        <Field label="Verdict">
                                            <select
                                                aria-label={`Review verdict for ${heading}`}
                                                value={value.verdict}
                                                onChange={(event) =>
                                                    update(
                                                        entry.id,
                                                        entry.attempt,
                                                        {
                                                            verdict:
                                                                event.target
                                                                    .value,
                                                        },
                                                    )
                                                }
                                            >
                                                <option value="">
                                                    No label
                                                </option>
                                                <option value="good">
                                                    Good
                                                </option>
                                                <option value="bad">Bad</option>
                                                <option value="needs_review">
                                                    Needs review
                                                </option>
                                            </select>
                                        </Field>
                                        <Field label="Failure tags">
                                            <input
                                                aria-label={`Failure tags for ${heading}`}
                                                value={
                                                    tagText[id] ??
                                                    value.tags.join(", ")
                                                }
                                                onChange={(event) =>
                                                    setTagText((current) => ({
                                                        ...current,
                                                        [id]: event.target
                                                            .value,
                                                    }))
                                                }
                                                placeholder="wrong-tool, policy-gap"
                                                disabled={!value.verdict}
                                            />
                                        </Field>
                                        <Field label="Notes">
                                            <textarea
                                                aria-label={`Review notes for ${heading}`}
                                                maxLength={4000}
                                                value={value.notes}
                                                onChange={(event) =>
                                                    update(
                                                        entry.id,
                                                        entry.attempt,
                                                        {
                                                            notes: event.target
                                                                .value,
                                                        },
                                                    )
                                                }
                                                placeholder="What should someone know about this result?"
                                                disabled={!value.verdict}
                                            />
                                        </Field>
                                    </div>
                                </details>
                            );
                        })}
                    </div>
                    <div className="generation-row">
                        <Button
                            primary
                            disabled={busy || !edited}
                            onClick={save}
                        >
                            {busy ? "Saving labels…" : "Save review labels"}
                        </Button>
                        {reviewPath && (
                            <small className="mono">
                                Saved separately at {reviewPath}
                            </small>
                        )}
                    </div>
                </>
            )}
        </section>
    );
}

export function ResultReviewsArtifact({
    artifact,
    catalog,
    onOpen,
}: {
    artifact: Artifact;
    catalog: Catalog;
    onOpen: (item: Item) => void;
}) {
    const source = artifact.data.source;
    const sourceItem = catalog.items.find(
        (item) =>
            item.path === source.path &&
            item.fingerprint === source.fingerprint &&
            item.kind === source.kind &&
            item.id === source.id,
    );
    return (
        <section className="page-content">
            <div className="page-heading">
                <div>
                    <h1>Review labels</h1>
                    <p>
                        Separate human notes for {source.kind} {source.id}.
                    </p>
                </div>
            </div>
            <p>
                Source: <span className="mono">{source.path}</span>
            </p>
            <Button
                disabled={!sourceItem}
                onClick={() => sourceItem && onOpen(sourceItem)}
            >
                {sourceItem
                    ? "Open saved result"
                    : "Source result is unavailable"}
            </Button>
            <div className="result-review-list">
                {artifact.data.reviews.map((review: ReviewLabel) => (
                    <article
                        className="result-review-row result-review-summary"
                        key={key(review.case_id, review.attempt)}
                    >
                        <div className="section-heading">
                            <strong>
                                {review.case_id}
                                {review.attempt
                                    ? ` · attempt ${review.attempt}`
                                    : ""}
                            </strong>
                            <Badge status={review.verdict} />
                        </div>
                        {!!review.tags.length && (
                            <p className="review-tags">
                                {review.tags.map((tag) => (
                                    <span className="tag" key={tag}>
                                        {tag}
                                    </span>
                                ))}
                            </p>
                        )}
                        {review.notes && <p>{review.notes}</p>}
                    </article>
                ))}
                {!artifact.data.reviews.length && (
                    <p className="muted">No cases have review labels yet.</p>
                )}
            </div>
        </section>
    );
}
