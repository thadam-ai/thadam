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
afterEach(cleanup);
it("requires explicit async selection and sends the selected concurrency to the job API", async () => {
    vi.mocked(api).mockImplementation(async (path) =>
        path === "agents" ? [] : { id: "job" },
    );
    const started = vi.fn();
    render(
        <RunPanel
            open
            onToggle={() => {}}
            active={false}
            onStarted={started}
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
    const limit = screen.getByRole("spinbutton", {
        name: /Maximum concurrent cases/,
    }) as HTMLInputElement;
    expect(limit.disabled).toBe(true);
    fireEvent.change(
        screen.getByRole("combobox", { name: "Execution engine" }),
        { target: { value: "async" } },
    );
    expect(limit.disabled).toBe(false);
    fireEvent.change(limit, { target: { value: "3" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Agent reference/ }), {
        target: { value: "agent:run" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run evaluation" }));
    await waitFor(() => expect(started).toHaveBeenCalledWith({ id: "job" }));
    expect(api).toHaveBeenCalledWith(
        "jobs",
        expect.objectContaining({
            reference: "agent:run",
            async_execution: true,
            max_concurrency: 3,
        }),
    );
});
