import { Check, CircleAlert, Clipboard, Folder } from "lucide-react";
import React, { useState, type ReactNode } from "react";
import { json, type Artifact } from "./api";
let sequence = 0;
export const uid = () =>
    Date.now().toString(36) + "-" + (++sequence).toString(36);
export function Badge({ status }: { status: string }) {
    return (
        <span className={"badge " + status.replaceAll(" ", "-")}>{status}</span>
    );
}
export function Button({
    children,
    primary = false,
    quiet = false,
    ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    primary?: boolean;
    quiet?: boolean;
}) {
    return (
        <button
            className={
                primary ? "button primary" : quiet ? "button quiet" : "button"
            }
            {...props}
        >
            {children}
        </button>
    );
}
export function Field({
    label,
    hint,
    children,
}: {
    label: string;
    hint?: string;
    children: ReactNode;
}) {
    return (
        <label className="field">
            <span>{label}</span>
            {children}
            {hint && <small>{hint}</small>}
        </label>
    );
}
export function Json({ value, label }: { value: unknown; label?: string }) {
    return (
        <div className="json-block">
            {label && <div className="json-label">{label}</div>}
            <pre>{json(value)}</pre>
        </div>
    );
}
export function Copy({
    value,
    label = "Copy",
}: {
    value: string;
    label?: string;
}) {
    const [done, setDone] = useState(false);
    return (
        <Button
            quiet
            onClick={async () => {
                try {
                    await navigator.clipboard.writeText(value);
                    setDone(true);
                    setTimeout(() => setDone(false), 1600);
                } catch {
                    setDone(false);
                }
            }}
        >
            {done ? <Check size={14} /> : <Clipboard size={14} />}{" "}
            {done ? "Copied" : label}
        </Button>
    );
}
export function Empty({
    title,
    children,
    action,
}: {
    title: string;
    children: ReactNode;
    action?: ReactNode;
}) {
    return (
        <div className="empty">
            <div className="empty-icon">
                <Folder size={25} />
            </div>
            <h2>{title}</h2>
            <p>{children}</p>
            {action}
        </div>
    );
}
export function ErrorBox({ error }: { error: string }) {
    return (
        <div className="error-box" role="alert">
            <CircleAlert size={17} />
            <span>{error}</span>
        </div>
    );
}
export function titlePath(path: string) {
    return path.split("/").at(-1) || path;
}
export function exportArtifact(artifact: Artifact) {
    const url = URL.createObjectURL(
        new Blob([json(artifact.data)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = titlePath(artifact.path);
    link.click();
    URL.revokeObjectURL(url);
}
