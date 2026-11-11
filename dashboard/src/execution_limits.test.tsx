// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { RunPanel } from "./evaluations";
vi.mock("./api", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

function panel() {
    vi.mocked(api).mockImplementation(async (path) =>
        path === "agents" ? [] : { id: "job" },
    );
    render(
        <RunPanel
            open
            onToggle={() => {}}
            active={false}
            onStarted={() => {}}
            catalog={{
                name: "project",
                root: "/project",
                invalid: [],
                items: [
                    {
                        path: "cases.json",
                        kind: "suite",
                        fingerprint: "x",
                        cases: 1,
                        modified_ns: 0,
                    },
                ],
            }}
        />,
    );
    fireEvent.click(screen.getByText(/Execution & save settings/));
    fireEvent.change(screen.getByRole("textbox", { name: /Agent reference/ }), {
        target: { value: "agent:create" },
    });
}

it("sends explicit per-case limits and fixture environment hooks", async () => {
    panel();
    fireEvent.change(screen.getByRole("combobox", { name: "Execution mode" }), {
        target: { value: "fixtures" },
    });
    fireEvent.change(
        screen.getByRole("spinbutton", { name: /Maximum conversation turns/ }),
        { target: { value: "2" } },
    );
    fireEvent.change(
        screen.getByRole("spinbutton", { name: /Case deadline/ }),
        { target: { value: "10" } },
    );
    fireEvent.change(
        screen.getByRole("spinbutton", { name: /Cleanup grace/ }),
        { target: { value: "0.5" } },
    );
    fireEvent.change(
        screen.getByRole("textbox", { name: /Environment hooks/ }),
        { target: { value: "agent:environment" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));
    await waitFor(() =>
        expect(api).toHaveBeenCalledWith(
            "jobs",
            expect.objectContaining({
                mode: "fixtures",
                environment: "agent:environment",
                execution_limits: {
                    max_turns: 2,
                    timeout_seconds: 10,
                    cleanup_timeout_seconds: 0.5,
                },
            }),
        ),
    );
});

it("omits inactive environment hooks and leaves deadlines opt-in", async () => {
    panel();
    fireEvent.change(screen.getByRole("combobox", { name: "Execution mode" }), {
        target: { value: "fixtures" },
    });
    fireEvent.change(
        screen.getByRole("textbox", { name: /Environment hooks/ }),
        { target: { value: "agent:environment" } },
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Execution mode" }), {
        target: { value: "shared" },
    });
    expect(
        screen.queryByRole("textbox", { name: /Environment hooks/ }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));
    await waitFor(() =>
        expect(
            vi.mocked(api).mock.calls.some(([path]) => path === "jobs"),
        ).toBe(true),
    );
    const job = vi.mocked(api).mock.calls.find(([path]) => path === "jobs")![1];
    expect(job).not.toHaveProperty("environment");
    expect(job).not.toHaveProperty("execution_limits");
});
