// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Artifact } from "./api";
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
        fireEvent.click(
            screen.getAllByRole("button", { name: "Remove case" })[1],
        );
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
