// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { comparisonResult } from "./comparisons";
import { CaseList } from "./evaluations";

afterEach(cleanup);

describe("investigating results", () => {
    it("surfaces a regression inside an errored case without hiding errors on the baseline", () => {
        const result = comparisonResult({
            exit_code: 1,
            cases: [
                {
                    change: "error",
                    baseline_errors: [{ source: "agent" }],
                    candidate_errors: [],
                    checks: [{ change: "regression" }],
                },
            ],
        });
        expect(result.title).toBe("1 case regressed");
        expect(result.errors).toBe(1);
    });
    it("keeps incompatible contracts distinct from failed expectations", () => {
        expect(
            comparisonResult({
                exit_code: 2,
                cases: [{ change: "incompatible", checks: [] }],
            }).title,
        ).toBe("Reports are incompatible");
    });
    it("does not label a tolerated repeated-rate drop as a blocked regression", () => {
        const result = comparisonResult({
            exit_code: 0,
            cases: [
                {
                    change: "tolerated_drop",
                    checks: [
                        {
                            change: "tolerated_drop",
                            baseline: { errors: 0 },
                            candidate: { errors: 0 },
                        },
                    ],
                },
            ],
        });
        expect(result.title).toBe("No new regressions");
        expect(result.regressed).toBe(0);
    });
    it("opens the first failing case and failed check before raw invocation data", () => {
        const test = {
            id: "failing-case",
            status: "failed",
            duration_ms: 1,
            input: { request: "refund" },
            output: { approved: true },
            output_available: true,
            check_definitions: [{ id: "policy", type: "output_equals" }],
            assertions: [
                {
                    id: "policy",
                    passed: false,
                    message: "Expected a denial",
                    expected: { approved: false },
                    actual: { approved: true },
                    event_ids: [],
                },
            ],
            errors: [],
            events: null,
        };
        render(
            <CaseList
                cases={[
                    { ...test, id: "passing-case", status: "passed" },
                    test,
                ]}
            />,
        );
        const failedCase = screen.getByText("failing-case").closest("details");
        expect(failedCase?.open).toBe(true);
        expect(
            within(failedCase!).getByText("policy").closest("details")?.open,
        ).toBe(true);
        expect(
            within(failedCase!)
                .getByText("Invocation input and output")
                .closest("details")?.open,
        ).toBe(false);
        expect(within(failedCase!).getByText("Expected a denial")).toBeTruthy();
        expect(screen.getAllByText(/-case$/)[0].textContent).toBe(
            "failing-case",
        );
    });
});
