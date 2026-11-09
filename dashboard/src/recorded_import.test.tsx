// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, type Artifact } from "./api";
import { RecordedExampleImport } from "./recorded_import";
vi.mock("./api", async (original) => ({
    ...(await original<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(() => {
    cleanup();
    vi.resetAllMocks();
});

it("previews a masked file and imports the selected draft with its source fingerprint", async () => {
    const onImported = vi.fn();
    const artifact = {
        path: "regression-drafts/example.json",
        kind: "regression_draft",
        fingerprint: "draft-fingerprint",
        data: { kind: "regression_draft" },
    } as unknown as Artifact;
    vi.mocked(api).mockImplementation(async (path) => {
        if (path === "recorded-examples/preview")
            return {
                path: "data/examples.jsonl",
                fingerprint: "source-fingerprint",
                format: "jsonl",
                mapping: { input: "prompt" },
                mask_fields: ["input.email"],
                summary: {
                    total: 1,
                    valid: 1,
                    invalid: 0,
                    duplicates: 0,
                    already_imported: 0,
                },
                rows: [
                    {
                        line: 1,
                        source_id: "example-1",
                        record: {
                            source_id: "example-1",
                            input: { email: "[REDACTED]" },
                        },
                        has_expected: false,
                        valid: true,
                        errors: [],
                        warnings: [],
                        duplicate_of: null,
                        duplicate_reasons: [],
                        already_imported: false,
                    },
                ],
            };
        if (path === "recorded-examples/import") return { drafts: [artifact] };
        throw Error(String(path));
    });

    render(<RecordedExampleImport onImported={onImported} />);
    fireEvent.change(screen.getByLabelText(/Examples file/), {
        target: { value: "data/examples.jsonl" },
    });
    fireEvent.change(screen.getByLabelText(/Fields to mask before preview/), {
        target: { value: "input.email" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview rows" }));
    await screen.findByText("Row 1 · example-1");
    expect(screen.getByText(/\[REDACTED\]/)).toBeTruthy();

    fireEvent.click(
        screen.getByRole("button", { name: "Import 1 selected drafts" }),
    );
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(artifact));
    expect(api).toHaveBeenCalledWith(
        "recorded-examples/import",
        expect.objectContaining({
            path: "data/examples.jsonl",
            format: "jsonl",
            mapping: { input: "prompt" },
            mask_fields: ["input.email"],
            fingerprint: "source-fingerprint",
            selected_rows: [1],
            acknowledged_duplicates: [],
        }),
    );
});

it("discards a preview response that arrives after its configuration changed", async () => {
    const pending: {
        body: unknown;
        resolve: (value: unknown) => void;
    }[] = [];
    vi.mocked(api).mockImplementation((path, body) => {
        if (path !== "recorded-examples/preview") throw Error(String(path));
        return new Promise((resolve) => pending.push({ body, resolve }));
    });
    const row = (sourceId: string) => ({
        line: 1,
        source_id: sourceId,
        record: { source_id: sourceId, input: sourceId },
        has_expected: false,
        valid: true,
        errors: [],
        warnings: [],
        duplicate_of: null,
        duplicate_reasons: [],
        already_imported: false,
    });
    const preview = (path: string, sourceId: string) => ({
        path,
        fingerprint: `${sourceId}-fingerprint`,
        format: "jsonl",
        mapping: { input: "prompt" },
        mask_fields: [],
        summary: {
            total: 1,
            valid: 1,
            invalid: 0,
            duplicates: 0,
            already_imported: 0,
        },
        rows: [row(sourceId)],
    });

    render(<RecordedExampleImport onImported={vi.fn()} />);
    const pathField = screen.getByLabelText(/Examples file/);
    fireEvent.change(pathField, {
        target: { value: "data/first.jsonl" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview rows" }));
    await waitFor(() => expect(pending).toHaveLength(1));

    fireEvent.change(pathField, {
        target: { value: "data/second.jsonl" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview rows" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    expect(pending[1].body).toMatchObject({ path: "data/second.jsonl" });
    pending[1].resolve(preview("data/second.jsonl", "second"));
    await screen.findByText("Row 1 · second");

    pending[0].resolve(preview("data/first.jsonl", "first"));
    await waitFor(() =>
        expect(screen.getByText("Row 1 · second")).toBeTruthy(),
    );
    expect(screen.queryByText("Row 1 · first")).toBeNull();
});
