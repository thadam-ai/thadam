// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, json, type Artifact } from "./api";
import { DraftReview, SuggestPanel } from "./generation";
vi.mock("./api", async (original) => ({
    ...(await original<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});
const caseData = {
    id: "echo",
    input: 1,
    assertions: [{ id: "answer", type: "output_equals", expected: 1 }],
};
const catalog = { name: "project", root: "/project", invalid: [], items: [] };
it("previews explicit context before generation and never chooses a billing fallback", async () => {
    const started = vi.fn();
    vi.mocked(api).mockImplementation(async (path, body) => {
        if (path === "providers")
            return { available: true, chatgpt: false, api_key: true };
        if (path.startsWith("providers/models"))
            return [{ id: "selected", name: "Selected model" }];
        if (path === "generate/preview")
            return { request: body, instructions: "fixed instructions" };
        if (path === "generate")
            return { id: "job", settings: { kind: "generation" } };
        return {};
    });
    render(
        <SuggestPanel
            catalog={catalog}
            active={false}
            onStarted={started}
            onDirty={() => {}}
        />,
    );
    await waitFor(() => expect(api).toHaveBeenCalledWith("providers"));
    fireEvent.change(screen.getByRole("combobox", { name: "Use AI through" }), {
        target: { value: "api_key" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Load models/ }));
    await screen.findByRole("option", { name: "Selected model" });
    fireEvent.change(
        screen.getByRole("combobox", { name: "Generation model" }),
        { target: { value: "selected" } },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: "Agent description" }),
        { target: { value: "Echo agent" } },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: /Expected behavior/ }),
        { target: { value: "Return input" } },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: /Input\/output examples/ }),
        { target: { value: '[{"input":1,"output":1}]' } },
    );
    fireEvent.click(
        screen.getByRole("button", { name: "Preview outgoing context" }),
    );
    const generate = (await screen.findByRole("button", {
        name: "Generate 5 suggestions",
    })) as HTMLButtonElement;
    expect(generate.disabled).toBe(true);
    expect(
        vi.mocked(api).mock.calls.some(([path]) => path === "generate"),
    ).toBe(false);
    fireEvent.click(
        screen.getByRole("checkbox", { name: /reviewed this context/ }),
    );
    fireEvent.click(generate);
    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(api).toHaveBeenCalledWith(
        "generate",
        expect.objectContaining({
            connection: "api_key",
            model: "selected",
            source: null,
            request: expect.objectContaining({
                existing_cases: [],
                description: "Echo agent",
            }),
        }),
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: /Expected behavior/ }),
        { target: { value: "Changed rule" } },
    );
    expect(
        screen.queryByRole("button", { name: "Generate 5 suggestions" }),
    ).toBeNull();
});

function artifact(): Artifact {
    return {
        path: "draft.json",
        kind: "scenario_draft",
        fingerprint: "one",
        cases: 1,
        modified_ns: 0,
        data: {
            generation: { model: "fixture" },
            source: null,
            candidates: [
                {
                    case: caseData,
                    decision: "pending",
                    original: {
                        category: "normal",
                        rationale: "Echo contract",
                        uncertainty: "",
                    },
                    reviews: [],
                },
            ],
        },
    };
}
it("reviews one exact case without publishing a suite", async () => {
    const updated = vi.fn(),
        saved = vi.fn();
    const draft = artifact();
    vi.mocked(api).mockImplementation(async (path) =>
        path.startsWith("draft/issues")
            ? [[]]
            : { ...draft, fingerprint: "two" },
    );
    render(
        <DraftReview
            artifact={draft}
            onUpdated={updated}
            onSaved={saved}
            onDirty={() => {}}
        />,
    );
    fireEvent.click(
        screen.getByRole("button", { name: /Accept reviewed case/ }),
    );
    await waitFor(() => expect(updated).toHaveBeenCalled());
    expect(api).toHaveBeenCalledWith("draft/review", {
        path: "draft.json",
        fingerprint: "one",
        index: 0,
        decision: "accepted",
        case: caseData,
    });
    expect(saved).not.toHaveBeenCalled();
    expect(
        vi.mocked(api).mock.calls.some(([path]) => path === "draft/publish"),
    ).toBe(false);
});
it("requires suite preview and acknowledgement before explicit saving", async () => {
    const draft = artifact(),
        saved = vi.fn();
    draft.data.candidates[0].decision = "accepted";
    vi.mocked(api).mockImplementation(async (path) =>
        path.startsWith("draft/issues")
            ? [[]]
            : path === "draft/preview"
              ? { schema_version: 2, cases: [caseData] }
              : { path: "suites/reviewed-cases.json", kind: "suite" },
    );
    render(
        <DraftReview
            artifact={draft}
            onUpdated={() => {}}
            onSaved={saved}
            onDirty={() => {}}
        />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: /Suite revision/ }), {
        target: { value: "v1" },
    });
    fireEvent.click(
        screen.getByRole("button", { name: "Preview suite changes" }),
    );
    const save = (await screen.findByRole("button", {
        name: "Save reviewed suite",
    })) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(
        screen.getByRole("checkbox", { name: /reviewed the resulting suite/ }),
    );
    fireEvent.click(save);
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(api).toHaveBeenCalledWith(
        "draft/publish",
        expect.objectContaining({
            fingerprint: "one",
            revision: "v1",
            expected_fingerprint: null,
        }),
    );
});
it("keeps malformed edits visible without submitting or switching cases", async () => {
    const draft = artifact();
    vi.mocked(api).mockResolvedValue([[]]);
    render(
        <DraftReview
            artifact={draft}
            onUpdated={() => {}}
            onSaved={() => {}}
            onDirty={() => {}}
        />,
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: /Proposed case JSON/ }),
        { target: { value: "{" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Save draft edits/ }));
    await screen.findByRole("alert");
    expect(
        (
            screen.getByRole("textbox", {
                name: /Proposed case JSON/,
            }) as HTMLTextAreaElement
        ).value,
    ).toBe("{");
    expect(
        vi.mocked(api).mock.calls.some(([path]) => path === "draft/review"),
    ).toBe(false);
});

it("keeps a malformed generated case visible for repair", async () => {
    const draft = artifact();
    draft.data.candidates[0].case = { id: { invalid: true } };
    vi.mocked(api).mockResolvedValue([["Case ID must be a string"]]);
    render(
        <DraftReview
            artifact={draft}
            onUpdated={() => {}}
            onSaved={() => {}}
            onDirty={() => {}}
        />,
    );
    expect(screen.getByRole("heading", { name: "Suggestion 1" })).toBeTruthy();
    expect(
        (
            screen.getByRole("textbox", {
                name: /Proposed case JSON/,
            }) as HTMLTextAreaElement
        ).value,
    ).toContain('"invalid"');
});

it("explains signed-in accounts without plan permission", async () => {
    vi.mocked(api).mockResolvedValue({
        available: true,
        chatgpt: true,
        plan_enabled: false,
        email: "user@example.com",
    });
    render(
        <SuggestPanel
            catalog={catalog}
            active={false}
            onStarted={() => {}}
            onDirty={() => {}}
        />,
    );
    await screen.findByText(/Signed in, but ChatGPT plan usage is not enabled/);
    expect(
        (
            screen.getByRole("button", {
                name: /Load models/,
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});
