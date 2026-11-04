import { useEffect, useState } from "react";
import { Check, ExternalLink, RefreshCw, WandSparkles, X } from "lucide-react";
import {
    api,
    json,
    parseJSON,
    type Artifact,
    type Catalog,
    type Data,
} from "./api";
import { Badge, Button, ErrorBox, Field, Json, uid } from "./components";

function caseLabel(value: unknown, index: number): string {
    const id = value && typeof value === "object" ? (value as Data).id : null;
    return typeof id === "string" && id.trim() ? id : `Suggestion ${index + 1}`;
}

export function SuggestPanel({
    catalog,
    active,
    onStarted,
    onDirty,
}: {
    catalog: Catalog;
    active: boolean;
    onStarted: (job: Data) => void;
    onDirty: (dirty: boolean) => void;
}) {
    const [connection, setConnection] = useState("chatgpt");
    const [status, setStatus] = useState<Data>({});
    const [key, setKey] = useState("");
    const [models, setModels] = useState<Data[]>([]);
    const [model, setModel] = useState("");
    const [description, setDescription] = useState("");
    const [behavior, setBehavior] = useState("");
    const [examples, setExamples] = useState("[]");
    const [schemas, setSchemas] = useState("{}");
    const [tools, setTools] = useState("[]");
    const [source, setSource] = useState<Artifact | null>(null);
    const [sourcePath, setSourcePath] = useState("");
    const [selected, setSelected] = useState<number[]>([]);
    const [count, setCount] = useState(5);
    const [destination, setDestination] = useState(
        "drafts/suggestions-" + uid() + ".json",
    );
    const [preview, setPreview] = useState<Data | null>(null);
    const [confirmed, setConfirmed] = useState(false);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [loginUrl, setLoginUrl] = useState("");
    const [watchLogin, setWatchLogin] = useState(false);
    const [notice, setNotice] = useState(false);
    const [submitted, setSubmitted] = useState("");
    const formSnapshot = json({
        description,
        behavior,
        examples,
        schemas,
        tools,
        count,
        selected,
        sourcePath,
        connection,
        model,
        destination,
    });
    useEffect(() => {
        onDirty(
            (!!description ||
                !!behavior ||
                examples !== "[]" ||
                schemas !== "{}" ||
                tools !== "[]") &&
                formSnapshot !== submitted,
        );
    }, [formSnapshot, submitted]);
    async function refreshConnection() {
        const next = await api<Data>("providers");
        setStatus(next);
        if (next.chatgpt && next.plan_enabled && !next.plan_notice_ack)
            setNotice(true);
        if (next.signin?.state === "error") {
            setError(next.signin.error);
            setWatchLogin(false);
        }
        if (next.signin?.state === "connected") {
            setWatchLogin(false);
            setLoginUrl("");
        }
    }
    useEffect(() => {
        refreshConnection().catch((e) => setError(e.message));
    }, []);
    useEffect(() => {
        if (!watchLogin) return;
        const timer = setInterval(() => {
            refreshConnection().catch((e) => setError(e.message));
        }, 1000);
        return () => clearInterval(timer);
    }, [watchLogin]);
    useEffect(() => {
        setModels([]);
        setModel("");
    }, [connection, status.chatgpt, status.api_key]);
    useEffect(() => {
        setPreview(null);
        setConfirmed(false);
    }, [
        description,
        behavior,
        examples,
        schemas,
        tools,
        count,
        source,
        selected,
        connection,
        model,
    ]);
    useEffect(() => {
        let alive = true;
        setSource(null);
        setSelected([]);
        if (sourcePath)
            api<Artifact>("artifact?path=" + encodeURIComponent(sourcePath))
                .then((value) => {
                    if (alive) setSource(value);
                })
                .catch((e) => {
                    if (alive) setError(e.message);
                });
        return () => {
            alive = false;
        };
    }, [sourcePath]);
    async function perform(task: () => Promise<void>) {
        setBusy(true);
        setError("");
        try {
            await task();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    const ready =
        connection === "chatgpt" ? status.plan_enabled : status.api_key;
    return (
        <>
            <div className="page-heading">
                <div>
                    <h1>Suggest test cases</h1>
                    <p>
                        Describe the contract. Review every expectation before
                        saving.
                    </p>
                </div>
                <WandSparkles size={18} className="teal" />
            </div>
            {error && <ErrorBox error={error} />}
            <section
                className="generation-connection"
                aria-label="Generation connection"
            >
                <div className="generation-row">
                    <Field label="Use AI through">
                        <select
                            value={connection}
                            onChange={(e) => setConnection(e.target.value)}
                        >
                            <option value="chatgpt">
                                ChatGPT subscription
                            </option>
                            <option value="api_key">OpenAI API key</option>
                        </select>
                    </Field>
                    <div className="connection-caption">
                        <Badge status={ready ? "connected" : "not connected"} />
                        <span>
                            {connection === "chatgpt"
                                ? status.email ||
                                  "Eligible requests use your ChatGPT plan."
                                : "Generation uses your OpenAI API billing."}
                        </span>
                    </div>
                </div>
                {status.available === false && (
                    <p className="amber">
                        AI support is not installed. In your terminal, install{" "}
                        <code>python -m pip install -e '.[ai]'</code>.
                    </p>
                )}
                {connection === "chatgpt" &&
                    status.chatgpt &&
                    !status.plan_enabled && (
                        <p className="amber">
                            Signed in, but ChatGPT plan usage is not enabled.
                            Continue with ChatGPT and authorize plan usage to
                            generate suggestions.
                        </p>
                    )}
                {connection === "chatgpt" ? (
                    <div className="generation-row">
                        <Button
                            disabled={
                                busy || active || status.available === false
                            }
                            onClick={() =>
                                perform(async () => {
                                    const result = await api<Data>(
                                        "providers/chatgpt",
                                        {},
                                    );
                                    setLoginUrl(result.url);
                                    setWatchLogin(true);
                                    window.open(
                                        result.url,
                                        "_blank",
                                        "noopener,noreferrer",
                                    );
                                })
                            }
                        >
                            {watchLogin
                                ? "Waiting for sign-in…"
                                : "Continue with ChatGPT"}
                        </Button>
                        {loginUrl && (
                            <a href={loginUrl} target="_blank" rel="noreferrer">
                                Open sign-in <ExternalLink size={12} />
                            </a>
                        )}
                        {status.chatgpt && (
                            <Button
                                quiet
                                disabled={busy || active}
                                onClick={() =>
                                    perform(async () => {
                                        await api("providers/disconnect", {
                                            connection: "chatgpt",
                                        });
                                        setWatchLogin(false);
                                        await refreshConnection();
                                    })
                                }
                            >
                                Disconnect
                            </Button>
                        )}
                        <a
                            href={
                                status.usage_url ||
                                "https://chatgpt.com/#settings/Usage"
                            }
                            target="_blank"
                            rel="noreferrer"
                        >
                            Manage usage <ExternalLink size={12} />
                        </a>
                    </div>
                ) : (
                    <div className="generation-row">
                        <Field
                            label="API key"
                            hint="Saved privately for your local user, outside this project."
                        >
                            <input
                                type="password"
                                autoComplete="off"
                                value={key}
                                onChange={(e) => setKey(e.target.value)}
                            />
                        </Field>
                        <Button
                            disabled={
                                !key ||
                                busy ||
                                active ||
                                status.available === false
                            }
                            onClick={() =>
                                perform(async () => {
                                    const supplied = key;
                                    setKey("");
                                    await api("providers/api-key", {
                                        key: supplied,
                                    });
                                    await refreshConnection();
                                })
                            }
                        >
                            Connect key
                        </Button>
                        {status.api_key && (
                            <Button
                                quiet
                                disabled={busy || active}
                                onClick={() =>
                                    perform(async () => {
                                        await api("providers/disconnect", {
                                            connection: "api_key",
                                        });
                                        await refreshConnection();
                                    })
                                }
                            >
                                Remove saved key
                            </Button>
                        )}
                        {status.api_key_environment && (
                            <small>
                                OPENAI_API_KEY is available in the server
                                environment; unset it there to disconnect it.
                            </small>
                        )}
                    </div>
                )}
                <div className="generation-row">
                    <Field label="Generation model">
                        <select
                            value={model}
                            disabled={!models.length || busy}
                            onChange={(e) => setModel(e.target.value)}
                        >
                            <option value="">Choose an available model</option>
                            {models.map((x) => (
                                <option key={x.id} value={x.id}>
                                    {x.name}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <Button
                        quiet
                        disabled={!ready || busy || active}
                        onClick={() =>
                            perform(async () => {
                                const list = await api<Data[]>(
                                    "providers/models?connection=" + connection,
                                );
                                setModels(list);
                                if (!list.length)
                                    throw new Error(
                                        "No models are available for this connection.",
                                    );
                            })
                        }
                    >
                        <RefreshCw size={13} /> Load models
                    </Button>
                    {connection === "chatgpt" && ready && (
                        <small className="teal">Using ChatGPT plan</small>
                    )}
                </div>
            </section>
            <div className="generation-fields">
                <Field label="Agent description">
                    <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="What does your agent do?"
                    />
                </Field>
                <Field
                    label="Expected behavior"
                    hint="State the rules that determine a correct answer. Gaps remain incomplete drafts."
                >
                    <textarea
                        value={behavior}
                        onChange={(e) => setBehavior(e.target.value)}
                        placeholder="For example: approve refunds within 30 days when the item is unopened."
                    />
                </Field>
                <Field
                    label="Append to an existing suite"
                    hint="Optional. Its cases are sent only when selected below."
                >
                    <select
                        value={sourcePath}
                        onChange={(e) => setSourcePath(e.target.value)}
                    >
                        <option value="">
                            Create a new suite after review
                        </option>
                        {catalog.items
                            .filter((x) => x.kind === "suite")
                            .map((x) => (
                                <option key={x.path} value={x.path}>
                                    {x.path}
                                </option>
                            ))}
                    </select>
                </Field>
                {source && (
                    <fieldset className="selected-context">
                        <legend>Cases to include as context</legend>
                        {source.data.cases.map((test: Data, i: number) => (
                            <label className="check" key={test.id}>
                                <input
                                    type="checkbox"
                                    checked={selected.includes(i)}
                                    onChange={(e) =>
                                        setSelected(
                                            e.target.checked
                                                ? [...selected, i]
                                                : selected.filter(
                                                      (x) => x !== i,
                                                  ),
                                        )
                                    }
                                />
                                {test.id}
                            </label>
                        ))}
                        <small>
                            {selected.length} selected · the source suite is
                            captured locally for later saving.
                        </small>
                    </fieldset>
                )}
                <Field
                    label="Input/output examples (JSON)"
                    hint='An array of {"input": …, "output": …} examples. Required unless schemas or existing cases supply context.'
                >
                    <textarea
                        className="code-input"
                        spellCheck={false}
                        value={examples}
                        onChange={(e) => setExamples(e.target.value)}
                    />
                </Field>
                <details>
                    <summary>Optional schemas and tool context</summary>
                    <Field label="Input/output schemas (JSON)">
                        <textarea
                            className="code-input"
                            spellCheck={false}
                            value={schemas}
                            onChange={(e) => setSchemas(e.target.value)}
                        />
                    </Field>
                    <Field
                        label="Tool schemas (JSON array)"
                        hint="Context only. Generation never calls these tools."
                    >
                        <textarea
                            className="code-input"
                            spellCheck={false}
                            value={tools}
                            onChange={(e) => setTools(e.target.value)}
                        />
                    </Field>
                </details>
                <div className="generation-row">
                    <Field label="Number of suggestions">
                        <input
                            type="number"
                            min={1}
                            max={20}
                            value={count}
                            onChange={(e) => setCount(Number(e.target.value))}
                        />
                    </Field>
                    <Field label="Draft file">
                        <input
                            value={destination}
                            onChange={(e) => setDestination(e.target.value)}
                        />
                    </Field>
                </div>
                <Button
                    disabled={busy || active || (!!sourcePath && !source)}
                    onClick={() =>
                        perform(async () => {
                            setPreview(
                                await api("generate/preview", {
                                    description,
                                    behavior,
                                    examples: parseJSON(examples),
                                    schemas: parseJSON(schemas),
                                    tool_schemas: parseJSON(tools),
                                    existing_cases: selected.map(
                                        (i) => source!.data.cases[i],
                                    ),
                                    count,
                                }),
                            );
                        })
                    }
                >
                    Preview outgoing context
                </Button>
            </div>
            {preview && (
                <section className="generation-preview">
                    <h2>What will be sent</h2>
                    <p>
                        Only this context and the instructions below go to
                        OpenAI. Review it for private data.
                    </p>
                    <Json value={preview.request} />
                    <details>
                        <summary>Generation instructions</summary>
                        <pre className="wrap-pre">{preview.instructions}</pre>
                    </details>
                    <label className="check">
                        <input
                            type="checkbox"
                            checked={confirmed}
                            onChange={(e) => setConfirmed(e.target.checked)}
                        />
                        I reviewed this context and the selected billing method.
                    </label>
                    <Button
                        primary
                        disabled={
                            !confirmed || !model || !ready || busy || active
                        }
                        onClick={() =>
                            perform(async () => {
                                const job = await api<Data>("generate", {
                                    connection,
                                    model,
                                    request: preview.request,
                                    source: source
                                        ? {
                                              path: source.path,
                                              fingerprint: source.fingerprint,
                                          }
                                        : null,
                                    report: destination,
                                });
                                onStarted(job);
                                setSubmitted(formSnapshot);
                            })
                        }
                    >
                        {busy ? "Starting…" : `Generate ${count} suggestions`}
                    </Button>
                </section>
            )}
            {notice && (
                <div className="plan-notice-backdrop">
                    <section
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="plan-notice-title"
                        className="plan-notice"
                    >
                        <h2 id="plan-notice-title">
                            You’re using your ChatGPT plan
                        </h2>
                        <p>
                            Eligible generation requests use your ChatGPT plan
                            allowance or available credits. Manage app access
                            and usage in ChatGPT settings.
                        </p>
                        <Button
                            primary
                            autoFocus
                            onClick={() =>
                                perform(async () => {
                                    await api("providers/notice", {});
                                    setNotice(false);
                                    await refreshConnection();
                                })
                            }
                        >
                            Got it
                        </Button>
                    </section>
                </div>
            )}
        </>
    );
}

export function DraftReview({
    artifact,
    onUpdated,
    onSaved,
    onDirty,
}: {
    artifact: Artifact;
    onUpdated: (artifact: Artifact) => void;
    onSaved: (artifact: Artifact) => void;
    onDirty: (dirty: boolean) => void;
}) {
    const [index, setIndex] = useState(0);
    const [text, setText] = useState(json(artifact.data.candidates[0].case));
    const [issues, setIssues] = useState<string[][]>([]);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const source = artifact.data.source;
    const [destination, setDestination] = useState(
        source?.path || "suites/reviewed-cases.json",
    );
    const [suiteId, setSuiteId] = useState(
        source?.data.suite?.id || "reviewed-cases",
    );
    const [revision, setRevision] = useState("");
    const [preview, setPreview] = useState<Data | null>(null);
    const [confirmed, setConfirmed] = useState(false);
    const entry = artifact.data.candidates[index];
    const changed = text !== json(entry.case);
    useEffect(() => {
        onDirty(changed);
    }, [changed]);
    useEffect(() => {
        api<string[][]>(
            "draft/issues?path=" + encodeURIComponent(artifact.path),
        )
            .then(setIssues)
            .catch((e) => setError(e.message));
        setPreview(null);
        setConfirmed(false);
    }, [artifact.fingerprint]);
    useEffect(() => {
        setPreview(null);
        setConfirmed(false);
    }, [destination, suiteId, revision, text]);
    async function perform(task: () => Promise<void>) {
        setBusy(true);
        setError("");
        try {
            await task();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    function choose(next: number) {
        if (changed && !window.confirm("Discard unsaved suggestion edits?"))
            return;
        setIndex(next);
        setText(json(artifact.data.candidates[next].case));
        setError("");
    }
    async function review(decision: string) {
        await perform(async () => {
            const saved = await api<Artifact>("draft/review", {
                path: artifact.path,
                fingerprint: artifact.fingerprint,
                index,
                decision,
                case: parseJSON(text),
            });
            setText(json(saved.data.candidates[index].case));
            onDirty(false);
            onUpdated(saved);
        });
    }
    const accepted = artifact.data.candidates.filter(
        (x: Data) => x.decision === "accepted",
    ).length;
    const saveBody = {
        path: artifact.path,
        fingerprint: artifact.fingerprint,
        suite_id: suiteId,
        revision,
    };
    return (
        <>
            <div className="page-heading">
                <div>
                    <h1>Review suggestions</h1>
                    <p>
                        {accepted} accepted · {artifact.data.candidates.length}{" "}
                        proposed · {artifact.data.generation.model}
                    </p>
                </div>
                <Badge status="review required" />
            </div>
            <p>
                AI-generated expectations need your judgment. Accepting a case
                confirms you reviewed its input and checks.
            </p>
            {error && <ErrorBox error={error} />}
            <div className="suite-workspace generation-review">
                <aside className="case-navigator" aria-label="Suggested cases">
                    <div className="case-nav-heading">
                        <h2>Suggestions</h2>
                    </div>
                    <div className="case-nav-list">
                        {artifact.data.candidates.map(
                            (candidate: Data, i: number) => (
                                <button
                                    key={i}
                                    className={
                                        "case-nav-item " +
                                        (i === index ? "selected" : "")
                                    }
                                    aria-pressed={i === index}
                                    onClick={() => choose(i)}
                                >
                                    <div>
                                        <strong>
                                            {caseLabel(candidate.case, i)}
                                        </strong>
                                        <small>
                                            {candidate.original.category} ·{" "}
                                            {candidate.decision}
                                        </small>
                                    </div>
                                </button>
                            ),
                        )}
                    </div>
                </aside>
                <section className="generation-case suite-cases">
                    <div className="generation-row">
                        <h2>{caseLabel(entry.case, index)}</h2>
                        <Badge status={entry.decision} />
                    </div>
                    <p>{entry.original.rationale}</p>
                    {entry.original.uncertainty && (
                        <p className="amber">
                            Needs your judgment: {entry.original.uncertainty}
                        </p>
                    )}
                    {issues[index]?.length > 0 && (
                        <ul className="amber">
                            {issues[index].map((issue) => (
                                <li key={issue}>{issue}</li>
                            ))}
                        </ul>
                    )}
                    <Field
                        label="Proposed case JSON"
                        hint="Edit the input, stable ID and supported assertions. Saving edits resets acceptance."
                    >
                        <textarea
                            className="code-input draft-case-json"
                            spellCheck={false}
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                        />
                    </Field>
                    <div className="generation-row">
                        <Button
                            primary
                            disabled={busy}
                            onClick={() => review("accepted")}
                        >
                            <Check size={13} />
                            Accept reviewed case
                        </Button>
                        <Button
                            disabled={busy}
                            onClick={() => review("pending")}
                        >
                            Save draft edits
                        </Button>
                        <Button
                            quiet
                            disabled={busy}
                            onClick={() => review("discarded")}
                        >
                            <X size={13} />
                            Discard
                        </Button>
                    </div>
                </section>
            </div>
            <section className="generation-save">
                <h2>Save accepted cases to a suite</h2>
                <p>
                    {source
                        ? `Append to the captured ${source.path} suite. Its current file must still match.`
                        : "Create a reusable suite from the cases you accepted."}
                </p>
                <div className="generation-row">
                    <Field label="Suite destination">
                        <input
                            value={destination}
                            onChange={(e) => setDestination(e.target.value)}
                        />
                    </Field>
                    <Field label="Suite ID">
                        <input
                            value={suiteId}
                            disabled={!!source?.data.suite}
                            onChange={(e) => setSuiteId(e.target.value)}
                        />
                    </Field>
                    {(!source || source.data.suite) && (
                        <Field
                            label="Suite revision"
                            hint={
                                source?.data.suite
                                    ? `Must differ from ${source.data.suite.revision}`
                                    : "For example: v1"
                            }
                        >
                            <input
                                value={revision}
                                onChange={(e) => setRevision(e.target.value)}
                            />
                        </Field>
                    )}
                </div>
                <Button
                    disabled={!accepted || busy || changed}
                    onClick={() =>
                        perform(async () => {
                            setPreview(
                                await api<Data>("draft/preview", saveBody),
                            );
                            setConfirmed(false);
                        })
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
                            disabled={!confirmed || busy || changed}
                            onClick={() =>
                                perform(async () => {
                                    const saved = await api<Artifact>(
                                        "draft/publish",
                                        {
                                            ...saveBody,
                                            destination,
                                            expected_fingerprint:
                                                source?.path === destination
                                                    ? source.fingerprint
                                                    : null,
                                        },
                                    );
                                    onSaved(saved);
                                })
                            }
                        >
                            Save reviewed suite
                        </Button>
                    </>
                )}
            </section>
            <details className="generation-history">
                <summary>Generation context and review history</summary>
                <Json
                    value={{
                        created_at: artifact.data.created_at,
                        generation: artifact.data.generation,
                        request: artifact.data.request,
                        reviews: artifact.data.candidates.map((x: Data) => ({
                            original: x.original,
                            reviews: x.reviews,
                        })),
                    }}
                />
            </details>
        </>
    );
}
