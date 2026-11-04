import { parse, stringify, LosslessNumber } from "lossless-json";
export type Data = Record<string, any>;
export type Item = {
    path: string;
    kind: string;
    duration_ms?: number | null;
    suite?: { id: string; revision: string };
    summary?: Data;
    exit_code?: number;
    modified_ns: number;
    cases: number;
    fingerprint: string;
    attempts?: number;
    agent_revision?: string;
};
export type Artifact = Item & { data: Data; review_digest?: string };
export type Catalog = {
    name: string;
    root: string;
    items: Item[];
    invalid: { path: string; error: string }[];
};
export async function api<T = any>(
    path: string,
    body?: unknown,
    method = "POST",
): Promise<T> {
    const response = await fetch(
        "/api/" + path,
        body === undefined
            ? undefined
            : {
                  method,
                  headers: { "Content-Type": "application/json" },
                  body: stringify(body),
              },
    );
    const data = parseJSON(await response.text());
    if (!response.ok)
        throw new Error(
            data.error ||
                data.detail?.[0]?.msg ||
                "The request could not complete. Try again.",
        );
    return data;
}
export function evaluation(data: Data): Data {
    return data.kind === "approved_baseline"
        ? data.review.candidate
        : data.kind === "baseline_review"
          ? data.candidate
          : data;
}
export function counts(data: Data): {
    passed: number;
    failed: number;
    errors: number;
    total: number;
} {
    const source = evaluation(data),
        s = source.summary || {};
    return {
        passed: s.passed || 0,
        failed: s.failed || 0,
        errors: s.errors || 0,
        total: s.total_invocations ?? s.total ?? source.cases?.length ?? 0,
    };
}
export function outcome(
    item: Pick<Item, "kind" | "summary" | "exit_code">,
): string {
    if (item.kind === "suite") return "ready";
    if (item.kind === "scenario_draft") return "review required";
    if (item.kind === "approved_baseline") return "approved";
    if (item.kind === "baseline_review")
        return item.exit_code ? "blocked" : "review required";
    if (item.kind.includes("comparison"))
        return item.exit_code === 2
            ? "incompatible"
            : item.exit_code
              ? "blocked"
              : "passed";
    return item.summary?.errors
        ? "error"
        : item.summary?.failed
          ? "failed"
          : "passed";
}
export const kindName: Record<string, string> = {
    run: "Single run",
    repeated_run: "Repeated run",
    comparison: "Regression comparison",
    reliability_comparison: "Reliability comparison",
    suite: "Test suite",
    scenario_draft: "Scenario draft",
    baseline_review: "Baseline review",
    approved_baseline: "Approved baseline",
};
export function json(value: unknown): string {
    return stringify(value, null, 2) ?? "Unavailable";
}

export function parseJSON(text: string): any {
    return parse(text, undefined, {
        parseNumber(value: string) {
            const number = Number(value);
            if (/^-?\d+$/.test(value) && !Number.isSafeInteger(number))
                return new LosslessNumber(value);
            if (!Number.isFinite(number))
                throw new Error("JSON numbers must be finite");
            return number;
        },
    });
}
