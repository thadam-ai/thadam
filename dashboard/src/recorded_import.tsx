import { useRef, useState } from "react";
import { api, json, parseJSON, type Artifact, type Data } from "./api";
import { Button, ErrorBox, Field, Json } from "./components";

type ImportRow = {
    line: number;
    source_id: string;
    record: Data;
    has_expected: boolean;
    valid: boolean;
    errors: string[];
    warnings: string[];
    duplicate_of: number | null;
    duplicate_reasons: string[];
    already_imported: boolean;
};

type ImportPreview = {
    path: string;
    fingerprint: string;
    format: string;
    mapping: Data;
    mask_fields: string[];
    summary: {
        total: number;
        valid: number;
        invalid: number;
        duplicates: number;
        already_imported: number;
    };
    rows: ImportRow[];
};

const exampleMapping = {
    source_id: "id",
    input: "input",
    actual: "output",
    expected: "expected",
    context: "context",
    events: "events",
    tags: "tags",
};

export function RecordedExampleImport({
    onImported,
}: {
    onImported: (artifact: Artifact) => void;
}) {
    const [path, setPath] = useState("");
    const [format, setFormat] = useState("jsonl");
    const [mappingText, setMappingText] = useState(json(exampleMapping));
    const [maskText, setMaskText] = useState("");
    const [preview, setPreview] = useState<ImportPreview | null>(null);
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [acknowledged, setAcknowledged] = useState<Set<number>>(new Set());
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const previewRequest = useRef(0);
    const importing = useRef(false);

    function requestBody() {
        const mapping = parseJSON(mappingText);
        const mask_fields = maskText
            .split(",")
            .map((field) => field.trim())
            .filter(Boolean);
        return { path: path.trim(), format, mapping, mask_fields };
    }

    async function showPreview() {
        const requestId = ++previewRequest.current;
        setBusy(true);
        setError("");
        setPreview(null);
        try {
            const body = requestBody();
            const result = await api<ImportPreview>(
                "recorded-examples/preview",
                body,
            );
            if (requestId !== previewRequest.current) return;
            setPreview(result);
            setAcknowledged(new Set());
            setSelected(
                new Set(
                    result.rows
                        .filter(
                            (row) =>
                                row.valid &&
                                !row.duplicate_reasons.length &&
                                !row.already_imported,
                        )
                        .map((row) => row.line),
                ),
            );
        } catch (e) {
            if (requestId === previewRequest.current)
                setError((e as Error).message);
        } finally {
            if (requestId === previewRequest.current) setBusy(false);
        }
    }

    function toggle(
        setter: (value: Set<number>) => void,
        current: Set<number>,
        line: number,
    ) {
        const next = new Set(current);
        if (next.has(line)) next.delete(line);
        else next.add(line);
        setter(next);
    }

    function changeAcknowledgement(line: number) {
        const next = new Set(acknowledged);
        if (next.has(line)) {
            next.delete(line);
            setSelected((current) => {
                const selectedRows = new Set(current);
                selectedRows.delete(line);
                return selectedRows;
            });
        } else {
            next.add(line);
        }
        setAcknowledged(next);
    }

    function clearPreview() {
        previewRequest.current += 1;
        if (!importing.current) setBusy(false);
        setPreview(null);
        setSelected(new Set());
        setAcknowledged(new Set());
    }

    async function importSelected() {
        if (!preview) return;
        importing.current = true;
        setBusy(true);
        setError("");
        try {
            const result = await api<{ drafts: Artifact[] }>(
                "recorded-examples/import",
                {
                    path: preview.path,
                    format: preview.format,
                    mapping: preview.mapping,
                    mask_fields: preview.mask_fields,
                    fingerprint: preview.fingerprint,
                    selected_rows: Array.from(selected).sort((a, b) => a - b),
                    acknowledged_duplicates: Array.from(acknowledged)
                        .filter((line) => selected.has(line))
                        .sort((a, b) => a - b),
                },
            );
            if (!result.drafts.length)
                throw new Error("No drafts were imported");
            onImported(result.drafts[0]);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            importing.current = false;
            setBusy(false);
        }
    }

    return (
        <section className="recorded-import">
            <div className="page-heading">
                <div>
                    <h1>Import recorded examples</h1>
                    <p>
                        Turn local JSONL or CSV rows into regression drafts.
                        Importing never runs an agent or trusts an expected
                        answer without review.
                    </p>
                </div>
            </div>
            {error && <ErrorBox error={error} />}
            <div className="form-grid">
                <Field
                    label="Examples file"
                    hint="Use a relative path inside this project. Files stay local."
                >
                    <input
                        value={path}
                        onChange={(event) => {
                            setPath(event.target.value);
                            clearPreview();
                        }}
                        placeholder="data/agent-examples.jsonl"
                    />
                </Field>
                <Field label="Format">
                    <select
                        value={format}
                        onChange={(event) => {
                            setFormat(event.target.value);
                            clearPreview();
                        }}
                    >
                        <option value="jsonl">JSONL</option>
                        <option value="csv">CSV</option>
                    </select>
                </Field>
            </div>
            <Field
                label="Field mapping (JSON)"
                hint="Map input plus any source ID, observed output, expected output, context, events, or tags. JSONL paths can use dots or array indexes; CSV mappings use exact header names. CSV cells remain text."
            >
                <textarea
                    className="code-input import-mapping"
                    spellCheck={false}
                    value={mappingText}
                    onChange={(event) => {
                        setMappingText(event.target.value);
                        clearPreview();
                    }}
                />
            </Field>
            <Field
                label="Fields to mask before preview"
                hint="Comma-separated paths in the mapped fields, such as input.customer.email or context.*. Source IDs remain visible for provenance."
            >
                <input
                    value={maskText}
                    onChange={(event) => {
                        setMaskText(event.target.value);
                        clearPreview();
                    }}
                    placeholder="input.customer.email, context.phone"
                />
            </Field>
            <div className="generation-row">
                <Button
                    primary
                    disabled={busy || !path.trim()}
                    onClick={showPreview}
                >
                    {busy ? "Reading examples…" : "Preview rows"}
                </Button>
                <small>
                    Preview applies masks before sending data to the browser.
                    Redaction only covers the paths you select.
                </small>
            </div>

            {preview && (
                <section className="import-preview" aria-label="Import preview">
                    <div className="section-heading">
                        <div>
                            <h2>Review import</h2>
                            <p>
                                {preview.summary.valid} valid ·{" "}
                                {preview.summary.invalid} invalid ·{" "}
                                {preview.summary.duplicates} duplicates ·{" "}
                                {preview.summary.already_imported} already
                                imported
                            </p>
                        </div>
                        <small className="mono">{preview.path}</small>
                    </div>
                    <div className="result-review-list">
                        {preview.rows.map((row) => (
                            <article
                                className="result-review-row"
                                key={row.line}
                            >
                                <div className="section-heading import-row-heading">
                                    <label className="check">
                                        <input
                                            type="checkbox"
                                            aria-label={`Import row ${row.line}`}
                                            checked={selected.has(row.line)}
                                            disabled={
                                                !row.valid ||
                                                row.already_imported ||
                                                (!!row.duplicate_reasons
                                                    .length &&
                                                    !acknowledged.has(row.line))
                                            }
                                            onChange={() =>
                                                toggle(
                                                    setSelected,
                                                    selected,
                                                    row.line,
                                                )
                                            }
                                        />
                                        Row {row.line} · {row.source_id}
                                    </label>
                                    {row.already_imported ? (
                                        <span className="muted">
                                            Already imported
                                        </span>
                                    ) : row.duplicate_reasons.length ? (
                                        <span className="badge review-required">
                                            Duplicate of row {row.duplicate_of}
                                        </span>
                                    ) : !row.valid ? (
                                        <span className="badge error">
                                            Invalid
                                        </span>
                                    ) : (
                                        <span className="badge unreviewed">
                                            Draft
                                        </span>
                                    )}
                                </div>
                                {!!row.duplicate_reasons.length && (
                                    <label className="check import-duplicate-check">
                                        <input
                                            type="checkbox"
                                            aria-label={`Acknowledge duplicate row ${row.line}`}
                                            checked={acknowledged.has(row.line)}
                                            onChange={() =>
                                                changeAcknowledgement(row.line)
                                            }
                                        />
                                        I reviewed this duplicate and want to
                                        import it.
                                    </label>
                                )}
                                {row.errors.map((message) => (
                                    <p className="error-text" key={message}>
                                        {message}
                                    </p>
                                ))}
                                {row.warnings.map((message) => (
                                    <p className="muted" key={message}>
                                        {message}
                                    </p>
                                ))}
                                {row.valid && <Json value={row.record} />}
                            </article>
                        ))}
                    </div>
                    <div className="generation-row">
                        <Button
                            primary
                            disabled={busy || !selected.size}
                            onClick={importSelected}
                        >
                            {busy
                                ? "Importing…"
                                : `Import ${selected.size} selected drafts`}
                        </Button>
                    </div>
                </section>
            )}
        </section>
    );
}
