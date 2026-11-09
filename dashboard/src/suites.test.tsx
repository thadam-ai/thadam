// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type Artifact } from "./api";
import { SuiteEditor } from "./suites";

vi.mock("./api", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(cleanup);
const artifact = {
    path: "cases.json",
    kind: "suite",
    fingerprint: "old",
    modified_ns: 0,
    cases: 2,
    data: {
        schema_version: 2,
        suite: { id: "suite", revision: "1" },
        cases: [
            {
                id: "first",
                input: { a: 1 },
                assertions: [
                    {
                        id: "out",
                        type: "output_equals",
                        expected: { ok: true },
                    },
                ],
            },
            {
                id: "second",
                input: { a: 1 },
                assertions: [
                    {
                        id: "out",
                        type: "output_equals",
                        expected: { ok: true },
                    },
                ],
            },
        ],
    },
} as Artifact;
function editor() {
    return render(
        <SuiteEditor
            artifact={artifact}
            onDirty={() => {}}
            onSaved={() => {}}
        />,
    );
}

describe("suite editor state", () => {
    it("edits an exact tool-call order check", async () => {
        vi.mocked(api).mockResolvedValue(artifact);
        editor();
        fireEvent.change(
            screen.getAllByRole("combobox", { name: "Check type" })[0],
            {
                target: { value: "tool_call_sequence" },
            },
        );
        fireEvent.change(
            screen.getByRole("textbox", { name: /Expected tool-call order/ }),
            { target: { value: "lookup, retry, fallback" } },
        );
        fireEvent.click(screen.getByText("Suite settings"));
        fireEvent.change(
            screen.getByRole("textbox", { name: /Suite revision/ }),
            {
                target: { value: "2" },
            },
        );
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

        await waitFor(() =>
            expect(api).toHaveBeenCalledWith(
                "suite",
                expect.objectContaining({
                    data: expect.objectContaining({
                        cases: expect.arrayContaining([
                            expect.objectContaining({
                                id: "first",
                                assertions: [
                                    {
                                        id: "out",
                                        type: "tool_call_sequence",
                                        tools: ["lookup", "retry", "fallback"],
                                    },
                                ],
                            }),
                        ]),
                    }),
                }),
                "PUT",
            ),
        );
    });

    it("saves tool scripts and call bounds in an identified schema-3 suite", async () => {
        vi.mocked(api).mockResolvedValue(artifact);
        editor();
        fireEvent.click(
            screen.getByRole("button", { name: "Configure tool failures" }),
        );
        fireEvent.change(
            screen.getByRole("textbox", { name: "New fixture tool name" }),
            { target: { value: "get_order" } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Add tool" }));
        fireEvent.change(screen.getByRole("combobox", { name: "Response 1" }), {
            target: { value: "raise" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Add response" }));
        fireEvent.change(
            screen.getByRole("textbox", {
                name: "Returned JSON for get_order, response 2",
            }),
            { target: { value: '{"amount":25}' } },
        );
        fireEvent.click(
            screen.getByRole("checkbox", { name: "Repeat final response" }),
        );
        fireEvent.change(screen.getByRole("combobox", { name: "Check type" }), {
            target: { value: "tool_call_count" },
        });
        fireEvent.change(screen.getByRole("textbox", { name: "Tool name" }), {
            target: { value: "get_order" },
        });
        fireEvent.change(
            screen.getByRole("spinbutton", { name: "Minimum calls" }),
            { target: { value: "2" } },
        );
        fireEvent.change(
            screen.getByRole("spinbutton", { name: /Maximum calls/ }),
            { target: { value: "2" } },
        );
        fireEvent.click(screen.getByText("Suite settings"));
        fireEvent.change(
            screen.getByRole("textbox", { name: /Suite revision/ }),
            { target: { value: "2" } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() =>
            expect(api).toHaveBeenCalledWith(
                "suite",
                expect.objectContaining({
                    data: expect.objectContaining({
                        schema_version: 3,
                        cases: expect.arrayContaining([
                            expect.objectContaining({
                                id: "first",
                                tool_fixtures: {
                                    get_order: {
                                        steps: [
                                            {
                                                type: "raise",
                                                error: "ConnectionError",
                                                message: "Service unavailable",
                                            },
                                            {
                                                type: "return",
                                                value: { amount: 25 },
                                            },
                                        ],
                                        repeat_last: true,
                                    },
                                },
                                assertions: [
                                    {
                                        id: "out",
                                        type: "tool_call_count",
                                        tool: "get_order",
                                        min_calls: 2,
                                        max_calls: 2,
                                    },
                                ],
                            }),
                            expect.objectContaining({
                                id: "second",
                                tool_fixtures: {},
                            }),
                        ]),
                    }),
                }),
                "PUT",
            ),
        );
    });
    it("retains invalid fixture JSON across cases and clears it when the tool is removed", () => {
        editor();
        fireEvent.click(
            screen.getByRole("button", { name: "Configure tool failures" }),
        );
        fireEvent.change(
            screen.getByRole("textbox", { name: "New fixture tool name" }),
            { target: { value: "lookup" } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Add tool" }));
        fireEvent.change(
            screen.getByRole("textbox", {
                name: "Returned JSON for lookup, response 1",
            }),
            { target: { value: '{"unfinished":' } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Edit second" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Save changes",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        fireEvent.click(screen.getByRole("button", { name: /Edit first/ }));
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Returned JSON for lookup, response 1",
                }) as HTMLTextAreaElement
            ).value,
        ).toBe('{"unfinished":');
        fireEvent.click(screen.getByRole("button", { name: "Remove tool" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Save changes",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(false);
        fireEvent.click(screen.getByRole("button", { name: "Add case" }));
        fireEvent.click(screen.getByRole("button", { name: /^JSON$/ }));
        const raw = JSON.parse(
            (
                screen.getByRole("textbox", {
                    name: "Suite JSON",
                }) as HTMLTextAreaElement
            ).value,
        );
        expect(raw.cases.every((test: any) => test.tool_fixtures)).toBe(true);
    });
    it("keeps invalid JSON blocked when another case is removed", async () => {
        editor();
        fireEvent.change(screen.getAllByRole("textbox", { name: "Input" })[0], {
            target: { value: '{"invalid":' },
        });
        expect(
            (
                screen.getByRole("button", {
                    name: "Save changes",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        fireEvent.click(screen.getByRole("button", { name: "Edit second" }));
        fireEvent.click(screen.getByRole("button", { name: "Remove case" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Save changes",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        expect(
            screen
                .getByRole("textbox", { name: "Input" })
                .getAttribute("aria-invalid"),
        ).toBe("true");
    });
    it("retains unfinished JSON when switching cases and refuses to discard it through JSON view", () => {
        editor();
        fireEvent.change(screen.getByRole("textbox", { name: "Input" }), {
            target: { value: '{"unfinished":' },
        });
        fireEvent.click(screen.getByRole("button", { name: "Edit second" }));
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Input",
                }) as HTMLTextAreaElement
            ).value,
        ).toContain('"a": 1');
        expect(
            (
                screen.getByRole("button", {
                    name: "Save changes",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        fireEvent.click(screen.getByRole("button", { name: /^JSON$/ }));
        expect(screen.getByRole("alert").textContent).toContain(
            "Fix invalid JSON fields",
        );
        fireEvent.click(
            screen.getByRole("button", { name: "Edit first, invalid JSON" }),
        );
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Input",
                }) as HTMLTextAreaElement
            ).value,
        ).toBe('{"unfinished":');
    });
    it("saves edits from multiple cases with the original stale-write fingerprint", async () => {
        vi.mocked(api).mockResolvedValueOnce(artifact);
        editor();
        fireEvent.change(screen.getByRole("textbox", { name: "Input" }), {
            target: { value: '{"a": 2}' },
        });
        fireEvent.click(screen.getByRole("button", { name: "Edit second" }));
        fireEvent.change(
            screen.getByRole("textbox", { name: "Expected output" }),
            { target: { value: '{"ok": false}' } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() =>
            expect(api).toHaveBeenCalledWith(
                "suite",
                {
                    path: "cases.json",
                    fingerprint: "old",
                    data: {
                        ...artifact.data,
                        cases: [
                            { ...artifact.data.cases[0], input: { a: 2 } },
                            {
                                ...artifact.data.cases[1],
                                assertions: [
                                    {
                                        id: "out",
                                        type: "output_equals",
                                        expected: { ok: false },
                                    },
                                ],
                            },
                        ],
                    },
                },
                "PUT",
            ),
        );
    });
    it("selects a newly added case and returns to a neighbour when it is removed", () => {
        editor();
        fireEvent.click(screen.getByRole("button", { name: "Add case" }));
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Case ID",
                }) as HTMLInputElement
            ).value,
        ).toMatch(/^case-/);
        fireEvent.click(screen.getByRole("button", { name: "Remove case" }));
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Case ID",
                }) as HTMLInputElement
            ).value,
        ).toBe("second");
    });
    it("keeps a case selected when full JSON removes the previously selected case", () => {
        editor();
        fireEvent.click(screen.getByRole("button", { name: "Edit second" }));
        fireEvent.click(screen.getByRole("button", { name: /^JSON$/ }));
        fireEvent.change(screen.getByRole("textbox", { name: "Suite JSON" }), {
            target: {
                value: JSON.stringify({
                    ...artifact.data,
                    cases: [artifact.data.cases[0]],
                }),
            },
        });
        fireEvent.click(screen.getByRole("button", { name: "Form" }));
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Case ID",
                }) as HTMLInputElement
            ).value,
        ).toBe("first");
    });
    it("does not transfer invalid JSON from a removed case to its neighbour", async () => {
        editor();
        fireEvent.change(screen.getAllByRole("textbox", { name: "Input" })[0], {
            target: { value: "broken" },
        });
        fireEvent.click(
            screen.getAllByRole("button", { name: "Remove case" })[0],
        );
        await waitFor(() =>
            expect(
                (
                    screen.getByRole("button", {
                        name: "Save changes",
                    }) as HTMLButtonElement
                ).disabled,
            ).toBe(false),
        );
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Input",
                }) as HTMLTextAreaElement
            ).value,
        ).toContain('"a": 1');
    });
    it("clears an obsolete expected-value error when changing check type", async () => {
        editor();
        fireEvent.change(
            screen.getAllByRole("textbox", {
                name: "Expected output",
            })[0],
            { target: { value: "broken" } },
        );
        fireEvent.change(
            screen.getAllByRole("combobox", { name: "Check type" })[0],
            { target: { value: "tool_called" } },
        );
        await waitFor(() =>
            expect(
                (
                    screen.getByRole("button", {
                        name: "Save changes",
                    }) as HTMLButtonElement
                ).disabled,
            ).toBe(false),
        );
    });
    it("keeps focus and content while renaming a case", () => {
        editor();
        const input = screen.getAllByRole("textbox", { name: "Case ID" })[0];
        input.focus();
        fireEvent.change(input, { target: { value: "renamed-case" } });
        expect(document.activeElement).toBe(input);
        expect((input as HTMLInputElement).value).toBe("renamed-case");
    });
});
