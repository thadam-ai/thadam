import { describe, expect, it } from "vitest";
import { counts, evaluation, outcome, parseJSON, json } from "./api";

describe("saved evidence presentation", () => {
    it("uses every repeated attempt as the denominator", () => {
        expect(
            counts({
                kind: "repeated_run",
                summary: {
                    total_cases: 3,
                    total_invocations: 15,
                    passed: 10,
                    failed: 4,
                    errors: 1,
                },
            }),
        ).toEqual({ total: 15, passed: 10, failed: 4, errors: 1 });
    });
    it("unwraps reviews and approvals without merging old and new outcomes", () => {
        const candidate = {
            summary: { total: 3, passed: 2, failed: 1, errors: 0 },
        };
        expect(
            evaluation({ kind: "approved_baseline", review: { candidate } }),
        ).toBe(candidate);
        expect(counts({ kind: "baseline_review", candidate })).toEqual({
            total: 3,
            passed: 2,
            failed: 1,
            errors: 0,
        });
    });
    it("does not show incompatible comparisons as passing", () => {
        expect(outcome({ kind: "comparison", exit_code: 2 })).toBe(
            "incompatible",
        );
        expect(outcome({ kind: "reliability_comparison", exit_code: 1 })).toBe(
            "blocked",
        );
        expect(outcome({ kind: "comparison", exit_code: 0 })).toBe("passed");
    });
    it("distinguishes review readiness from approval and errors from failed checks", () => {
        expect(outcome({ kind: "baseline_review", exit_code: 0 })).toBe(
            "review required",
        );
        expect(outcome({ kind: "approved_baseline" })).toBe("approved");
        expect(
            outcome({ kind: "run", summary: { failed: 1, errors: 1 } }),
        ).toBe("error");
        expect(
            outcome({ kind: "run", summary: { failed: 1, errors: 0 } }),
        ).toBe("failed");
    });
});

it("preserves large numeric identifiers across viewing and editing", () => {
    const source =
        '{"order":9223372036854775807,"nested":[123456789012345678901234567890]}';
    expect(json(parseJSON(source))).toContain("9223372036854775807");
    expect(json(parseJSON(source))).toContain("123456789012345678901234567890");
    expect(parseJSON(source).order).not.toBeTypeOf("number");
});
it("rejects duplicate JSON keys and non-finite editor numbers", () => {
    expect(() => parseJSON('{"x":1,"x":2}')).toThrow();
    expect(() => parseJSON('{"x":1e999}')).toThrow();
});
