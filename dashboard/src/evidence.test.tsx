// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TraceView } from "./evaluations";
afterEach(cleanup);
describe("observable evidence availability", () => {
    it("keeps reported zero distinct from unavailable token usage and returned null", () => {
        render(
            <TraceView
                test={{
                    events: [
                        {
                            id: "e",
                            kind: "model",
                            name: "scripted",
                            status: "completed",
                            started_at_ms: 0,
                            duration_ms: 1,
                            parent_id: null,
                            input: null,
                            input_available: true,
                            output: null,
                            output_available: true,
                            error: null,
                            usage: {
                                input_tokens: 0,
                                output_tokens: null,
                                total_tokens: null,
                            },
                        },
                    ],
                    trace_complete: true,
                    trace_warnings: [],
                }}
            />,
        );
        expect(screen.getByText("0", { exact: true })).toBeTruthy();
        expect(
            screen.getAllByText("Unavailable", { exact: true }),
        ).toHaveLength(2);
        expect(screen.getAllByText("null", { exact: true })).toHaveLength(2);
    });
    it("distinguishes missing tracing from an observed empty trace", () => {
        const view = render(<TraceView test={{ events: null }} />);
        expect(screen.getByText(/Tracing was not available/)).toBeTruthy();
        view.rerender(
            <TraceView
                test={{ events: [], trace_complete: true, trace_warnings: [] }}
            />,
        );
        expect(
            screen.getByText(/Tracing was observed, with no recorded/),
        ).toBeTruthy();
    });
});
