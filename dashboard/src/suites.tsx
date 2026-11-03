import { Plus, Save, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, json, parseJSON, type Artifact, type Data } from "./api";
import { Badge, Button, ErrorBox, Field, titlePath, uid } from "./components";
const emptySuite = {
    schema_version: 2,
    suite: { id: "my-agent", revision: "v1" },
    cases: [
        {
            id: "first-case",
            input: { message: "hello" },
            assertions: [
                {
                    id: "answer",
                    type: "output_equals",
                    expected: { message: "hello" },
                },
            ],
        },
    ],
};
const types = [
    "output_equals",
    "output_has_keys",
    "tool_called",
    "tool_not_called",
    "tool_arguments_match",
];
export function JsonInput({
    label,
    value,
    onChange,
    onValid,
}: {
    label: string;
    value: unknown;
    onChange: (value: any) => void;
    onValid: (valid: boolean) => void;
}) {
    const [text, setText] = useState(json(value)),
        [error, setError] = useState("");
    useEffect(() => {
        setText(json(value));
        setError("");
        onValid(true);
    }, [json(value)]);
    return (
        <Field label={label}>
            <textarea
                aria-label={label}
                className={"code-input " + (error ? "invalid" : "")}
                aria-invalid={!!error}
                value={text}
                rows={4}
                spellCheck={false}
                onChange={(e) => {
                    setText(e.target.value);
                    try {
                        const parsed = parseJSON(e.target.value);
                        setError("");
                        onValid(true);
                        onChange(parsed);
                    } catch {
                        setError("Enter valid JSON");
                        onValid(false);
                    }
                }}
            />
            {error && <small className="red">{error}</small>}
        </Field>
    );
}

export function SuiteEditor({
    artifact,
    onSaved,
    onDirty,
}: {
    artifact?: Artifact;
    onDirty: (dirty: boolean) => void;
    onSaved: (artifact: Artifact) => void;
}) {
    const [text, setText] = useState(json(artifact?.data || emptySuite)),
        [path, setPath] = useState(artifact?.path || "cases.json"),
        [tab, setTab] = useState("form");
    const [error, setError] = useState(""),
        [busy, setBusy] = useState(false),
        [invalid, setInvalid] = useState<Record<string, boolean>>({}),
        [saved, setSaved] = useState(false);
    const stable = useRef<{
        cases: string[];
        checks: Record<string, string[]>;
    }>({ cases: [], checks: {} });
    function caseKey(index: number): string {
        return (stable.current.cases[index] ||= uid());
    }
    function checkKey(index: number, check: number): string {
        const key = caseKey(index),
            list = (stable.current.checks[key] ||= []);
        return key + ":" + (list[check] ||= uid());
    }
    function clearCase(index: number) {
        const key = caseKey(index);
        stable.current.cases.splice(index, 1);
        delete stable.current.checks[key];
        setInvalid((current) =>
            Object.fromEntries(
                Object.entries(current).filter(
                    ([name]) => !name.startsWith(key + ":"),
                ),
            ),
        );
    }
    function clearCheck(index: number, check: number) {
        const key = checkKey(index, check);
        stable.current.checks[caseKey(index)].splice(check, 1);
        setInvalid((current) =>
            Object.fromEntries(
                Object.entries(current).filter(([name]) => name !== key),
            ),
        );
    }
    let data: Data | null = null;
    try {
        data = parseJSON(text);
    } catch {}
    const original = artifact?.data;
    const changed =
        text !== json(original || emptySuite) ||
        Object.values(invalid).some(Boolean);
    useEffect(() => {
        onDirty(changed);
        const listener = (event: BeforeUnloadEvent) => {
            if (changed) {
                event.preventDefault();
                event.returnValue = "";
            }
        };
        window.addEventListener("beforeunload", listener);
        return () => {
            window.removeEventListener("beforeunload", listener);
            onDirty(false);
        };
    }, [changed]);
    function change(next: Data) {
        setText(json(next));
        setSaved(false);
        setError("");
    }
    function validity(key: string, valid: boolean) {
        setInvalid((current) => ({ ...current, [key]: !valid }));
    }
    function caseChange(index: number, next: Data) {
        if (data)
            change({
                ...data,
                cases: data.cases.map((item: Data, i: number) =>
                    i === index ? next : item,
                ),
            });
    }
    async function save() {
        setBusy(true);
        setError("");
        try {
            if (!data) throw new Error("Fix the JSON before saving.");
            const result = await api<Artifact>(
                "suite",
                {
                    path,
                    data,
                    fingerprint:
                        artifact && path === artifact.path
                            ? artifact.fingerprint
                            : null,
                },
                "PUT",
            );
            setSaved(true);
            onDirty(false);
            onSaved(result);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    }
    return (
        <>
            <div className="page-heading">
                <div>
                    <div className="title-with-badge">
                        <h1>
                            {artifact?.data.suite?.id ||
                                (artifact
                                    ? "Test suite"
                                    : "Create a test suite")}
                        </h1>
                        {changed && <Badge status="unsaved" />}
                    </div>
                    <p>
                        Define expected behavior. Validate and save before
                        running.
                    </p>
                </div>
                <div className="segmented" aria-label="Editor view">
                    <button
                        className={tab === "form" ? "selected" : ""}
                        onClick={() => {
                            if (!data)
                                setError(
                                    "Fix the JSON before opening form view.",
                                );
                            else setTab("form");
                        }}
                    >
                        Form
                    </button>
                    <button
                        className={tab === "json" ? "selected" : ""}
                        onClick={() => setTab("json")}
                    >
                        JSON
                    </button>
                </div>
            </div>
            {error && <ErrorBox error={error} />}
            <div className="editor-metadata">
                <Field
                    label="Suite file"
                    hint={
                        artifact
                            ? "Use a different path for Save as. Existing reports cannot be overwritten."
                            : "Relative to your selected project folder."
                    }
                >
                    <input
                        value={path}
                        onChange={(e) => setPath(e.target.value)}
                    />
                </Field>
                {data?.schema_version === 2 ? (
                    <>
                        <Field label="Suite ID">
                            <input
                                value={data.suite?.id || ""}
                                onChange={(e) =>
                                    change({
                                        ...data,
                                        suite: {
                                            ...data.suite,
                                            id: e.target.value,
                                        },
                                    })
                                }
                            />
                        </Field>
                        <Field
                            label="Suite revision"
                            hint="Change this when inputs, cases, or checks change."
                        >
                            <input
                                value={data.suite?.revision || ""}
                                onChange={(e) =>
                                    change({
                                        ...data,
                                        suite: {
                                            ...data.suite,
                                            revision: e.target.value,
                                        },
                                    })
                                }
                            />
                        </Field>
                    </>
                ) : (
                    <Button
                        onClick={() =>
                            data &&
                            change({
                                ...data,
                                schema_version: 2,
                                suite: {
                                    id: titlePath(path).replace(".json", ""),
                                    revision: "v1",
                                },
                            })
                        }
                    >
                        Add suite identity & revision
                    </Button>
                )}
            </div>
            {tab === "json" ? (
                <Field label="Suite JSON">
                    <textarea
                        className="full-json code-input"
                        spellCheck={false}
                        value={text}
                        onChange={(e) => {
                            setText(e.target.value);
                            setInvalid({});
                            setSaved(false);
                        }}
                    />
                </Field>
            ) : data && Array.isArray(data.cases) ? (
                <div className="suite-cases">
                    {data.cases.map((test: Data, index: number) => (
                        <section className="case-editor" key={caseKey(index)}>
                            <div className="case-editor-heading">
                                <h2>Case {index + 1}</h2>
                                <Button
                                    quiet
                                    onClick={() => {
                                        change({
                                            ...data,
                                            cases: data!.cases.filter(
                                                (_: Data, i: number) =>
                                                    i !== index,
                                            ),
                                        });
                                        clearCase(index);
                                    }}
                                >
                                    <X size={14} />
                                    Remove case
                                </Button>
                            </div>
                            <Field label="Case ID">
                                <input
                                    value={test.id || ""}
                                    onChange={(e) =>
                                        caseChange(index, {
                                            ...test,
                                            id: e.target.value,
                                        })
                                    }
                                />
                            </Field>
                            <JsonInput
                                label="Input"
                                value={test.input}
                                onChange={(input) =>
                                    caseChange(index, { ...test, input })
                                }
                                onValid={(valid) =>
                                    validity(caseKey(index) + ":input", valid)
                                }
                            />
                            <div className="section-heading">
                                <h3>Assertions</h3>
                                <Button
                                    quiet
                                    onClick={() =>
                                        caseChange(index, {
                                            ...test,
                                            assertions: [
                                                ...(test.assertions || []),
                                                {
                                                    id: "check-" + uid(),
                                                    type: "output_equals",
                                                    expected: null,
                                                },
                                            ],
                                        })
                                    }
                                >
                                    <Plus size={14} />
                                    Add check
                                </Button>
                            </div>
                            {(test.assertions || []).map(
                                (check: Data, ci: number) => (
                                    <div
                                        className="check-editor"
                                        key={checkKey(index, ci)}
                                    >
                                        <div className="check-fields">
                                            <Field label="Check ID">
                                                <input
                                                    value={check.id || ""}
                                                    onChange={(e) =>
                                                        caseChange(index, {
                                                            ...test,
                                                            assertions:
                                                                test.assertions.map(
                                                                    (
                                                                        a: Data,
                                                                        i: number,
                                                                    ) =>
                                                                        i === ci
                                                                            ? {
                                                                                  ...a,
                                                                                  id: e
                                                                                      .target
                                                                                      .value,
                                                                              }
                                                                            : a,
                                                                ),
                                                        })
                                                    }
                                                />
                                            </Field>
                                            <Field label="Check type">
                                                <select
                                                    value={check.type}
                                                    onChange={(e) => {
                                                        const type =
                                                            e.target.value;
                                                        const next = {
                                                            id: check.id,
                                                            type,
                                                            ...(type ===
                                                            "output_equals"
                                                                ? {
                                                                      expected:
                                                                          null,
                                                                  }
                                                                : type ===
                                                                    "output_has_keys"
                                                                  ? {
                                                                        keys: [
                                                                            "field",
                                                                        ],
                                                                    }
                                                                  : {
                                                                        tool: "tool_name",
                                                                        ...(type ===
                                                                        "tool_arguments_match"
                                                                            ? {
                                                                                  expected:
                                                                                      {
                                                                                          argument:
                                                                                              "value",
                                                                                      },
                                                                              }
                                                                            : {}),
                                                                    }),
                                                        };
                                                        validity(
                                                            checkKey(index, ci),
                                                            true,
                                                        );
                                                        caseChange(index, {
                                                            ...test,
                                                            assertions:
                                                                test.assertions.map(
                                                                    (
                                                                        a: Data,
                                                                        i: number,
                                                                    ) =>
                                                                        i === ci
                                                                            ? next
                                                                            : a,
                                                                ),
                                                        });
                                                    }}
                                                >
                                                    {types.map((t) => (
                                                        <option key={t}>
                                                            {t}
                                                        </option>
                                                    ))}
                                                </select>
                                            </Field>
                                            <button
                                                className="icon-button"
                                                aria-label={
                                                    "Remove " + check.id
                                                }
                                                onClick={() => {
                                                    caseChange(index, {
                                                        ...test,
                                                        assertions:
                                                            test.assertions.filter(
                                                                (
                                                                    _: Data,
                                                                    i: number,
                                                                ) => i !== ci,
                                                            ),
                                                    });
                                                    clearCheck(index, ci);
                                                }}
                                            >
                                                <X size={16} />
                                            </button>
                                        </div>
                                        {check.type.startsWith("tool_") && (
                                            <Field label="Tool name">
                                                <input
                                                    value={check.tool || ""}
                                                    onChange={(e) =>
                                                        caseChange(index, {
                                                            ...test,
                                                            assertions:
                                                                test.assertions.map(
                                                                    (
                                                                        a: Data,
                                                                        i: number,
                                                                    ) =>
                                                                        i === ci
                                                                            ? {
                                                                                  ...a,
                                                                                  tool: e
                                                                                      .target
                                                                                      .value,
                                                                              }
                                                                            : a,
                                                                ),
                                                        })
                                                    }
                                                />
                                            </Field>
                                        )}
                                        {check.type === "output_has_keys" ? (
                                            <Field
                                                label="Required output keys"
                                                hint="Separate top-level field names with commas."
                                            >
                                                <input
                                                    value={(
                                                        check.keys || []
                                                    ).join(", ")}
                                                    onChange={(e) =>
                                                        caseChange(index, {
                                                            ...test,
                                                            assertions:
                                                                test.assertions.map(
                                                                    (
                                                                        a: Data,
                                                                        i: number,
                                                                    ) =>
                                                                        i === ci
                                                                            ? {
                                                                                  ...a,
                                                                                  keys: e.target.value
                                                                                      .split(
                                                                                          ",",
                                                                                      )
                                                                                      .map(
                                                                                          (
                                                                                              v,
                                                                                          ) =>
                                                                                              v.trim(),
                                                                                      ),
                                                                              }
                                                                            : a,
                                                                ),
                                                        })
                                                    }
                                                />
                                            </Field>
                                        ) : check.type.includes("equals") ||
                                          check.type ===
                                              "tool_arguments_match" ? (
                                            <JsonInput
                                                label={
                                                    check.type ===
                                                    "tool_arguments_match"
                                                        ? "Expected tool arguments"
                                                        : "Expected output"
                                                }
                                                value={check.expected}
                                                onValid={(valid) =>
                                                    validity(
                                                        checkKey(index, ci),
                                                        valid,
                                                    )
                                                }
                                                onChange={(expected) =>
                                                    caseChange(index, {
                                                        ...test,
                                                        assertions:
                                                            test.assertions.map(
                                                                (
                                                                    a: Data,
                                                                    i: number,
                                                                ) =>
                                                                    i === ci
                                                                        ? {
                                                                              ...a,
                                                                              expected,
                                                                          }
                                                                        : a,
                                                            ),
                                                    })
                                                }
                                            />
                                        ) : null}
                                    </div>
                                ),
                            )}
                        </section>
                    ))}
                    <Button
                        onClick={() =>
                            change({
                                ...data,
                                cases: [
                                    ...data!.cases,
                                    {
                                        id: "case-" + uid(),
                                        input: {},
                                        assertions: [
                                            {
                                                id: "answer",
                                                type: "output_equals",
                                                expected: {},
                                            },
                                        ],
                                    },
                                ],
                            })
                        }
                    >
                        <Plus size={16} />
                        Add case
                    </Button>
                </div>
            ) : (
                <ErrorBox error="Suite JSON must contain a cases array." />
            )}
            <div className="save-bar">
                <p>
                    {saved
                        ? "Suite saved."
                        : changed
                          ? "Changes have not been saved."
                          : "Saved suites are validated before execution."}
                </p>
                <Button
                    primary
                    onClick={save}
                    disabled={
                        busy || !data || Object.values(invalid).some(Boolean)
                    }
                >
                    <Save size={15} />
                    {busy
                        ? "Validating…"
                        : artifact && path !== artifact.path
                          ? "Save as"
                          : artifact
                            ? "Save changes"
                            : "Create suite"}
                </Button>
            </div>
        </>
    );
}
