import { ChevronRight, CircleAlert, Plus, Save, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, json, parseJSON, type Artifact, type Data } from "./api";
import { Badge, Button, ErrorBox, Field, titlePath, uid } from "./components";
import { JsonInput } from "./json-input";
import { FixtureEditor } from "./fixtures";
export { JsonInput } from "./json-input";
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
    "tool_call_count",
];
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
        [tab, setTab] = useState("form"),
        [selectedCase, setSelectedCase] = useState(0);
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
    useEffect(() => {
        if (Array.isArray(data?.cases))
            setSelectedCase((current) =>
                Math.min(current, Math.max(0, data!.cases.length - 1)),
            );
    }, [data?.cases?.length]);
    const original = artifact?.data;
    const changed =
        text !== json(original || emptySuite) ||
        path !== (artifact?.path || "cases.json") ||
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
                        {data?.cases?.length ?? 0} cases ·{" "}
                        {artifact?.path || "New suite"}
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
                        onClick={() => {
                            if (Object.values(invalid).some(Boolean))
                                setError(
                                    "Fix invalid JSON fields before switching to JSON view. Your drafts are still in the form.",
                                );
                            else setTab("json");
                        }}
                    >
                        JSON
                    </button>
                </div>
            </div>
            {error && <ErrorBox error={error} />}
            <details className="suite-settings" open={!artifact}>
                <summary>
                    Suite settings{" "}
                    <span className="mono">
                        {data?.suite?.revision || "Legacy suite"}
                    </span>
                    <ChevronRight size={15} />
                </summary>
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
                    {data?.suite ? (
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
                                        id: titlePath(path).replace(
                                            ".json",
                                            "",
                                        ),
                                        revision: "v1",
                                    },
                                })
                            }
                        >
                            Add suite identity & revision
                        </Button>
                    )}
                </div>
            </details>
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
                <div className="suite-workspace">
                    <aside className="case-navigator" aria-label="Suite cases">
                        <div className="case-nav-heading">
                            <h2>Cases</h2>
                            <span>{data.cases.length}</span>
                        </div>
                        <div className="case-nav-list">
                            {data.cases.map((test: Data, index: number) => {
                                const hasInvalid = Object.entries(invalid).some(
                                    ([key, value]) =>
                                        value &&
                                        key.startsWith(caseKey(index) + ":"),
                                );
                                return (
                                    <button
                                        key={caseKey(index)}
                                        className={
                                            "case-nav-item " +
                                            (selectedCase === index
                                                ? "selected"
                                                : "")
                                        }
                                        aria-current={
                                            selectedCase === index
                                                ? "true"
                                                : undefined
                                        }
                                        aria-label={
                                            "Edit " +
                                            (test.id || "untitled case") +
                                            (hasInvalid ? ", invalid JSON" : "")
                                        }
                                        onClick={() => setSelectedCase(index)}
                                    >
                                        <span>
                                            <strong>
                                                {test.id || "Untitled case"}
                                            </strong>
                                            <small>
                                                {(test.assertions || []).length}{" "}
                                                {(test.assertions || [])
                                                    .length === 1
                                                    ? "check"
                                                    : "checks"}
                                            </small>
                                        </span>
                                        {hasInvalid ? (
                                            <CircleAlert
                                                size={15}
                                                className="red"
                                            />
                                        ) : (
                                            <ChevronRight size={14} />
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                        <Button
                            quiet
                            onClick={() => {
                                setSelectedCase(data!.cases.length);
                                change({
                                    ...data,
                                    cases: [
                                        ...data!.cases,
                                        {
                                            id: "case-" + uid(),
                                            ...(data.schema_version === 3
                                                ? { tool_fixtures: {} }
                                                : {}),
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
                                });
                            }}
                        >
                            <Plus size={15} />
                            Add case
                        </Button>
                    </aside>
                    <div className="suite-cases">
                        {data.cases.length === 0 && (
                            <p className="muted">
                                Add a case to define its input and expected
                                behavior.
                            </p>
                        )}
                        {data.cases.map((test: Data, index: number) => (
                            <section
                                className="case-editor"
                                key={caseKey(index)}
                                hidden={selectedCase !== index}
                                aria-label={"Case " + (test.id || index + 1)}
                            >
                                <div className="case-editor-heading">
                                    <h2>{test.id || "Untitled case"}</h2>
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
                                            setSelectedCase((current) =>
                                                Math.max(
                                                    0,
                                                    current > index
                                                        ? current - 1
                                                        : Math.min(
                                                              current,
                                                              data!.cases
                                                                  .length - 2,
                                                          ),
                                                ),
                                            );
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
                                        validity(
                                            caseKey(index) + ":input",
                                            valid,
                                        )
                                    }
                                />
                                {data.schema_version === 3 ? (
                                    <FixtureEditor
                                        value={test.tool_fixtures || {}}
                                        onChange={(tool_fixtures) =>
                                            caseChange(index, {
                                                ...test,
                                                tool_fixtures,
                                            })
                                        }
                                        onValid={(valid) =>
                                            validity(
                                                caseKey(index) + ":fixtures",
                                                valid,
                                            )
                                        }
                                    />
                                ) : (
                                    <Button
                                        quiet
                                        onClick={() =>
                                            change({
                                                ...data,
                                                schema_version: 3,
                                                suite: data.suite || {
                                                    id: titlePath(path).replace(
                                                        ".json",
                                                        "",
                                                    ),
                                                    revision: "v1",
                                                },
                                                cases: data.cases.map(
                                                    (item: Data) => ({
                                                        ...item,
                                                        tool_fixtures: {},
                                                    }),
                                                ),
                                            })
                                        }
                                    >
                                        Configure tool failures
                                    </Button>
                                )}
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
                                                                            i ===
                                                                            ci
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
                                                                            "tool_call_count"
                                                                                ? {
                                                                                      min_calls: 0,
                                                                                      max_calls: 3,
                                                                                  }
                                                                                : {}),
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
                                                                checkKey(
                                                                    index,
                                                                    ci,
                                                                ),
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
                                                                            i ===
                                                                            ci
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
                                                                    ) =>
                                                                        i !==
                                                                        ci,
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
                                                                            i ===
                                                                            ci
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
                                            {check.type ===
                                                "tool_call_count" && (
                                                <div className="form-grid">
                                                    {(
                                                        [
                                                            "min_calls",
                                                            "max_calls",
                                                        ] as const
                                                    ).map((bound) => (
                                                        <Field
                                                            key={bound}
                                                            label={
                                                                bound ===
                                                                "min_calls"
                                                                    ? "Minimum calls"
                                                                    : "Maximum calls"
                                                            }
                                                            hint={
                                                                bound ===
                                                                "max_calls"
                                                                    ? "Leave blank for no upper bound. Counts failed attempts too; does not stop execution."
                                                                    : undefined
                                                            }
                                                        >
                                                            <input
                                                                type="number"
                                                                min={0}
                                                                step={1}
                                                                value={
                                                                    check[
                                                                        bound
                                                                    ] ?? ""
                                                                }
                                                                onChange={(
                                                                    event,
                                                                ) =>
                                                                    caseChange(
                                                                        index,
                                                                        {
                                                                            ...test,
                                                                            assertions:
                                                                                test.assertions.map(
                                                                                    (
                                                                                        a: Data,
                                                                                        i: number,
                                                                                    ) =>
                                                                                        i ===
                                                                                        ci
                                                                                            ? {
                                                                                                  ...a,
                                                                                                  [bound]:
                                                                                                      event
                                                                                                          .target
                                                                                                          .value ===
                                                                                                          "" &&
                                                                                                      bound ===
                                                                                                          "max_calls"
                                                                                                          ? null
                                                                                                          : Number(
                                                                                                                event
                                                                                                                    .target
                                                                                                                    .value,
                                                                                                            ),
                                                                                              }
                                                                                            : a,
                                                                                ),
                                                                        },
                                                                    )
                                                                }
                                                            />
                                                        </Field>
                                                    ))}
                                                </div>
                                            )}
                                            {check.type ===
                                            "output_has_keys" ? (
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
                                                                            i ===
                                                                            ci
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
                    </div>
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
