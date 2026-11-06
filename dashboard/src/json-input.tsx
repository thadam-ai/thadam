import { useEffect, useState } from "react";
import { json, parseJSON } from "./api";
import { Field } from "./components";

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
