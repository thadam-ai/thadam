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
            mask_fields: ["input.email"],
            fingerprint: "source-fingerprint",
            selected_rows: [1],
            acknowledged_duplicates: [],
        }),
    );
});
