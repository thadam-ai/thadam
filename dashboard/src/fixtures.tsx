import { Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { type Data } from "./api";
import { Button, ErrorBox, Field, uid } from "./components";
import { JsonInput } from "./json-input";

export function FixtureEditor({
    value,
    onChange,
    onValid,
}: {
    value: Data;
    onChange: (value: Data) => void;
    onValid: (valid: boolean) => void;
}) {
    const [name, setName] = useState("");
    const [error, setError] = useState("");
    const [invalid, setInvalid] = useState<Record<string, boolean>>({});
    const keys = useRef<Record<string, string[]>>(Object.create(null));
    const hasInvalid = Object.values(invalid).some(Boolean);
    useEffect(() => {
        onValid(!hasInvalid);
    }, [hasInvalid]);
    function stepKey(tool: string, index: number) {
        const list = (keys.current[tool] ||= []);
        return (list[index] ||= uid());
    }
    function update(tool: string, script: Data) {
        onChange({ ...value, [tool]: script });
    }
    function updateStep(tool: string, index: number, step: Data) {
        update(tool, {
            ...value[tool],
            steps: value[tool].steps.map((current: Data, i: number) =>
                i === index ? step : current,
            ),
        });
    }
    function clear(ids: string[]) {
        setInvalid((current) =>
            Object.fromEntries(
                Object.entries(current).filter(([key]) => !ids.includes(key)),
            ),
        );
    }
    if (
        !value ||
        Array.isArray(value) ||
        typeof value !== "object" ||
        Object.values(value).some(
            (script) =>
                !script ||
                !Array.isArray(script.steps) ||
                script.steps.some(
                    (step: Data) =>
                        !step || !["return", "raise"].includes(step.type),
                ),
        )
    ) {
        return (
            <ErrorBox error="Invalid tool fixtures. Open JSON view and supply named scripts with a steps array and repeat_last." />
        );
    }
    return (
        <section aria-label="Tool fixtures" className="fixture-editor">
            <div className="section-heading">
                <h3>Tool fixtures</h3>
            </div>
            <p className="muted">
                Script responses in call order. Each case attempt starts fresh.
                Connect these names through a tool fixture factory.
            </p>
            {error && <ErrorBox error={error} />}
            {Object.entries(value).map(([tool, script]) => (
                <div className="check-editor" key={tool}>
                    <div className="section-heading">
                        <strong className="mono">{tool}</strong>
                        <Button
                            quiet
                            onClick={() => {
                                const next = { ...value };
                                delete next[tool];
                                onChange(next);
                                clear(keys.current[tool] || []);
                                delete keys.current[tool];
                            }}
                        >
                            <X size={14} />
                            Remove tool
                        </Button>
                    </div>
                    {script.steps.map((step: Data, index: number) => (
                        <div
                            className="fixture-step"
                            key={stepKey(tool, index)}
                        >
                            <div className="check-fields">
                                <Field label={`Response ${index + 1}`}>
                                    <select
                                        value={step.type}
                                        onChange={(event) => {
                                            clear([stepKey(tool, index)]);
                                            updateStep(
                                                tool,
                                                index,
                                                event.target.value === "return"
                                                    ? {
                                                          type: "return",
                                                          value: null,
                                                      }
                                                    : {
                                                          type: "raise",
                                                          error: "ConnectionError",
                                                          message:
                                                              "Service unavailable",
                                                      },
                                            );
                                        }}
                                    >
                                        <option value="return">
                                            Return JSON
                                        </option>
                                        <option value="raise">
                                            Raise simulated error
                                        </option>
                                    </select>
                                </Field>
                                <Button
                                    quiet
                                    disabled={script.steps.length === 1}
                                    aria-label={`Remove response ${index + 1} from ${tool}`}
                                    onClick={() => {
                                        clear([stepKey(tool, index)]);
                                        keys.current[tool].splice(index, 1);
                                        update(tool, {
                                            ...script,
                                            steps: script.steps.filter(
                                                (_: Data, i: number) =>
                                                    i !== index,
                                            ),
                                        });
                                    }}
                                >
                                    <X size={14} />
                                </Button>
                            </div>
                            {step.type === "return" ? (
                                <JsonInput
                                    label={`Returned JSON for ${tool}, response ${index + 1}`}
                                    value={step.value}
                                    onChange={(next) =>
                                        updateStep(tool, index, {
                                            ...step,
                                            value: next,
                                        })
                                    }
                                    onValid={(valid) =>
                                        setInvalid((current) => ({
                                            ...current,
                                            [stepKey(tool, index)]: !valid,
                                        }))
                                    }
                                />
                            ) : (
                                <div className="form-grid">
                                    <Field label="Simulated error">
                                        <select
                                            value={step.error}
                                            onChange={(event) =>
                                                updateStep(tool, index, {
                                                    ...step,
                                                    error: event.target.value,
                                                })
                                            }
                                        >
                                            {[
                                                "TimeoutError",
                                                "ConnectionError",
                                                "RuntimeError",
                                            ].map((type) => (
                                                <option key={type}>
                                                    {type}
                                                </option>
                                            ))}
                                        </select>
                                    </Field>
                                    <Field label="Error message">
                                        <input
                                            value={step.message}
                                            onChange={(event) =>
                                                updateStep(tool, index, {
                                                    ...step,
                                                    message: event.target.value,
                                                })
                                            }
                                        />
                                    </Field>
                                </div>
                            )}
                        </div>
                    ))}
                    <div className="fixture-actions">
                        <Button
                            quiet
                            onClick={() =>
                                update(tool, {
                                    ...script,
                                    steps: [
                                        ...script.steps,
                                        { type: "return", value: null },
                                    ],
                                })
                            }
                        >
                            <Plus size={14} />
                            Add response
                        </Button>
                        <label className="checkbox">
                            <input
                                type="checkbox"
                                checked={script.repeat_last}
                                onChange={(event) =>
                                    update(tool, {
                                        ...script,
                                        repeat_last: event.target.checked,
                                    })
                                }
                            />
                            Repeat final response
                        </label>
                    </div>
                    <p className="muted">
                        {script.repeat_last
                            ? "The final step repeats until the agent stops. Call-count checks do not interrupt execution."
                            : "An extra call after the final step is an evaluation error. Unused responses are allowed."}
                    </p>
                </div>
            ))}
            <div className="inline-field">
                <Field label="New fixture tool name">
                    <input
                        value={name}
                        placeholder="get_order"
                        onChange={(event) => {
                            setName(event.target.value);
                            setError("");
                        }}
                    />
                </Field>
                <Button
                    onClick={() => {
                        const tool = name.trim();
                        if (!tool || Object.hasOwn(value, tool)) {
                            setError("Enter a unique, non-empty tool name.");
                            return;
                        }
                        onChange({
                            ...value,
                            [tool]: {
                                steps: [{ type: "return", value: null }],
                                repeat_last: false,
                            },
                        });
                        setName("");
                    }}
                >
                    <Plus size={14} />
                    Add tool
                </Button>
            </div>
        </section>
    );
}
