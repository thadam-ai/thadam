// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api, type Artifact, type Data } from "./api";
import { ResultReviewsArtifact, ResultReviewEditor } from "./result_reviews";

vi.mock("./api", async (original) => ({
    ...(await original<typeof import("./api")>()),
    api: vi.fn(),
}));

afterEach(() => {
    cleanup();
    vi.resetAllMocks();
});

it("saves labels, notes, and tags as a separate artifact", async () => {
    const artifact = {
        path: "run.json",
        kind: "run",
        fingerprint: "run-fingerprint",
        modified_ns: 0,
        cases: 1,
        data: {
            run_id: "run-1",
            cases: [{ id: "refund" }],
        },
    } as unknown as Artifact;
    const onSaved = vi.fn();
    vi.mocked(api).mockImplementation(async (path, body) => {
        if (path === "result-reviews?path=run.json")
            return {
                path: "review-labels/abc.json",
                fingerprint: null,
                data: { reviews: [] },
            };
        if (path === "result-reviews")
            return {
                path: "review-labels/abc.json",
                kind: "result_reviews",
                fingerprint: "labels-fingerprint",
                data: { reviews: (body as Data).reviews },
            };
        throw new Error(path);
    });
    render(<ResultReviewEditor artifact={artifact} onSaved={onSaved} />);

    fireEvent.change(
        await screen.findByRole("combobox", {
            name: "Review verdict for refund",
        }),
        { target: { value: "bad" } },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: "Failure tags for refund" }),
        {
            target: { value: "wrong-tool, policy-gap" },
        },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: "Review notes for refund" }),
        {
            target: { value: "Expected a policy lookup." },
        },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save review labels" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(artifact));
    expect(api).toHaveBeenCalledWith("result-reviews", {
        path: "run.json",
        fingerprint: "run-fingerprint",
        review_path: "review-labels/abc.json",
        review_fingerprint: null,
        reviews: [
            {
                case_id: "refund",
                attempt: null,
                verdict: "bad",
                notes: "Expected a policy lookup.",
                tags: ["wrong-tool", "policy-gap"],
            },
        ],
    });
});

it("keeps commas while typing tags and parses them when saving", async () => {
    const user = userEvent.setup();
    const artifact = {
        path: "run.json",
        kind: "run",
        fingerprint: "run-fingerprint",
        modified_ns: 0,
        cases: 1,
        data: {
            run_id: "run-1",
            cases: [{ id: "refund" }],
        },
    } as unknown as Artifact;
    vi.mocked(api).mockImplementation(async (path, body) => {
        if (path === "result-reviews?path=run.json")
            return {
                path: "review-labels/revision.json",
                fingerprint: null,
                data: { reviews: [] },
            };
        if (path === "result-reviews")
            return {
                path: "review-labels/revision.json",
                kind: "result_reviews",
                fingerprint: "labels-fingerprint",
                data: { reviews: (body as Data).reviews },
            };
        throw new Error(path);
    });
    render(<ResultReviewEditor artifact={artifact} onSaved={vi.fn()} />);

    fireEvent.change(
        await screen.findByRole("combobox", {
            name: "Review verdict for refund",
        }),
        { target: { value: "bad" } },
    );
    const tags = screen.getByRole("textbox", {
        name: "Failure tags for refund",
    });
    await user.type(tags, "wrong-tool, policy-gap");
    expect((tags as HTMLInputElement).value).toBe("wrong-tool, policy-gap");
    fireEvent.click(screen.getByRole("button", { name: "Save review labels" }));

    await waitFor(() => {
        expect(api).toHaveBeenCalledWith(
            "result-reviews",
            expect.objectContaining({
                review_path: "review-labels/revision.json",
                reviews: [
                    expect.objectContaining({
                        case_id: "refund",
                        tags: ["wrong-tool", "policy-gap"],
                    }),
                ],
            }),
        );
    });
});

it("labels repeated attempts independently", async () => {
    const artifact = {
        path: "repeated.json",
        kind: "repeated_run",
        fingerprint: "repeat-fingerprint",
        modified_ns: 0,
        cases: 1,
        data: {
            report_id: "repeat-1",
            runs: [
                { cases: [{ id: "refund" }] },
                { cases: [{ id: "refund" }] },
            ],
        },
    } as unknown as Artifact;
    vi.mocked(api).mockResolvedValue({
        path: "review-labels/repeat.json",
        fingerprint: null,
        data: { reviews: [] },
    });
    render(<ResultReviewEditor artifact={artifact} onSaved={vi.fn()} />);
    expect(
        await screen.findByRole("combobox", {
            name: "Review verdict for refund · attempt 1",
        }),
    ).toBeTruthy();
    expect(
        screen.getByRole("combobox", {
            name: "Review verdict for refund · attempt 2",
        }),
    ).toBeTruthy();
});

it("does not link an old review artifact to a replacement result", () => {
    const review = {
        path: "review-labels/old.json",
        kind: "result_reviews",
        fingerprint: "review-fingerprint",
        modified_ns: 0,
        cases: 1,
        data: {
            source: {
                path: "run.json",
                fingerprint: "old-fingerprint",
                kind: "run",
                id: "old-run",
            },
            reviews: [],
        },
    } as unknown as Artifact;
    const catalog = {
        name: "project",
        root: "/project",
        invalid: [],
        items: [
            {
                path: "run.json",
                kind: "run",
                id: "new-run",
                fingerprint: "new-fingerprint",
                modified_ns: 0,
                cases: 1,
            },
        ],
    };
    render(
        <ResultReviewsArtifact
            artifact={review}
            catalog={catalog}
            onOpen={vi.fn()}
        />,
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Source result is unavailable",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});
