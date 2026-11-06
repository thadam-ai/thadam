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
import { RegressionDraft } from "./regression";
import { EvaluationView } from "./evaluations";
vi.mock("./api", async (original) => ({
    ...(await original<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(() => {
    cleanup();
    vi.resetAllMocks();
});
it("requires supplied checks and explicit review before preview and suite saving", async () => {
    const artifact = {
        path: "draft.json",
        kind: "regression_draft",
        fingerprint: "old",
        data: {
            reviewed: false,
            case: { id: "a", input: 1, assertions: [] },
            source: {
                path: "run.json",
                case_id: "a",
                attempt: 2,
                run: { cases: [{ id: "a", output: 9 }] },
            },
        },
    } as unknown as Artifact;
    const saved = vi.fn();
    vi.mocked(api).mockImplementation(async (path, body: any) => {
        if (path === "regression/review")
            return {
                ...artifact,
                fingerprint: "new",
                data: {
                    ...artifact.data,
                    case: body.case,
                    reviewed: body.reviewed,
                },
            };
        if (path === "regression/preview")
            return { schema_version: 2, cases: [] };
        if (path === "regression/publish")
            return { path: "suites/regressions.json" };
        throw Error(path);
    });
    render(
        <RegressionDraft
            artifact={artifact}
            catalog={{ name: "test", root: "/test", items: [], invalid: [] }}
            onSaved={saved}
            onDirty={() => {}}
        />,
    );
    const preview = screen.getByRole("button", {
        name: "Preview suite changes",
    }) as HTMLButtonElement;
    expect(preview.disabled).toBe(true);
    const field = screen.getByRole("textbox", {
        name: /Regression case JSON/,
    }) as HTMLTextAreaElement;
    expect(JSON.parse(field.value).assertions).toEqual([]);
    fireEvent.change(field, {
        target: {
            value: JSON.stringify({
                id: "a",
                input: 1,
                assertions: [
                    { id: "answer", type: "output_equals", expected: 2 },
                ],
            }),
        },
    });
    fireEvent.click(
        screen.getByRole("checkbox", { name: /I reviewed the input/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save reviewed case" }));
    await waitFor(() => expect(preview.disabled).toBe(false));
    fireEvent.click(preview);
    const save = (await screen.findByRole("button", {
        name: "Save reviewed suite",
    })) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(
        screen.getByRole("checkbox", { name: /I reviewed the resulting/ }),
    );
    fireEvent.click(save);
    await waitFor(() =>
        expect(saved).toHaveBeenCalledWith({ path: "suites/regressions.json" }),
    );
    expect(api).toHaveBeenCalledWith(
        "regression/publish",
        expect.objectContaining({
            fingerprint: "new",
            confirmed: true,
            expected_fingerprint: null,
        }),
    );
});
it("uses the selected individual repeated attempt when creating a regression", () => {
    const callback = vi.fn();
    const test = {
        id: "a",
        status: "failed",
        duration_ms: 1,
        assertions: [],
        errors: [],
        events: null,
    };
    render(
        <EvaluationView
            data={{
                kind: "repeated_run",
                summary: {},
                runs: [{ cases: [test] }, { cases: [test] }],
                cases: [],
            }}
            onRegression={callback}
        />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Choose attempt" }), {
        target: { value: "1" },
    });
    fireEvent.click(
        screen.getByRole("button", { name: "Create regression case" }),
    );
    expect(callback).toHaveBeenCalledWith("a", 2);
});
