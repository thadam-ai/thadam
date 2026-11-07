// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api, type Artifact, type Data } from "./api";
vi.mock("./api", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./api")>()),
    api: vi.fn(),
}));
const run: Artifact = {
    path: "report.json",
    kind: "run",
    fingerprint: "report-old",
    modified_ns: 0,
    cases: 0,
    summary: { total: 0, passed: 0, failed: 0, errors: 0 },
    data: {
        schema_version: 3,
        run_id: "local-run",
        summary: { total: 0, passed: 0, failed: 0, errors: 0 },
        cases: [],
    },
};
const suite: Artifact = {
    path: "cases.json",
    kind: "suite",
    fingerprint: "suite-old",
    modified_ns: 0,
    cases: 1,
    data: {
        schema_version: 2,
        suite: { id: "refund", revision: "v1" },
        cases: [
            {
                id: "request",
                input: { days: 7 },
                assertions: [
                    {
                        id: "policy",
                        type: "output_equals",
                        expected: { approved: true },
                    },
                ],
            },
        ],
    },
};
let savedSuite: Artifact;
beforeEach(() => {
    history.replaceState(null, "", "/");
    localStorage.clear();
    Object.defineProperty(window, "innerWidth", {
        value: 1280,
        configurable: true,
    });
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    vi.spyOn(window, "confirm").mockReturnValue(false);
    savedSuite = structuredClone(suite);
    vi.mocked(api).mockReset();
    vi.mocked(api).mockImplementation(async (path: string, body?: unknown) => {
        if (path === "workspace")
            return {
                name: "local",
                root: "/project",
                items: [run, savedSuite],
                invalid: [],
            };
        if (["jobs", "agents"].includes(path)) return [];
        if (path === "artifact?path=report.json") return run;
        if (path === "artifact?path=cases.json") return savedSuite;
        if (path === "suite") {
            savedSuite = {
                ...savedSuite,
                data: (body as Data).data,
                fingerprint: "suite-new",
            };
            return savedSuite;
        }
        throw new Error("Unexpected API call: " + path);
    });
});
afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
});

describe("evidence workspace navigation", () => {
    it("searches saved results by case and failure tag and filters by verdict", async () => {
        const labeledRun = {
            ...run,
            review_state: "in progress",
            review_verdicts: ["bad"],
            review_case_ids: ["refund"],
            review_tags: ["policy-gap"],
        };
        vi.mocked(api).mockImplementation(async (path: string) => {
            if (path === "workspace")
                return {
                    name: "local",
                    root: "/project",
                    items: [labeledRun, savedSuite],
                    invalid: [],
                };
            if (["jobs", "agents"].includes(path)) return [];
            if (path === "artifact?path=report.json") return run;
            if (path === "artifact?path=cases.json") return savedSuite;
            if (path === "result-reviews?path=report.json")
                return {
                    path: "review-labels/report.json",
                    fingerprint: null,
                    data: { reviews: [] },
                };
            throw new Error("Unexpected API call: " + path);
        });
        render(<App />);
        await screen.findByRole("heading", { name: "report.json" });
        const library = screen.getByRole("region", { name: "Saved evidence" });
        const search = screen.getByRole("textbox", {
            name: "Search saved files",
        });
        fireEvent.change(search, { target: { value: "refund" } });
        expect(
            within(library).getByRole("button", { name: "Open report.json" }),
        ).toBeTruthy();
        fireEvent.change(search, { target: { value: "policy-gap" } });
        expect(
            within(library).getByRole("button", { name: "Open report.json" }),
        ).toBeTruthy();
        fireEvent.change(search, { target: { value: "" } });
        fireEvent.change(
            screen.getByRole("combobox", { name: "Filter by review label" }),
            { target: { value: "good" } },
        );
        expect(
            within(library).queryByRole("button", { name: "Open report.json" }),
        ).toBeNull();
        fireEvent.change(
            screen.getByRole("combobox", { name: "Filter by review label" }),
            { target: { value: "bad" } },
        );
        expect(
            within(library).getByRole("button", { name: "Open report.json" }),
        ).toBeTruthy();
    });

    it("keeps the mixed file list visible while inspecting a suite and never executes code during discovery", async () => {
        render(<App />);
        // The first render includes session setup, catalog loading, automatic
        // selection, and artifact loading; allow cold CI workers to finish.
        await screen.findByRole(
            "heading",
            { name: "report.json" },
            { timeout: 5000 },
        );
        fireEvent.click(
            screen.getByRole("button", { name: "Open cases.json" }),
        );
        await screen.findByRole("textbox", { name: "Case ID" });
        const library = screen.getByRole("region", { name: "Saved evidence" });
        expect(
            within(library).getByRole("button", { name: "Open report.json" }),
        ).toBeTruthy();
        expect(
            within(library)
                .getByRole("button", { name: "Open cases.json" })
                .getAttribute("aria-current"),
        ).toBe("true");
        expect(
            vi.mocked(api).mock.calls.every(([, body]) => body === undefined),
        ).toBe(true);
    });
    it("respects a cancelled unsaved-edit warning for both file selection and the global run action", async () => {
        render(<App />);
        fireEvent.click(
            await screen.findByRole("button", { name: "Open cases.json" }),
        );
        const input = await screen.findByRole("textbox", { name: "Input" });
        fireEvent.change(input, { target: { value: '{"draft":' } });
        fireEvent.click(
            screen.getByRole("button", { name: "Open report.json" }),
        );
        expect(window.confirm).toHaveBeenCalledTimes(1);
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Input",
                }) as HTMLTextAreaElement
            ).value,
        ).toBe('{"draft":');
        fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));
        expect(window.confirm).toHaveBeenCalledTimes(2);
        expect(
            screen.queryByRole("combobox", { name: "Test suite" }),
        ).toBeNull();
        expect(
            screen
                .getByRole("button", { name: "Open cases.json" })
                .getAttribute("aria-current"),
        ).toBe("true");
    });
    it("updates the editor after saving the selected suite and uses its new fingerprint on the next save", async () => {
        render(<App />);
        fireEvent.click(
            await screen.findByRole("button", { name: "Open cases.json" }),
        );
        fireEvent.change(
            await screen.findByRole("textbox", { name: "Input" }),
            { target: { value: '{"days":8}' } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() =>
            expect(screen.queryByText("unsaved", { exact: true })).toBeNull(),
        );
        fireEvent.change(screen.getByRole("textbox", { name: "Input" }), {
            target: { value: '{"days":9}' },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() =>
            expect(
                vi.mocked(api).mock.calls.filter(([path]) => path === "suite"),
            ).toHaveLength(2),
        );
        const writes = vi
            .mocked(api)
            .mock.calls.filter(([path]) => path === "suite");
        expect((writes[0][1] as Data).fingerprint).toBe("suite-old");
        expect((writes[1][1] as Data).fingerprint).toBe("suite-new");
    });
    it("returns to the file list on narrow screens without automatically reopening an item", async () => {
        Object.defineProperty(window, "innerWidth", {
            value: 390,
            configurable: true,
        });
        render(<App />);
        expect(
            await screen.findByRole("heading", { name: "Select a saved file" }),
        ).toBeTruthy();
        fireEvent.click(
            await screen.findByRole("button", { name: "Open report.json" }),
        );
        await screen.findByRole("heading", { name: "report.json" });
        fireEvent.click(screen.getByRole("button", { name: "Back to files" }));
        await screen.findByRole("heading", { name: "Select a saved file" });
        expect(
            screen
                .getByRole("button", { name: "Open report.json" })
                .getAttribute("aria-current"),
        ).toBeNull();
    });
});
