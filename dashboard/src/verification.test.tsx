// @vitest-environment jsdom
import {
    cleanup,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, type Catalog, type Data, type Item } from "./api";
import {
    matchingVerificationBaselines,
    VerificationPanel,
} from "./verification";
vi.mock("./api", async (original) => ({
    ...(await original<typeof import("./api")>()),
    api: vi.fn(),
}));
afterEach(() => {
    cleanup();
    vi.resetAllMocks();
});

it("offers only baselines with a comparable attempt count and execution mode", () => {
    const items = [
        { kind: "run", path: "one.json" },
        {
            kind: "repeated_run",
            path: "two.json",
            attempts: 2,
            execution_mode: "shared",
        },
        {
            kind: "repeated_run",
            path: "other-mode.json",
            attempts: 2,
            execution_mode: "factory",
        },
        {
            kind: "repeated_run",
            path: "other-count.json",
            attempts: 3,
            execution_mode: "shared",
        },
    ] as Item[];
    expect(
        matchingVerificationBaselines(items, 1, "shared").map(
            (item) => item.path,
        ),
    ).toEqual(["one.json"]);
    expect(
        matchingVerificationBaselines(items, 2, "shared").map(
            (item) => item.path,
        ),
    ).toEqual(["two.json"]);
});

it("starts a selected candidate run and keeps its explicitly selected baseline", async () => {
    const catalog = {
        name: "test",
        root: "/test",
        invalid: [],
        items: [
            { path: "suites/reviewed.json", kind: "suite" },
            { path: "reports/baseline.json", kind: "run", attempts: 1 },
        ],
    } as unknown as Catalog;
    const job = {
        id: "job-1",
        state: "running",
        completed: 0,
        total: 1,
        settings: { suite: "suites/reviewed.json", reference: "candidate:run" },
    };
    vi.mocked(api).mockImplementation(async (path) => {
        if (path === "artifact?path=suites%2Freviewed.json")
            return {
                data: {
                    schema_version: 2,
                    cases: [
                        {
                            id: "fix",
                            input: "hello",
                            assertions: [
                                {
                                    id: "output",
                                    type: "output_equals",
                                    expected: "hello",
                                },
                            ],
                        },
                    ],
                },
            };
        if (path === "jobs") return job;
        if (path === "jobs/job-1") return job;
        throw Error(String(path));
    });
    const onStarted = vi.fn();
    const onOpen = vi.fn();
    render(
        <VerificationPanel
            catalog={catalog}
            active={false}
            onStarted={onStarted}
            onOpen={onOpen}
        />,
    );
    await screen.findByRole("option", { name: "reports/baseline.json" });
    fireEvent.change(screen.getByLabelText(/Candidate agent/), {
        target: { value: "candidate:run" },
    });
    fireEvent.change(screen.getByLabelText(/Baseline report/), {
        target: { value: "reports/baseline.json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run candidate" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(job));
    expect(api).toHaveBeenCalledWith(
        "jobs",
        expect.objectContaining({
            suite: "suites/reviewed.json",
            reference: "candidate:run",
            mode: "shared",
            attempts: 1,
            agent_revision: null,
        }),
    );
});
